# discord_watch

A self-hosted Discord triage dashboard. It watches the channels you pick, all of your DMs, and friend and message requests. A small **local** model (Ollama, CPU-only) judges each message against plain-English criteria you write for each section. Anything worth your attention lands in a private web inbox with browser notifications.

Everything runs on your own machine. No message content leaves it.

```
Discord gateway ──> listener ──> Postgres <── classifier ──> Ollama (host, CPU)
                                    │
                         server (FastAPI) <── client (React, nginx :8095) <── you, over Tailscale
```

| service | what it does |
|---|---|
| `listener` | Holds one passive, read-only Discord session and stores only messages from watched sections. |
| `classifier` | Every ~45s, sends pending messages to Ollama in small per-channel batches and saves each verdict: `ignore` / `fyi` / `important` / `urgent`, plus "needs reply" and a one-line reason. |
| `server` | REST API; runs migrations on boot. |
| `client` | The dashboard: inbox, per-section criteria editor with a dry-run tester, settings. |
| `postgres` | Storage. Unimportant items are purged after 14 days (configurable). |

## ⚠️ This uses your user account (read this)

Bots can't see your DMs or friend and message requests, so the listener logs in **as you**, with your user token, using [`discord.py-self`](https://github.com/dolfies/discord.py-self). Automating a user account is against Discord's Terms of Service, and accounts *can* be banned for it. Bans overwhelmingly hit selfbots that **do** things: auto-replies, mass DMs, joining servers, spam, and scraping history. This one is built to be as passive as possible:

- **It never sends anything.** No messages, reactions, typing, or presence changes.
- **It never marks anything as read**, so your unread badges in the real app are untouched.
- **No polling.** Discord pushes events over the gateway to every logged-in session, the same way it does to your phone. There's nothing to poll.
- **The only extra API calls** are a startup catch-up (watched channels only, ≤25 newest messages each, at most 30 channels, one at a time with 2–4s gaps; you can turn it off in Settings) and one profile lookup per *new* friend request, the same one the app makes when you open it.

### Muted channels and "read elsewhere"

- **While the listener is running**, every message in a watched channel is seen live, muted or not. Muting only changes notifications, not what Discord sends to the session.
- **The startup catch-up** normally fetches only channels Discord marks as unread. That misses channels you never see as unread: muted ones, or ones you read on your phone while the PC was off.
- **To catch those too**, tick **"Always catch up after downtime"** on the section. It then fetches whatever arrived since the listener last ran, looking back at most 3 days, whether or not it shows as unread.

It's still your call and your account.

## Setup

**Requirements:** Docker Desktop, [Ollama](https://ollama.com) running on the host, and Tailscale if you want to reach it from other devices.

1. **Pull the model:**
   ```sh
   ollama pull qwen2.5:3b-instruct-q4_K_M
   ```
2. **Configure:**
   ```sh
   cp .env.example .env   # then set DB_PASSWORD and DISCORD_TOKEN
   ```
3. **Getting your token:** open <https://discord.com/app> in a desktop browser and open DevTools (F12) → **Network**. Filter by `api`, click around Discord, select any request to `discord.com/api/...`, and copy the **`Authorization`** request header. Treat it like your password: anyone who has it has your account. Changing your password invalidates it.
4. **Start:**
   ```sh
   docker compose up -d --build
   ```
   Open <http://localhost:8095>. The status pill turns green once Discord is connected and the classifier has run. Every service is `restart: unless-stopped`, so it comes back whenever Docker does.
5. **Configure what to watch:**
   - On the **Watching** page, add channels (or **a whole server** at once) and write what "important" means for each one. DMs and requests are already there with starter criteria. A channel watched on its own overrides its server's criteria. In a whole-server section you can untick individual channels or entire categories to leave them out; an excluded category also covers channels added to it later.
   - Use **Test criteria** to see how the model would judge recent messages under your wording. It's a dry run, so nothing is saved.
   - In **Settings → About me**, give the model some context about you.

## Access over Tailscale, with notifications

Plain `http://<tailscale-ip>:8095` works, but browsers only allow notifications on HTTPS pages. Tailscale can provide HTTPS:

```sh
tailscale serve --bg --https=8443 http://localhost:8095
```

Then open `https://<machine>.<tailnet>.ts.net:8443` and click **Enable notifications**. This needs MagicDNS and HTTPS certificates enabled in the Tailscale admin console. Without HTTPS you still get the unread count in the tab title and on the favicon.

## Why it's unnoticeable during normal use

- The model runs with `num_gpu: 0`, so it uses **no VRAM**. Games and other GPU models are unaffected.
- CPU work is capped by the thread count in Settings (default 4), and happens in short bursts only when new messages arrive.
- The model unloads from RAM (~2.4 GB) after 2 minutes idle (the `keep_alive` setting).
- A batch of a few messages takes a handful of seconds on CPU.

## Development

```sh
docker compose run --rm server pytest   # server tests
cd client && npm install && npm run dev # Vite dev server on :5173 (proxies /api to :8000)
```

Classification logic that doesn't do I/O (prompt building, guardrails, routing, backfill decisions) is kept separate in `server/app/classifier/prompt.py` and `server/app/listener/routing.py`, and that's what the tests cover.

Schema changes: edit `server/app/models/`, then run:

```sh
docker compose run --rm -v "$PWD/server:/app" server alembic revision --autogenerate -m "..."
```

Migrations run automatically when the server starts.
