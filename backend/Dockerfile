
FROM python:3.11-slim
WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates && rm -rf /var/lib/apt/lists/*

# Install requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy project
COPY . /app

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Railway provides $PORT; fall back to 8080 locally
CMD ["/bin/sh","-c","uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
