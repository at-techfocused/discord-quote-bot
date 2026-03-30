# Discord Quote Bot

A Discord bot for storing, managing, and retrieving user-generated quotes. Supports both active Discord members and legacy/non-Discord authors, with full multi-server data isolation.

## Features

- **8 Slash Commands** — Add, remove, edit, search, and browse quotes
- **Multi-Server Isolation** — Quotes are scoped per server with independent sequential IDs
- **Hybrid Author System** — Supports both `@User` mentions (stored as Discord IDs, rendered as clickable pings) and plain text names for legacy/non-Discord authors
- **Paginated Results** — Interactive Previous/Next buttons for browsing large result sets
- **Permission System** — Only the quote adder or users with Admin/Manage Messages can edit/remove
- **Rich Embeds** — Citation-style formatting, dynamic role-based border colors, author avatar thumbnails, Discord-native timestamps
- **Legacy Data Import** — Tools to scrape and migrate quotes from older bots

## Commands

| Command | Parameters | Description |
|---------|-----------|-------------|
| `/qadd` | `text` `[author_user]` `[author_text]` | Add a new quote (max 1000 chars). Provide either a Discord user or text name as author. |
| `/qremove` | `id` | Remove a quote by ID. Requires being the adder or having Manage Messages/Admin. |
| `/qedit` | `id` `[text]` `[author_user]` `[author_text]` | Edit a quote's text or author. Same permissions as `/qremove`. |
| `/qrandom` | `[author_user]` `[author_text]` | Pull a random quote, optionally filtered by author. |
| `/qget` | `id` | Retrieve a specific quote by its server-scoped ID. |
| `/quser` | `[author_user]` `[author_text]` | List all quotes by an author (paginated). |
| `/qsearch` | `keyword` | Search quote text by keyword (paginated). |
| `/qhelp` | — | Display the bot usage guide. |

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new Application and add a Bot
3. Copy the **Bot Token**
4. Under **Privileged Gateway Intents**, enable **Server Members Intent** (needed for avatar/role color lookups)
5. Go to **OAuth2 > URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: Send Messages, Embed Links, Use Slash Commands
6. Copy the generated URL, open it in your browser, and invite the bot to your server

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

### 4. Run

```bash
python bot.py
```

The bot automatically creates the SQLite database, syncs slash commands, and seeds any legacy data from `cleaned_quotes.json` on first run.

## Deployment (Railway)

The bot is configured for Railway with a `Procfile` and `runtime.txt`.

1. Connect your GitHub repo in [Railway](https://railway.com)
2. Add env var: `DISCORD_BOT_TOKEN`
3. Add a Volume mounted at `/data`
4. Add env var: `DB_PATH=/data/quotes.db`
5. Railway auto-deploys on every push

## Data Migration Tools

For migrating quotes from an older bot:

| Script | Purpose |
|--------|---------|
| `scraper.py` | Searches Discord message history via the search API for old bot embeds, exports to JSON/TXT |
| `csv_to_json.py` | Converts a CSV of quotes (with Discord user IDs) to `cleaned_quotes.json` |
| `import_quotes.py` | Cleans scraped data, detects duplicates, and imports into the database |

Place `cleaned_quotes.json` in the repo root and the bot will auto-seed on first startup if the database is empty.

## Project Structure

```
bot.py              # Main bot — slash commands, embeds, event handlers
database.py         # Async SQLite layer — CRUD operations, auto-seed
paginator.py        # Paginated embed UI with Previous/Next buttons
scraper.py          # Discord search API scraper for legacy quote migration
csv_to_json.py      # CSV-to-JSON converter for quote data
import_quotes.py    # Data cleaning, dedup, and database import tool
tests/              # Database unit tests (22 tests)
Procfile            # Railway deployment config
runtime.txt         # Python version for Railway
```

## Next Phase Ideas

### 1. Quote Reactions and Favorites
Let users react to a quote with a star or emoji to "favorite" it. Add `/qfavorites` to show a user's saved quotes and `/qtop` to display the most-favorited quotes in the server. Tracks engagement and surfaces the best content.

### 2. Quote of the Day
Scheduled daily post to a designated channel with a random quote. Configurable via `/qotd set #channel` and `/qotd disable`. Uses Discord scheduled events or a background task loop. Keeps the server active and resurfaces old quotes.

### 3. Author Leaderboard and Stats
Add `/qstats` to show server-wide quote statistics: most quoted author, most active adder, total quote count, quotes per month graph. Add `/qstats @user` for individual breakdowns. Gives the community a fun competitive element.

### 4. Quote Tags and Categories
Allow optional tags when adding quotes (`/qadd text:"..." author:@user tags:"funny, sports"`). Add `/qtag funny` to browse by tag. Enables better organization and discovery beyond keyword search, especially as the quote count grows.

### 5. Multi-Format Export
Add `/qexport` (admin-only) to export all server quotes as a downloadable CSV or JSON file attachment. Useful for backups, migration to another bot, or archiving. Could also support `/qimport` to bulk-load from an uploaded file directly in Discord.
