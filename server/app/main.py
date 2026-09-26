from fastapi import FastAPI

from app.api import discord_dir, items, settings as settings_api, watches

# No auth by design: reachable only over Tailscale, single user. The client's
# nginx proxies /api here, so no CORS is needed either.
app = FastAPI(title="discord_watch API")

app.include_router(items.router)
app.include_router(watches.router)
app.include_router(discord_dir.router)
app.include_router(settings_api.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
