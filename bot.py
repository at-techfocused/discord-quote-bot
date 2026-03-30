import os
import random
import discord
from datetime import datetime, timezone
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from database import init_db, add_quote, remove_quote, edit_quote, get_quote
from database import get_random_quote, get_quotes_by_author, search_quotes
from paginator import PaginatorView, build_page_embed, format_quote

load_dotenv()

QUOTE_MAX_LENGTH = 1000

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


def to_discord_timestamp(ts_str: str, style: str = "d") -> str:
    """Convert a timestamp string to Discord's <t:UNIX:style> format.
    Falls back to the raw string if parsing fails."""
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(ts_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return "<t:%d:%s>" % (int(dt.timestamp()), style)
        except ValueError:
            continue
    return ts_str


def format_added_by(quote: dict) -> str:
    """Format the Added By field. Uses <@ID> for Discord IDs, plain text for legacy names."""
    added_by = quote["added_by_user_id"]
    if added_by and added_by.isdigit():
        return "<@%s>" % added_by
    return added_by or "Unknown"


def get_embed_color(guild: discord.Guild | None, quote: dict) -> discord.Color:
    """Get embed color from the author's top role, or random if not a member."""
    if guild and quote.get("author_user_id"):
        member = guild.get_member(int(quote["author_user_id"]))
        if member and member.top_role.color.value != 0:
            return member.top_role.color
    return discord.Color.from_rgb(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))


def format_single_quote_embed(quote: dict, guild: discord.Guild | None = None) -> discord.Embed:
    author = (
        "<@%s>" % quote["author_user_id"]
        if quote["author_user_id"]
        else quote["author_name"] or "Unknown"
    )
    embed = discord.Embed(
        description="> %s\n> \n> *\u2014 %s*" % (quote["quote_text"], author),
        color=get_embed_color(guild, quote),
    )
    embed.set_author(name="Quote #%d" % quote["quote_id"])

    # Set author's avatar as thumbnail if they're a Discord user
    if guild and quote.get("author_user_id"):
        member = guild.get_member(int(quote["author_user_id"]))
        if member and member.avatar:
            embed.set_thumbnail(url=member.avatar.url)

    # Metadata in footer (footers don't render mentions, so resolve to display name)
    added_by_raw = quote["added_by_user_id"]
    if added_by_raw and added_by_raw.isdigit() and guild:
        member = guild.get_member(int(added_by_raw))
        added_by_text = member.display_name if member else "User %s" % added_by_raw
    else:
        added_by_text = added_by_raw or "Unknown"
    # Format date as plain text for footer (Discord formatting doesn't work in footers)
    ts_plain = quote["timestamp"]
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(ts_plain, fmt)
            ts_plain = dt.strftime("%m/%d/%Y")
            break
        except ValueError:
            continue
    embed.set_footer(text="Added by %s \u2022 %s" % (added_by_text, ts_plain))
    return embed


def has_manage_permission(interaction: discord.Interaction, quote: dict) -> bool:
    if str(interaction.user.id) == str(quote["added_by_user_id"]):
        return True
    perms = interaction.user.guild_permissions
    return perms.administrator or perms.manage_messages


@bot.event
async def on_ready():
    await init_db()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    print(f"Bot is ready as {bot.user}")


@bot.tree.command(name="qadd", description="Add a new quote")
@app_commands.describe(
    text="The quote text (max 1000 characters)",
    author_user="The Discord user who said the quote",
    author_text="The name of the author (for non-Discord users)",
)
@app_commands.guild_only()
async def qadd(
    interaction: discord.Interaction,
    text: str,
    author_user: discord.User | None = None,
    author_text: str | None = None,
):
    if author_user and author_text:
        await interaction.response.send_message(
            "Please provide either `author_user` or `author_text`, not both.",
            ephemeral=True,
        )
        return

    if len(text) > QUOTE_MAX_LENGTH:
        await interaction.response.send_message(
            f"Quote text must be {QUOTE_MAX_LENGTH} characters or fewer (yours: {len(text)}).",
            ephemeral=True,
        )
        return

    quote_id = await add_quote(
        server_id=str(interaction.guild_id),
        quote_text=text,
        added_by_user_id=str(interaction.user.id),
        author_user_id=str(author_user.id) if author_user else None,
        author_name=author_text,
    )

    author_display = (
        author_user.mention if author_user else author_text or "Unknown"
    )
    embed = discord.Embed(
        description="> %s\n> \n> *\u2014 %s*" % (text, author_display),
        color=discord.Color.green(),
    )
    embed.set_author(name="Quote #%d Added" % quote_id)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="qremove", description="Remove a quote by ID")
@app_commands.describe(id="The quote ID to remove")
@app_commands.guild_only()
async def qremove(interaction: discord.Interaction, id: int):
    quote = await get_quote(str(interaction.guild_id), id)
    if not quote:
        await interaction.response.send_message(
            f"Quote #{id} not found.", ephemeral=True
        )
        return

    if not has_manage_permission(interaction, quote):
        await interaction.response.send_message(
            "You don't have permission to remove this quote.", ephemeral=True
        )
        return

    await remove_quote(str(interaction.guild_id), id)
    await interaction.response.send_message(
        f"Quote #{id} has been removed.",
        embed=format_single_quote_embed(quote, interaction.guild),
    )


@bot.tree.command(name="qedit", description="Edit an existing quote")
@app_commands.describe(
    id="The quote ID to edit",
    text="New quote text",
    author_user="New Discord user author",
    author_text="New text author name",
)
@app_commands.guild_only()
async def qedit(
    interaction: discord.Interaction,
    id: int,
    text: str | None = None,
    author_user: discord.User | None = None,
    author_text: str | None = None,
):
    if author_user and author_text:
        await interaction.response.send_message(
            "Please provide either `author_user` or `author_text`, not both.",
            ephemeral=True,
        )
        return

    if text is not None and len(text) > QUOTE_MAX_LENGTH:
        await interaction.response.send_message(
            f"Quote text must be {QUOTE_MAX_LENGTH} characters or fewer.",
            ephemeral=True,
        )
        return

    if text is None and author_user is None and author_text is None:
        await interaction.response.send_message(
            "You must provide at least one field to edit.", ephemeral=True
        )
        return

    quote = await get_quote(str(interaction.guild_id), id)
    if not quote:
        await interaction.response.send_message(
            f"Quote #{id} not found.", ephemeral=True
        )
        return

    if not has_manage_permission(interaction, quote):
        await interaction.response.send_message(
            "You don't have permission to edit this quote.", ephemeral=True
        )
        return

    updated = await edit_quote(
        server_id=str(interaction.guild_id),
        quote_id=id,
        quote_text=text,
        author_user_id=str(author_user.id) if author_user else None,
        author_name=author_text,
    )
    embed = format_single_quote_embed(updated, interaction.guild)
    embed.title = f"Quote #{id} Updated"
    embed.color = discord.Color.orange()
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="qrandom", description="Get a random quote")
@app_commands.describe(
    author_user="Filter by Discord user",
    author_text="Filter by text author name",
)
@app_commands.guild_only()
async def qrandom(
    interaction: discord.Interaction,
    author_user: discord.User | None = None,
    author_text: str | None = None,
):
    if author_user and author_text:
        await interaction.response.send_message(
            "Please provide either `author_user` or `author_text`, not both.",
            ephemeral=True,
        )
        return

    quote = await get_random_quote(
        server_id=str(interaction.guild_id),
        author_user_id=str(author_user.id) if author_user else None,
        author_name=author_text,
    )
    if not quote:
        await interaction.response.send_message("No quotes found.", ephemeral=True)
        return

    await interaction.response.send_message(embed=format_single_quote_embed(quote, interaction.guild))


@bot.tree.command(name="qget", description="Get a specific quote by ID")
@app_commands.describe(id="The quote ID to retrieve")
@app_commands.guild_only()
async def qget(interaction: discord.Interaction, id: int):
    quote = await get_quote(str(interaction.guild_id), id)
    if not quote:
        await interaction.response.send_message(
            f"Quote #{id} not found.", ephemeral=True
        )
        return

    await interaction.response.send_message(embed=format_single_quote_embed(quote, interaction.guild))


@bot.tree.command(name="quser", description="Get all quotes by an author")
@app_commands.describe(
    author_user="The Discord user to look up",
    author_text="The text author name to look up",
)
@app_commands.guild_only()
async def quser(
    interaction: discord.Interaction,
    author_user: discord.User | None = None,
    author_text: str | None = None,
):
    if author_user and author_text:
        await interaction.response.send_message(
            "Please provide either `author_user` or `author_text`, not both.",
            ephemeral=True,
        )
        return

    if not author_user and not author_text:
        await interaction.response.send_message(
            "Please provide an author to search for.", ephemeral=True
        )
        return

    quotes = await get_quotes_by_author(
        server_id=str(interaction.guild_id),
        author_user_id=str(author_user.id) if author_user else None,
        author_name=author_text,
    )

    if not quotes:
        await interaction.response.send_message("No quotes found for that author.", ephemeral=True)
        return

    author_display = author_user.display_name if author_user else author_text
    title = f"Quotes by {author_display}"

    if len(quotes) <= 5:
        embed = build_page_embed(quotes, 0, title)
        await interaction.response.send_message(embed=embed)
    else:
        view = PaginatorView(quotes, title, interaction.user.id)
        embed = build_page_embed(quotes, 0, title)
        await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="qsearch", description="Search quotes by keyword")
@app_commands.describe(keyword="The keyword to search for in quote text")
@app_commands.guild_only()
async def qsearch(interaction: discord.Interaction, keyword: str):
    quotes = await search_quotes(str(interaction.guild_id), keyword)

    if not quotes:
        await interaction.response.send_message(
            f"No quotes found matching \"{keyword}\".", ephemeral=True
        )
        return

    title = f"Search results for \"{keyword}\""

    if len(quotes) <= 5:
        embed = build_page_embed(quotes, 0, title)
        await interaction.response.send_message(embed=embed)
    else:
        view = PaginatorView(quotes, title, interaction.user.id)
        embed = build_page_embed(quotes, 0, title)
        await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="qhelp", description="Show help for the quote bot")
async def qhelp(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Quote Bot Help",
        description="Store, manage, and retrieve quotes in your server!",
        color=discord.Color.blurple(),
    )
    commands_info = [
        (
            "/qadd",
            "`text` `[author_user]` `[author_text]`\nAdd a new quote. Provide either a Discord user or a text name as the author.",
        ),
        ("/qremove", "`id`\nRemove a quote. You must be the one who added it, or have Manage Messages/Admin permissions."),
        (
            "/qedit",
            "`id` `[text]` `[author_user]` `[author_text]`\nEdit a quote's text or author. Same permissions as /qremove.",
        ),
        (
            "/qrandom",
            "`[author_user]` `[author_text]`\nGet a random quote, optionally filtered by author.",
        ),
        ("/qget", "`id`\nGet a specific quote by its ID."),
        (
            "/quser",
            "`[author_user]` `[author_text]`\nGet all quotes by an author (paginated).",
        ),
        ("/qsearch", "`keyword`\nSearch quotes by keyword (paginated)."),
    ]
    for name, value in commands_info:
        embed.add_field(name=name, value=value, inline=False)

    embed.set_footer(text="Quotes are server-specific. IDs are unique per server.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN not set. Copy .env.example to .env and add your token.")
        return
    bot.run(token)


if __name__ == "__main__":
    main()
