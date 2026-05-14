# Docker Deployment Guide

## Local Development

1. Copy env template:
   ```
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. Start services:
   ```
   docker compose up --build
   ```

3. Access:
   - DB: `localhost:5432` (psql postgres://postgres:postgres@localhost:5432/crypto_bot)
   - Bot logs: docker compose logs bot

## VPS Deployment

1. Build & push image:
   ```
   docker build -t crypto-bot:latest .
   docker tag crypto-bot:latest yourregistry/crypto-bot:latest
   docker push yourregistry/crypto-bot:latest
   ```

2. On VPS (with Docker & Docker Compose):
   ```
   mkdir crypto-bot && cd crypto-bot
   wget yourregistry/crypto-bot:latest  # or docker pull
   cp .env.example .env  # configure .env
   docker compose up -d
   ```

3. SSH tunnel or expose ports as needed.

## Manual DB Migration (outside Docker)
```
docker compose exec bot alembic upgrade head
```
