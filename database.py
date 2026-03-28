import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "quotes.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
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


async def get_next_quote_id(db, server_id: str) -> int:
    cursor = await db.execute(
        "SELECT MAX(quote_id) FROM quotes WHERE server_id = ?",
        (server_id,),
    )
    row = await cursor.fetchone()
    return (row[0] or 0) + 1


async def add_quote(
    server_id: str,
    quote_text: str,
    added_by_user_id: str,
    author_user_id: str | None = None,
    author_name: str | None = None,
) -> int:
    from datetime import datetime, timezone

    async with aiosqlite.connect(DB_PATH) as db:
        quote_id = await get_next_quote_id(db, server_id)
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
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    clear_author_user: bool = False,
    clear_author_name: bool = False,
) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?",
            (server_id, str(quote_id)),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        quote = dict(row)

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
            return quote

        params.extend([server_id, str(quote_id)])
        await db.execute(
            f"UPDATE quotes SET {', '.join(updates)} WHERE server_id = ? AND quote_id = ?",
            params,
        )
        await db.commit()

        cursor = await db.execute(
            "SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?",
            (server_id, str(quote_id)),
        )
        return dict(await cursor.fetchone())


async def get_quote(server_id: str, quote_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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


async def get_quotes_by_author(
    server_id: str,
    author_user_id: str | None = None,
    author_name: str | None = None,
) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM quotes WHERE server_id = ?"
        params: list = [server_id]

        if author_user_id:
            query += " AND author_user_id = ?"
            params.append(author_user_id)
        elif author_name:
            query += " AND author_name = ?"
            params.append(author_name)

        query += " ORDER BY quote_id ASC"
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def search_quotes(server_id: str, keyword: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM quotes WHERE server_id = ? AND quote_text LIKE ? ORDER BY quote_id ASC",
            (server_id, f"%{keyword}%"),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
