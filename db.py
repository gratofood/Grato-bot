import sqlite3

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS carts (
    user_id INTEGER,
    item TEXT
)
""")
conn.commit()


def add_item(user_id, item):
    cursor.execute("INSERT INTO carts (user_id, item) VALUES (?, ?)", (user_id, item))
    conn.commit()


def get_cart(user_id):
    cursor.execute("SELECT item FROM carts WHERE user_id=?", (user_id,))
    return [row[0] for row in cursor.fetchall()]


def clear_cart(user_id):
    cursor.execute("DELETE FROM carts WHERE user_id=?", (user_id,))
    conn.commit()
