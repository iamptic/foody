import os
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, Update
from aiogram.enums import ParseMode

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "changeme")
WEBAPP_PUBLIC = os.getenv("WEBAPP_PUBLIC", "")
WEBAPP_BUYER_URL = os.getenv("WEBAPP_BUYER_URL", f"{WEBAPP_PUBLIC}/web/buyer/")
WEBAPP_MERCHANT_URL = os.getenv("WEBAPP_MERCHANT_URL", f"{WEBAPP_PUBLIC}/web/merchant/")
BACKEND_PUBLIC = os.getenv("BACKEND_PUBLIC", "")
CORS = os.getenv("CORS_ORIGINS", "*")

app = FastAPI(title="Foody Bot/WebApp")
app.add_middleware(CORSMiddleware, allow_origins=CORS.split(",") if CORS else ["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)
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

@app.on_event("startup")
async def on_startup():
    if not BOT_TOKEN or not WEBAPP_PUBLIC:
        raise RuntimeError("BOT_TOKEN and WEBAPP_PUBLIC must be set")
    await bot.set_webhook(url=f"{WEBAPP_PUBLIC}/tg/webhook", secret_token=WEBHOOK_SECRET, drop_pending_updates=False)

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
def health():
    return {"ok": True, "webhook": f"{WEBAPP_PUBLIC}/tg/webhook"}

app.mount("/web", StaticFiles(directory="web", html=True), name="web")
