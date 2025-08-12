
import os, json, traceback, logging
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("foody-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "foodySecret123")
WEBAPP_PUBLIC = os.getenv("WEBAPP_PUBLIC", "https://example.com")
WEBAPP_BUYER_URL = os.getenv("WEBAPP_BUYER_URL", f"{WEBAPP_PUBLIC}/web/buyer/")
WEBAPP_MERCHANT_URL = os.getenv("WEBAPP_MERCHANT_URL", f"{WEBAPP_PUBLIC}/web/merchant/")

if not BOT_TOKEN:
    log.warning("BOT_TOKEN is empty — Telegram replies will fail.")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = FastAPI()

@app.get("/health")
async def health(): 
    return {"ok": True}

def kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛒 Витрина", web_app=WebAppInfo(url=WEBAPP_BUYER_URL)),
        InlineKeyboardButton(text="👨‍🍳 ЛК партнёра", web_app=WebAppInfo(url=WEBAPP_MERCHANT_URL))
    ]])

@dp.message(CommandStart())
async def start(m):
    log.info("Handling /start from chat %s", m.chat.id)
    await m.answer("Привет! Я помогу спасти еду 💚\nВыбери раздел:", reply_markup=kb())

@app.post("/tg/webhook")
async def tg_webhook(request: Request):
    sec = request.headers.get("x-telegram-bot-api-secret-token")
    if sec != WEBHOOK_SECRET:
        log.warning("Bad secret header: got=%r expected=%r", sec, WEBHOOK_SECRET)
        raise HTTPException(401, "bad secret")
    data = await request.json()
    try:
        upd = Update.model_validate(data)
        kind = "unknown"
        if upd.message and upd.message.text:
            kind = f"message:{upd.message.text[:50]}"
        log.info("Incoming update: %s", kind)
        await dp.feed_update(bot, upd)
        return "OK"
    except Exception as e:
        log.error("feed_update error: %s\n%s", e, traceback.format_exc())
        # Возвращаем 200, чтобы Telegram не ретраил бесконечно
        return "OK"
