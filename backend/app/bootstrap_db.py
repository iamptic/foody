# app/bootstrap_db.py
import os, asyncio
from sqlalchemy.ext.asyncio import create_async_engine

async def run():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL env is required")
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True, future=True)

    schema_sql = '''
    CREATE TABLE IF NOT EXISTS foody_restaurants (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        lat DOUBLE PRECISION,
        lng DOUBLE PRECISION
    );
    CREATE TABLE IF NOT EXISTS foody_offers (
        id TEXT PRIMARY KEY,
        restaurant_id TEXT REFERENCES foody_restaurants(id),
        title TEXT NOT NULL,
        price_cents INTEGER NOT NULL,
        qty_total INTEGER NOT NULL DEFAULT 1,
        qty_left INTEGER NOT NULL DEFAULT 1,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_foody_offers_restaurant ON foody_offers(restaurant_id);
    CREATE INDEX IF NOT EXISTS idx_foody_offers_expires ON foody_offers(expires_at);

    CREATE TABLE IF NOT EXISTS foody_reservations (
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
    CREATE INDEX IF NOT EXISTS idx_foody_reservations_restaurant ON foody_reservations(restaurant_id);
    CREATE INDEX IF NOT EXISTS idx_foody_reservations_code ON foody_reservations(code);
    '''

    async with engine.begin() as conn:
        await conn.exec_driver_sql(schema_sql)

    if os.getenv("SEED_DEMO", "0") == "1":
        seed_sql = '''
        INSERT INTO foody_restaurants (id, title, lat, lng)
        VALUES ('RID_DEMO', 'DEMO Bakery', 55.751, 37.618)
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO foody_offers (id, restaurant_id, title, price_cents, qty_total, qty_left, expires_at)
        VALUES ('OFF_DEMO_1', 'RID_DEMO', 'Набор выпечки', 35000, 10, 10, NOW() AT TIME ZONE 'UTC' + INTERVAL '90 minutes')
        ON CONFLICT (id) DO NOTHING;
        '''
        async with engine.begin() as conn:
            await conn.exec_driver_sql(seed_sql)

if __name__ == "__main__":
    asyncio.run(run())
