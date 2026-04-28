import telebot
from telebot import types
import os
import json

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 6877877555

bot = telebot.TeleBot(TOKEN)

# ===== MENU JSONDAN OLISH =====
def load_menu():
    try:
        with open("menu.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("MENU ERROR:", e)
        return {}

menu = load_menu()

user_carts = {}

# ===== MENULAR =====
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for cat in menu:
        markup.add(cat)
    markup.add("🛒 Savat", "✅ Buyurtma berish")
    return markup

def food_menu(category):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for food, price in menu.get(category, {}).items():
        markup.add(f"{food} - {price} so'm")
    markup.add("🔙 Orqaga")
    return markup

# ===== START =====
@bot.message_handler(commands=["start"])
def start(msg):
    user_carts[msg.chat.id] = []
    bot.send_message(msg.chat.id, "Bo'lim tanlang:", reply_markup=main_menu())

# ===== HANDLER =====
@bot.message_handler(content_types=["text", "contact"])
def handler(msg):
    chat_id = msg.chat.id
    text = msg.text if msg.text else ""

    # ===== TELEFON KELDI → ZAKAZ =====
    if msg.content_type == "contact":
        phone = msg.contact.phone_number
        cart = user_carts.get(chat_id, [])

        if not cart:
            bot.send_message(chat_id, "Savat bo'sh")
            return

        total = 0
        text_order = "🛒 Yangi zakaz:\n"

        for item in set(cart):
            count = cart.count(item)
            price = 0

            for cat in menu:
                if item in menu[cat]:
                    price = menu[cat][item]

            total += price * count
            text_order += f"{item} x{count}\n"

        text_order += f"\n📞 {phone}\n💰 Jami: {total} so'm"

        bot.send_message(ADMIN_ID, text_order)

        user_carts[chat_id] = []
        bot.send_message(chat_id, "✅ Zakazingiz qabul qilindi!", reply_markup=main_menu())
        return

    # ===== ORQAGA =====
    if text == "🔙 Orqaga":
        bot.send_message(chat_id, "Menu:", reply_markup=main_menu())

    # ===== SAVAT =====
    elif text == "🛒 Savat":
        cart = user_carts.get(chat_id, [])

        if not cart:
            bot.send_message(chat_id, "Savat bo'sh")
            return

        text_cart = "🛒 Savat:\n"
        for item in set(cart):
            text_cart += f"{item} x{cart.count(item)}\n"

        bot.send_message(chat_id, text_cart)

    # ===== BUYURTMA =====
    elif text == "✅ Buyurtma berish":
        cart = user_carts.get(chat_id, [])

        if not cart:
            bot.send_message(chat_id, "Savat bo'sh")
            return

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📞 Raqam yuborish", request_contact=True))

        bot.send_message(chat_id, "Telefon raqamingizni yuboring:", reply_markup=markup)

    # ===== KATEGORIYA =====
    elif text in menu:
        bot.send_message(chat_id, text, reply_markup=food_menu(text))

    # ===== MAHSULOT =====
    else:
        for cat in menu:
            for food in menu[cat]:
                if text.startswith(food):
                    user_carts.setdefault(chat_id, []).append(food)
                    bot.send_message(chat_id, f"{food} qo'shildi ✅")
                    return

# ===== RUN =====
bot.infinity_polling()
