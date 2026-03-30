# Discord Quote Bot 💬

A robust, highly interactive Discord bot designed to immortalize your community's best inside jokes and memorable moments. Built with modern Discord UI standards, it utilizes Slash Commands, Context Menus, Reaction listeners, and a highly optimized SQLite backend to ensure fast, reliable quote retrieval.

## ✨ Core Features

* **Frictionless Saving** — Save quotes actively via `/qadd`, instantly via right-clicking a message (`Apps -> Save Quote`), or passively by reacting to any message with a 🗣️ emoji.
* **Shareable Image Generation** — Use `/qimage` to instantly generate a custom, stylized PNG graphic of any quote (complete with circular avatars and dates) for easy sharing outside of Discord.
* **Hybrid Author Autocomplete** — Attributes quotes to active Discord members (via clickable `@User` pings) or legacy/non-Discord users. Slash commands feature dynamic database autocomplete for legacy names.
* **Smart UI & Interactive Pagination** — Browse quotes using numbered emoji buttons (1️⃣, 2️⃣, 3️⃣) to instantly expand list results into detailed, rich embeds.
* **Media Support** — Quotes aren't just text. Attach images via slash commands, context menus, or reactions, and the bot will archive and display the media alongside the quote.
* **Optimized Architecture** — Features a persistent database connection, stateless SQLite `LIMIT/OFFSET` pagination for low memory usage, duplicate-save prevention, global error handling, and automatic database schema migrations.
* **Role-Based Security** — Quotes can only be deleted (via an interactive confirmation prompt) or edited by the original submitter or a user with Server Administrator/Manage Messages permissions.

## 🛠️ Commands & Interactions

### Interactions
| Action | Description |
| :--- | :--- |
| **Reaction Save** | React to any message with 🗣️ to instantly save it. (Prevents duplicates automatically). |
| **Context Menu** | Right-click (or long-press) any message -> Apps -> `Save Quote`. |

### Slash Commands
| Command | Parameters | Description |
| :--- | :--- | :--- |
| `/qadd` | `text` `[author_user]` `[author_text]` `[attachment]` | Add a new quote manually. Provide either a Discord user or text name. |
| `/qimage` | `id` | Generates and uploads a stylized, shareable PNG graphic of a specific quote. |
| `/qremove` | `id` | Delete a quote by ID. Prompts a Red/Gray button confirmation screen. |
| `/qedit` | `id` `[text]` `[author_user]` `[author_text]` `[attachment]` | Edit an existing quote's text, author, or image. |
| `/qrandom` | `[author_user]` `[author_text]` | Pull a random quote, optionally filtered by a specific author. |
| `/qget` | `id` | Retrieve a specific quote by its server-scoped ID number. |
| `/quser` | `[author_user]` `[author_text]` | Browse all quotes attributed to a specific author (Interactive Paginator). |
| `/qsearch` | `keyword` | Search all quote text for a specific keyword (Interactive Paginator). |
| `/qhelp` | — | Display the bot usage guide and command syntax. |

## 🚀 Setup & Installation

### 1. Create the Discord Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Create a new Application, add a Bot, and copy the **Bot Token**.
3. Under **Privileged Gateway Intents**, enable **Server Members Intent** (for fetching avatars) and **Message Content Intent** (for reading text from reactions).
4. Go to **OAuth2 > URL Generator**, select the `bot` and `applications.commands` scopes, and grant *Manage Messages*, *Send Messages*, *Attach Files*, *Embed Links*, and *Use Slash Commands* permissions.

### 2. Local Environment
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

### 5. Run Tests

```bash
python -m pytest tests/ -v
```

22 tests covering all database CRUD operations, pagination, search, and edge cases.

## ☁️ Deployment (Railway)

The bot is configured for Railway with a `Procfile` and `runtime.txt`.

1. Connect your GitHub repo in [Railway](https://railway.com)
2. Add env var: `DISCORD_BOT_TOKEN`
3. Add a Volume mounted at `/data`
4. Add env var: `DB_PATH=/data/quotes.db`
5. Railway auto-deploys on every push

## 🏗️ Architecture

### Database (`database.py`)

- **Persistent connection** — A single `aiosqlite` connection is opened on startup and reused for all queries, avoiding per-request connection overhead.
- **SQL-level pagination** — Paginated commands (`/quser`, `/qsearch`) use `LIMIT`/`OFFSET` queries, fetching only the current page instead of loading all results into memory.
- **Indexed queries** — Indexes on `(server_id, quote_id)`, `(server_id, author_user_id)`, and `(server_id, author_name)` for fast lookups.
- **Auto-seeding** — On first startup, if `cleaned_quotes.json` exists and the database is empty, quotes are bulk-inserted automatically.

### Bot (`bot.py`)

- **Global error handler** — All slash command errors are caught, logged with traceback, and the user receives a clean ephemeral error message.
- **Embed formatting** — Citation-style embeds using a hanging em-dash (`***—*** Author`) for mobile-friendly rendering, with dynamic role colors from the quoted author's top role.
- **Graceful shutdown** — Database connection is closed on bot shutdown via the `on_close` event.

### Paginator (`paginator.py`)

- **Stateless design** — Each page turn calls a `fetch_page` callback to query the database, rather than holding all quotes in memory.
- **Author-locked navigation** — Only the user who ran the command can use the Previous/Next buttons.
- **Auto-disable on timeout** — Buttons are disabled after 2 minutes of inactivity.

## 🔧 Data Migration Tools

For migrating quotes from an older bot:

| Script | Purpose |
|--------|---------|
| `scraper.py` | Searches Discord message history via the search API for old bot embeds, exports to JSON/TXT |
| `csv_to_json.py` | Converts a CSV of quotes (with Discord user IDs) to `cleaned_quotes.json` |
| `import_quotes.py` | Cleans scraped data, detects duplicates, and imports into the database |

Place `cleaned_quotes.json` in the repo root and the bot will auto-seed on first startup if the database is empty.

## 📁 Project Structure

```
bot.py              # Main bot — slash commands, embeds, event handlers
database.py         # Async SQLite layer — CRUD, pagination, auto-seed
paginator.py        # Stateless paginated embed UI with Previous/Next buttons
scraper.py          # Discord search API scraper for legacy quote migration
csv_to_json.py      # CSV-to-JSON converter for quote data
import_quotes.py    # Data cleaning, dedup, and database import tool
tests/              # Database unit tests (22 tests)
Procfile            # Railway deployment config
runtime.txt         # Python version for Railway
requirements.txt    # Python dependencies
.env.example        # Environment variable template
```

## 💡 Next Phase Ideas

### 1. Quote Reactions and Favorites
Let users react to a quote with a star or emoji to "favorite" it. Add `/qfavorites` to show a user's saved quotes and `/qtop` to display the most-favorited quotes in the server. Tracks engagement and surfaces the best content.

### 2. Quote of the Day
Scheduled daily post to a designated channel with a random quote. Configurable via `/qotd set #channel` and `/qotd disable`. Uses a background task loop. Keeps the server active and resurfaces old quotes.

### 3. Author Leaderboard and Stats
Add `/qstats` to show server-wide quote statistics: most quoted author, most active adder, total quote count, quotes per month. Add `/qstats @user` for individual breakdowns. Gives the community a fun competitive element.

### 4. Quote Tags and Categories
Allow optional tags when adding quotes (`/qadd text:"..." author:@user tags:"funny, sports"`). Add `/qtag funny` to browse by tag. Enables better organization and discovery beyond keyword search, especially as the quote count grows.

### 5. Multi-Format Export
Add `/qexport` (admin-only) to export all server quotes as a downloadable CSV or JSON file attachment. Useful for backups, migration to another bot, or archiving. Could also support `/qimport` to bulk-load from an uploaded file directly in Discord.
