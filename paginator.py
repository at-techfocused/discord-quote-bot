import discord
from typing import Callable, Awaitable

QUOTES_PER_PAGE = 5

def format_quote(index: int, quote: dict) -> str:
    author = (
        f"<@{quote['author_user_id']}>"
        if quote["author_user_id"]
        else quote["author_name"] or "Unknown"
    )
    image_indicator = " \n> 🖼️ *[Image Attached]*" if quote.get("image_url") else ""
    text = quote['quote_text']
    if len(text) > 200:
        text = text[:197] + "..."
    
    return f"**{index}. Quote #{quote['quote_id']}**\n> {text}{image_indicator}\n> \n> ***\u2014*** {author}"

def build_page_embed(
    quotes: list[dict], page: int, total: int, title: str = "Quotes"
) -> discord.Embed:
    total_pages = max(1, (total + QUOTES_PER_PAGE - 1) // QUOTES_PER_PAGE)
    description = "\n\n".join(format_quote(i + 1, q) for i, q in enumerate(quotes))
    
    embed = discord.Embed(
        title=title,
        description=description or "No quotes found.",
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Page {page + 1}/{total_pages} | {total} total quotes")
    return embed

class PaginatorView(discord.ui.View):
    def __init__(
        self,
        fetch_page: Callable[[int], Awaitable[list[dict]]],
        total: int,
        title: str,
        author_id: int,
        format_single_embed: Callable[[dict], discord.Embed],
        first_page_quotes: list[dict],
        format_single_view: Callable[[dict], discord.ui.View | None] = None
    ):
        super().__init__(timeout=120)
        self.fetch_page = fetch_page
        self.total = total
        self.title = title
        self.page = 0
        self.author_id = author_id
        self.format_single_embed = format_single_embed
        self.format_single_view = format_single_view
        self.total_pages = max(1, (total + QUOTES_PER_PAGE - 1) // QUOTES_PER_PAGE)
        self.current_quotes = first_page_quotes
        
        self.build_ui()

    def build_ui(self):
        self.clear_items()
        number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for i, quote in enumerate(self.current_quotes):
            btn = discord.ui.Button(emoji=number_emojis[i], style=discord.ButtonStyle.primary, row=0)
            btn.callback = self.generate_select_callback(i)
            self.add_item(btn)

        prev_btn = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, row=1, disabled=self.page <= 0)
        prev_btn.callback = self.on_prev_page
        self.add_item(prev_btn)

        close_btn = discord.ui.Button(emoji="❌", style=discord.ButtonStyle.danger, row=1)
        close_btn.callback = self.on_close
        self.add_item(close_btn)

        next_btn = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary, row=1, disabled=self.page >= self.total_pages - 1)
        next_btn.callback = self.on_next_page
        self.add_item(next_btn)

    def generate_select_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                return await interaction.response.send_message("Only the command user can expand a quote.", ephemeral=True)
                
            selected_quote = self.current_quotes[index]
            single_embed = self.format_single_embed(selected_quote)
            
            # Fetch the URL link button if it exists
            single_view = self.format_single_view(selected_quote) if self.format_single_view else None
            
            if single_view:
                await interaction.response.edit_message(embed=single_embed, view=single_view)
            else:
                await interaction.response.edit_message(embed=single_embed, view=None)
                
        return callback

    async def on_close(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command user can close this search.", ephemeral=True)
        await interaction.message.delete()

    async def on_prev_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command user can navigate pages.", ephemeral=True)
        self.page -= 1
        await self._refresh(interaction)

    async def on_next_page(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command user can navigate pages.", ephemeral=True)
        self.page += 1
        await self._refresh(interaction)

    async def _refresh(self, interaction: discord.Interaction):
        self.current_quotes = await self.fetch_page(self.page)
        self.build_ui()
        embed = build_page_embed(self.current_quotes, self.page, self.total, self.title)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True