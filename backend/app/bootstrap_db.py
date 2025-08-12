import os, datetime as dt
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

async def run():
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    async with engine.begin() as conn:
        # tables
        await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS foody_restaurants(
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            lat DOUBLE PRECISION NULL,
            lng DOUBLE PRECISION NULL,
            api_key TEXT NULL
        );
        CREATE TABLE IF NOT EXISTS foody_offers(
            id TEXT PRIMARY KEY,
            restaurant_id TEXT REFERENCES foody_restaurants(id),
            title TEXT NOT NULL,
            price_cents INTEGER NOT NULL,
            qty_total INTEGER NOT NULL,
            qty_left INTEGER NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_offers_restaurant ON foody_offers(restaurant_id);
        CREATE INDEX IF NOT EXISTS idx_offers_expires ON foody_offers(expires_at);

        CREATE TABLE IF NOT EXISTS foody_reservations(
            id TEXT PRIMARY KEY,
            offer_id TEXT REFERENCES foody_offers(id),
            restaurant_id TEXT REFERENCES foody_restaurants(id),
            buyer_tg_id TEXT,
            code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'reserved',
            expires_at TIMESTAMPTZ NOT NULL,
            redeemed_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_res_restaurant ON foody_reservations(restaurant_id);
        CREATE INDEX IF NOT EXISTS idx_res_buyer ON foody_reservations(buyer_tg_id);
        CREATE INDEX IF NOT EXISTS idx_res_code ON foody_reservations(code);
        """))

        if os.getenv("SEED_DEMO", "0") == "1":
            await conn.execute(text("""
            INSERT INTO foody_restaurants(id, title, lat, lng)
            VALUES ('RID_DEMO','Демо-ресторан',55.751244,37.618423)
            ON CONFLICT (id) DO NOTHING;
            """))
            # one offer 2h ahead
            await conn.execute(text("""
            INSERT INTO foody_offers(id, restaurant_id, title, price_cents, qty_total, qty_left, expires_at)
            VALUES ('OFF_DEMO_1','RID_DEMO','Сеты к закрытию', 19900, 10, 10, NOW() + INTERVAL '2 hours')
            ON CONFLICT (id) DO NOTHING;
            """))
    await engine.dispose()
