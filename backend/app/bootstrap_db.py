import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def run():
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    async with engine.begin() as conn:
        # Tables
        await conn.execute(text("""                CREATE TABLE IF NOT EXISTS foody_restaurants (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                lat DOUBLE PRECISION NULL,
                lng DOUBLE PRECISION NULL,
                api_key TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""))
        await conn.execute(text("""                CREATE TABLE IF NOT EXISTS foody_offers (
                id TEXT PRIMARY KEY,
                restaurant_id TEXT REFERENCES foody_restaurants(id),
                title TEXT NOT NULL,
                price_cents INTEGER NOT NULL,
                qty_total INTEGER NOT NULL,
                qty_left INTEGER NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""))
        await conn.execute(text("""                CREATE TABLE IF NOT EXISTS foody_reservations (
                id TEXT PRIMARY KEY,
                offer_id TEXT REFERENCES foody_offers(id),
                restaurant_id TEXT REFERENCES foody_restaurants(id),
                buyer_tg_id TEXT,
                code TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'reserved',
                expires_at TIMESTAMPTZ NOT NULL,
                redeemed_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""))

        # --- Safe column migrations (idempotent) ---
        # restaurants
        await conn.execute(text("ALTER TABLE foody_restaurants ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT 'Restaurant'"))
        await conn.execute(text("ALTER TABLE foody_restaurants ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION"))
        await conn.execute(text("ALTER TABLE foody_restaurants ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION"))
        await conn.execute(text("ALTER TABLE foody_restaurants ADD COLUMN IF NOT EXISTS api_key TEXT"))
        await conn.execute(text("ALTER TABLE foody_restaurants ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"))
        # offers
        await conn.execute(text("ALTER TABLE foody_offers ADD COLUMN IF NOT EXISTS restaurant_id TEXT"))
        await conn.execute(text("ALTER TABLE foody_offers ADD COLUMN IF NOT EXISTS title TEXT"))
        await conn.execute(text("ALTER TABLE foody_offers ADD COLUMN IF NOT EXISTS price_cents INTEGER"))
        await conn.execute(text("ALTER TABLE foody_offers ADD COLUMN IF NOT EXISTS qty_total INTEGER"))
        await conn.execute(text("ALTER TABLE foody_offers ADD COLUMN IF NOT EXISTS qty_left INTEGER"))
        await conn.execute(text("ALTER TABLE foody_offers ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE foody_offers ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"))
        # reservations
        await conn.execute(text("ALTER TABLE foody_reservations ADD COLUMN IF NOT EXISTS offer_id TEXT"))
        await conn.execute(text("ALTER TABLE foody_reservations ADD COLUMN IF NOT EXISTS restaurant_id TEXT"))
        await conn.execute(text("ALTER TABLE foody_reservations ADD COLUMN IF NOT EXISTS buyer_tg_id TEXT"))
        await conn.execute(text("ALTER TABLE foody_reservations ADD COLUMN IF NOT EXISTS code TEXT"))
        await conn.execute(text("ALTER TABLE foody_reservations ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'reserved'"))
        await conn.execute(text("ALTER TABLE foody_reservations ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ"))
        await conn.execute(text("ALTER TABLE foody_reservations ADD COLUMN IF NOT EXISTS redeemed_at TIMESTAMPTZ NULL"))
        await conn.execute(text("ALTER TABLE foody_reservations ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"))

        # Indexes
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rest_api_key ON foody_restaurants(api_key)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_offers_rest ON foody_offers(restaurant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_offers_exp ON foody_offers(expires_at)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_res_rest ON foody_reservations(restaurant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_res_code ON foody_reservations(code)"))

        # Seed demo (first run only if env flag set)
        if os.getenv("SEED_DEMO","0") == "1":
            await conn.execute(text("""                  INSERT INTO foody_restaurants (id, title, lat, lng)
              VALUES ('RID_DEMO','Demo Bakery',55.75,37.62)
              ON CONFLICT (id) DO NOTHING;"""))
            await conn.execute(text("""                  INSERT INTO foody_offers (id, restaurant_id, title, price_cents, qty_total, qty_left, expires_at)
              VALUES ('OFF_DEMO_1','RID_DEMO','Набор выпечки',29900,10,10, NOW() + INTERVAL '3 HOURS')
              ON CONFLICT (id) DO NOTHING;"""))
