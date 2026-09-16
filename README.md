# Calendar Bot

Discord calendar bot for weekly game/event schedules. Built in Python for Railway + PostgreSQL.

## What it does

- **Week calendar** (Mon–Sun) listing events under each day — no hour grid
- **Live calendar message** that refreshes when events are added/edited/removed
- **Week navigation** with Prev / This Week / Next buttons (Prev/Next = mods only)
- **Interest / RSVP** via `/event view` + ⭐ Interested button
- **Mods/admins only** for add / edit / remove (plus Manage Server / Administrator)
- **Monday snapshot** posted automatically to a channel you configure
- **PostgreSQL** on Railway so events survive restarts and you can browse past weeks

## Commands

| Command | Who | What |
|---|---|---|
| `/calendar` | Everyone | Show this week + navigate weeks |
| `/post_calendar` | Mods | Pin a live updating calendar in a channel |
| `/event add` | Mods | Private Proceed → one form (title, date, time) |
| `/event edit` | Mods | Edit an event by id |
| `/event remove` | Mods | Remove an event by id |
| `/event view` | Everyone | Event details + mark Interested |
| `/setup announce_channel` | Mods | Monday weekly post channel |
| `/setup timezone` | Mods | e.g. `America/New_York` |
| `/setup status` | Everyone | Show current settings |

Event ids appear on the calendar as `(#3)` next to each event.

## Discord setup

1. Open [Discord Developer Portal](https://discord.com/developers/applications) → **New Application** → name it (e.g. Calendar Bot).
2. Left sidebar → **Bot** → **Add Bot**.
3. Reset / copy the **Bot Token** — you'll put this in Railway as `DISCORD_TOKEN`.
4. Under **Privileged Gateway Intents**, you can leave them **off**.
5. Left sidebar → **OAuth2** → **URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`, `Read Message History`, `View Channels`
6. Copy the generated URL, open it, invite the bot to your server.
7. Optional but recommended: copy your server (guild) ID and set `GUILD_ID` so slash commands appear instantly.

## Railway setup (bot + Postgres)

### 1. Deploy the bot

1. [railway.com](https://railway.com) → **New Project** → **Deploy from GitHub repo** → `Kinorahh/Calendar-bot`.
2. Start command is in `railway.toml`: `python -m bot.main`

### 2. Add PostgreSQL

1. In the same Railway project, click **Create** → **Database** → **PostgreSQL**.
2. Wait until the Postgres service is online.
3. Open your **bot service** → **Variables**.
4. Click **+ New Variable** → **Add Reference** (or “Shared Variable” / variable reference).
5. Select the Postgres service’s **`DATABASE_URL`** and add it to the bot.
   - Variable name on the bot should be exactly `DATABASE_URL`.
6. You do **not** need a volume or `DATABASE_PATH` anymore when Postgres is connected.

### 3. Other bot variables

| Variable | Example | Notes |
|---|---|---|
| `DISCORD_TOKEN` | `your bot token` | Required |
| `DATABASE_URL` | *(from Postgres reference)* | Required on Railway |
| `TIMEZONE` | `America/New_York` | Default week/Monday timezone |
| `WEEKLY_POST_HOUR` | `9` | Local hour (0–23) for the Monday post |
| `ADMIN_ROLE_NAMES` | `Admin,Moderator,Mod` | Role names that can manage events |
| `GUILD_ID` | `123...` | Recommended for instant slash-command updates |

### 4. Redeploy and verify

1. Redeploy the bot (Railway usually does this when variables change).
2. In **Logs**, look for:
   - `Connected to PostgreSQL`
   - `Logged in as ...`
3. In Discord, re-run setup if needed (`/setup`, `/post_calendar`), then `/event add`.

Old SQLite data on the container disk is **not** migrated automatically — add events again (or ask for a one-time migration if you already have a lot).

## Local run (optional)

Without Postgres, the bot uses SQLite:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# set DISCORD_TOKEN; leave DATABASE_URL empty; optional DATABASE_PATH=./data/calendar.db
python -m bot.main
```

## Repo

https://github.com/Kinorahh/Calendar-bot
