import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime
import requests

import telebot
from telebot import types
from api.database import init_db, list_admins, list_orders, save_order
from api.database import get_stats, list_user_ids, upsert_user, users_count
from api.database import set_admin_password

# ===== CONFIG =====
BASE_DIR = Path(__file__).resolve().parent
MENU_PATH = BASE_DIR / "menu.json"

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or "8500279228:AAEJSwSkU72fOM53ntPHMoVoSMudIQv-7ZE"
# Backward compatibility for old code paths that still reference TOKEN.
TOKEN = BOT_TOKEN
ADMIN_ID = int(os.getenv("ADMIN_ID", "7825940174"))
WEB_APP_URL = os.getenv("WEB_APP_URL", "")
API_BASE = os.getenv("API_BASE", "https://grato-api-production.up.railway.app")
API_URL = os.getenv("API_URL", API_BASE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

# ===== BOT INIT (must be before handlers) =====
bot = telebot.TeleBot(BOT_TOKEN)
init_db()


# ===== HELPERS =====
def load_menu():
    with open(MENU_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # Legacy bot logic expects: {category: {item: price}}
    if isinstance(raw, dict) and "categories" in raw:
        converted = {}
        for category in raw.get("categories", []):
            name = category.get("name", "Kategoriya")
            emoji = category.get("emoji", "")
            key = f"{emoji} {name}".strip()
            converted[key] = {}
            for item in category.get("items", []):
                converted[key][item["name"]] = int(item["price"])
        return converted

    return raw


user_carts = {}
admin_modes = {}
admin_password_modes = set()


def main_menu():
    menu = load_menu()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for cat in menu:
        markup.add(cat)

    markup.add("🛒 Savat", "✅ Buyurtmani yakunlash")
    if WEB_APP_URL:
        markup.add(types.KeyboardButton("🛒 Buyurtma berish", web_app=types.WebAppInfo(WEB_APP_URL)))
    markup.add("🗑 Savatni tozalash")
    return markup


def food_menu(category):
    menu = load_menu()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for food, price in menu[category].items():
        markup.add(f"{food} - {price} so'm")

    markup.add("🔙 Orqaga")
    return markup


def show_cart(chat_id):
    menu = load_menu()
    cart = user_carts.get(chat_id, [])

    if not cart:
        bot.send_message(chat_id, "Savat bo'sh 🛒", reply_markup=main_menu())
        return

    all_prices = {}
    for c in menu:
        all_prices.update(menu[c])

    text_report = "🛒 Savatingiz:\n"
    total = 0

    for item in set(cart):
        count = cart.count(item)
        price = all_prices[item]
        total += price * count
        text_report += f"• {item} — {count} ta\n"

    text_report += f"\n💰 Jami: {total:,} so'm"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for item in set(cart):
        markup.add(f"❌ {item}")

    markup.add("🔙 Orqaga", "🗑 Savatni tozalash")
    bot.send_message(chat_id, text_report, reply_markup=markup)


def format_web_order(data: dict):
    items = data.get("items", [])
    total = int(data.get("total", 0))
    phone = data.get("phone", "Noma'lum")
    address = data.get("address", "Noma'lum")

    lines = []
    for item in items:
        name = item.get("name", "Noma'lum")
        qty = int(item.get("qty", 1))
        price = int(item.get("price", 0))
        lines.append(f"• {name} x{qty} — {price * qty:,} so'm")

    text = (
        "🧾 Mini App buyurtmasi\n"
        + ("\n".join(lines) if lines else "• Mahsulot topilmadi")
        + f"\n\n📞 Telefon: {phone}\n📍 Manzil: {address}\n💰 Jami: {total:,} so'm"
    )
    return text


def process_web_app_order(msg):
    try:
        data = json.loads(msg.web_app_data.data)
    except Exception:
        bot.send_message(msg.chat.id, "❌ Buyurtma ma'lumotini o'qib bo'lmadi.")
        return

    summary = format_web_order(data)
    items = data.get("items", [])
    total = int(data.get("total", 0))
    phone = data.get("phone", "Noma'lum")
    address = data.get("address", "Noma'lum")
    order_id = save_order_to_db(phone=phone, address=address, items=items, total=total)
    bot.send_message(msg.chat.id, f"✅ Buyurtmangiz qabul qilindi!\n\n{summary}")
    text = build_order_message(order_id, phone, address, items, total)
    notify_all_admins(text)


def save_order_to_db(phone, address, items, total):
    try:
        res = requests.post(
            f"{API_URL}/api/orders",
            json={"phone": phone, "address": address, "items": items, "total": int(total)},
            timeout=10,
        )
        data = res.json() if res.content else {}
        return int(data.get("order_id", 0))
    except Exception as e:
        print(f"Order save error: {e}")
        return 0


def build_order_message(order_id: int, phone: str, address: str, items: list, total: int):
    lines = []
    for item in items:
        name = item.get("name", "Noma'lum")
        qty = int(item.get("qty", 1))
        price = int(item.get("price", 0))
        lines.append(f"• {name} x{qty} — {price * qty:,} so'm")
    order_lines = "\n".join(lines) if lines else "• Buyurtma bo'sh"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"🔔 Yangi buyurtma! #{order_id}\n"
        f"📞 Telefon: {phone}\n"
        f"📍 Manzil: {address}\n\n"
        f"🛒 Buyurtma:\n{order_lines}\n\n"
        f"💰 Jami: {total:,} so'm\n"
        f"🕐 Vaqt: {now}"
    )


def notify_all_admins(text: str):
    admins = list_admins()
    for admin in admins:
        try:
            bot.send_message(int(admin["telegram_id"]), text)
        except Exception as e:
            print(f"Admin {admin['telegram_id']} ga yuborishda xato: {e}")


def finish(msg):
    menu = load_menu()
    chat_id = msg.chat.id

    if not user_carts.get(chat_id):
        return

    phone = msg.contact.phone_number if msg.content_type == "contact" else msg.text
    cart = user_carts[chat_id]

    all_prices = {}
    for c in menu:
        all_prices.update(menu[c])

    total = sum(all_prices[item] for item in cart)

    items = []
    for item in set(cart):
        items.append({"name": item, "qty": cart.count(item), "price": all_prices[item]})
    order_id = save_order_to_db(phone=phone, address="Bot orqali", items=items, total=total)
    notify_all_admins(build_order_message(order_id, phone, "Bot orqali", items, total))

    user_carts[chat_id] = []
    bot.send_message(chat_id, "Buyurtma qabul qilindi ✅", reply_markup=main_menu())


def is_admin(chat_id: int):
    return any(str(a["telegram_id"]) == str(chat_id) for a in list_admins())


def render_order_text(order):
    items = order.get("items", [])
    lines = [f"• {i.get('name')} x{i.get('qty')} — {int(i.get('price', 0)) * int(i.get('qty', 1)):,} so'm" for i in items]
    return (
        f"🧾 Buyurtma #{order['id']}\n"
        f"🕐 {order['created_at']}\n"
        f"📞 {order['phone']}\n"
        f"📍 {order['address']}\n\n"
        f"🛒 Buyurtma:\n" + ("\n".join(lines) if lines else "• Bo'sh")
        + f"\n\n💰 Jami: {int(order['total']):,} so'm\n"
        f"📌 Status: {order['status']}"
    )


# ===== HANDLERS =====
@bot.message_handler(commands=["start"])
def start(msg):
    upsert_user(
        user_id=msg.from_user.id,
        username=msg.from_user.username or "",
        first_name=msg.from_user.first_name or "",
    )
    user_carts[msg.chat.id] = []
    bot.send_message(msg.chat.id, "Bo'lim tanlang:", reply_markup=main_menu())


@bot.message_handler(commands=["app"])
def open_app(msg):
    if not WEB_APP_URL:
        bot.send_message(msg.chat.id, "Mini App URL sozlanmagan. WEB_APP_URL ni o'rnating.")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🛒 Buyurtma berish", web_app=types.WebAppInfo(WEB_APP_URL)))
    markup.add("🔙 Orqaga")
    bot.send_message(msg.chat.id, "Mini Appni ochish uchun tugmani bosing:", reply_markup=markup)


@bot.message_handler(commands=["admins"])
def admins_cmd(msg):
    admins = list_admins()
    if not admins:
        bot.send_message(msg.chat.id, "Adminlar ro'yxati bo'sh.")
        return
    text = "👥 Adminlar:\n\n"
    for a in admins:
        text += f"• {a['telegram_id']} | @{a['username']} | {a['role']}\n"
    bot.send_message(msg.chat.id, text)


@bot.message_handler(commands=["orders"])
def orders_cmd(msg):
    if not is_admin(msg.chat.id):
        bot.send_message(msg.chat.id, "Bu komanda faqat adminlar uchun.")
        return
    orders = list_orders()[:10]
    if not orders:
        bot.send_message(msg.chat.id, "Buyurtmalar topilmadi.")
        return
    for o in orders:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("Ko'rish", callback_data=f"view_order:{o['id']}"))
        short = f"#{o['id']} | {o['phone']} | {int(o['total']):,} so'm | {o['status']}"
        bot.send_message(msg.chat.id, short, reply_markup=kb)


@bot.message_handler(commands=["addadmin"])
def add_admin_cmd(msg):
    if str(msg.chat.id) != str(ADMIN_ID):
        bot.send_message(msg.chat.id, "Faqat superadmin bu komandani ishlata oladi.")
        return

    parts = (msg.text or "").split()
    if len(parts) < 3:
        bot.send_message(msg.chat.id, "Format: /addadmin [telegram_id] [username]")
        return

    telegram_id = parts[1]
    username = parts[2]
    payload = json.dumps({"telegram_id": telegram_id, "username": username, "role": "admin"}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/api/admins",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        bot.send_message(msg.chat.id, f"✅ Admin qo'shildi: {telegram_id} ({username})")
        try:
            bot.send_message(
                int(telegram_id),
                "Siz Grato admin paneliga qo'shildingiz!\nParol o'rnatish uchun: /setpassword",
            )
        except Exception:
            pass
    except urllib.error.HTTPError as e:
        bot.send_message(msg.chat.id, f"❌ Xato: {e.read().decode('utf-8')}")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Xato: {e}")


@bot.message_handler(commands=["setpassword"])
def set_password_cmd(msg):
    if not is_admin(msg.chat.id):
        bot.send_message(msg.chat.id, "Bu komanda faqat adminlar uchun.")
        return
    admin_password_modes.add(msg.chat.id)
    bot.send_message(msg.chat.id, "Yangi parol kiriting:")


@bot.message_handler(commands=["broadcast"])
def broadcast_cmd(msg):
    if str(msg.chat.id) != str(ADMIN_ID):
        bot.send_message(msg.chat.id, "Faqat superadmin bu komandani ishlata oladi.")
        return
    admin_modes[msg.chat.id] = "broadcast"
    bot.send_message(msg.chat.id, "Xabar matnini yuboring:")


@bot.message_handler(commands=["akciya"])
def akciya_cmd(msg):
    if str(msg.chat.id) != str(ADMIN_ID):
        bot.send_message(msg.chat.id, "Faqat superadmin bu komandani ishlata oladi.")
        return
    admin_modes[msg.chat.id] = "akciya"
    bot.send_message(msg.chat.id, "Akciya matnini yuboring:")


@bot.message_handler(commands=["stats"])
def stats_cmd(msg):
    if str(msg.chat.id) != str(ADMIN_ID):
        bot.send_message(msg.chat.id, "Faqat superadmin bu komandani ishlata oladi.")
        return
    s = get_stats()
    text = (
        "📊 Bot statistikasi:\n"
        f"👥 Jami foydalanuvchilar: {users_count()}\n"
        f"📦 Jami buyurtmalar: {s.get('total_orders', 0)}\n"
        f"💰 Jami daromad: {int(s.get('total_revenue', 0)):,} so'm\n"
        f"📅 Bugun buyurtmalar: {s.get('today_orders', 0)}"
    )
    bot.send_message(msg.chat.id, text)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("view_order:"))
def view_order_cb(call):
    if not is_admin(call.message.chat.id):
        bot.answer_callback_query(call.id, "Ruxsat yo'q")
        return
    oid = int(call.data.split(":")[1])
    order = next((x for x in list_orders() if int(x["id"]) == oid), None)
    if not order:
        bot.answer_callback_query(call.id, "Topilmadi")
        return
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"status:{oid}:confirmed"),
        types.InlineKeyboardButton("🚚 Yetkazildi", callback_data=f"status:{oid}:delivered"),
        types.InlineKeyboardButton("❌ Bekor", callback_data=f"status:{oid}:cancelled"),
    )
    bot.send_message(call.message.chat.id, render_order_text(order), reply_markup=kb)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("status:"))
def change_status_cb(call):
    if not is_admin(call.message.chat.id):
        bot.answer_callback_query(call.id, "Ruxsat yo'q")
        return
    _, oid, status = call.data.split(":")
    payload = json.dumps({"status": status}).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/api/orders/{oid}/status",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        bot.answer_callback_query(call.id, "Status yangilandi")
        bot.send_message(call.message.chat.id, f"✅ Buyurtma #{oid} statusi: {status}")
    except Exception as e:
        bot.answer_callback_query(call.id, "Xato")
        bot.send_message(call.message.chat.id, f"❌ Xato: {e}")


@bot.message_handler(func=lambda m: True, content_types=["text", "contact", "web_app_data"])
def handler(msg):
    menu = load_menu()
    chat_id = msg.chat.id
    text = msg.text if msg.text else ""

    if msg.chat.id in admin_modes and msg.content_type == "text":
        mode = admin_modes.pop(msg.chat.id)
        if mode == "broadcast":
            sent = 0
            for uid in list_user_ids():
                try:
                    bot.send_message(int(uid), text)
                    sent += 1
                except Exception:
                    continue
            bot.send_message(msg.chat.id, f"✅ {sent} ta foydalanuvchiga yuborildi")
            return
        if mode == "akciya":
            payload = f"🎉 AKSIYA!\n{text}\n📞 Buyurtma: @Gratodeliverybot"
            sent = 0
            for uid in list_user_ids():
                try:
                    bot.send_message(int(uid), payload)
                    sent += 1
                except Exception:
                    continue
            bot.send_message(msg.chat.id, f"✅ {sent} ta foydalanuvchiga yuborildi")
            return

    if msg.chat.id in admin_password_modes and msg.content_type == "text":
        password = (text or "").strip()
        if len(password) < 4:
            bot.send_message(msg.chat.id, "Parol kamida 4 ta belgidan iborat bo'lsin.")
            return
        ok = set_admin_password(str(msg.chat.id), password)
        if ok:
            bot.send_message(msg.chat.id, "✅ Parol muvaffaqiyatli o'rnatildi.")
            admin_password_modes.discard(msg.chat.id)
        else:
            bot.send_message(msg.chat.id, "❌ Parolni o'rnatishda xato.")
        return

    if msg.content_type == "web_app_data":
        process_web_app_order(msg)
        return

    if msg.content_type == "contact" or (text.isdigit() and len(text) >= 9):
        finish(msg)
        return

    if text == "🔙 Orqaga":
        bot.send_message(chat_id, "Bo'lim:", reply_markup=main_menu())

    elif text == "🛒 Savat":
        show_cart(chat_id)

    elif text == "🗑 Savatni tozalash":
        user_carts[chat_id] = []
        bot.send_message(chat_id, "Savat tozalandi", reply_markup=main_menu())

    elif text.startswith("❌ "):
        item = text.replace("❌ ", "")
        if item in user_carts.get(chat_id, []):
            user_carts[chat_id].remove(item)
        show_cart(chat_id)

    elif text == "✅ Buyurtmani yakunlash":
        if not user_carts.get(chat_id):
            bot.send_message(chat_id, "Savat bo'sh")
        else:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            markup.add(types.KeyboardButton("📞 Raqam yuborish", request_contact=True))
            bot.send_message(chat_id, "Raqamingizni yuboring:", reply_markup=markup)

    elif text in menu:
        bot.send_message(chat_id, text, reply_markup=food_menu(text))

    else:
        for cat in menu:
            for food in menu[cat]:
                if text.startswith(food):
                    if chat_id not in user_carts:
                        user_carts[chat_id] = []

                    user_carts[chat_id].append(food)
                    show_cart(chat_id)
                    return


# ===== RUN =====
if __name__ == "__main__":
    logging.info("Bot ishga tushdi...")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as exc:
            logging.exception("Polling xatoligi: %s", exc)
            time.sleep(5)
