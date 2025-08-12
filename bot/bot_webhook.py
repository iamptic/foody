import os
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "foodySecret123")
WEBAPP_PUBLIC = os.getenv("WEBAPP_PUBLIC", "https://example.com")
WEBAPP_BUYER_URL = os.getenv("WEBAPP_BUYER_URL", f"{WEBAPP_PUBLIC}/web/buyer/")
WEBAPP_MERCHANT_URL = os.getenv("WEBAPP_MERCHANT_URL", f"{WEBAPP_PUBLIC}/web/merchant/")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = FastAPI()

@app.get("/health")
async def health(): return {"ok": True}

def kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛒 Витрина", web_app=WebAppInfo(url=WEBAPP_BUYER_URL)),
        InlineKeyboardButton(text="👨‍🍳 ЛК партнёра", web_app=WebAppInfo(url=WEBAPP_MERCHANT_URL))
    ]])

@dp.message(CommandStart())
async def start(m):
    await m.answer("Привет! Я помогу спасти еду 💚\nВыбери раздел:", reply_markup=kb())

@app.post("/tg/webhook")
async def tg_webhook(request: Request):
    if request.headers.get("x-telegram-bot-api-secret-token") != WEBHOOK_SECRET:
        raise HTTPException(401, "bad secret")
    data = await request.json()
    await dp.feed_update(bot, Update.model_validate(data))
    return "OK"
