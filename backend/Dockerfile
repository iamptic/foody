FROM python:3.11-slim
WORKDIR /app

# Speed up, basic deps
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential curl ca-certificates     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Railway listens on 8080 by default
ENV PORT=8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
