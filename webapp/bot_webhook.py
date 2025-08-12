import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, Update
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "changeme")
WEBAPP_PUBLIC = os.getenv("WEBAPP_PUBLIC", "")
WEBAPP_BUYER_URL = os.getenv("WEBAPP_BUYER_URL", f"{WEBAPP_PUBLIC}/web/buyer/")
WEBAPP_MERCHANT_URL = os.getenv("WEBAPP_MERCHANT_URL", f"{WEBAPP_PUBLIC}/web/merchant/")
BACKEND_PUBLIC = os.getenv("BACKEND_PUBLIC", "")
CORS = os.getenv("CORS_ORIGINS", "*")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env is required")
if not WEBAPP_PUBLIC:
    raise RuntimeError("WEBAPP_PUBLIC env is required")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
r = Router()
dp.include_router(r)

@r.message(F.text == "/start")
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛒 Покупатель", web_app=WebAppInfo(url=WEBAPP_BUYER_URL)),
        InlineKeyboardButton(text="👨‍🍳 Партнёр", web_app=WebAppInfo(url=WEBAPP_MERCHANT_URL)),
    ]])
    await message.answer("Привет! Выберите роль:", reply_markup=kb)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await bot.set_webhook(
        url=f"{WEBAPP_PUBLIC}/tg/webhook",
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=False
    )
    yield
    # Shutdown
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass

app = FastAPI(title="Foody Bot/WebApp", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS.split(",") if CORS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/tg/webhook")
async def tg_webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        raise HTTPException(403, "bad secret")
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/config.js")
def config_js():
    return Response(content=f"window.BACKEND_PUBLIC='{BACKEND_PUBLIC}';", media_type="application/javascript")

@app.get("/health")
async def health():
    info = await bot.get_webhook_info()
    return {"ok": True, "webhook_url": info.url}

# Dev helper (можно удалить на проде)
@app.get("/debug/wh")
async def debug_wh():
    info = await bot.get_webhook_info()
    return info.model_dump()

app.mount("/web", StaticFiles(directory="web", html=True), name="web")
