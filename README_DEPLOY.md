Монорепозиторий Foody (Railway)
- backend/  — FastAPI + Dockerfile
- bot/      — Aiogram webhook + Dockerfile
- web/      — Node (Express), static /web/* + /health

Деплой: для каждого сервиса создайте отдельный сервис в Railway и загрузите соответствующую папку.
Start command пустой (используются Dockerfile или package.json).