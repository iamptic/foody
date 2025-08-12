Foody Monorepo

1) Backend: upload /backend (ZIP), clear build cache, env DATABASE_URL/RUN_MIGRATIONS/CORS_ORIGINS.
2) Web: upload /web (ZIP), clear build cache. GET /health = {"ok":true}
3) Bot: upload /bot (ZIP), clear build cache, env vars; setWebhook.

Deploy order: backend -> web -> bot.
