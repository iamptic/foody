# Foody Backend Service

ENV:
- DATABASE_URL=postgresql://postgres:...@postgres.railway.internal:5432/railway
- RUN_MIGRATIONS=1
- SEED_DEMO=1 (первый запуск)
- CORS_ORIGINS=https://foody-reg.vercel.app,https://foody-buyer.vercel.app

Проверка:
- GET /health
- GET /api/v1/offers?restaurant_id=RID_DEMO
