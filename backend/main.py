# main.py — Backend Service (safe boot)
import os, traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.bootstrap_db import run as run_migrations

__version__ = "foody-backend-service-safe-2025-08-12"

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
async def _startup():
    # 1) migrations (optional)
    if os.getenv("RUN_MIGRATIONS", "1") == "1":
        try:
            await run_migrations()
            print("[startup] migrations: OK")
        except Exception as e:
            print("[startup] migrations FAILED:", e)
            traceback.print_exc()

    # 2) lazy import routers after migrations
    try:
        from app.features.offers_reservations_foody import router as offers_router
        app.include_router(offers_router)
        print("[startup] router mounted: offers/reservations (foody_*)")
    except Exception as e:
        print("[startup] router mount FAILED:", e)
        traceback.print_exc()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/")
def root():
    return {"ok": True, "service": "backend", "version": __version__}

@app.get("/diag/env")
def diag_env():
    safe = {k: v for k, v in os.environ.items() if k in {
        "DATABASE_URL","RUN_MIGRATIONS","SEED_DEMO","CORS_ORIGINS"
    }}
    redacted = {k: ("***" if k=="DATABASE_URL" else v) for k,v in safe.items()}
    return {"env": redacted}
