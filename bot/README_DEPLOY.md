Bot (Aiogram3 webhook)
ENV:
- BOT_TOKEN
- WEBHOOK_SECRET
- WEBAPP_PUBLIC=https://<web-domain>
- WEBAPP_BUYER_URL=${WEBAPP_PUBLIC}/web/buyer/
- WEBAPP_MERCHANT_URL=${WEBAPP_PUBLIC}/web/merchant/

Start command: empty (Dockerfile runs uvicorn)
After deploy, set webhook:
curl -sS "https://api.telegram.org/bot$BOT_TOKEN/setWebhook"   -d "url=https://<bot-domain>/tg/webhook"   -d "secret_token=$WEBHOOK_SECRET"
