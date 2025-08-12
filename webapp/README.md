# Foody Bot + WebApp (AIOHTTP + Aiogram v3)

ENV (Railway -> this service):
- BOT_TOKEN=...
- WEBHOOK_SECRET=foodySecret123
- WEBAPP_PUBLIC=https://<this-service>.up.railway.app
- BACKEND_PUBLIC=https://foodyback-production.up.railway.app
- WEBAPP_BUYER_URL=https://<this-service>.up.railway.app/web/buyer/
- WEBAPP_MERCHANT_URL=https://<this-service>.up.railway.app/web/merchant/
- CORS_ORIGINS=https://<this-service>.up.railway.app

Health: GET /health
Webhook: POST /tg/webhook (Telegram will call with secret header)
Static: /web/... and /config.js
