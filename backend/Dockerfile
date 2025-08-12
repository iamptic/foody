FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["/bin/sh","-c","uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
ARG CACHE_BUST=2025-08-12-1   # меняй на -2, -3 и т.д.
