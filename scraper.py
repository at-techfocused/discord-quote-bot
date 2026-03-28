import os
import re
import json
from datetime import datetime, timezone
import discord
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

OUTPUT_FILE = "scraped_quotes.json"
READABLE_FILE = "scraped_quotes.txt"


def parse_embed(embed: discord.Embed) -> dict | None:
    """Parse an old quote bot embed into structured data."""
    # Check if this is a "Successfully added new quote" embed
    title = embed.title or ""
    if "successfully added" not in title.lower():
        return None

    description = embed.description or ""
    footer_text = embed.footer.text or "" if embed.footer else ""

    # Parse quote text and author from description
    # Format: "quote text\n\n- Author" or "quote text\n- Author"
    lines = description.strip().split("\n")

    # Find the author line (starts with "- " or "– ")
    quote_lines = []
    author = None
    for line in lines:
        stripped = line.strip()
        if re.match(r"^[-–—]\s+", stripped):
            author = re.sub(r"^[-–—]\s+", "", stripped).strip()
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


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print("Scanning for old quote bot messages...\n")

    all_quotes = []

    for guild in client.guilds:
        print(f"Scanning server: {guild.name}")

        # Only scan channels under the "General" category
        cutoff = datetime(2022, 7, 8, tzinfo=timezone.utc)

        for channel in guild.text_channels:
            category_name = channel.category.name.lower() if channel.category else ""
            if not category_name.startswith("general"):
                print(f"  Skipping #{channel.name} (not in General category)")
                continue

            # Check if bot has permission to read history
            perms = channel.permissions_for(guild.me)
            if not perms.read_message_history or not perms.read_messages:
                print(f"  Skipping #{channel.name} (no permission)")
                continue

            print(f"  Scanning #{channel.name}...", end="", flush=True)
            count = 0

            try:
                async for message in channel.history(limit=None, oldest_first=True, before=cutoff):
                    for embed in message.embeds:
                        parsed = parse_embed(embed)
                        if parsed:
                            parsed["channel"] = channel.name
                            parsed["message_url"] = message.jump_url
                            all_quotes.append(parsed)
                            count += 1
            except discord.Forbidden:
                print(" (forbidden)")
                continue
            except Exception as e:
                print(f" (error: {e})")
                continue

            print(f" found {count} quotes")

    # Sort by old ID if available, otherwise by order found
    all_quotes.sort(key=lambda q: q["old_id"] or 0)

    # Remove duplicates by old_id
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
    with open(READABLE_FILE, "w") as f:
        f.write(f"SCRAPED QUOTES ({len(unique_quotes)} total)\n")
        f.write("=" * 60 + "\n\n")
        for q in unique_quotes:
            f.write(f"ID: {q['old_id'] or '?'}\n")
            f.write(f"Quote: {q['quote_text']}\n")
            f.write(f"Author: {q['author'] or 'Unknown'}\n")
            f.write(f"Added by: {q['added_by'] or 'Unknown'}\n")
            f.write(f"Date: {q['timestamp'] or 'Unknown'}\n")
            f.write(f"Channel: #{q['channel']}\n")
            f.write("-" * 60 + "\n")

    print(f"\nDone! Found {len(unique_quotes)} unique quotes.")
    print(f"  JSON:     {OUTPUT_FILE}")
    print(f"  Readable: {READABLE_FILE}")

    await client.close()


def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: Set DISCORD_BOT_TOKEN in .env")
        return
    client.run(token)


if __name__ == "__main__":
    main()
