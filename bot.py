import telebot
from telebot import types
import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import pytz

# ── SOZLAMALAR ──
TOKEN        = os.getenv("TOKEN")
ADMIN_ID     = int(os.getenv("ADMIN_ID", "6877877555"))
DATABASE_URL = os.getenv("DATABASE_URL")
TIMEZONE     = pytz.timezone("Asia/Tashkent")
OPEN_HOUR    = 8
CLOSE_HOUR   = 22

bot = telebot.TeleBot(TOKEN)

# ── DATABASE ──
def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id         SERIAL PRIMARY KEY,
            user_id    BIGINT, username TEXT,
            name TEXT, phone TEXT, address TEXT, note TEXT, location TEXT,
            items JSONB, subtotal INTEGER, promo TEXT, discount INTEGER, total INTEGER,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS order_counter (id INTEGER PRIMARY KEY DEFAULT 1, count INTEGER DEFAULT 0)")
    cur.execute("INSERT INTO order_counter (id, count) VALUES (1, 0) ON CONFLICT DO NOTHING")
    conn.commit(); cur.close(); conn.close()

def next_order_number():
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE order_counter SET count = count + 1 WHERE id = 1 RETURNING count")
    num = cur.fetchone()["count"]
    conn.commit(); cur.close(); conn.close()
    return num

def save_order(user_id, username, data):
    num = next_order_number()
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders (id,user_id,username,name,phone,address,note,location,items,subtotal,promo,discount,total)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (num, user_id, username,
          data.get("name"), data.get("phone"),
          data.get("address",""), data.get("note",""),
          json.dumps(data.get("location")) if data.get("location") else None,
          json.dumps(data.get("items",[])),
          data.get("subtotal",0), data.get("promo"),
          data.get("discount",0), data.get("total",0)))
    conn.commit(); cur.close(); conn.close()
    return num

def get_order(order_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    row = cur.fetchone(); cur.close(); conn.close()
    return row

def update_status(order_id, status):
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
    conn.commit(); cur.close(); conn.close()

def get_user_orders(user_id, limit=5):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user_id, limit))
    rows = cur.fetchall(); cur.close(); conn.close()
    return rows

def get_daily_stats():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) AS count, COALESCE(SUM(total),0) AS revenue, status
        FROM orders WHERE created_at::date = CURRENT_DATE GROUP BY status
    """)
    rows = cur.fetchall()
    cur.execute("SELECT items FROM orders WHERE created_at::date = CURRENT_DATE")
    all_orders = cur.fetchall()
    cur.close(); conn.close()
    return rows, all_orders

# ── YORDAMCHI ──
def fmt(n): return f"{n:,} so'm".replace(",", " ")

def is_open():
    now = datetime.now(TIMEZONE)
    return OPEN_HOUR <= now.hour < CLOSE_HOUR

def status_label(s):
    return {
        "new":       "🆕 Yangi",
        "accepted":  "✅ Qabul qilindi",
        "cooking":   "👨‍🍳 Tayyorlanmoqda",
        "on_way":    "🚗 Yo'lda",
        "delivered": "🎉 Yetkazildi",
        "cancelled": "❌ Bekor qilindi"
    }.get(s, s)

def order_text(order_id, data, username=None):
    if isinstance(data, dict):
        items=data.get("items",[]); name=data.get("name"); phone=data.get("phone")
        address=data.get("address",""); note=data.get("note","")
        promo=data.get("promo"); discount=data.get("discount",0)
        subtotal=data.get("subtotal",0); total=data.get("total",0)
    else:
        items=json.loads(data["items"]) if isinstance(data["items"],str) else data["items"]
        name=data["name"]; phone=data["phone"]; address=data["address"] or ""
        note=data["note"] or ""; promo=data["promo"]; discount=data["discount"]
        subtotal=data["subtotal"]; total=data["total"]

    t  = f"🛒 YANGI BUYURTMA #{order_id}\n━━━━━━━━━━━━━━━━\n"
    t += f"👤 {name}\n📞 {phone}\n"
    if address: t += f"🏠 {address}\n"
    if note:    t += f"💬 {note}\n"
    if username: t += f"🔗 @{username}\n"
    t += "━━━━━━━━━━━━━━━━\n🍽 Buyurtma:\n"
    for i in items:
        t += f"  • {i['name']} x{i['qty']} = {fmt(i['price']*i['qty'])}\n"
    t += "━━━━━━━━━━━━━━━━\n"
    if promo and discount:
        t += f"🏷 Promo: {promo} (-{discount}%)\n💵 Chegirmasiz: {fmt(subtotal)}\n"
    t += f"💰 Jami: {fmt(total)}\n"
    return t

def admin_kb(order_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Qabul",           callback_data=f"status_{order_id}_accepted"),
        types.InlineKeyboardButton("👨‍🍳 Tayyorlanmoqda", callback_data=f"status_{order_id}_cooking"),
    )
    kb.add(
        types.InlineKeyboardButton("🚗 Yo'lda",          callback_data=f"status_{order_id}_on_way"),
        types.InlineKeyboardButton("🎉 Yetkazildi",      callback_data=f"status_{order_id}_delivered"),
    )
    kb.add(types.InlineKeyboardButton("❌ Bekor",        callback_data=f"status_{order_id}_cancelled"))
    return kb

# ── /start ──
@bot.message_handler(commands=["start"])
def start(msg):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    webApp = types.WebAppInfo("https://gratofood.github.io/miniapp/")
    markup.add(types.KeyboardButton("🛍 Buyurtma berish", web_app=webApp))
    markup.add(types.KeyboardButton("📋 Buyurtmalarim"), types.KeyboardButton("ℹ️ Ma'lumot"))
    status = "✅ Hozir ochiq" if is_open() else f"❌ Hozir yopiq ({OPEN_HOUR}:00–{CLOSE_HOUR}:00)"
    bot.send_message(msg.chat.id, f"Xush kelibsiz! {status}\nBuyurtma berish 👇", reply_markup=markup)

# ── /stats (faqat admin) ──
@bot.message_handler(commands=["stats"])
def stats(msg):
    if msg.chat.id != ADMIN_ID: return
    rows, all_orders = get_daily_stats()
    total_count   = sum(r["count"] for r in rows)
    total_revenue = sum(r["revenue"] for r in rows)
    t  = f"📊 Bugungi statistika\n━━━━━━━━━━━━━━━━\n"
    t += f"📦 Jami: {total_count} ta\n💰 Daromad: {fmt(total_revenue)}\n\n"
    for r in rows:
        t += f"{status_label(r['status'])}: {r['count']} ta\n"
    item_counts = {}
    for o in all_orders:
        for i in (json.loads(o["items"]) if isinstance(o["items"],str) else o["items"]):
            item_counts[i["name"]] = item_counts.get(i["name"],0) + i["qty"]
    if item_counts:
        t += "\n🏆 Eng ko'p buyurtma:\n"
        for idx,(name,cnt) in enumerate(sorted(item_counts.items(),key=lambda x:x[1],reverse=True)[:5],1):
            t += f"  {idx}. {name} — {cnt} ta\n"
    bot.send_message(ADMIN_ID, t)

# ── Buyurtmalarim ──
@bot.message_handler(func=lambda m: m.text == "📋 Buyurtmalarim")
def my_orders(msg):
    orders = get_user_orders(msg.chat.id)
    if not orders:
        return bot.send_message(msg.chat.id, "Sizda hali buyurtma yo'q 😊")
    t = "📋 So'nggi buyurtmalaringiz:\n━━━━━━━━━━━━━━━━\n"
    for o in orders:
        items = json.loads(o["items"]) if isinstance(o["items"],str) else o["items"]
        date  = o["created_at"].strftime("%d.%m %H:%M")
        t += f"\n#{o['id']} | {date}\n💰 {fmt(o['total'])} | {status_label(o['status'])}\n"
        for item in items[:3]:
            t += f"  • {item['name']} x{item['qty']}\n"
        if len(items) > 3: t += f"  ... va yana {len(items)-3} ta\n"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 Oxirgisini takrorlash", callback_data=f"reorder_{orders[0]['id']}"))
    bot.send_message(msg.chat.id, t, reply_markup=kb)

# ── Ma'lumot ──
@bot.message_handler(func=lambda m: m.text == "ℹ️ Ma'lumot")
def info(msg):
    t  = "🍽 Grato Kafe\n━━━━━━━━━━━━━━━━\n"
    t += f"🕐 Ish vaqti: {OPEN_HOUR}:00 – {CLOSE_HOUR}:00\n"
    t += "📞 +998943650036\n📸 Instagram: @grato_food\n✈️ Telegram: @Grato_kafe\n"
    t += f"\n{'✅ Hozir ochiq' if is_open() else '❌ Hozir yopiq'}"
    bot.send_message(msg.chat.id, t)

# ── WebApp data ──
@bot.message_handler(content_types=["web_app_data"])
def webapp(msg):
    try:
        data = json.loads(msg.web_app_data.data)
    except:
        return bot.send_message(msg.chat.id, "Xatolik ❌ Qayta urinib ko'ring")
    if not is_open():
        return bot.send_message(msg.chat.id, f"⚠️ Kafe yopiq!\nIsh vaqti: {OPEN_HOUR}:00–{CLOSE_HOUR}:00")
    if not data.get("items"):
        return bot.send_message(msg.chat.id, "Savat bo'sh ❌")
    order_id = save_order(msg.chat.id, msg.from_user.username, data)
    bot.send_message(msg.chat.id,
        f"✅ Buyurtma qabul qilindi!\n📌 Raqam: #{order_id}\n💰 Jami: {fmt(data.get('total',0))}\n\nHolati haqida xabar beramiz 😊")
    bot.send_message(ADMIN_ID, order_text(order_id, data, msg.from_user.username), reply_markup=admin_kb(order_id))

# ── Callbacks ──
@bot.callback_query_handler(func=lambda c: True)
def callback(c):

    if c.data.startswith("status_") and c.from_user.id == ADMIN_ID:
        parts    = c.data.split("_")
        order_id = int(parts[1])
        status   = "_".join(parts[2:])
        update_status(order_id, status)
        order    = get_order(order_id)
        new_text = order_text(order_id, order) + f"\n📌 Holat: {status_label(status)}"
        try:
            bot.edit_message_text(new_text, c.message.chat.id, c.message.message_id,
                reply_markup=admin_kb(order_id) if status not in ["delivered","cancelled"] else None)
        except: pass
        status_msgs = {
            "accepted":  "✅ Buyurtmangiz qabul qilindi!",
            "cooking":   "👨‍🍳 Buyurtmangiz tayyorlanmoqda!",
            "on_way":    "🚗 Buyurtmangiz yo'lda!",
            "delivered": "🎉 Buyurtmangiz yetkazildi!",
            "cancelled": "❌ Buyurtmangiz bekor qilindi.",
        }
        if order and order["user_id"] and status in status_msgs:
            try: bot.send_message(order["user_id"], f"📌 Buyurtma #{order_id}\n{status_msgs[status]}")
            except: pass
        bot.answer_callback_query(c.id, status_label(status))

    elif c.data.startswith("reorder_"):
        order_id = int(c.data.split("_")[1])
        order = get_order(order_id)
        if not order: return bot.answer_callback_query(c.id, "Topilmadi")
        if not is_open():
            return bot.answer_callback_query(c.id, f"Kafe yopiq! {OPEN_HOUR}:00–{CLOSE_HOUR}:00", show_alert=True)
        items = json.loads(order["items"]) if isinstance(order["items"],str) else order["items"]
        t = "🔄 Takrorlash:\n━━━━━━━━━━━━━━━━\n"
        for i in items: t += f"• {i['name']} x{i['qty']} = {fmt(i['price']*i['qty'])}\n"
        t += f"━━━━━━━━━━━━━━━━\n💰 Jami: {fmt(order['total'])}\n\nTaskdiqlaysizmi?"
        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("✅ Ha", callback_data=f"confirm_reorder_{order_id}"),
            types.InlineKeyboardButton("❌ Yo'q", callback_data="cancel_reorder"),
        )
        bot.send_message(c.message.chat.id, t, reply_markup=kb)
        bot.answer_callback_query(c.id)

    elif c.data.startswith("confirm_reorder_"):
        order_id  = int(c.data.split("_")[2])
        old_order = get_order(order_id)
        if not old_order: return bot.answer_callback_query(c.id, "Xatolik")
        data = {
            "name": old_order["name"], "phone": old_order["phone"],
            "address": old_order["address"], "note": old_order["note"],
            "items": json.loads(old_order["items"]) if isinstance(old_order["items"],str) else old_order["items"],
            "subtotal": old_order["subtotal"], "promo": old_order["promo"],
            "discount": old_order["discount"], "total": old_order["total"],
        }
        new_id = save_order(c.from_user.id, c.from_user.username, data)
        bot.send_message(c.message.chat.id, f"✅ Buyurtma #{new_id} yuborildi!\n💰 {fmt(old_order['total'])}")
        bot.send_message(ADMIN_ID, order_text(new_id, data, c.from_user.username), reply_markup=admin_kb(new_id))
        bot.answer_callback_query(c.id, "Yuborildi!")

    elif c.data == "cancel_reorder":
        bot.answer_callback_query(c.id, "Bekor qilindi")
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass

# ── ISHGA TUSHIRISH ──
if __name__ == "__main__":
    print("Ma'lumotlar bazasi tayyorlanmoqda...")
    init_db()
    print("Bot ishga tushdi!")
    bot.infinity_polling()
