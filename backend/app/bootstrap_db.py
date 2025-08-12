import os

async def _add_original_price(conn):
    try:
        await conn.exec_driver_sql("ALTER TABLE IF EXISTS foody_offers ADD COLUMN IF NOT EXISTS original_price_cents INTEGER NULL")
    except Exception:
        pass

from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL.startswith("postgresql://"):
    ASYNC_URL = "postgresql+asyncpg://" + DATABASE_URL.split("://",1)[1]
else:
    ASYNC_URL = DATABASE_URL.replace("sqlite://","sqlite+aiosqlite://")

engine: AsyncEngine = create_async_engine(ASYNC_URL, echo=False)

async def run():
    async with engine.begin() as conn:
        # core schema created elsewhere; here we do lightweight alter-s
        await conn.exec_driver_sql("ALTER TABLE IF EXISTS foody_offers ADD COLUMN IF NOT EXISTS original_price_cents INTEGER NULL")
        await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_fo_active ON foody_offers(expires_at)")
