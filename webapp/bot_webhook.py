import os, asyncio, logging, json
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET","foodySecret123")
WEBAPP_PUBLIC = os.getenv("WEBAPP_PUBLIC","")
BACKEND_PUBLIC = os.getenv("BACKEND_PUBLIC","")
WEBAPP_BUYER_URL = os.getenv("WEBAPP_BUYER_URL", WEBAPP_PUBLIC + "/web/buyer/")
WEBAPP_MERCHANT_URL = os.getenv("WEBAPP_MERCHANT_URL", WEBAPP_PUBLIC + "/web/merchant/")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🧑‍🍳 ЛК партнёра", web_app=WebAppInfo(url=WEBAPP_MERCHANT_URL)),
        InlineKeyboardButton(text="🛒 Витрина", web_app=WebAppInfo(url=WEBAPP_BUYER_URL)),
    ]])
    await message.answer(
        "Привет! Это Foody — спасаем еду со скидкой.
Выбери, что открыть:",
        reply_markup=kb
    )

async def handle_webhook(request: web.Request):
    # Verify secret token
    secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret != WEBHOOK_SECRET:
        return web.Response(status=403, text="forbidden")
    data = await request.json()
    update = types.Update(**data)
    await dp.feed_update(bot, update)
    return web.Response(text="OK")

# --- Web / Health / Config
async def handle_health(request: web.Request):
    return web.json_response({"ok": True})

async def handle_root(request: web.Request):
    return web.Response(text="Foody Bot/WebApp OK")

async def handle_config_js(request: web.Request):
    js = f"window.BACKEND_PUBLIC='{BACKEND_PUBLIC}';"
    return web.Response(text=js, content_type="application/javascript")

# Static web serving
STATIC_DIR = os.path.join(os.path.dirname(__file__), "web")

async def on_startup(app: web.Application):
    # set webhook
    url = WEBAPP_PUBLIC.rstrip("/") + "/tg/webhook"
    try:
        await bot.set_webhook(url=url, secret_token=WEBHOOK_SECRET)
        logging.info("Webhook set to %s", url)
    except Exception as e:
        logging.exception("set_webhook failed: %s", e)

async def on_cleanup(app: web.Application):
    await bot.session.close()

def make_app():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/config.js", handle_config_js)
    app.router.add_post("/tg/webhook", handle_webhook)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_static("/web/", STATIC_DIR, show_index=True)
    return app

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    web.run_app(make_app(), host="0.0.0.0", port=port)
