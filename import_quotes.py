import json
import re
import os
import sqlite3
from collections import defaultdict

INPUT_FILE = "scraped_quotes.json"
DUPES_FILE = "duplicate_review.txt"
CLEAN_FILE = "cleaned_quotes.json"
DB_PATH = os.getenv("DB_PATH", "quotes.db")

# ============================================================
# CONFIGURE THESE BEFORE RUNNING
# ============================================================
SERVER_ID = ""  # Your Discord server/guild ID (required)
# ============================================================


def clean_author(author_str):
    """Strip emoji shortcodes like :speaking_head: from author names."""
    if not author_str:
        return None
    # Remove Discord emoji shortcodes like :speaking_head:
    cleaned = re.sub(r":[a-zA-Z0-9_]+:", "", author_str).strip()
    # Remove leftover emoji characters
    cleaned = re.sub(r"^[\U0001f000-\U0001ffff\u2600-\u27ff\ufe0f]+\s*", "", cleaned).strip()
    return cleaned or None


def find_duplicates(quotes):
    """Find potential duplicate quotes by normalized text similarity."""
    dupes = []
    seen = defaultdict(list)

    for q in quotes:
        text = (q.get("quote_text") or "").strip().lower()
        # Normalize: remove extra whitespace, punctuation variations
        normalized = re.sub(r"\s+", " ", text)
        seen[normalized].append(q)

    for normalized, group in seen.items():
        if len(group) > 1:
            dupes.append(group)

    return dupes


def main():
    if not SERVER_ID:
        print("ERROR: Set SERVER_ID in import_quotes.py before running.")
        print("To find your server ID: Discord Settings > Advanced > Developer Mode")
        print("Then right-click your server name > Copy Server ID")
        return

    # Load scraped quotes
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        quotes = json.load(f)

    print("Loaded %d quotes from %s" % (len(quotes), INPUT_FILE))

    # ---- Step 1: Clean the data ----
    cleaned = []
    skipped = []

    for q in quotes:
        text = (q.get("quote_text") or "").strip()
        author = clean_author(q.get("author"))
        added_by = (q.get("added_by") or "Unknown").strip()
        timestamp = (q.get("timestamp") or q.get("date") or "Unknown").strip()
        old_id = q.get("old_id")

        # Skip entries with no quote text
        if not text or text == "(could not parse)":
            skipped.append({"old_id": old_id, "reason": "no quote text", "raw": q})
            continue

        cleaned.append({
            "old_id": old_id,
            "quote_text": text,
            "author_name": author,
            "added_by": added_by,
            "timestamp": timestamp,
        })

    print("Cleaned: %d valid, %d skipped (no text)" % (len(cleaned), len(skipped)))

    # ---- Step 2: Find duplicates ----
    dupes = find_duplicates(cleaned)

    with open(DUPES_FILE, "w", encoding="utf-8") as f:
        if dupes:
            f.write("POTENTIAL DUPLICATES - REVIEW BEFORE IMPORTING\n")
            f.write("=" * 60 + "\n")
            f.write("Edit cleaned_quotes.json to remove any unwanted duplicates.\n")
            f.write("Then re-run this script.\n")
            f.write("=" * 60 + "\n\n")

            for i, group in enumerate(dupes, 1):
                f.write("Duplicate Group #%d (%d copies):\n" % (i, len(group)))
                for q in group:
                    f.write("  Old ID: %s\n" % q["old_id"])
                    f.write("  Quote:  %s\n" % q["quote_text"][:100])
                    f.write("  Author: %s\n" % q["author_name"])
                    f.write("  Added:  %s\n" % q["added_by"])
                    f.write("  Date:   %s\n" % q["timestamp"])
                    f.write("  ---\n")
                f.write("\n")

            print("\n*** FOUND %d DUPLICATE GROUPS ***" % len(dupes))
            print("Review: %s" % DUPES_FILE)
        else:
            f.write("No duplicates found. All quotes are unique.\n")
            print("No duplicates found.")

    # ---- Step 3: Write cleaned JSON for review ----
    with open(CLEAN_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

    print("Cleaned data written to: %s" % CLEAN_FILE)

    if skipped:
        print("\nSkipped quotes (no text):")
        for s in skipped:
            print("  Old ID %s: %s" % (s["old_id"], s["reason"]))

    # ---- Step 4: Ask to proceed with import ----
    print("\n" + "=" * 60)
    print("REVIEW THE FILES ABOVE BEFORE IMPORTING:")
    print("  1. %s - check/remove duplicates" % DUPES_FILE)
    print("  2. %s - edit any quotes, then re-run" % CLEAN_FILE)
    print("=" * 60)

    answer = input("\nImport %d quotes into %s now? (yes/no): " % (len(cleaned), DB_PATH))
    if answer.strip().lower() not in ("yes", "y"):
        print("Aborted. Edit %s and run again when ready." % CLEAN_FILE)
        return

    # ---- Step 5: Import into database ----
    # Re-read cleaned file in case user edited it
    with open(CLEAN_FILE, "r", encoding="utf-8") as f:
        to_import = json.load(f)

    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()

    # Create table if it doesn't exist
    cursor.execute("""
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

    # Get current max quote_id for this server
    cursor.execute(
        "SELECT MAX(quote_id) FROM quotes WHERE server_id = ?", (SERVER_ID,)
    )
    row = cursor.fetchone()
    next_id = (row[0] or 0) + 1

    imported = 0
    for q in to_import:
        cursor.execute(
            """INSERT INTO quotes
               (server_id, quote_id, quote_text, author_user_id, author_name,
                added_by_user_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                SERVER_ID,
                next_id,
                q["quote_text"],
                None,  # author_user_id - old bot only had text names
                q["author_name"],
                q["added_by"],  # stored as text since we don't have Discord IDs
                q["timestamp"],
            ),
        )
        next_id += 1
        imported += 1

    db.commit()
    db.close()

    print("\nImported %d quotes into %s" % (imported, DB_PATH))
    print("Quote IDs: 1 through %d" % (next_id - 1))
    print("\nUpload %s to your Railway volume at /data/quotes.db" % DB_PATH)


if __name__ == "__main__":
    main()
