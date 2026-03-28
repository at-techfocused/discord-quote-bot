import os
import re
import json
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
OUTPUT_FILE = "scraped_quotes.json"
READABLE_FILE = "scraped_quotes.txt"

HEADERS = {"Authorization": "Bot " + (TOKEN or "")}
API_BASE = "https://discord.com/api/v10"


async def api_get(session, url, params=None):
    while True:
        async with session.get(url, headers=HEADERS, params=params) as resp:
            if resp.status == 429:
                data = await resp.json()
                wait = data.get("retry_after", 1.0)
                print("    Rate limited, waiting %.1fs..." % wait)
                await asyncio.sleep(wait)
                continue
            if resp.status != 200:
                text = await resp.text()
                print("    API error %d: %s" % (resp.status, text[:200]))
                return None
            return await resp.json()


async def search_guild_messages(session, guild_id, query):
    """Search guild and return only the matched (hit) messages."""
    hit_messages = []
    offset = 0

    while True:
        params = {"content": query, "offset": offset}
        url = "%s/guilds/%s/messages/search" % (API_BASE, guild_id)
        data = await api_get(session, url, params)

        if not data or "messages" not in data:
            break

        total = data.get("total_results", 0)
        batch = data["messages"]

        if not batch:
            break

        # Each item in batch is a list of messages (hit + context).
        # The actual matched message has "hit": true
        for msg_group in batch:
            for msg in msg_group:
                if msg.get("hit"):
                    hit_messages.append(msg)

        offset += len(batch)
        print("    Fetched %d / %d results..." % (min(offset, total), total))

        if offset >= total:
            break

    return hit_messages


def dump_message(msg, label=""):
    """Print full raw message data for debugging."""
    author = msg.get("author", {})
    print("  %s" % label)
    print("    From: %s (id: %s, discriminator: %s)" % (
        author.get("username", "?"),
        author.get("id", "?"),
        author.get("discriminator", "?"),
    ))
    print("    Content: %r" % (msg.get("content") or ""))
    print("    Timestamp: %s" % msg.get("timestamp"))
    print("    Embeds: %d" % len(msg.get("embeds", [])))
    for i, emb in enumerate(msg.get("embeds", [])):
        print("    --- Embed #%d ---" % i)
        for key in ["title", "description", "url", "color", "type"]:
            val = emb.get(key)
            if val is not None:
                print("      %s: %r" % (key, str(val)[:300]))
        footer = emb.get("footer")
        if footer:
            print("      footer.text: %r" % footer.get("text"))
            print("      footer.icon_url: %r" % footer.get("icon_url"))
        emb_author = emb.get("author")
        if emb_author:
            print("      author.name: %r" % emb_author.get("name"))
        for f in emb.get("fields", []):
            print("      field: %r = %r" % (f.get("name"), f.get("value")))
    print("")


def extract_all_text(msg):
    """Get all searchable text from a message (content + all embed text)."""
    parts = [msg.get("content") or ""]
    for emb in msg.get("embeds", []):
        parts.append(emb.get("title") or "")
        parts.append(emb.get("description") or "")
        footer = emb.get("footer") or {}
        parts.append(footer.get("text") or "")
        emb_author = emb.get("author") or {}
        parts.append(emb_author.get("name") or "")
        for f in emb.get("fields", []):
            parts.append(f.get("name") or "")
            parts.append(f.get("value") or "")
    return "\n".join(parts)


def parse_quote_from_message(msg):
    """Try to parse quote data from a message. Very flexible matching."""
    all_text = extract_all_text(msg)
    embeds = msg.get("embeds", [])
    timestamp = msg.get("timestamp")
    channel_id = msg.get("channel_id")
    msg_id = msg.get("id")

    # Try to find a quote ID with various patterns
    old_id = None
    for pattern in [
        r"QuoteID:\s*(\d+)",
        r"Quote\s*ID:\s*(\d+)",
        r"Quote\s*#\s*(\d+)",
        r"\bID\s+(\d+)",
        r"#(\d+)",
    ]:
        match = re.search(pattern, all_text, re.IGNORECASE)
        if match:
            old_id = int(match.group(1))
            break

    # Extract quote text, author, and added_by from embed description.
    # Actual format from the old bot (embed description):
    #
    #   > Quote text here
    #   >
    #   > - 🗣 Author
    #
    #   Added by Username#1234
    #   ✍ at 2022-05-07 12:07:30.023561 🕑 !
    #   QuoteID: 359 ✏
    #
    # The quote text and author are inside a blockquote (> prefixed lines).
    # Metadata (Added by, timestamp, QuoteID) is outside the blockquote.
    #
    quote_text = None
    quote_author = None
    added_by = None
    quote_timestamp = None

    for emb in embeds:
        desc = emb.get("description") or ""
        if not desc:
            continue

        # Debug: always print raw description for first 5 IDs
        if old_id and old_id <= 5:
            print("  [RAW DESC for ID %d]:" % old_id)
            for dl in desc.split("\n"):
                print("    | %r" % dl)
            print("")

        # Separate blockquoted lines (quote content) from non-blockquoted (metadata)
        blockquote_lines = []
        metadata_lines = []

        for line in desc.split("\n"):
            if line.startswith("> ") or line == ">":
                # Strip the "> " prefix
                blockquote_lines.append(line[2:] if line.startswith("> ") else "")
            else:
                metadata_lines.append(line)

        # If no blockquote found, fall back to splitting on "Added by"
        if not blockquote_lines:
            parts = re.split(r"(?=Added by\s)", desc, maxsplit=1, flags=re.IGNORECASE)
            blockquote_lines = parts[0].strip().split("\n")
            if len(parts) > 1:
                metadata_lines = parts[1].strip().split("\n")

        # Parse the blockquote: quote text + author
        q_lines = []
        for line in blockquote_lines:
            stripped = line.strip()
            if not stripped:
                continue
            # Author line starts with - or – or —
            if re.match(r"^[-\u2013\u2014~]\s+", stripped):
                quote_author = re.sub(r"^[-\u2013\u2014~]\s+", "", stripped).strip()
            else:
                q_lines.append(stripped)

        if q_lines:
            quote_text = "\n".join(q_lines).strip()
            # Remove surrounding quote marks
            quote_text = re.sub(r'^["""\u201c]|["""\u201d]$', "", quote_text).strip()

        # Parse metadata lines for Added by, timestamp, QuoteID
        metadata_text = "\n".join(metadata_lines)

        m = re.search(r"Added by\s+(.+?)(?:\n|$)", metadata_text, re.IGNORECASE)
        if m:
            added_by = m.group(1).strip()

        m = re.search(r"at\s+([\d-]+\s+[\d:.]+)", metadata_text)
        if m:
            quote_timestamp = m.group(1).strip()

        if quote_text or quote_author:
            break

    # Also check footer (some versions may use footer)
    if not added_by:
        for emb in embeds:
            footer_text = (emb.get("footer") or {}).get("text") or ""
            if footer_text:
                m = re.search(r"Added by\s+(.+?)(?:\n|$)", footer_text)
                if m:
                    added_by = m.group(1).strip()

    if not quote_text and not old_id:
        return None

    return {
        "old_id": old_id,
        "quote_text": quote_text or "(could not parse)",
        "author": quote_author,
        "added_by": added_by,
        "timestamp": quote_timestamp or timestamp,
        "channel_id": channel_id,
        "message_id": msg_id,
    }


async def main():
    if not TOKEN:
        print("Error: Set DISCORD_BOT_TOKEN in .env")
        return

    print("Starting quote scraper...\n")

    async with aiohttp.ClientSession() as session:
        guilds_data = await api_get(session, API_BASE + "/users/@me/guilds")
        if not guilds_data:
            print("Failed to fetch guilds")
            return

        all_quotes = []

        for guild in guilds_data:
            guild_id = guild["id"]
            guild_name = guild["name"]
            print("Server: %s (ID: %s)" % (guild_name, guild_id))

            # Search with multiple queries to cast a wide net
            search_terms = ["QuoteID", "Successfully added new quote"]
            seen_msg_ids = set()

            for term in search_terms:
                print('  Searching for "%s"...' % term)
                messages = await search_guild_messages(session, guild_id, term)
                print("  Found %d hit messages" % len(messages))

                # Debug: dump first 5 unique messages per search term
                debug_shown = 0
                for msg in messages:
                    mid = msg.get("id")
                    if mid in seen_msg_ids:
                        continue
                    seen_msg_ids.add(mid)

                    if debug_shown < 5:
                        debug_shown += 1
                        dump_message(msg, "[DEBUG #%d for '%s']" % (debug_shown, term))

                    parsed = parse_quote_from_message(msg)
                    if parsed:
                        all_quotes.append(parsed)

            print("  Total parsed so far: %d\n" % len(all_quotes))

        # Sort by old ID
        all_quotes.sort(key=lambda q: q.get("old_id") or 0)

        # Deduplicate by ID or quote text
        seen = set()
        unique_quotes = []
        for q in all_quotes:
            key = q["old_id"] if q["old_id"] else q["quote_text"]
            if key not in seen:
                seen.add(key)
                unique_quotes.append(q)

        # Write JSON
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(unique_quotes, f, indent=2, ensure_ascii=False)

        # Write readable text
        with open(READABLE_FILE, "w", encoding="utf-8") as f:
            f.write("SCRAPED QUOTES (%d total)\n" % len(unique_quotes))
            f.write("=" * 60 + "\n\n")
            for q in unique_quotes:
                f.write("ID: %s\n" % (q["old_id"] or "?"))
                f.write("Quote: %s\n" % q["quote_text"])
                f.write("Author: %s\n" % (q["author"] or "Unknown"))
                f.write("Added by: %s\n" % (q["added_by"] or "Unknown"))
                f.write("Date: %s\n" % (q["timestamp"] or "Unknown"))
                f.write("-" * 60 + "\n")

        print("Done! Found %d unique quotes." % len(unique_quotes))
        print("  JSON:     %s" % OUTPUT_FILE)
        print("  Readable: %s" % READABLE_FILE)


if __name__ == "__main__":
    asyncio.run(main())
