import os, secrets
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from app.bootstrap_db import run as run_migrations
from app.features.offers_reservations_foody import router as offers_router, merchant as merchant_router
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

__version__ = "foody-backend-service-v3-2025-08-11T23:41:04.349025"

app = FastAPI(title="Foody Backend", version=__version__)

cors_origins = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",")] if cors_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _run_migs():
    if os.getenv("RUN_MIGRATIONS", "1") == "1":
        await run_migrations()

app.include_router(offers_router)
app.include_router(merchant_router)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/")
def root():
    return {"ok": True, "service": "backend", "version": __version__}

ADMIN_MIGRATE_TOKEN = os.getenv("ADMIN_MIGRATE_TOKEN", "")

@app.post("/admin/generate_api_key")
async def gen_key(restaurant_id: str = Query(...), token: str = Query(...)):
    if not ADMIN_MIGRATE_TOKEN or token != ADMIN_MIGRATE_TOKEN:
        raise HTTPException(403, "forbidden")
    db_url = os.environ.get("DATABASE_URL")
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True, future=True)
    key = secrets.token_urlsafe(24).replace("-", "_")
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as s:
        await s.execute(text("UPDATE foody_restaurants SET api_key=:k WHERE id=:rid").bindparams(k=key, rid=restaurant_id))
        await s.commit()
    return {"restaurant_id": restaurant_id, "api_key": key}
