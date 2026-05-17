# Deployment Guide

## Prerequisites
- Docker 24+ and Docker Compose v2
- A server with SSH access (Ubuntu 22.04+ recommended)
- A PostgreSQL 16 instance (or use the bundled docker-compose service)
- Domain name with DNS pointing to your server

## Environment Setup

Copy and fill in the production template:
```bash
cp .env.prod .env
```

Generate strong secrets:
```bash
# SECRET_KEY
openssl rand -hex 32

# JWT_SECRET_KEY
openssl rand -hex 32
```

Required env vars for production:
| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask secret (32-byte hex) |
| `JWT_SECRET_KEY` | JWT signing key (32-byte hex) |
| `DATABASE_URL` | `postgresql://user:pass@host:5432/db` |
| `MAIL_USERNAME` | Gmail address |
| `MAIL_PASSWORD` | Gmail App Password (16 chars, no spaces) |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio phone in E.164 format |
| `FRONTEND_URL` | Your production domain e.g. `https://otpguard.co.ke` |
| `SENTRY_DSN` | Sentry DSN for error tracking |

## First Deploy

```bash
# On your server
git clone https://github.com/your-org/OTPGuard.git /opt/otpguard
cd /opt/otpguard
cp .env.prod .env
# Edit .env with your values

# Build and start
docker compose -f docker-compose.yml up -d --build

# Run database migrations
docker compose run --rm backend alembic upgrade head

# Verify
curl http://localhost/api/health
```

## Subsequent Deploys

The CD pipeline handles this automatically on push to `main`. For manual deploy:

```bash
cd /opt/otpguard
docker compose pull
docker compose run --rm backend alembic upgrade head
docker compose up -d --remove-orphans
docker system prune -f
```

## SSL / HTTPS

Add Certbot to the nginx container or use a reverse proxy (Cloudflare, Nginx Proxy Manager):

```bash
# Example with Certbot standalone (stop nginx first)
docker compose stop nginx
certbot certonly --standalone -d yourdomain.com
# Copy certs to nginx/certs/ and update nginx/nginx.conf
docker compose start nginx
```

## Health Monitoring

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | Liveness probe |
| `GET /api/health/detailed` | DB + mail + SMS status |
| `GET /metrics` | Prometheus metrics |

Configure your uptime monitor (UptimeRobot, Betterstack) to hit `/api/health` every minute.

## Scaling

To scale the backend horizontally:
```bash
docker compose up -d --scale backend=3
```

Ensure `FLASK_LIMITER_STORAGE_URI` is set to a Redis URL when running multiple instances:
```
FLASK_LIMITER_STORAGE_URI=redis://redis:6379/0
```

## Rollback

```bash
# Roll back to previous image
docker compose stop backend
docker compose run --rm backend alembic downgrade -1
# Update IMAGE tag in docker-compose.yml to previous version
docker compose up -d backend
```

## Logs

```bash
# All services
docker compose logs -f

# Backend only (JSON structured logs)
docker compose logs -f backend | jq .

# Tail last 100 lines
docker compose logs --tail=100 backend
```
