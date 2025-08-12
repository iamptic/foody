Backend (FastAPI)
ENV (Railway):
- DATABASE_URL=postgresql://...
- RUN_MIGRATIONS=1
- CORS_ORIGINS=https://<web>,https://<bot>

Start command: leave empty (Dockerfile runs uvicorn).
Health: GET /health
