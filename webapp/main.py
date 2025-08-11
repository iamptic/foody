# main.py — WebApp + Bot Service
import os
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.bot_webhook import bot, dp

__version__ = "foody-webapp-bot-2025-08-12"

app = FastAPI(title="Foody WebApp+Bot", version=__version__)

cors_origins = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",")] if cors_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static MiniApp pages
app.mount("/web", StaticFiles(directory="webapp", html=True), name="web")

BACKEND_PUBLIC = os.getenv("BACKEND_PUBLIC", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "foodySecret123")

@app.get("/config.js")
def config_js():
    js = f"window.BACKEND_PUBLIC={BACKEND_PUBLIC!r};"
    return Response(js, media_type="application/javascript")

@app.on_event("startup")
async def _startup():
    # set webhook
    url = os.getenv("WEBAPP_PUBLIC", "") or os.getenv("BACKEND_PUBLIC", "")
    # prefer explicit WEBAPP_PUBLIC; fallback to BACKEND_PUBLIC if same domain
    if not url:
        # Best effort guess from Render/Railway envs, leave empty otherwise
        pass
    webhook_url = (url.rstrip("/")) + "/tg/webhook"
    await bot.set_webhook(url=webhook_url, secret_token=WEBHOOK_SECRET)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/tg/webhook")
async def tg_webhook(request: Request):
    secret = request.headers.get("x-telegram-bot-api-secret-token", "")
    if secret != WEBHOOK_SECRET:
        raise HTTPException(403, "forbidden")
    from aiogram.types import Update
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
def root():
    return {"ok": True, "service": "webapp-bot", "version": __version__}
