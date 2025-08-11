# Foody WebApp + Bot Service

Переменные окружения (Railway):
- BOT_TOKEN=<токен бота>
- WEBHOOK_SECRET=foodySecret123      # латиница/цифры/подчёрки/дефис
- WEBAPP_PUBLIC=https://<домен этого сервиса>.up.railway.app
- BACKEND_PUBLIC=https://<домен backend-сервиса>.up.railway.app
- WEBAPP_BUYER_URL=https://<домен этого сервиса>/web/buyer/
- WEBAPP_MERCHANT_URL=https://<домен этого сервиса>/web/merchant/
- CORS_ORIGINS=https://foody-reg.vercel.app,https://foody-buyer.vercel.app

Шаги:
1) Задеплой этот сервис.
2) Проверь GET /health → {"ok":true}
3) В Telegram /start → увидишь две кнопки. Они открывают мини-страницы этого же сервиса.
4) Мини-страницы обращаются к BACKEND_PUBLIC (/api/v1/...).
