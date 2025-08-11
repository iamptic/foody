import os
from aiogram import Bot, Dispatcher
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_BUYER_URL = os.getenv("WEBAPP_BUYER_URL", "https://example.com/web/buyer/")
WEBAPP_MERCHANT_URL = os.getenv("WEBAPP_MERCHANT_URL", "https://example.com/web/merchant/")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env is required")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def on_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="👨‍🍳 ЛК партнёра", web_app=WebAppInfo(url=f"{WEBAPP_MERCHANT_URL}")),
        InlineKeyboardButton(text="🛒 Витрина", web_app=WebAppInfo(url=f"{WEBAPP_BUYER_URL}"))
    ]])
    await message.answer("Foody к вашим услугам 👋", reply_markup=kb)
