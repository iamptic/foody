# main.py — Foody Backend v3 + admin /set_api_key
import os
from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware
from app.bootstrap_db import run as run_migrations
from app.features.offers_reservations_foody import router as offers_router

__version__ = "foody-backend-service-v3"

app = FastAPI(title="Foody Backend", version=__version__)

# --- CORS ---
cors_origins = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",")] if cors_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# --- Startup: миграции ---
@app.on_event("startup")
async def _run_migs():
    if os.getenv("RUN_MIGRATIONS", "1") == "1":
        await run_migrations()

# --- Основные роуты (offers / reservations / merchant) ---
app.include_router(offers_router)

# --- Health ---
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/")
def root():
    return {"ok": True, "service": "backend", "version": __version__}

# ---------------------------------------------------------------------
# Admin helper: вручную выставить api_key ресторану (если нет SQL-консоли)
# POST /api/v1/admin/set_api_key?token=<ADMIN_MIGRATE_TOKEN>
# body: {"restaurant_id":"RID_DEMO","api_key":"<ваш ключ>"}
# ---------------------------------------------------------------------
from typing import Optional
from fastapi import Query, Body, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

ADMIN_TOKEN = os.getenv("ADMIN_MIGRATE_TOKEN", "changeme")

_DB_URL = os.getenv("DATABASE_URL", "")
if _DB_URL.startswith("postgresql://"):
    _DB_URL = _DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

_engine_admin = create_async_engine(_DB_URL, echo=False, pool_pre_ping=True)

class _SetKeyIn(BaseModel):
    restaurant_id: str
    api_key: str

@app.post("/api/v1/admin/set_api_key")
async def set_api_key(token: str = Query(...), body: _SetKeyIn = Body(...)):
    if token != ADMIN_TOKEN:
        raise HTTPException(403, "forbidden")
    async with _engine_admin.begin() as conn:
        await conn.execute(
            text("UPDATE foody_restaurants SET api_key=:k WHERE id=:rid"),
            {"k": body.api_key, "rid": body.restaurant_id},
        )
    return {"ok": True, "restaurant_id": body.restaurant_id, "api_key": body.api_key}
