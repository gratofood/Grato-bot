import telebot
from telebot import types
import json
import os

TOKEN = os.getenv("TOKEN")
ADMIN_ID = 6877877555

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=["start"])
def start(msg):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    webApp = types.WebAppInfo("https://gratofood.github.io/miniapp/")

    markup.add(types.KeyboardButton("🛍 Buyurtma berish", web_app=webApp))

    bot.send_message(msg.chat.id, "Buyurtma berish 👇", reply_markup=markup)


@bot.message_handler(content_types=["web_app_data"])
def webapp(msg):
    try:
        data = json.loads(msg.web_app_data.data)
    except:
        return bot.send_message(msg.chat.id, "Xatolik ❌")

    text = "🛒 YANGI ZAKAZ\n\n"
    text += f"👤 {data.get('name')}\n"
    text += f"📞 +998{data.get('phone')}\n"
    text += f"📍 {data.get('location')}\n"
    text += f"🏠 {data.get('address')}\n\n"

    text += "🍽 Buyurtma:\n"

    for item in data.get("items", []):
        text += f"{item['name']} x{item['qty']} = {item['price']*item['qty']} so'm\n"

    text += f"\n💰 Jami: {data.get('total')} so'm"

    bot.send_message(ADMIN_ID, text)
    bot.send_message(msg.chat.id, "✅ Zakaz yuborildi")

bot.infinity_polling()
