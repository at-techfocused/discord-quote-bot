import discord

QUOTES_PER_PAGE = 5

def format_quote(quote: dict) -> str:
    author = (
        "<@%s>" % quote["author_user_id"]
        if quote["author_user_id"]
        else quote["author_name"] or "Unknown"
    )
    # Uses the "Hanging Citation" format (Mobile Fix applied here)
    return "**Quote #%d**\n> %s\n> \n> ***\u2014*** %s" % (quote["quote_id"], quote["quote_text"], author)

def build_page_embed(
    quotes: list[dict], page: int, title: str = "Quotes"
) -> discord.Embed:
    total_pages = max(1, (len(quotes) + QUOTES_PER_PAGE - 1) // QUOTES_PER_PAGE)
    start = page * QUOTES_PER_PAGE
    end = start + QUOTES_PER_PAGE
    page_quotes = quotes[start:end]

    description = "\n\n".join(format_quote(q) for q in page_quotes)
    embed = discord.Embed(
        title=title,
        description=description or "No quotes found.",
        color=discord.Color.blurple(),
    )
    
    embed.set_footer(text=f"Page {page + 1}/{total_pages} | {len(quotes)} total quotes")
    return embed

class PaginatorView(discord.ui.View):
    def __init__(self, quotes: list[dict], title: str, author_id: int):
        super().__init__(timeout=120)
        self.quotes = quotes
        self.title = title
        self.page = 0
        self.author_id = author_id
        self.total_pages = max(
            1, (len(quotes) + QUOTES_PER_PAGE - 1) // QUOTES_PER_PAGE
        )
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.page <= 0
        self.next_button.disabled = self.page >= self.total_pages - 1

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
        self._update_buttons()
        embed = build_page_embed(self.quotes, self.page, self.title)
        await interaction.response.edit_message(embed=embed, view=self)

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
        self._update_buttons()
        embed = build_page_embed(self.quotes, self.page, self.title)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True