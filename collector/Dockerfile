FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Preserve python package hierarchy (collector.app...)
COPY . ./collector

ENV BACKEND_URL="http://backend:8000"
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["python", "-m", "collector.app.main", "--mode", "wifi", "--mock", "--backend-url", "http://backend:8000"]
