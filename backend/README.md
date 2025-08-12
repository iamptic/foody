# Foody Backend (FastAPI, SQLAlchemy async)

## ENV
- DATABASE_URL (postgresql://USER:PASS@HOST:PORT/DB)
- RUN_MIGRATIONS=1
- SEED_DEMO=1 (only first deploy, then remove)
- ADMIN_MIGRATE_TOKEN=foodyAdmin123
- CORS_ORIGINS=https://foodybot-production.up.railway.app

## Health
GET /health

## Admin
POST /api/v1/admin/set_api_key?token=<ADMIN_MIGRATE_TOKEN>
body: {"restaurant_id":"RID_DEMO", "api_key":"<key>"}
