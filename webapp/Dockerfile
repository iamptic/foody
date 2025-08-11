FROM python:3.11-slim
WORKDIR /app
ARG CACHE_BUST=2025-08-12-wb2
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["sh","-lc","uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
