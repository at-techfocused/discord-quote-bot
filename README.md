# Discord Quote Bot

A Discord bot for storing, managing, and retrieving user-generated quotes. Supports both active Discord members and legacy/non-Discord authors, with full multi-server isolation.

## Features

- **Slash Commands**: `/qadd`, `/qremove`, `/qedit`, `/qrandom`, `/qget`, `/quser`, `/qsearch`, `/qhelp`
- **Multi-Server Isolation**: Quotes are scoped per server with independent sequential IDs
- **Hybrid Authors**: Support for both `@User` mentions and plain text author names
- **Paginated Results**: Interactive Previous/Next buttons for browsing results
- **Permission System**: Only the quote adder or users with Admin/Manage Messages can edit/remove quotes

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new Application and add a Bot
3. Enable the bot and copy the **Bot Token**
4. Invite the bot to your server with permissions: Read Messages, Send Messages, Embed Links, Use Slash Commands

### 2. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your bot token
```

### 4. Run the Bot

```bash
python bot.py
```

The bot will automatically create the SQLite database and sync slash commands on first run.

## Commands

| Command | Description |
|---------|-------------|
| `/qadd` | Add a new quote with optional author |
| `/qremove` | Remove a quote by ID (permission-gated) |
| `/qedit` | Edit a quote's text or author (permission-gated) |
| `/qrandom` | Get a random quote, optionally filtered by author |
| `/qget` | Get a specific quote by ID |
| `/quser` | List all quotes by an author (paginated) |
| `/qsearch` | Search quotes by keyword (paginated) |
| `/qhelp` | Display bot usage guide |
