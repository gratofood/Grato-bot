import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "orders.db"


def get_conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            items_json TEXT NOT NULL,
            total INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    conn.commit()
    conn.close()


def save_order(phone: str, address: str, items: list, total: int, status: str = "new"):
    conn = get_conn()
    cur = conn.execute(
        """
        INSERT INTO orders (phone, address, items_json, total, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (phone, address, json.dumps(items, ensure_ascii=False), int(total), status),
    )
    conn.commit()
    order_id = cur.lastrowid
    conn.close()
    return order_id


def list_orders():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        d["items"] = json.loads(d.pop("items_json"))
        results.append(d)
    return results


def update_order_status(order_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()


def get_stats():
    conn = get_conn()
    total_orders = conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    total_revenue = conn.execute("SELECT COALESCE(SUM(total), 0) s FROM orders").fetchone()["s"]
    today_orders = conn.execute(
        "SELECT COUNT(*) c FROM orders WHERE DATE(created_at) = DATE('now', 'localtime')"
    ).fetchone()["c"]
    today_revenue = conn.execute(
        "SELECT COALESCE(SUM(total),0) s FROM orders WHERE DATE(created_at) = DATE('now', 'localtime')"
    ).fetchone()["s"]

    rows = conn.execute("SELECT items_json FROM orders").fetchall()
    conn.close()

    item_counts = {}
    for row in rows:
        items = json.loads(row["items_json"])
        for item in items:
            name = item.get("name", "Noma'lum")
            qty = int(item.get("qty", 1))
            item_counts[name] = item_counts.get(name, 0) + qty

    top_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    return {
        "total_orders": total_orders,
        "total_revenue": int(total_revenue or 0),
        "today_orders": today_orders,
        "today_revenue": int(today_revenue or 0),
        "top_items": [{"name": name, "count": count} for name, count in top_items],
    }
