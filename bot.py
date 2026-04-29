import telebot
from telebot import types
import os
import json
import threading

from fastapi import FastAPI
import uvicorn

# ===== ENV =====
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise Exception("TOKEN topilmadi")

ADMIN_ID = 6877877555

bot = telebot.TeleBot(TOKEN)

# ===== FASTAPI (Railway uchun) =====
app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}


# ===== START =====
@bot.message_handler(commands=["start"])
def start(msg):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    webApp = types.WebAppInfo("https://gratofood.github.io/miniapp/")

    markup.add(types.KeyboardButton("🛍 Buyurtma berish", web_app=webApp))

    bot.send_message(
        msg.chat.id,
        "Buyurtma berish uchun tugmani bosing 👇",
        reply_markup=markup
    )


# ===== MINIAPP DATA =====
@bot.message_handler(content_types=["web_app_data"])
def webapp(msg):
    chat_id = msg.chat.id

    try:
        data = json.loads(msg.web_app_data.data)
    except:
        bot.send_message(chat_id, "Xatolik ❌")
        return

    if not data:
        bot.send_message(chat_id, "Savat bo'sh ❌")
        return

    text = "🛒 Yangi zakaz:\n\n"

    counts = {}
    for item in data:
        counts[item] = counts.get(item, 0) + 1

    for item in counts:
        text += f"{item} x{counts[item]}\n"

    bot.send_message(ADMIN_ID, text)
    bot.send_message(chat_id, "✅ Buyurtmangiz yuborildi!")


# ===== BOT RUN =====
def run_bot():
    print("🤖 Bot ishga tushdi...")
    bot.infinity_polling()


# ===== MAIN =====
if __name__ == "__main__":
    threading.Thread(target=run_bot).start()

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
