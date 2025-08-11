# main.py — Backend Service (API only)
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.bootstrap_db import run as run_migrations
from app.features.offers_reservations_foody import router as offers_router

__version__ = "foody-backend-service-2025-08-12"

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

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/")
def root():
    return {"ok": True, "service": "backend", "version": __version__}
