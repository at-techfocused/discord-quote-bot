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

# Search terms that should match the old quote bot embeds
SEARCH_QUERIES = [
    "Successfully added new quote",
    "Successfully added",
]


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
        params = {"content": query, "has": "embed", "offset": offset}
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


def parse_embed_dict(embed):
    """Parse an embed dict (from API) into a quote."""
    title = embed.get("title") or ""
    if "successfully added" not in title.lower():
        return None

    description = embed.get("description") or ""
    footer = embed.get("footer", {}) or {}
    footer_text = footer.get("text") or ""

    # Parse quote text and author from description
    lines = description.strip().split("\n")

    quote_lines = []
    author = None
    for line in lines:
        stripped = line.strip()
        if re.match(r"^[-\u2013\u2014]\s+", stripped):
            author = re.sub(r"^[-\u2013\u2014]\s+", "", stripped).strip()
        elif stripped:
            quote_lines.append(stripped)

    quote_text = " ".join(quote_lines).strip()
    # Remove surrounding quotes if present
    quote_text = re.sub(r'^["""\u201c]|["""\u201d]$', "", quote_text).strip()

    # Parse footer: "Added by Username#1234\nat YYYY-MM-DD HH:MM:SS | ID 184"
    added_by = None
    old_id = None
    timestamp = None

    added_match = re.search(r"Added by\s+(.+?)(?:\n|$)", footer_text)
    if added_match:
        added_by = added_match.group(1).strip()

    id_match = re.search(r"ID\s+(\d+)", footer_text)
    if id_match:
        old_id = int(id_match.group(1))

    time_match = re.search(r"at\s+([\d-]+\s+[\d:]+)", footer_text)
    if time_match:
        timestamp = time_match.group(1).strip()

    if not quote_text:
        return None

    return {
        "old_id": old_id,
        "quote_text": quote_text,
        "author": author,
        "added_by": added_by,
        "timestamp": timestamp,
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

        for guild in guilds_data:
            guild_id = guild["id"]
            guild_name = guild["name"]
            print("Searching server: %s" % guild_name)

            for query in SEARCH_QUERIES:
                print("  Searching for: \"%s\"" % query)
                messages = await search_guild(session, guild_id, query)
                print("  Found %d messages" % len(messages))

                for msg in messages:
                    embeds = msg.get("embeds", [])
                    channel_id = msg.get("channel_id", "unknown")

                    # Debug: show first few raw embeds
                    if len(all_quotes) == 0 and embeds:
                        print("  [DEBUG] Sample embed from message:")
                        print("    Title: %r" % (embeds[0].get("title"),))
                        print("    Desc:  %r" % (embeds[0].get("description"),))
                        footer = embeds[0].get("footer", {}) or {}
                        print("    Footer: %r" % (footer.get("text"),))

                    for embed in embeds:
                        parsed = parse_embed_dict(embed)
                        if parsed:
                            parsed["channel_id"] = channel_id
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
        with open(OUTPUT_FILE, "w") as f:
            json.dump(unique_quotes, f, indent=2)

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
