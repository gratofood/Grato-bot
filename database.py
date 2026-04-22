import hashlib
import json
import os
import urllib.parse

import pg8000

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    url = urllib.parse.urlparse(DATABASE_URL)
    return pg8000.connect(
        host=url.hostname,
        port=url.port or 5432,
        database=url.path[1:],
        user=url.username,
        password=url.password,
        ssl_context=True,
    )


def _rows_to_dicts(cursor, rows):
    columns = [col[0] for col in (cursor.description or [])]
    return [dict(zip(columns, row)) for row in rows]


def _row_to_dict(cursor, row):
    if not row:
        return None
    columns = [col[0] for col in (cursor.description or [])]
    return dict(zip(columns, row))


def init_db(superadmin_telegram_id: str | None = None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                telegram_id TEXT UNIQUE,
                username TEXT,
                role TEXT,
                password_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                phone TEXT,
                address TEXT,
                items_json TEXT,
                total INTEGER,
                status TEXT DEFAULT 'new'
            )
            """
        )
        cur.execute("ALTER TABLE admins ADD COLUMN IF NOT EXISTS password_hash TEXT")

        if superadmin_telegram_id:
            cur.execute(
                """
                INSERT INTO admins (telegram_id, username, role)
                VALUES (%s, %s, 'superadmin')
                ON CONFLICT (telegram_id) DO NOTHING
                """,
                (str(superadmin_telegram_id), "superadmin"),
            )
        conn.commit()
    finally:
        conn.close()


def upsert_user(user_id: str, username: str = "", first_name: str = ""):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (user_id, username, first_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_seen = CURRENT_TIMESTAMP
            """,
            (str(user_id), username or "", first_name or ""),
        )
        conn.commit()
    finally:
        conn.close()


def list_user_ids():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users")
        rows = cur.fetchall()
        columns = [col[0] for col in (cur.description or [])]
        idx = columns.index("user_id") if "user_id" in columns else 0
        return [r[idx] for r in rows]
    finally:
        conn.close()


def users_count():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        count = cur.fetchone()[0]
        return int(count or 0)
    finally:
        conn.close()


def list_admins():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, telegram_id, username, role, created_at FROM admins ORDER BY id ASC")
        rows = cur.fetchall()
        return _rows_to_dicts(cur, rows)
    finally:
        conn.close()


def get_admin_by_telegram_id(telegram_id: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, telegram_id, username, role, password_hash, created_at FROM admins WHERE telegram_id = %s",
            (str(telegram_id),),
        )
        row = cur.fetchone()
        return _row_to_dict(cur, row)
    finally:
        conn.close()


def add_admin(telegram_id: str, username: str, role: str = "admin"):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO admins (telegram_id, username, role) VALUES (%s, %s, %s)",
            (str(telegram_id), username, role),
        )
        conn.commit()
    finally:
        conn.close()


def set_admin_password(telegram_id: str, password: str):
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE admins SET password_hash = %s WHERE telegram_id = %s",
            (password_hash, str(telegram_id)),
        )
        updated = cur.rowcount
        conn.commit()
        return updated > 0
    finally:
        conn.close()


def verify_admin(telegram_id: str, password: str):
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, telegram_id, username, role, created_at
            FROM admins
            WHERE telegram_id = %s AND password_hash = %s
            """,
            (str(telegram_id), password_hash),
        )
        row = cur.fetchone()
        return _row_to_dict(cur, row)
    finally:
        conn.close()


def delete_admin(telegram_id: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT role FROM admins WHERE telegram_id = %s", (str(telegram_id),))
        role = cur.fetchone()
        if role and role[0] == "superadmin":
            return False
        cur.execute("DELETE FROM admins WHERE telegram_id = %s", (str(telegram_id),))
        conn.commit()
        return True
    finally:
        conn.close()


def save_order(phone: str, address: str, items: list, total: int, status: str = "new"):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO orders (phone, address, items_json, total, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (phone, address, json.dumps(items, ensure_ascii=False), int(total), status),
        )
        oid = cur.fetchone()[0]
        conn.commit()
        return oid
    finally:
        conn.close()


def list_orders():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders ORDER BY id DESC")
        rows = cur.fetchall()
        raw = _rows_to_dicts(cur, rows)
        out = []
        for d in raw:
            d["items"] = json.loads(d.pop("items_json") or "[]")
            out.append(d)
        return out
    finally:
        conn.close()


def update_order_status(order_id: int, status: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE orders SET status = %s WHERE id = %s", (status, order_id))
        conn.commit()
    finally:
        conn.close()


def get_stats():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM orders")
        total_orders = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(total), 0) FROM orders")
        total_revenue = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = CURRENT_DATE")
        today_orders = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(total), 0) FROM orders WHERE DATE(created_at) = CURRENT_DATE")
        today_revenue = cur.fetchone()[0]

        cur.execute("SELECT items_json FROM orders")
        rows = cur.fetchall()

        item_counts = {}
        for row in rows:
            for item in json.loads((row[0] or "[]")):
                name = item.get("name", "Noma'lum")
                qty = int(item.get("qty", 1))
                item_counts[name] = item_counts.get(name, 0) + qty

        top = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "total_orders": int(total_orders or 0),
            "total_revenue": int(total_revenue or 0),
            "today_orders": int(today_orders or 0),
            "today_revenue": int(today_revenue or 0),
            "top_items": [{"name": n, "count": c} for n, c in top],
        }
    finally:
        conn.close()
