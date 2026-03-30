import os
import random
import logging
import traceback
import discord
from datetime import datetime, timezone
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from database import (
    init_db, close_db, add_quote, remove_quote, edit_quote, get_quote,
    get_random_quote, count_quotes_by_author, get_quotes_by_author_page,
    count_search_quotes, search_quotes_page, get_unique_author_names, 
    check_quote_by_message_id, QUOTES_PER_PAGE,
)
from paginator import PaginatorView, build_page_embed

load_dotenv()

logger = logging.getLogger("quote_bot")

QUOTE_MAX_LENGTH = 1000
REACTION_EMOJI = "🗣️"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True # Required for reading message text from reactions
bot = commands.Bot(command_prefix="!", intents=intents)


# ---- Helpers & UI Views ----

def get_embed_color(guild: discord.Guild | None, quote: dict) -> discord.Color:
    if guild and quote.get("author_user_id"):
        member = guild.get_member(int(quote["author_user_id"]))
        if member and member.top_role.color.value != 0:
            return member.top_role.color
    return discord.Color.from_rgb(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))


def format_single_quote_embed(quote: dict, guild: discord.Guild | None = None) -> discord.Embed:
    author_mention = (
        f"<@{quote['author_user_id']}>"
        if quote["author_user_id"]
        else quote["author_name"] or "Unknown"
    )

    ts_plain = quote["timestamp"]
    parsed_dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(ts_plain, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            parsed_dt = dt
            break
        except ValueError:
            continue

    embed = discord.Embed(
        description=f"> {quote['quote_text']}\n> \n> ***\u2014*** {author_mention}",
        color=get_embed_color(guild, quote),
        timestamp=parsed_dt,
    )
    embed.set_author(name=f"Quote #{quote['quote_id']}")

    if quote.get("image_url"):
        embed.set_image(url=quote["image_url"])

    if quote.get("author_user_id"):
        user_id = int(quote["author_user_id"])
        user = guild.get_member(user_id) if guild else None
        if not user:
            user = bot.get_user(user_id)
        if user:
            embed.set_thumbnail(url=user.display_avatar.url)

    added_by_raw = quote["added_by_user_id"]
    if added_by_raw and added_by_raw.isdigit():
        user_id = int(added_by_raw)
        user = guild.get_member(user_id) if guild else None
        if not user:
            user = bot.get_user(user_id)
            
        added_by_text = user.display_name if user else f"User {added_by_raw}"
    else:
        added_by_text = added_by_raw or "Unknown"

    embed.set_footer(text=f"Added by {added_by_text}")
    return embed


def has_manage_permission(interaction: discord.Interaction, quote: dict) -> bool:
    if str(interaction.user.id) == str(quote["added_by_user_id"]):
        return True
    perms = interaction.user.guild_permissions
    return perms.administrator or perms.manage_messages


class ConfirmRemoveView(discord.ui.View):
    def __init__(self, author_id: int, quote: dict, guild: discord.Guild):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.quote = quote
        self.guild = guild

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command user can confirm this.", ephemeral=True)
            
        await remove_quote(str(interaction.guild_id), self.quote["quote_id"])
        
        for child in self.children:
            child.disabled = True
            
        embed = format_single_quote_embed(self.quote, self.guild)
        embed.color = discord.Color.red()
        embed.set_author(name=f"Quote #{self.quote['quote_id']} Deleted")
        
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command user can cancel this.", ephemeral=True)
            
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Deletion cancelled.", embed=None, view=self)


async def author_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    names = await get_unique_author_names(str(interaction.guild_id), current)
    return [app_commands.Choice(name=name, value=name) for name in names]


# ---- Events ----

@bot.event
async def on_ready():
    await init_db()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands (including context menus)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    print(f"Bot is ready as {bot.user}")

@bot.event
async def on_close():
    await close_db()

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.error("Command /%s failed: %s", interaction.command.name if interaction.command else "unknown", error)
    traceback.print_exception(type(error), error, error.__traceback__)
    message = "Something went wrong. Try again in a moment."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


# ---- Reaction Save Event ----

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    # Only run in servers, and only for the designated emoji
    if not payload.guild_id or str(payload.emoji) != REACTION_EMOJI:
        return

    # Check if this message was already quoted to prevent duplicates
    server_id = str(payload.guild_id)
    message_id = str(payload.message_id)
    
    is_duplicate = await check_quote_by_message_id(server_id, message_id)
    if is_duplicate:
        return # Silently ignore, it's already saved

    # Fetch the channel and message
    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
        
    try:
        message = await channel.fetch_message(payload.message_id)
    except (discord.NotFound, discord.Forbidden):
        return

    # Don't quote the bot itself
    if message.author.bot:
        return

    text = message.content.strip()
    image_url = message.attachments[0].url if message.attachments else None
    
    if not text and not image_url:
        return

    if len(text) > QUOTE_MAX_LENGTH:
        return # Too long to quote

    # Fetch the user who added the reaction
    added_by_user = bot.get_user(payload.user_id)
    added_by_name = added_by_user.display_name if added_by_user else "Unknown User"

    # Save the quote
    quote_id = await add_quote(
        server_id=server_id,
        quote_text=text or "[Image Only]",
        added_by_user_id=str(payload.user_id),
        author_user_id=str(message.author.id),
        author_name=None,
        image_url=image_url,
        original_message_id=message_id
    )

    # Build the confirmation embed
    embed = discord.Embed(
        description=f"> {text or '[Image Only]'}\n> \n> ***\u2014*** {message.author.mention}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=f"Quote #{quote_id} Added via Reaction")
    embed.set_thumbnail(url=message.author.display_avatar.url)
    if image_url:
        embed.set_image(url=image_url)
    embed.set_footer(text=f"Added by {added_by_name}")
    
    # Send confirmation back to the channel as a reply
    try:
        await channel.send(embed=embed, reference=message)
    except discord.Forbidden:
        pass # Bot doesn't have permission to send messages here


# ---- Commands ----

@bot.tree.context_menu(name="Save Quote")
async def save_quote_context(interaction: discord.Interaction, message: discord.Message):
    text = message.content.strip()
    image_url = message.attachments[0].url if message.attachments else None
    
    if not text and not image_url:
        await interaction.response.send_message("This message has no text or image to save.", ephemeral=True)
        return

    if len(text) > QUOTE_MAX_LENGTH:
        await interaction.response.send_message(f"Message is too long ({len(text)} chars) to save as a quote.", ephemeral=True)
        return

    # Context menus also check for duplicates!
    server_id = str(interaction.guild_id)
    message_id = str(message.id)
    
    is_duplicate = await check_quote_by_message_id(server_id, message_id)
    if is_duplicate:
        await interaction.response.send_message("This message has already been saved as a quote!", ephemeral=True)
        return

    quote_id = await add_quote(
        server_id=server_id,
        quote_text=text or "[Image Only]",
        added_by_user_id=str(interaction.user.id),
        author_user_id=str(message.author.id),
        author_name=None,
        image_url=image_url,
        original_message_id=message_id
    )

    embed = discord.Embed(
        description=f"> {text or '[Image Only]'}\n> \n> ***\u2014*** {message.author.mention}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=f"Quote #{quote_id} Added via Context Menu")
    embed.set_thumbnail(url=message.author.display_avatar.url)
    if image_url:
        embed.set_image(url=image_url)
    embed.set_footer(text=f"Added by {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="qadd", description="Add a new quote")
@app_commands.describe(
    text="The quote text (max 1000 characters)",
    author_user="The Discord user who said the quote",
    author_text="The name of the author (for non-Discord users)",
    attachment="An optional image to attach to the quote"
)
@app_commands.autocomplete(author_text=author_autocomplete)
@app_commands.guild_only()
async def qadd(
    interaction: discord.Interaction,
    text: str,
    author_user: discord.User | None = None,
    author_text: str | None = None,
    attachment: discord.Attachment | None = None
):
    if author_user and author_text:
        return await interaction.response.send_message("Please provide either `author_user` or `author_text`, not both.", ephemeral=True)

    if len(text) > QUOTE_MAX_LENGTH:
        return await interaction.response.send_message(f"Quote text must be {QUOTE_MAX_LENGTH} characters or fewer.", ephemeral=True)

    image_url = attachment.url if attachment else None

    quote_id = await add_quote(
        server_id=str(interaction.guild_id),
        quote_text=text,
        added_by_user_id=str(interaction.user.id),
        author_user_id=str(author_user.id) if author_user else None,
        author_name=author_text,
        image_url=image_url
    )

    author_display = author_user.mention if author_user else author_text or "Unknown"

    embed = discord.Embed(
        description=f"> {text}\n> \n> ***\u2014*** {author_display}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=f"Quote #{quote_id} Added")
    
    if image_url:
        embed.set_image(url=image_url)
    if author_user:
        embed.set_thumbnail(url=author_user.display_avatar.url)
        
    embed.set_footer(text=f"Added by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="qremove", description="Remove a quote by ID")
@app_commands.describe(id="The quote ID to remove")
@app_commands.guild_only()
async def qremove(interaction: discord.Interaction, id: int):
    quote = await get_quote(str(interaction.guild_id), id)
    if not quote:
        return await interaction.response.send_message(f"Quote #{id} not found.", ephemeral=True)

    if not has_manage_permission(interaction, quote):
        return await interaction.response.send_message("You don't have permission to remove this quote.", ephemeral=True)

    embed = format_single_quote_embed(quote, interaction.guild)
    view = ConfirmRemoveView(interaction.user.id, quote, interaction.guild)
    
    await interaction.response.send_message(
        content="⚠️ **Are you sure you want to permanently delete this quote?**",
        embed=embed, 
        view=view,
        ephemeral=True
    )


@bot.tree.command(name="qedit", description="Edit an existing quote")
@app_commands.describe(
    id="The quote ID to edit",
    text="New quote text",
    author_user="New Discord user author",
    author_text="New text author name",
    attachment="New image attachment (overwrites existing)"
)
@app_commands.autocomplete(author_text=author_autocomplete)
@app_commands.guild_only()
async def qedit(
    interaction: discord.Interaction,
    id: int,
    text: str | None = None,
    author_user: discord.User | None = None,
    author_text: str | None = None,
    attachment: discord.Attachment | None = None
):
    if author_user and author_text:
        return await interaction.response.send_message("Please provide either `author_user` or `author_text`, not both.", ephemeral=True)

    if text is not None and len(text) > QUOTE_MAX_LENGTH:
        return await interaction.response.send_message(f"Quote text must be {QUOTE_MAX_LENGTH} characters or fewer.", ephemeral=True)

    if text is None and author_user is None and author_text is None and attachment is None:
        return await interaction.response.send_message("You must provide at least one field to edit.", ephemeral=True)

    quote = await get_quote(str(interaction.guild_id), id)
    if not quote:
        return await interaction.response.send_message(f"Quote #{id} not found.", ephemeral=True)

    if not has_manage_permission(interaction, quote):
        return await interaction.response.send_message("You don't have permission to edit this quote.", ephemeral=True)

    image_url = attachment.url if attachment else None

    updated = await edit_quote(
        server_id=str(interaction.guild_id),
        quote_id=id,
        quote_text=text,
        author_user_id=str(author_user.id) if author_user else None,
        author_name=author_text,
        image_url=image_url
    )
    embed = format_single_quote_embed(updated, interaction.guild)
    embed.set_author(name=f"Quote #{id} Updated")
    embed.color = discord.Color.orange()
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="qrandom", description="Get a random quote")
@app_commands.describe(
    author_user="Filter by Discord user",
    author_text="Filter by text author name",
)
@app_commands.autocomplete(author_text=author_autocomplete)
@app_commands.guild_only()
async def qrandom(
    interaction: discord.Interaction,
    author_user: discord.User | None = None,
    author_text: str | None = None,
):
    if author_user and author_text:
        return await interaction.response.send_message("Please provide either `author_user` or `author_text`, not both.", ephemeral=True)

    quote = await get_random_quote(
        server_id=str(interaction.guild_id),
        author_user_id=str(author_user.id) if author_user else None,
        author_name=author_text,
    )
    if not quote:
        return await interaction.response.send_message("No quotes found.", ephemeral=True)

    await interaction.response.send_message(embed=format_single_quote_embed(quote, interaction.guild))


@bot.tree.command(name="qget", description="Get a specific quote by ID")
@app_commands.describe(id="The quote ID to retrieve")
@app_commands.guild_only()
async def qget(interaction: discord.Interaction, id: int):
    quote = await get_quote(str(interaction.guild_id), id)
    if not quote:
        return await interaction.response.send_message(f"Quote #{id} not found.", ephemeral=True)

    await interaction.response.send_message(embed=format_single_quote_embed(quote, interaction.guild))


@bot.tree.command(name="quser", description="Get all quotes by an author")
@app_commands.describe(
    author_user="The Discord user to look up",
    author_text="The text author name to look up",
)
@app_commands.autocomplete(author_text=author_autocomplete)
@app_commands.guild_only()
async def quser(
    interaction: discord.Interaction,
    author_user: discord.User | None = None,
    author_text: str | None = None,
):
    if author_user and author_text:
        return await interaction.response.send_message("Please provide either `author_user` or `author_text`, not both.", ephemeral=True)

    if not author_user and not author_text:
        return await interaction.response.send_message("Please provide an author to search for.", ephemeral=True)

    server_id = str(interaction.guild_id)
    uid = str(author_user.id) if author_user else None
    name = author_text

    total = await count_quotes_by_author(server_id, author_user_id=uid, author_name=name)
    if total == 0:
        return await interaction.response.send_message("No quotes found for that author.", ephemeral=True)

    author_display = author_user.display_name if author_user else author_text
    title = f"Quotes by {author_display}"

    first_page = await get_quotes_by_author_page(server_id, 0, author_user_id=uid, author_name=name)
    embed = build_page_embed(first_page, 0, total, title)

    if total <= QUOTES_PER_PAGE:
        await interaction.response.send_message(embed=embed)
    else:
        async def fetch_page(page: int) -> list[dict]:
            return await get_quotes_by_author_page(server_id, page, author_user_id=uid, author_name=name)

        view = PaginatorView(fetch_page, total, title, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="qsearch", description="Search quotes by keyword")
@app_commands.describe(keyword="The keyword to search for in quote text")
@app_commands.guild_only()
async def qsearch(interaction: discord.Interaction, keyword: str):
    server_id = str(interaction.guild_id)

    total = await count_search_quotes(server_id, keyword)
    if total == 0:
        return await interaction.response.send_message(f"No quotes found matching \"{keyword}\".", ephemeral=True)

    title = f"Search results for \"{keyword}\""

    first_page = await search_quotes_page(server_id, keyword, 0)
    embed = build_page_embed(first_page, 0, total, title)

    if total <= QUOTES_PER_PAGE:
        await interaction.response.send_message(embed=embed)
    else:
        async def fetch_page(page: int) -> list[dict]:
            return await search_quotes_page(server_id, keyword, page)

        view = PaginatorView(fetch_page, total, title, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="qhelp", description="Show help for the quote bot")
async def qhelp(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Quote Bot Help",
        description="Store, manage, and retrieve quotes in your server!",
        color=discord.Color.blurple(),
    )
    commands_info = [
        ("Reaction Save", "React to any message with 🗣️ to instantly save it as a quote."),
        ("Right-Click Save", "Right-click any message -> Apps -> `Save Quote` to instantly save it."),
        ("/qadd", "`text` `[author_user]` `[author_text]` `[attachment]`\nAdd a new quote manually. Supports image uploads."),
        ("/qremove", "`id`\nRemove a quote safely with a confirmation prompt."),
        ("/qedit", "`id` `[text]` `[author_user]` `[author_text]` `[attachment]`\nEdit a quote's text, author, or image."),
        ("/qrandom", "`[author_user]` `[author_text]`\nGet a random quote, optionally filtered by author."),
        ("/qget", "`id`\nGet a specific quote by its ID."),
        ("/quser", "`[author_user]` `[author_text]`\nGet all quotes by an author. Features text autocomplete."),
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