import json
import aiosqlite
import os
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "quotes.db")
SEED_FILE = os.path.join(os.path.dirname(__file__), "cleaned_quotes.json")
SEED_SERVER_ID = "219948617425747968"

QUOTES_PER_PAGE = 5

# Persistent connection
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
    return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def init_db():
    db = await get_db()
    await db.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            internal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id TEXT NOT NULL,
            quote_id INTEGER NOT NULL,
            quote_text TEXT NOT NULL,
            author_user_id TEXT,
            author_name TEXT,
            added_by_user_id TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_server_quote
        ON quotes (server_id, quote_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_server_author_user
        ON quotes (server_id, author_user_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_server_author_name
        ON quotes (server_id, author_name)
    """)
    await db.commit()

    # One-time seed from cleaned_quotes.json if DB is empty
    if os.path.exists(SEED_FILE):
        cursor = await db.execute(
            "SELECT COUNT(*) FROM quotes WHERE server_id = ?",
            (SEED_SERVER_ID,),
        )
        count = (await cursor.fetchone())[0]
        if count == 0:
            with open(SEED_FILE, "r", encoding="utf-8") as f:
                quotes = json.load(f)
            for i, q in enumerate(quotes, start=1):
                await db.execute(
                    """INSERT INTO quotes
                       (server_id, quote_id, quote_text, author_user_id,
                        author_name, added_by_user_id, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        SEED_SERVER_ID,
                        i,
                        q["quote_text"],
                        q.get("author_user_id"),
                        q.get("author_name"),
                        q.get("added_by_user_id") or q.get("added_by", "Unknown"),
                        q.get("timestamp", "Unknown"),
                    ),
                )
            await db.commit()
            print("Seeded %d quotes from %s" % (len(quotes), SEED_FILE))


async def add_quote(
    server_id: str,
    quote_text: str,
    added_by_user_id: str,
    author_user_id: str | None = None,
    author_name: str | None = None,
) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT MAX(quote_id) FROM quotes WHERE server_id = ?",
        (server_id,),
    )
    row = await cursor.fetchone()
    quote_id = (row[0] or 0) + 1

    await db.execute(
        """INSERT INTO quotes
           (server_id, quote_id, quote_text, author_user_id, author_name,
            added_by_user_id, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            server_id,
            quote_id,
            quote_text,
            author_user_id,
            author_name,
            added_by_user_id,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await db.commit()
    return quote_id


async def remove_quote(server_id: str, quote_id: int) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?",
        (server_id, str(quote_id)),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    quote = dict(row)
    await db.execute(
        "DELETE FROM quotes WHERE server_id = ? AND quote_id = ?",
        (server_id, str(quote_id)),
    )
    await db.commit()
    return quote


async def edit_quote(
    server_id: str,
    quote_id: int,
    quote_text: str | None = None,
    author_user_id: str | None = None,
    author_name: str | None = None,
) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?",
        (server_id, str(quote_id)),
    )
    row = await cursor.fetchone()
    if not row:
        return None

    updates = []
    params = []
    if quote_text is not None:
        updates.append("quote_text = ?")
        params.append(quote_text)
    if author_user_id is not None:
        updates.append("author_user_id = ?")
        params.append(author_user_id)
        updates.append("author_name = ?")
        params.append(None)
    elif author_name is not None:
        updates.append("author_name = ?")
        params.append(author_name)
        updates.append("author_user_id = ?")
        params.append(None)

    if not updates:
        return dict(row)

    params.extend([server_id, str(quote_id)])
    await db.execute(
        "UPDATE quotes SET %s WHERE server_id = ? AND quote_id = ?" % ", ".join(updates),
        params,
    )
    await db.commit()

    cursor = await db.execute(
        "SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?",
        (server_id, str(quote_id)),
    )
    return dict(await cursor.fetchone())


async def get_quote(server_id: str, quote_id: int) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?",
        (server_id, str(quote_id)),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_random_quote(
    server_id: str,
    author_user_id: str | None = None,
    author_name: str | None = None,
) -> dict | None:
    db = await get_db()
    query = "SELECT * FROM quotes WHERE server_id = ?"
    params: list = [server_id]

    if author_user_id:
        query += " AND author_user_id = ?"
        params.append(author_user_id)
    elif author_name:
        query += " AND author_name = ?"
        params.append(author_name)

    query += " ORDER BY RANDOM() LIMIT 1"
    cursor = await db.execute(query, params)
    row = await cursor.fetchone()
    return dict(row) if row else None


async def count_quotes_by_author(
    server_id: str,
    author_user_id: str | None = None,
    author_name: str | None = None,
) -> int:
    db = await get_db()
    query = "SELECT COUNT(*) FROM quotes WHERE server_id = ?"
    params: list = [server_id]

    if author_user_id:
        query += " AND author_user_id = ?"
        params.append(author_user_id)
    elif author_name:
        query += " AND author_name = ?"
        params.append(author_name)

    cursor = await db.execute(query, params)
    return (await cursor.fetchone())[0]


async def get_quotes_by_author_page(
    server_id: str,
    page: int,
    author_user_id: str | None = None,
    author_name: str | None = None,
) -> list[dict]:
    db = await get_db()
    query = "SELECT * FROM quotes WHERE server_id = ?"
    params: list = [server_id]

    if author_user_id:
        query += " AND author_user_id = ?"
        params.append(author_user_id)
    elif author_name:
        query += " AND author_name = ?"
        params.append(author_name)

    query += " ORDER BY quote_id ASC LIMIT ? OFFSET ?"
    params.extend([QUOTES_PER_PAGE, page * QUOTES_PER_PAGE])
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def count_search_quotes(server_id: str, keyword: str) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM quotes WHERE server_id = ? AND quote_text LIKE ?",
        (server_id, "%%%s%%" % keyword),
    )
    return (await cursor.fetchone())[0]


async def search_quotes_page(
    server_id: str, keyword: str, page: int
) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM quotes WHERE server_id = ? AND quote_text LIKE ? ORDER BY quote_id ASC LIMIT ? OFFSET ?",
        (server_id, "%%%s%%" % keyword, QUOTES_PER_PAGE, page * QUOTES_PER_PAGE),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
