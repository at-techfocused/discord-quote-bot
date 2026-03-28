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
    """Make a GET request with rate limit handling."""
    while True:
        async with session.get(url, headers=HEADERS, params=params) as resp:
            if resp.status == 429:
                data = await resp.json()
                wait = data.get("retry_after", 1.0)
                print("  Rate limited, waiting %.1fs..." % wait)
                await asyncio.sleep(wait)
                continue
            if resp.status != 200:
                print("  API error %d: %s" % (resp.status, await resp.text()))
                return None
            return await resp.json()


async def search_guild(session, guild_id, query):
    """Search a guild for messages matching a query. Returns message objects."""
    messages = []
    offset = 0

    while True:
        params = {"content": query, "offset": offset}
        url = "%s/guilds/%s/messages/search" % (API_BASE, guild_id)
        data = await api_get(session, url, params)

        if not data or "messages" not in data:
            break

        total = data.get("total_results", 0)
        batch = data["messages"]  # list of lists (each is a message group)

        if not batch:
            break

        for msg_group in batch:
            for msg in msg_group:
                messages.append(msg)

        offset += len(batch)
        print("  Fetched %d / %d search results..." % (offset, total))

        if offset >= total:
            break

    return messages


def parse_message(msg):
    """Parse a message containing QuoteID pattern.

    Looks at both message content and embeds for quote data.
    """
    content = msg.get("content") or ""
    author = msg.get("author", {})
    embeds = msg.get("embeds", [])
    msg_id = msg.get("id")
    channel_id = msg.get("channel_id")
    timestamp = msg.get("timestamp")

    # Try to extract QuoteID from content or embeds
    quote_id_match = re.search(r"QuoteID:\s*(\d+)", content, re.IGNORECASE)
    if not quote_id_match:
        # Also check embed footers, descriptions, and fields
        for embed in embeds:
            for text in [
                embed.get("description") or "",
                (embed.get("footer") or {}).get("text") or "",
                embed.get("title") or "",
            ]:
                quote_id_match = re.search(r"QuoteID:\s*(\d+)", text, re.IGNORECASE)
                if quote_id_match:
                    break
            # Check fields too
            if not quote_id_match:
                for field in embed.get("fields", []):
                    for text in [field.get("name", ""), field.get("value", "")]:
                        quote_id_match = re.search(r"QuoteID:\s*(\d+)", text, re.IGNORECASE)
                        if quote_id_match:
                            break
                    if quote_id_match:
                        break
            if quote_id_match:
                break

    if not quote_id_match:
        return None

    old_id = int(quote_id_match.group(1))

    # Now try to extract quote text and author from embeds or content
    quote_text = None
    quote_author = None
    added_by = None

    # Check embeds first (the old bot likely used embeds)
    for embed in embeds:
        desc = embed.get("description") or ""
        footer_text = (embed.get("footer") or {}).get("text") or ""
        title = embed.get("title") or ""

        # Try to get quote text from description
        if desc and not quote_text:
            lines = desc.strip().split("\n")
            q_lines = []
            for line in lines:
                stripped = line.strip()
                if re.match(r"^[-\u2013\u2014]\s+", stripped):
                    quote_author = re.sub(r"^[-\u2013\u2014]\s+", "", stripped).strip()
                elif stripped and not re.match(r"QuoteID:", stripped, re.IGNORECASE):
                    q_lines.append(stripped)
            if q_lines:
                quote_text = " ".join(q_lines).strip()
                quote_text = re.sub(r'^["""\u201c]|["""\u201d]$', "", quote_text).strip()

        # Try footer for "Added by"
        if footer_text:
            added_match = re.search(r"Added by\s+(.+?)(?:\n|$)", footer_text)
            if added_match:
                added_by = added_match.group(1).strip()
            # Also check for ID in footer as backup
            if not old_id:
                id_match = re.search(r"ID\s+(\d+)", footer_text)
                if id_match:
                    old_id = int(id_match.group(1))

    # If we still don't have quote text, try the message content
    if not quote_text:
        # Remove the QuoteID part and see what's left
        cleaned = re.sub(r"QuoteID:\s*\d+", "", content).strip()
        if cleaned:
            quote_text = cleaned

    return {
        "old_id": old_id,
        "quote_text": quote_text or "(could not parse)",
        "author": quote_author,
        "added_by": added_by,
        "timestamp": timestamp,
        "channel_id": channel_id,
        "message_id": msg_id,
    }


async def main():
    if not TOKEN:
        print("Error: Set DISCORD_BOT_TOKEN in .env")
        return

    async with aiohttp.ClientSession() as session:
        # Get the guilds the bot is in
        guilds_data = await api_get(session, API_BASE + "/users/@me/guilds")
        if not guilds_data:
            print("Failed to fetch guilds")
            return

        all_quotes = []
        debug_count = 0

        for guild in guilds_data:
            guild_id = guild["id"]
            guild_name = guild["name"]
            print("Searching server: %s" % guild_name)

            print('  Searching for "QuoteID:"...')
            messages = await search_guild(session, guild_id, "QuoteID:")
            print("  Found %d messages" % len(messages))

            for msg in messages:
                # Debug: print first 5 raw messages
                if debug_count < 5:
                    debug_count += 1
                    print("\n  [DEBUG MSG #%d]" % debug_count)
                    print("    From: %s" % msg.get("author", {}).get("username", "?"))
                    print("    Content: %r" % (msg.get("content") or "")[:200])
                    for i, emb in enumerate(msg.get("embeds", [])):
                        print("    Embed %d:" % i)
                        print("      Title: %r" % emb.get("title"))
                        print("      Desc:  %r" % (emb.get("description") or "")[:200])
                        footer = emb.get("footer") or {}
                        print("      Footer: %r" % footer.get("text"))
                        for f in emb.get("fields", []):
                            print("      Field: %s = %s" % (f.get("name"), f.get("value")))

                parsed = parse_message(msg)
                if parsed:
                    all_quotes.append(parsed)

        # Sort by old ID
        all_quotes.sort(key=lambda q: q.get("old_id") or 0)

        # Deduplicate
        seen_ids = set()
        unique_quotes = []
        for q in all_quotes:
            key = q["old_id"] or q["quote_text"]
            if key not in seen_ids:
                seen_ids.add(key)
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

        print("\nDone! Found %d unique quotes." % len(unique_quotes))
        print("  JSON:     %s" % OUTPUT_FILE)
        print("  Readable: %s" % READABLE_FILE)


if __name__ == "__main__":
    asyncio.run(main())
