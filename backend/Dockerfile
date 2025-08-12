FROM python:3.11-slim
ARG CACHE_BUST=20250812_161256
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["/bin/sh","-c","uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
