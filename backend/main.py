import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.db import engine
from app.features.offers_reservations_foody import router, ensure_schema

app = FastAPI(title="Foody Backend", version="v10")

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _boot():
    await ensure_schema()

@app.get("/health")
async def health(): return {"ok": True}

@app.get("/debug/routes")
async def routes():
    return JSONResponse([{"path": r.path, "name": r.name, "methods": list(r.methods or [])} for r in app.router.routes])

app.include_router(router)
