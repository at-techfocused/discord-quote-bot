import os
import aiosqlite
import datetime

# Automatically use Railway's DB_PATH variable if it exists, otherwise default to local quotes.db
DB_FILE = os.getenv("DB_PATH", "quotes.db")
QUOTES_PER_PAGE = 5

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
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
        
        # Automatic Migrations for new columns
        async with db.execute("PRAGMA table_info(quotes)") as cursor:
            columns = [row[1] for row in await cursor.fetchall()]
            if "image_url" not in columns:
                await db.execute("ALTER TABLE quotes ADD COLUMN image_url TEXT")
            if "original_message_id" not in columns:
                await db.execute("ALTER TABLE quotes ADD COLUMN original_message_id TEXT")
                
        # Optimization: Create indices for faster lookups
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_quote ON quotes(server_id, quote_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_author_name ON quotes(server_id, author_name)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_server_message ON quotes(server_id, original_message_id)")
        
        await db.commit()

async def close_db():
    pass # Reserved for future connection pooling cleanup

async def get_next_quote_id(server_id: str) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT MAX(quote_id) FROM quotes WHERE server_id = ?", (server_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return (row[0] or 0) + 1

async def add_quote(server_id: str, quote_text: str, added_by_user_id: str, author_user_id: str = None, author_name: str = None, image_url: str = None, original_message_id: str = None) -> int:
    quote_id = await get_next_quote_id(server_id)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO quotes (server_id, quote_id, quote_text, author_user_id, author_name, added_by_user_id, timestamp, image_url, original_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (server_id, quote_id, quote_text, author_user_id, author_name, added_by_user_id, timestamp, image_url, original_message_id))
        await db.commit()
    return quote_id

async def remove_quote(server_id: str, quote_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM quotes WHERE server_id = ? AND quote_id = ?", (server_id, quote_id))
        await db.commit()

async def edit_quote(server_id: str, quote_id: int, quote_text: str = None, author_user_id: str = None, author_name: str = None, image_url: str = None) -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = dict_factory
        
        async with db.execute("SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?", (server_id, quote_id)) as cursor:
            quote = await cursor.fetchone()
            
        if not quote:
            return None
            
        new_text = quote_text if quote_text is not None else quote['quote_text']
        new_image_url = image_url if image_url is not None else quote.get('image_url')
        
        if author_user_id is not None or author_name is not None:
            new_author_user_id = author_user_id
            new_author_name = author_name
        else:
            new_author_user_id = quote['author_user_id']
            new_author_name = quote['author_name']

        await db.execute("""
            UPDATE quotes 
            SET quote_text = ?, author_user_id = ?, author_name = ?, image_url = ?
            WHERE server_id = ? AND quote_id = ?
        """, (new_text, new_author_user_id, new_author_name, new_image_url, server_id, quote_id))
        await db.commit()
        
        async with db.execute("SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?", (server_id, quote_id)) as cursor:
            return await cursor.fetchone()

async def get_quote(server_id: str, quote_id: int) -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = dict_factory
        async with db.execute("SELECT * FROM quotes WHERE server_id = ? AND quote_id = ?", (server_id, quote_id)) as cursor:
            return await cursor.fetchone()

async def check_quote_by_message_id(server_id: str, message_id: str) -> bool:
    """Checks if a Discord message has already been saved as a quote to prevent duplicates."""
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT 1 FROM quotes WHERE server_id = ? AND original_message_id = ?", 
            (server_id, message_id)
        ) as cursor:
            return await cursor.fetchone() is not None

async def get_random_quote(server_id: str, author_user_id: str = None, author_name: str = None) -> dict:
    query = "SELECT * FROM quotes WHERE server_id = ?"
    params = [server_id]
    
    if author_user_id:
        query += " AND author_user_id = ?"
        params.append(author_user_id)
    elif author_name:
        query += " AND author_name LIKE ?"
        params.append(f"%{author_name}%")
        
    query += " ORDER BY RANDOM() LIMIT 1"
    
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = dict_factory
        async with db.execute(query, params) as cursor:
            return await cursor.fetchone()

async def count_quotes_by_author(server_id: str, author_user_id: str = None, author_name: str = None) -> int:
    query = "SELECT COUNT(*) FROM quotes WHERE server_id = ?"
    params = [server_id]
    
    if author_user_id:
        query += " AND author_user_id = ?"
        params.append(author_user_id)
    elif author_name:
        query += " AND author_name LIKE ?"
        params.append(f"%{author_name}%")
        
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row[0]

async def get_quotes_by_author_page(server_id: str, page: int, author_user_id: str = None, author_name: str = None) -> list:
    query = "SELECT * FROM quotes WHERE server_id = ?"
    params = [server_id]
    
    if author_user_id:
        query += " AND author_user_id = ?"
        params.append(author_user_id)
    elif author_name:
        query += " AND author_name LIKE ?"
        params.append(f"%{author_name}%")
        
    query += f" ORDER BY quote_id DESC LIMIT {QUOTES_PER_PAGE} OFFSET {page * QUOTES_PER_PAGE}"
    
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = dict_factory
        async with db.execute(query, params) as cursor:
            return await cursor.fetchall()

async def count_search_quotes(server_id: str, keyword: str) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM quotes WHERE server_id = ? AND quote_text LIKE ?",
            (server_id, f"%{keyword}%")
        ) as cursor:
            row = await cursor.fetchone()
            return row[0]

async def search_quotes_page(server_id: str, keyword: str, page: int) -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = dict_factory
        async with db.execute(
            f"SELECT * FROM quotes WHERE server_id = ? AND quote_text LIKE ? ORDER BY quote_id DESC LIMIT {QUOTES_PER_PAGE} OFFSET {page * QUOTES_PER_PAGE}",
            (server_id, f"%{keyword}%")
        ) as cursor:
            return await cursor.fetchall()

async def get_unique_author_names(server_id: str, current: str) -> list[str]:
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT DISTINCT author_name FROM quotes WHERE server_id = ? AND author_name LIKE ? AND author_name IS NOT NULL LIMIT 25",
            (server_id, f"%{current}%")
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]