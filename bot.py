import telebot
from telebot import types
import os
import json

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 6877877555

bot = telebot.TeleBot(TOKEN)


@bot.message_handler(commands=["start"])
def start(msg):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    web_app = types.WebAppInfo("https://gratofood.github.io/miniapp/?v=5")

    btn = types.KeyboardButton("🛍 Buyurtma berish", web_app=web_app)
    markup.add(btn)

    bot.send_message(msg.chat.id, "Buyurtma berish 👇", reply_markup=markup)


@bot.message_handler(content_types=["web_app_data"])
def webapp(msg):
    chat_id = msg.chat.id

    try:
        data = json.loads(msg.web_app_data.data)
    except:
        bot.send_message(chat_id, "Xatolik ❌")
        return

    if not data or "items" not in data:
        bot.send_message(chat_id, "Savat bo'sh ❌")
        return

    name = data.get("name", "Noma'lum")
    phone = data.get("phone", "Yo‘q")
    address = data.get("address", "Yo‘q")
    items = data.get("items", [])

    counts = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1

    text = "🛒 Yangi zakaz:\n\n"
    text += f"👤 Ism: {name}\n"
    text += f"📞 Telefon: {phone}\n"
    text += f"📍 Manzil: {address}\n\n"

    for item, qty in counts.items():
        text += f"{item} x{qty}\n"

    bot.send_message(ADMIN_ID, text)
    bot.send_message(chat_id, "✅ Buyurtma yuborildi!")


bot.infinity_polling()
