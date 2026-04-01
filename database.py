import os
import aiosqlite
import datetime

DB_FILE = os.getenv("DB_PATH", "quotes.db")
QUOTES_PER_PAGE = 5

# 1. SHARED CONNECTION: Persistent connection state
_db = None

async def get_db():
    """Returns the shared database connection, initializing it if necessary."""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_FILE)
    return _db

# Helper functions to replace the global row_factory manipulation,
# ensuring thread-safety and preventing tuple vs dict conflicts across queries.
def to_dict(cursor, row):
    if not row: return None
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

def to_dict_list(cursor, rows):
    return [to_dict(cursor, row) for row in rows]

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
        CREATE TABLE IF NOT EXISTS favorites (
            server_id TEXT NOT NULL,
            quote_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            PRIMARY KEY (server_id, quote_id, user_id)
        )
    """)
    
    async with db.execute("PRAGMA table_info(quotes)") as cursor:
        columns = [row[1] for row in await cursor.fetchall()]
        if "image_url" not in columns:
            await db.execute("ALTER TABLE quotes ADD COLUMN image_url TEXT")
        if "original_message_id" not in columns:
            await db.execute("ALTER TABLE quotes ADD COLUMN original_message_id TEXT")
            
    await db.execute("CREATE INDEX IF NOT EXISTS idx_server_quote ON quotes(server_id, quote_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_server_author_name ON quotes(server_id, author_name)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_server_message ON quotes(server_id, original_message_id)")
    
    await db.commit()

async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None

# 2. ATOMIC INSERT: Combines ID generation and insertion into one transaction
async def add_quote(server_id: str, quote_text: str, added_by_user_id: str, author_user_id: str = None, author_name: str = None, image_url: str = None, original_message_id: str = None) -> int:
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    db = await get_db()
    
    await db.execute("BEGIN IMMEDIATE")
    try:
        async with db.execute("SELECT MAX(quote_id) FROM quotes WHERE server_id = ?", (server_id,)) as cursor:
            row = await cursor.fetchone()
            quote_id = (row[0] or 0) + 1
            
        await db.execute("""
            INSERT INTO quotes (server_id, quote_id, quote_text, author_user_id, author_name, added_by_user_id, timestamp, image_url, original_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (server_id, quote_id, quote_text, author_user_id, author_name, added_by_user_id, timestamp, image_url, original_message_id))
        
        await db.commit()
        return quote_id
    except Exception:
        await db.rollback()
        raise

async def remove_quote(server_id: str, quote_id: int):
    db = await get_db()
    await db.execute("DELETE FROM quotes WHERE server_id = ? AND quote_id = ?", (server_id, quote_id))
    await db.execute("DELETE FROM favorites WHERE server_id = ? AND quote_id = ?", (server_id, quote_id))
    await db.commit()

async def edit_quote(server_id: str, quote_id: int, quote_text: str = None, author_user_id: str = None, author_name: str = None, image_url: str = None) -> dict:
    db = await get_db()
    
    async with db.execute("SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?", (server_id, quote_id)) as cursor:
        quote = to_dict(cursor, await cursor.fetchone())
        
    if not quote:
        return None
        
    new_text = quote_text if quote_text is not None else quote['quote_text']
    new_image_url = image_url if image_url is not None else quote.get('image_url')
    new_author_user_id = author_user_id if author_user_id is not None else quote['author_user_id']
    new_author_name = author_name if author_name is not None else quote['author_name']

    await db.execute("""
        UPDATE quotes 
        SET quote_text = ?, author_user_id = ?, author_name = ?, image_url = ?
        WHERE server_id = ? AND quote_id = ?
    """, (new_text, new_author_user_id, new_author_name, new_image_url, server_id, quote_id))
    await db.commit()
    
    async with db.execute("SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?", (server_id, quote_id)) as cursor:
        return to_dict(cursor, await cursor.fetchone())

async def get_quote(server_id: str, quote_id: int) -> dict:
    db = await get_db()
    async with db.execute("SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?", (server_id, quote_id)) as cursor:
        return to_dict(cursor, await cursor.fetchone())

async def check_quote_by_message_id(server_id: str, message_id: str) -> bool:
    db = await get_db()
    async with db.execute("SELECT 1 FROM quotes WHERE server_id = ? AND original_message_id = ?", (server_id, message_id)) as cursor:
        return await cursor.fetchone() is not None

async def get_random_quote(server_id: str, author_user_id: str = None, author_name: str = None) -> dict:
    db = await get_db()
    query = "SELECT * FROM quotes WHERE server_id = ?"
    params = [server_id]
    
    if author_user_id:
        query += " AND author_user_id = ?"
        params.append(author_user_id)
    elif author_name:
        query += " AND author_name LIKE ?"
        params.append(f"%{author_name}%")
        
    query += " ORDER BY RANDOM() LIMIT 1"
    
    async with db.execute(query, params) as cursor:
        return to_dict(cursor, await cursor.fetchone())

async def count_quotes_by_author(server_id: str, author_user_id: str = None, author_name: str = None) -> int:
    db = await get_db()
    query = "SELECT COUNT(*) FROM quotes WHERE server_id = ?"
    params = [server_id]
    
    if author_user_id:
        query += " AND author_user_id = ?"
        params.append(author_user_id)
    elif author_name:
        query += " AND author_name LIKE ?"
        params.append(f"%{author_name}%")
        
    async with db.execute(query, params) as cursor:
        return (await cursor.fetchone())[0]

async def get_quotes_by_author_page(server_id: str, page: int, author_user_id: str = None, author_name: str = None) -> list:
    db = await get_db()
    query = "SELECT * FROM quotes WHERE server_id = ?"
    params = [server_id]
    
    if author_user_id:
        query += " AND author_user_id = ?"
        params.append(author_user_id)
    elif author_name:
        query += " AND author_name LIKE ?"
        params.append(f"%{author_name}%")
        
    query += f" ORDER BY quote_id DESC LIMIT {QUOTES_PER_PAGE} OFFSET {page * QUOTES_PER_PAGE}"
    
    async with db.execute(query, params) as cursor:
        return to_dict_list(cursor, await cursor.fetchall())

async def count_search_quotes(server_id: str, keyword: str) -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM quotes WHERE server_id = ? AND quote_text LIKE ?", (server_id, f"%{keyword}%")) as cursor:
        return (await cursor.fetchone())[0]

async def search_quotes_page(server_id: str, keyword: str, page: int) -> list:
    db = await get_db()
    async with db.execute(f"SELECT * FROM quotes WHERE server_id = ? AND quote_text LIKE ? ORDER BY quote_id DESC LIMIT {QUOTES_PER_PAGE} OFFSET {page * QUOTES_PER_PAGE}",(server_id, f"%{keyword}%")) as cursor:
        return to_dict_list(cursor, await cursor.fetchall())

async def get_unique_author_names(server_id: str, current: str) -> list[str]:
    db = await get_db()
    async with db.execute("SELECT DISTINCT author_name FROM quotes WHERE server_id = ? AND author_name LIKE ? AND author_name IS NOT NULL LIMIT 25", (server_id, f"%{current}%")) as cursor:
        return [row[0] for row in await cursor.fetchall()]

async def get_global_stats(server_id: str) -> dict:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM quotes WHERE server_id = ?", (server_id,)) as cursor:
        total = (await cursor.fetchone())[0]
    async with db.execute("SELECT COUNT(DISTINCT added_by_user_id) FROM quotes WHERE server_id = ?", (server_id,)) as cursor:
        submitters = (await cursor.fetchone())[0]
    async with db.execute("SELECT COUNT(DISTINCT COALESCE(author_user_id, author_name)) FROM quotes WHERE server_id = ?", (server_id,)) as cursor:
        authors = (await cursor.fetchone())[0]
    return {"total_quotes": total, "unique_submitters": submitters, "unique_authors": authors}

async def get_top_authors(server_id: str, limit: int = 5) -> list:
    db = await get_db()
    query = """
        SELECT author_user_id, author_name, COUNT(*) as count 
        FROM quotes 
        WHERE server_id = ? AND (author_user_id IS NOT NULL OR author_name IS NOT NULL)
        GROUP BY COALESCE(author_user_id, author_name)
        ORDER BY count DESC 
        LIMIT ?
    """
    async with db.execute(query, (server_id, limit)) as cursor:
        return to_dict_list(cursor, await cursor.fetchall())

async def get_top_submitters(server_id: str, limit: int = 5) -> list:
    db = await get_db()
    query = """
        SELECT added_by_user_id, COUNT(*) as count 
        FROM quotes 
        WHERE server_id = ? 
        GROUP BY added_by_user_id 
        ORDER BY count DESC 
        LIMIT ?
    """
    async with db.execute(query, (server_id, limit)) as cursor:
        return to_dict_list(cursor, await cursor.fetchall())

async def get_user_stats(server_id: str, user_id: str) -> dict:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM quotes WHERE server_id = ? AND author_user_id = ?", (server_id, user_id)) as cursor:
        quoted_count = (await cursor.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM quotes WHERE server_id = ? AND added_by_user_id = ?", (server_id, user_id)) as cursor:
        submitted_count = (await cursor.fetchone())[0]

    author_rank_query = """
        SELECT COUNT(*) + 1 FROM (
            SELECT COUNT(*) as c FROM quotes WHERE server_id = ? AND author_user_id IS NOT NULL GROUP BY author_user_id
        ) WHERE c > ?
    """
    async with db.execute(author_rank_query, (server_id, quoted_count)) as cursor:
        author_rank = (await cursor.fetchone())[0] if quoted_count > 0 else 0

    submitter_rank_query = """
        SELECT COUNT(*) + 1 FROM (
            SELECT COUNT(*) as c FROM quotes WHERE server_id = ? GROUP BY added_by_user_id
        ) WHERE c > ?
    """
    async with db.execute(submitter_rank_query, (server_id, submitted_count)) as cursor:
        submitter_rank = (await cursor.fetchone())[0] if submitted_count > 0 else 0

    return {
        "quoted_count": quoted_count,
        "submitted_count": submitted_count,
        "author_rank": author_rank,
        "submitter_rank": submitter_rank
    }

async def add_favorite(server_id: str, quote_id: int, user_id: str):
    db = await get_db()
    await db.execute("INSERT OR IGNORE INTO favorites (server_id, quote_id, user_id) VALUES (?, ?, ?)", (server_id, quote_id, user_id))
    await db.commit()

async def remove_favorite(server_id: str, quote_id: int, user_id: str):
    db = await get_db()
    await db.execute("DELETE FROM favorites WHERE server_id = ? AND quote_id = ? AND user_id = ?", (server_id, quote_id, user_id))
    await db.commit()

async def count_user_favorites(server_id: str, user_id: str) -> int:
    db = await get_db()
    async with db.execute("SELECT COUNT(*) FROM favorites WHERE server_id = ? AND user_id = ?", (server_id, user_id)) as cursor:
        return (await cursor.fetchone())[0]

async def get_user_favorites_page(server_id: str, user_id: str, page: int) -> list:
    db = await get_db()
    query = """
        SELECT q.* FROM quotes q
        JOIN favorites f ON q.server_id = f.server_id AND q.quote_id = f.quote_id
        WHERE f.server_id = ? AND f.user_id = ?
        ORDER BY f.quote_id DESC LIMIT ? OFFSET ?
    """
    async with db.execute(query, (server_id, user_id, QUOTES_PER_PAGE, page * QUOTES_PER_PAGE)) as cursor:
        return to_dict_list(cursor, await cursor.fetchall())

async def get_top_favorited_quotes(server_id: str, limit: int = 3) -> list:
    db = await get_db()
    query = """
        SELECT q.quote_id, q.quote_text, q.author_user_id, q.author_name, COUNT(f.user_id) as fav_count
        FROM quotes q
        JOIN favorites f ON q.server_id = f.server_id AND q.quote_id = f.quote_id
        WHERE q.server_id = ?
        GROUP BY q.quote_id
        ORDER BY fav_count DESC, q.quote_id DESC
        LIMIT ?
    """
    async with db.execute(query, (server_id, limit)) as cursor:
        return to_dict_list(cursor, await cursor.fetchall())

# 3. PROPER LAYERING: Moved /qswap SQL logic out of bot.py into the database layer
async def swap_quotes(server_id: str, id1: int, id2: int) -> bool:
    db = await get_db()
    await db.execute("BEGIN IMMEDIATE")
    try:
        await db.execute("UPDATE quotes SET quote_id = 999999 WHERE server_id = ? AND quote_id = ?", (server_id, id1))
        await db.execute("UPDATE quotes SET quote_id = ? WHERE server_id = ? AND quote_id = ?", (id1, server_id, id2))
        await db.execute("UPDATE quotes SET quote_id = ? WHERE server_id = ? AND quote_id = 999999", (id2, server_id))
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        return False