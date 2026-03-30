import discord
from typing import Callable, Awaitable

QUOTES_PER_PAGE = 5


def format_quote(quote: dict) -> str:
    author = (
        f"<@{quote['author_user_id']}>"
        if quote["author_user_id"]
        else quote["author_name"] or "Unknown"
    )
    # Mobile Fix applied with bold quote header
    return f"**Quote #{quote['quote_id']}**\n> {quote['quote_text']}\n> \n> ***\u2014*** {author}"


def build_page_embed(
    quotes: list[dict], page: int, total: int, title: str = "Quotes"
) -> discord.Embed:
    total_pages = max(1, (total + QUOTES_PER_PAGE - 1) // QUOTES_PER_PAGE)

    description = "\n\n".join(format_quote(q) for q in quotes)
    embed = discord.Embed(
        title=title,
        description=description or "No quotes found.",
        color=discord.Color.blurple(),
    )
    embed.set_footer(text=f"Page {page + 1}/{total_pages} | {total} total quotes")
    return embed


class PaginatorView(discord.ui.View):
    """Stateless paginator that queries the DB on each page turn."""

    def __init__(
        self,
        fetch_page: Callable[[int], Awaitable[list[dict]]],
        total: int,
        title: str,
        author_id: int,
    ):
        super().__init__(timeout=120)
        self.fetch_page = fetch_page
        self.total = total
        self.title = title
        self.page = 0
        self.author_id = author_id
        self.total_pages = max(1, (total + QUOTES_PER_PAGE - 1) // QUOTES_PER_PAGE)
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    async def _refresh(self, interaction: discord.Interaction):
        quotes = await self.fetch_page(self.page)
        self._update_buttons()
        embed = build_page_embed(quotes, self.page, self.total, self.title)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the command author can navigate pages.", ephemeral=True
            )
            return
        self.page -= 1
        await self._refresh(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the command author can navigate pages.", ephemeral=True
            )
            return
        self.page += 1
        await self._refresh(interaction)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True