# Calendar Bot

Discord calendar bot for weekly game/event schedules. Built in Python for Railway + PostgreSQL.

## What it does

- **Week calendar** (Mon–Sun) listing events under each day — no hour grid
- **Live calendar message** that refreshes when events are added/edited/removed
- **Week navigation** with Prev / This Week / Next buttons (Prev/Next = admin roles only)
- **Match scheduling** via `/create match` for everyone (user vs user or role vs role)
- **Admin-role gated** management commands; match participants can edit/remove their own match
- **Monday auto-advance** of the live calendar to the current week
- **PostgreSQL** on Railway so events survive restarts and you can browse past weeks

## Commands

| Command | Who | What |
|---|---|---|
| `/post_calendar` | Admins | Pin a live updating calendar in a channel |
| `/create match` | Everyone | Schedule a match (two users or two roles) → date/time form |
| `/event add` | Admins | Private Proceed → one form (title, date, time) |
| `/event edit` | Admins or match participants | Edit date and/or time by id |
| `/event remove` | Admins or match participants | Remove an event by id |
| `/setup timezone` | Admins | e.g. `America/New_York` |
| `/setup status` | Admins | Show current settings |

Admin roles are configured with `ADMIN_ROLE_NAMES` (default: Admin, Moderator, Mod, Calendar Admin).

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
| `MATCH_CHANNEL_ID` | `123...` | Channel for `/create match` + match ping posts |
| `ADMIN_ROLE_NAMES` | `Admin,Moderator,Mod` | Role names that can manage the calendar |
| `GUILD_ID` | `123...` | Recommended for instant slash-command updates |

### 4. Redeploy and verify

1. Redeploy the bot (Railway usually does this when variables change).
2. In **Logs**, look for:
   - `Connected to PostgreSQL`
   - `Logged in as ...`
3. In Discord, re-run setup if needed (`/setup timezone`, `/post_calendar`), then `/event add` or `/create match`.

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
