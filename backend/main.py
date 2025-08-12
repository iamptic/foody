# main.py — Foody Backend v3 + admin + debug
import os, time
from fastapi import FastAPI, Query, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.bootstrap_db import run as run_migrations
from app.features.offers_reservations_foody import router as offers_router
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

__version__ = "foody-backend-service-v5"

app = FastAPI(title="Foody Backend", version=__version__)

# CORS
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

# Startup migrations
@app.on_event("startup")
async def _run_migs():
    if os.getenv("RUN_MIGRATIONS", "1") == "1":
        await run_migrations()

# Routers
app.include_router(offers_router)

# Health & root
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/")
def root():
    return {"ok": True, "service": "backend", "version": __version__}

# Admin set_api_key
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

# Debug helpers
@app.get("/debug/ping_db")
async def _debug_ping_db():
    t0 = time.perf_counter()
    async with _engine_admin.connect() as conn:
        await conn.execute(text("SELECT 1"))
    dt = round((time.perf_counter() - t0) * 1000, 1)
    return {"ok": True, "ms": dt}

@app.get("/debug/check_restaurant")
async def _debug_check_restaurant(rid: str):
    async with _engine_admin.connect() as conn:
        row = (await conn.execute(text("SELECT id, api_key FROM foody_restaurants WHERE id=:rid"), {"rid": rid})).first()
    if not row:
        return {"ok": False, "reason": "not_found"}
    return {"ok": True, "id": row[0], "has_key": bool(row[1])}

@app.get("/debug/routes")
def _debug_routes():
    return [{"path": r.path, "methods": sorted(list(getattr(r, "methods", []) or []))} for r in app.routes]
