import os, time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.bootstrap_db import run as run_migrations
from app.features.offers_reservations_foody import router as offers_router

__version__ = "foody-backend-v6"

app = FastAPI(title="Foody Backend", version=__version__)

cors_origins = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",")] if cors_origins else ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins if origins != ["*"] else ["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"], expose_headers=["*"])

@app.on_event("startup")
async def _run_migs():
    if os.getenv("RUN_MIGRATIONS", "1") == "1":
        await run_migrations()

app.include_router(offers_router)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/")
def root():
    return {"ok": True, "service": "backend", "version": __version__}

_DB_URL = os.getenv("DATABASE_URL","")
if _DB_URL.startswith("postgresql://"):
    _DB_URL = _DB_URL.replace("postgresql://","postgresql+asyncpg://",1)
engine_dbg = create_async_engine(_DB_URL, echo=False, pool_pre_ping=True)

@app.get("/debug/ping_db")
async def _debug_ping_db():
    t0=time.perf_counter()
    async with engine_dbg.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"ok": True, "ms": round((time.perf_counter()-t0)*1000,1)}

@app.get("/debug/routes")
def _debug_routes():
    return [{"path": r.path, "methods": sorted(list(getattr(r, "methods", []) or []))} for r in app.routes]
