import telebot
from telebot import types
import os
import json

from db import add_item, get_cart, clear_cart, remove_item

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise Exception("TOKEN topilmadi")

ADMIN_ID = 6877877555

bot = telebot.TeleBot(TOKEN)


# ===== MENU =====
def load_menu():
    with open("menu.json", "r", encoding="utf-8") as f:
        return json.load(f)


MENU = load_menu()


# ===== MENULAR =====
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    for cat in MENU:
        markup.add(cat)

    markup.add("🛒 Savat", "✅ Buyurtma berish")
    return markup


def food_menu(category):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    for food, price in MENU[category].items():
        markup.add(f"{food} - {price} so'm")

    markup.add("🔙 Orqaga")
    return markup


def cart_markup(cart):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    for item in set(cart):
        markup.add(f"❌ {item}")

    markup.add("🔙 Orqaga")
    return markup


def build_cart_text(cart):
    text = "🛒 Savat:\n\n"
    for item in set(cart):
        text += f"{item} x{cart.count(item)}\n"
    return text


# ===== START =====
@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id, "Bo'lim tanlang:", reply_markup=main_menu())


# ===== HANDLER =====
@bot.message_handler(content_types=["text", "contact"])
def handler(msg):
    chat_id = msg.chat.id
    text = msg.text if msg.text else ""

    # ===== TELEFON → ZAKAZ =====
    if msg.content_type == "contact":
        phone = msg.contact.phone_number
        cart = get_cart(chat_id)

        if not cart:
            bot.send_message(chat_id, "Savat bo'sh")
            return

        total = 0
        text_order = "🛒 Yangi zakaz:\n\n"

        for item in set(cart):
            count = cart.count(item)
            price = 0

            for cat in MENU:
                if item in MENU[cat]:
                    price = MENU[cat][item]

            total += price * count
            text_order += f"{item} x{count} = {price * count} so'm\n"

        text_order += f"\n📞 {phone}\n💰 Jami: {total} so'm"

        bot.send_message(ADMIN_ID, text_order)

        clear_cart(chat_id)
        bot.send_message(chat_id, "✅ Zakazingiz qabul qilindi!", reply_markup=main_menu())
        return

    # ===== ORQAGA =====
    if text == "🔙 Orqaga":
        bot.send_message(chat_id, "Menu:", reply_markup=main_menu())
        return

    # ===== SAVAT =====
    if text == "🛒 Savat":
        cart = get_cart(chat_id)

        if not cart:
            bot.send_message(chat_id, "Savat bo'sh")
            return

        bot.send_message(chat_id, build_cart_text(cart), reply_markup=cart_markup(cart))
        return

    # ===== BUYURTMA =====
    if text == "✅ Buyurtma berish":
        cart = get_cart(chat_id)

        if not cart:
            bot.send_message(chat_id, "Savat bo'sh")
            return

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📞 Raqam yuborish", request_contact=True))

        bot.send_message(chat_id, "Telefon raqamingizni yuboring:", reply_markup=markup)
        return

    # ===== O‘CHIRISH =====
    if text.startswith("❌ "):
        item = text.replace("❌ ", "")
        remove_item(chat_id, item)

        cart = get_cart(chat_id)

        if not cart:
            bot.send_message(chat_id, "Savat bo'sh", reply_markup=main_menu())
            return

        bot.send_message(
            chat_id,
            f"{item} o‘chirildi ❌\n\n{build_cart_text(cart)}",
            reply_markup=cart_markup(cart)
        )
        return

    # ===== KATEGORIYA =====
    if text in MENU:
        bot.send_message(chat_id, text, reply_markup=food_menu(text))
        return

    # ===== MAHSULOT =====
    for cat in MENU:
        for food in MENU[cat]:
            if text.startswith(food):
                add_item(chat_id, food)

                cart = get_cart(chat_id)

                bot.send_message(
                    chat_id,
                    f"{food} qo'shildi ✅\n\n{build_cart_text(cart)}",
                    reply_markup=cart_markup(cart)
                )
                return


print("🚀 Bot ishga tushdi...")
bot.infinity_polling()
