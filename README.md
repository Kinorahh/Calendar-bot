# Calendar Bot

Discord calendar bot for weekly game/event schedules. Built in Python for Railway.

## What it does

- **Week calendar** (Mon–Sun) listing events under each day — no hour grid
- **Live calendar message** that refreshes when events are added/edited/removed
- **Week navigation** with Prev / This Week / Next buttons
- **Interest / RSVP** via `/event view` + ⭐ Interested button
- **Mods/admins only** for add / edit / remove (plus Manage Server / Administrator)
- **Monday snapshot** posted automatically to a channel you configure

> A full Discord Activity (iframe app like some games) can be a later phase. This bot covers the schedule, live updates, interest, and weekly posts from your chat.

## Commands

| Command | Who | What |
|---|---|---|
| `/calendar` | Everyone | Show this week + navigate weeks |
| `/post_calendar` | Mods | Pin a live updating calendar in a channel |
| `/event add` | Mods | Guided setup: name → date → time (24h) |
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
4. Under **Privileged Gateway Intents**, you can leave them **off** (this bot does not need them).
5. Left sidebar → **OAuth2** → **URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`, `Read Message History`, `View Channels`
6. Copy the generated URL, open it, invite the bot to your server.
7. Optional but recommended while testing: copy your server (guild) ID and set `GUILD_ID` so slash commands appear instantly.

## Railway setup

1. Go to [railway.com](https://railway.com) → **New Project** → **Deploy from GitHub repo** → select `Kinorahh/Calendar-bot`.
2. Railway should detect Python via Nixpacks. Start command is already in `railway.toml`:  
   `python -m bot.main`
3. Open the service → **Variables** and add:

| Variable | Example | Notes |
|---|---|---|
| `DISCORD_TOKEN` | `your bot token` | Required |
| `TIMEZONE` | `America/New_York` | Default week/Monday timezone if a server hasn't set one via `/setup` |
| `WEEKLY_POST_HOUR` | `9` | Local hour (0–23) for the Monday post |
| `ADMIN_ROLE_NAMES` | `Admin,Moderator,Mod` | Role names that can manage events |
| `DATABASE_PATH` | `/data/calendar.db` | Keep this if you mount a volume at `/data` |
| `GUILD_ID` | `123...` | Optional; faster command sync while developing |

4. **Persistent storage (important):**  
   Railway's filesystem is ephemeral. Add a **Volume** mounted at `/data` so events survive redeploys. Then keep `DATABASE_PATH=/data/calendar.db`.
5. Deploy. Check **Logs** for `Logged in as ...` and `Synced ... commands`.
6. In Discord:
   - `/setup timezone America/New_York` (or your TZ)
   - `/setup announce_channel #your-channel`
   - `/post_calendar` in the channel where the live week view should live
   - `/event add` then follow the private prompts (name → date → time like `22:00`)

## Local run (optional)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env — set DISCORD_TOKEN and DATABASE_PATH=./data/calendar.db
python -m bot.main
```

## Repo

https://github.com/Kinorahh/Calendar-bot
