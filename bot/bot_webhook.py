
import os, logging, traceback
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramAPIError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("foody-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "foodySecret123")
WEBAPP_PUBLIC = os.getenv("WEBAPP_PUBLIC", "https://example.com").rstrip("/")
WEBAPP_BUYER_URL = os.getenv("WEBAPP_BUYER_URL", f"{WEBAPP_PUBLIC}/web/buyer/")
WEBAPP_MERCHANT_URL = os.getenv("WEBAPP_MERCHANT_URL", f"{WEBAPP_PUBLIC}/web/merchant/")

def _https(u:str)->str:
    u = (u or "").strip()
    if not u: return ""
    if u.startswith("http://"): u = "https://" + u[7:]
    if not u.startswith("http"): u = "https://" + u.lstrip('/')
    return u

WEBAPP_BUYER_URL = _https(WEBAPP_BUYER_URL)
WEBAPP_MERCHANT_URL = _https(WEBAPP_MERCHANT_URL)

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = FastAPI()

@app.get("/health")
async def health(): return {"ok": True}

def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🛒 Витрина", web_app=WebAppInfo(url=WEBAPP_BUYER_URL)),
        InlineKeyboardButton(text="👨‍🍳 ЛК партнёра", web_app=WebAppInfo(url=WEBAPP_MERCHANT_URL))
    ]])

@dp.message(CommandStart())
async def start(m):
    # parse deep-link payload after /start
    payload = None
    if m.text and " " in m.text:
        payload = m.text.split(" ",1)[1].strip()
    if payload and payload.startswith("offer_"):
        offer_id = payload.split("offer_",1)[1]
        open_btn = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Открыть предложение", web_app=WebAppInfo(url=f"{WEBAPP_BUYER_URL}?offer={offer_id}"))
        ]])
        try:
            await m.answer("Вот предложение 👇", reply_markup=open_btn)
            return
        except Exception as e:
            log.error("send deeplink failed: %s", e)
            try:
                await m.answer(f"Открыть предложение: {WEBAPP_BUYER_URL}?offer={offer_id}")
                return
            except Exception:
                pass
    # default menu
    await m.answer("Привет! Я помогу спасти еду 💚\nВыбери раздел:", reply_markup=kb_main())

@app.post("/tg/webhook")
async def tg_webhook(request: Request):
    if request.headers.get("x-telegram-bot-api-secret-token") != WEBHOOK_SECRET:
        raise HTTPException(401, "bad secret")
    data = await request.json()
    try:
        upd = Update.model_validate(data)
        await dp.feed_update(bot, upd)
        return "OK"
    except Exception as e:
        log.error("feed_update error: %s\n%s", e, traceback.format_exc())
        return "OK"
