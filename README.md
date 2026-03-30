# Discord Quote Bot 💬

A robust, highly interactive Discord bot designed to immortalize your community's best inside jokes and memorable moments. Built with modern Discord UI standards, it utilizes Slash Commands, Context Menus, Reaction listeners, and a highly optimized SQLite backend to ensure fast, reliable quote retrieval.

## ✨ Core Features

* **Frictionless Saving** — Save quotes actively via `/qadd`, instantly via right-clicking a message (`Apps -> Save Quote`), or passively by reacting to any message with a 🗣️ emoji.
* **Shareable Image Generation** — Use `/qimage` to instantly generate a custom, stylized PNG graphic of any quote (complete with circular avatars and dates) for easy sharing outside of Discord.
* **Hybrid Author Autocomplete** — Attributes quotes to active Discord members (via clickable `@User` pings) or legacy/non-Discord users. Slash commands feature dynamic database autocomplete for legacy names.
* **Smart UI & Interactive Pagination** — Browse quotes using numbered emoji buttons (1️⃣, 2️⃣, 3️⃣) to instantly expand list results into detailed, rich embeds. 
* **Media Support** — Quotes aren't just text. Attach images via slash commands, context menus, or reactions, and the bot will archive and display the media alongside the quote.
* **Optimized Architecture** — Features stateless SQLite `LIMIT/OFFSET` pagination for low memory usage, duplicate-save prevention, and automatic database schema migrations.
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