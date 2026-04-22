import json
import os
import uuid
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List

import telebot
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.database import (
    add_admin,
    delete_admin,
    get_stats,
    init_db,
    list_admins,
    list_orders,
    save_order,
    verify_admin,
    update_order_status,
)

BASE_DIR = Path(__file__).resolve().parent.parent
MENU_PATH = BASE_DIR / "menu.json"
WEBAPP_DIR = BASE_DIR / "webapp"
IMAGES_DIR = WEBAPP_DIR / "images"

TOKEN = os.getenv("BOT_TOKEN", "8500279228:AAEJSwSkU72fOM53ntPHMoVoSMudIQv-7ZE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7825940174"))
AUTH_SECRET = os.getenv("AUTH_SECRET", "grato-secret-2026")

bot = telebot.TeleBot(TOKEN)
active_tokens: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(str(ADMIN_ID))
    yield


app = FastAPI(title="Grato Bot Mini App API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")
if WEBAPP_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEBAPP_DIR)), name="static")


class OrderItem(BaseModel):
    name: str
    qty: int = Field(ge=1)


class OrderPayload(BaseModel):
    phone: str
    items: List[OrderItem]
    customer_name: str | None = None
    address: str = "Noma'lum"
    total: int = 0


class MenuUpdatePayload(BaseModel):
    category: str
    old_name: str
    new_name: str
    price: int


class AddItemPayload(BaseModel):
    category: str
    name: str
    price: int
    image: str = ""


class DeleteItemPayload(BaseModel):
    category: str
    name: str


class StatusPayload(BaseModel):
    status: str


class AdminPayload(BaseModel):
    telegram_id: str
    username: str
    role: str = "admin"


class LoginPayload(BaseModel):
    telegram_id: str
    password: str


class LogoutPayload(BaseModel):
    token: str


def load_menu():
    with open(MENU_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_menu(raw_menu):
    with open(MENU_PATH, "w", encoding="utf-8") as f:
        json.dump(raw_menu, f, ensure_ascii=False, indent=2)


def normalize_menu(raw_menu):
    # Format A (current): {"🥗 Salatlar": {"Grato": 35000, ...}, ...}
    if isinstance(raw_menu, dict) and "categories" not in raw_menu:
        categories = []
        item_id = 1
        for category_name, items in raw_menu.items():
            if not isinstance(items, dict):
                continue
            emoji = ""
            clean_name = category_name
            if category_name and category_name[0] in "🥗🍜🍛☕️🍔🍕🥤🥙🍱":
                emoji = category_name[0]
                clean_name = category_name[2:].strip()
            cat_items = []
            for name, price in items.items():
                cat_items.append({"id": item_id, "name": name, "price": int(price), "image": ""})
                item_id += 1
            categories.append({"name": clean_name, "emoji": emoji, "items": cat_items})
        return {"categories": categories}

    # Format B (new): {"categories": [...]}
    if isinstance(raw_menu, dict) and isinstance(raw_menu.get("categories"), list):
        return raw_menu

    return {"categories": []}


def get_price_map():
    menu = normalize_menu(load_menu())
    prices = {}
    for category in menu.get("categories", []):
        for item in category.get("items", []):
            prices[item["name"]] = int(item["price"])
    return prices


def build_order_message(order_id: int, phone: str, address: str, items: list[dict], total: int):
    lines = []
    for item in items:
        name = item.get("name", "Noma'lum")
        qty = int(item.get("qty", 1))
        price = int(item.get("price", 0))
        lines.append(f"• {name} x{qty} — {price:,} so'm")
    body = "\n".join(lines) if lines else "• Buyurtma bo'sh"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"🔔 Yangi buyurtma! #{order_id}\n"
        f"📞 Telefon: {phone}\n"
        f"📍 Manzil: {address}\n\n"
        f"🛒 Buyurtma:\n{body}\n\n"
        f"💰 Jami: {total:,} so'm\n"
        f"🕐 Vaqt: {now}"
    )


def notify_all_admins(text: str):
    for admin in list_admins():
        try:
            bot.send_message(int(admin["telegram_id"]), text)
        except Exception:
            continue


def generate_token(telegram_id: str):
    return hashlib.sha256(f"{telegram_id}{AUTH_SECRET}".encode()).hexdigest()


def get_current_admin(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.replace("Bearer ", "", 1).strip()
    admin = active_tokens.get(token)
    if not admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return admin


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/admin.html")
def admin_panel():
    return FileResponse(str(BASE_DIR / "webapp" / "admin.html"))


@app.get("/")
def index():
    return FileResponse(str(BASE_DIR / "webapp" / "index.html"))


@app.get("/api/menu")
def menu():
    return normalize_menu(load_menu())


@app.get("/menu")
def menu_legacy():
    return menu()


@app.post("/api/admin/menu/update")
def admin_menu_update(payload: MenuUpdatePayload, _: dict = Depends(get_current_admin)):
    raw = load_menu()
    menu = normalize_menu(raw)
    updated = False

    for cat in menu["categories"]:
        cat_name = f"{cat.get('emoji', '')} {cat.get('name', '')}".strip()
        if payload.category in (cat.get("name"), cat_name):
            for item in cat.get("items", []):
                if item.get("name") == payload.old_name:
                    item["name"] = payload.new_name
                    item["price"] = int(payload.price)
                    updated = True
                    break
    if not updated:
        raise HTTPException(status_code=404, detail="Item topilmadi")

    save_menu(menu)
    return {"ok": True}


@app.post("/api/admin/menu/add")
def admin_menu_add(payload: AddItemPayload, _: dict = Depends(get_current_admin)):
    raw = load_menu()
    menu = normalize_menu(raw)
    max_id = 0
    for cat in menu["categories"]:
        for item in cat.get("items", []):
            max_id = max(max_id, int(item.get("id", 0)))

    for cat in menu["categories"]:
        cat_name = f"{cat.get('emoji', '')} {cat.get('name', '')}".strip()
        if payload.category in (cat.get("name"), cat_name):
            cat.setdefault("items", []).append(
                {"id": max_id + 1, "name": payload.name, "price": int(payload.price), "image": payload.image}
            )
            save_menu(menu)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Kategoriya topilmadi")


@app.post("/api/admin/menu/delete")
def admin_menu_delete(payload: DeleteItemPayload, _: dict = Depends(get_current_admin)):
    raw = load_menu()
    menu = normalize_menu(raw)
    for cat in menu["categories"]:
        cat_name = f"{cat.get('emoji', '')} {cat.get('name', '')}".strip()
        if payload.category in (cat.get("name"), cat_name):
            old_len = len(cat.get("items", []))
            cat["items"] = [x for x in cat.get("items", []) if x.get("name") != payload.name]
            if len(cat["items"]) == old_len:
                raise HTTPException(status_code=404, detail="Item topilmadi")
            save_menu(menu)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Kategoriya topilmadi")


@app.post("/api/admin/upload-image")
async def admin_upload_image(file: UploadFile = File(...), _: dict = Depends(get_current_admin)):
    ext = Path(file.filename).suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = IMAGES_DIR / filename

    with open(filepath, "wb") as f:
        f.write(await file.read())

    return {"ok": True, "url": f"/images/{filename}"}


@app.get("/api/orders")
def orders():
    return {"orders": list_orders()}


@app.post("/api/orders")
def create_order_record(payload: OrderPayload):
    total = payload.total or sum(int(i.price) * int(i.qty) for i in payload.items)
    order_id = save_order(payload.phone, payload.address, [x.model_dump() for x in payload.items], total)
    return {"ok": True, "order_id": order_id}


@app.patch("/api/orders/{order_id}/status")
def set_order_status(order_id: int, payload: StatusPayload):
    if payload.status not in {"new", "confirmed", "delivered", "cancelled"}:
        raise HTTPException(status_code=400, detail="Noto'g'ri status")
    update_order_status(order_id, payload.status)
    return {"ok": True}


@app.get("/api/stats")
def stats():
    data = get_stats()
    data["orders"] = list_orders()
    return data


@app.post("/api/auth/login")
def auth_login(payload: LoginPayload):
    admin = verify_admin(payload.telegram_id, payload.password)
    if not admin:
        raise HTTPException(status_code=401, detail="Noto'g'ri login yoki parol")
    token = generate_token(payload.telegram_id)
    token_data = {"telegram_id": payload.telegram_id, "role": admin["role"], "username": admin["username"]}
    active_tokens[token] = token_data
    return {"ok": True, "token": token, "role": admin["role"], "username": admin["username"]}


@app.post("/api/auth/logout")
def auth_logout(payload: LogoutPayload):
    active_tokens.pop(payload.token, None)
    return {"ok": True}


@app.get("/api/me")
def me(admin: dict = Depends(get_current_admin)):
    return {"ok": True, **admin}


@app.get("/api/admins")
def admins():
    return {"admins": list_admins()}


@app.post("/api/admins")
def create_admin(payload: AdminPayload):
    if payload.role not in {"superadmin", "admin"}:
        raise HTTPException(status_code=400, detail="Noto'g'ri role")
    add_admin(payload.telegram_id, payload.username, payload.role)
    return {"ok": True}


@app.delete("/api/admins/{telegram_id}")
def remove_admin(telegram_id: str):
    ok = delete_admin(telegram_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Superadmin o'chirilmaydi")
    return {"ok": True}


@app.post("/order")
def create_order(payload: OrderPayload):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Items bo'sh bo'lmasligi kerak")

    prices = get_price_map()
    total = 0
    lines = []

    for item in payload.items:
        if item.name not in prices:
            raise HTTPException(status_code=400, detail=f"Noto'g'ri item: {item.name}")
        total += prices[item.name] * item.qty
        lines.append(f"{item.name}: {item.qty} ta")

    customer = payload.customer_name or "Noma'lum"
    order_id = save_order(
        phone=payload.phone,
        address=payload.address,
        items=[x.model_dump() for x in payload.items],
        total=total,
        status="new",
    )

    text = build_order_message(
        order_id=order_id,
        phone=payload.phone,
        address=payload.address,
        items=[x.model_dump() for x in payload.items],
        total=total,
    )
    notify_all_admins(text)
    return {"ok": True, "total": total, "order_id": order_id}
