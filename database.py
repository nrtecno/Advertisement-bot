import os
import libsql_client
from datetime import datetime

TURSO_URL = os.getenv("TURSO_DB_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

_client = None


async def get_client():
    global _client
    if _client is None:
        _client = libsql_client.create_client(
            url=TURSO_URL,
            auth_token=TURSO_AUTH_TOKEN,
        )
    return _client


async def init_db():
    client = await get_client()

    await client.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            mobile TEXT,
            credits INTEGER DEFAULT 0,
            total_views_ordered INTEGER DEFAULT 0,
            total_views_delivered INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await client.execute("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            link TEXT,
            views_target INTEGER,
            views_delivered INTEGER DEFAULT 0,
            credits_spent INTEGER,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    await client.execute("""
        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER,
            clicker_user_id INTEGER,
            clicked_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(link_id, clicker_user_id)
        )
    """)

    await client.execute("""
        CREATE TABLE IF NOT EXISTS ad_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER,
            user_id INTEGER,
            message_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(link_id, user_id)
        )
    """)

    await client.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_on INTEGER DEFAULT 0,
            message TEXT
        )
    """)
    await client.execute("""
        INSERT OR IGNORE INTO broadcast_state (id, is_on, message)
        VALUES (1, 0, '')
    """)

    await client.execute("""
        CREATE TABLE IF NOT EXISTS pending_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            credits INTEGER,
            amount REAL,
            screenshot_file_id TEXT,
            status TEXT DEFAULT 'pending',
            admin_message_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)


# ---------- USERS ----------
async def get_user(user_id: int):
    client = await get_client()
    result = await client.execute(
        "SELECT * FROM users WHERE user_id = ?", [user_id]
    )
    return result.rows[0] if result.rows else None


async def create_user(user_id: int, username: str = None, first_name: str = None):
    client = await get_client()
    await client.execute(
        """INSERT OR IGNORE INTO users (user_id, username, first_name, credits)
           VALUES (?, ?, ?, 0)""",
        [user_id, username, first_name],
    )
    return await get_user(user_id)


async def update_user_credits(user_id: int, delta: int):
    client = await get_client()
    await client.execute(
        """UPDATE users SET credits = credits + ?, updated_at = CURRENT_TIMESTAMP
           WHERE user_id = ?""",
        [delta, user_id],
    )


async def set_user_credits(user_id: int, credits: int):
    client = await get_client()
    await client.execute(
        """UPDATE users SET credits = ?, updated_at = CURRENT_TIMESTAMP
           WHERE user_id = ?""",
        [credits, user_id],
    )


async def update_user_mobile(user_id: int, mobile: str):
    client = await get_client()
    await client.execute(
        "UPDATE users SET mobile = ? WHERE user_id = ?", [mobile, user_id]
    )


async def get_all_user_ids():
    client = await get_client()
    result = await client.execute("SELECT user_id FROM users")
    return [row["user_id"] for row in result.rows]


async def get_user_count():
    client = await get_client()
    result = await client.execute("SELECT COUNT(*) as cnt FROM users")
    return result.rows[0]["cnt"]


# ---------- LINKS ----------
async def create_link(user_id: int, link: str, views_target: int, credits_spent: int):
    client = await get_client()
    result = await client.execute(
        """INSERT INTO links (user_id, link, views_target, credits_spent)
           VALUES (?, ?, ?, ?)""",
        [user_id, link, views_target, credits_spent],
    )
    return result.last_insert_rowid


async def get_active_links():
    client = await get_client()
    result = await client.execute(
        """SELECT * FROM links
           WHERE status = 'active' AND views_delivered < views_target"""
    )
    return result.rows


async def get_link_by_id(link_id: int):
    client = await get_client()
    result = await client.execute(
        "SELECT * FROM links WHERE id = ?", [link_id]
    )
    return result.rows[0] if result.rows else None


async def increment_link_views(link_id: int):
    client = await get_client()
    await client.execute(
        "UPDATE links SET views_delivered = views_delivered + 1 WHERE id = ?",
        [link_id],
    )
    link = await get_link_by_id(link_id)
    if link and link["views_delivered"] >= link["views_target"]:
        await client.execute(
            "UPDATE links SET status = 'completed' WHERE id = ?", [link_id]
        )
        return True
    return False


# ---------- CLICKS ----------
async def has_clicked(link_id: int, clicker_user_id: int):
    client = await get_client()
    result = await client.execute(
        "SELECT 1 FROM clicks WHERE link_id = ? AND clicker_user_id = ?",
        [link_id, clicker_user_id],
    )
    return len(result.rows) > 0


async def record_click(link_id: int, clicker_user_id: int):
    client = await get_client()
    await client.execute(
        "INSERT OR IGNORE INTO clicks (link_id, clicker_user_id) VALUES (?, ?)",
        [link_id, clicker_user_id],
    )


# ---------- AD DELIVERIES ----------
async def save_delivery(link_id: int, user_id: int, message_id: int):
    client = await get_client()
    await client.execute(
        """INSERT OR REPLACE INTO ad_deliveries (link_id, user_id, message_id)
           VALUES (?, ?, ?)""",
        [link_id, user_id, message_id],
    )


async def get_deliveries_for_link(link_id: int):
    client = await get_client()
    result = await client.execute(
        "SELECT * FROM ad_deliveries WHERE link_id = ?", [link_id]
    )
    return result.rows


# ---------- BROADCAST ----------
async def get_broadcast_state():
    client = await get_client()
    result = await client.execute("SELECT * FROM broadcast_state WHERE id = 1")
    return result.rows[0] if result.rows else {"is_on": 0, "message": ""}


async def set_broadcast_state(is_on: int, message: str = ""):
    client = await get_client()
    await client.execute(
        "UPDATE broadcast_state SET is_on = ?, message = ? WHERE id = 1",
        [is_on, message],
    )


# ---------- PENDING ORDERS ----------
async def create_pending_order(user_id: int, credits: int, amount: float,
                               screenshot_file_id: str):
    client = await get_client()
    result = await client.execute(
        """INSERT INTO pending_orders (user_id, credits, amount, screenshot_file_id)
           VALUES (?, ?, ?, ?)""",
        [user_id, credits, amount, screenshot_file_id],
    )
    return result.last_insert_rowid


async def get_pending_order(order_id: int):
    client = await get_client()
    result = await client.execute(
        "SELECT * FROM pending_orders WHERE id = ?", [order_id]
    )
    return result.rows[0] if result.rows else None


async def update_order_status(order_id: int, status: str):
    client = await get_client()
    await client.execute(
        "UPDATE pending_orders SET status = ? WHERE id = ?", [status, order_id]
    )


async def set_order_admin_message(order_id: int, admin_message_id: int):
    client = await get_client()
    await client.execute(
        "UPDATE pending_orders SET admin_message_id = ? WHERE id = ?",
        [admin_message_id, order_id],
    )


async def get_user_pending_orders(user_id: int):
    client = await get_client()
    result = await client.execute(
        "SELECT * FROM pending_orders WHERE user_id = ? AND status = 'pending'",
        [user_id],
    )
    return result.rows
