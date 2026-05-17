# OTPGuard — Codebase Guide

## What This Is
OTPGuard is a multi-factor authentication (MFA) platform. Businesses integrate it to add OTP-based 2FA to their apps via API keys. Users can receive OTPs by email, SMS (Twilio or Africa's Talking), or TOTP authenticator app.

## Tech Stack
| Layer | Tech |
|-------|------|
| Frontend | React 18 + Vite, Tailwind CSS |
| Backend | Flask 3.1, Flask-JWT-Extended, Flask-SQLAlchemy |
| Database | PostgreSQL 16 (SQLite in testing) |
| Migrations | Alembic |
| Auth | JWT (2h access / 30d refresh) + bcrypt |
| SMS | Twilio (primary) → Africa's Talking (fallback) |
| Email | Flask-Mail (Gmail SMTP) |
| Monitoring | Sentry + Slack/Discord/PagerDuty webhooks + Prometheus |
| Container | Docker + docker-compose |
| CI/CD | GitHub Actions (`.github/workflows/`) |

## Project Layout
```
OTPGuard/
├── backend/
│   ├── app/
│   │   ├── __init__.py          # App factory — CORS, headers, blueprints
│   │   ├── models.py            # All 15 SQLAlchemy models
│   │   ├── extensions.py        # db, jwt, mail, limiter singletons
│   │   ├── config.py            # Dev / Prod / Testing configs
│   │   ├── metrics.py           # Prometheus metrics
│   │   ├── monitoring.py        # Slack/Discord/PagerDuty alerting
│   │   ├── logging_config.py    # Structured JSON logging + sanitization
│   │   ├── sentry.py            # Sentry init with PII scrubbing
│   │   ├── audit.py             # Audit log helpers
│   │   ├── utils.py             # Input sanitization helpers
│   │   ├── email_templates.py   # Email renderer (uses templates/email/)
│   │   ├── templates/email/     # Jinja2 HTML email templates
│   │   ├── auth/routes.py       # /api/auth — register, login
│   │   ├── mfa/routes.py        # /api/mfa  — OTP request/verify, TOTP
│   │   ├── users/routes.py      # /api/users — profile, devices, API keys
│   │   ├── admin/routes.py      # /api/admin — user mgmt, analytics
│   │   ├── subscription/        # /api/subscription — plans, billing
│   │   ├── support/routes.py    # /api/support — tickets, KB, forum
│   │   └── notifications/       # Email + SMS send helpers
│   ├── migrations/              # Alembic migrations
│   │   └── versions/001_initial_schema.py
│   ├── tests/
│   │   ├── unit/                # Model + service unit tests
│   │   ├── integration/         # API endpoint tests
│   │   └── security/            # Auth/rate-limit tests
│   ├── alembic.ini
│   ├── conftest.py              # Pytest fixtures (users, tokens, plans)
│   ├── pytest.ini
│   ├── requirements.txt
│   ├── requirements-test.txt
│   ├── config.py
│   ├── run.py
│   └── gunicorn.conf.py
├── sdk/
│   ├── javascript/otpguard.js   # npm package
│   ├── python/otpguard.py
│   └── php/Client.php
├── src/                         # React frontend
├── .github/workflows/
│   ├── ci.yml                   # Test + lint on push/PR
│   └── cd.yml                   # Build + deploy on main
├── docker-compose.yml
├── docker-compose.override.yml  # Dev overrides
├── nginx/nginx.conf
└── docs/
    ├── API.md
    ├── DEPLOYMENT.md
    └── DEVELOPMENT.md
```

## Database Models (15 tables)
**Core:** `users`, `api_keys`, `otp_logs`, `devices`
**Billing:** `plans`, `subscriptions`, `usage_logs`, `usage_summaries`
**Support:** `contact_messages`, `support_tickets`, `ticket_messages`
**Knowledge:** `kb_categories`, `kb_articles`
**Community:** `forum_posts`, `forum_replies`

## API Blueprints
| Prefix | Blueprint | Key endpoints |
|--------|-----------|---------------|
| `/api/auth` | auth_bp | POST /register, POST /login |
| `/api/mfa` | mfa_bp | POST /request-otp, POST /verify-otp, POST /setup-totp |
| `/api/users` | users_bp | GET/PUT /profile, /devices, /api-keys |
| `/api/admin` | admin_bp | User mgmt, analytics, health checks |
| `/api/subscription` | subscription_bp | /plans, /subscribe, /cancel |
| `/api/support` | support_bp | /tickets, /kb/categories, /forum/posts |

Health: `GET /api/health`, `GET /api/health/detailed`
Metrics: `GET /metrics` (Prometheus)
API Docs: `GET /apidocs` (Swagger/Flasgger)

## Environment Variables
Copy `.env.dev` → `.env` for local dev. Key vars:
- `DATABASE_URL` — PostgreSQL connection string
- `SECRET_KEY` / `JWT_SECRET_KEY` — must be set in production
- `MAIL_USERNAME` / `MAIL_PASSWORD` — Gmail SMTP
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_PHONE_NUMBER`
- `AT_API_KEY` / `AT_USERNAME` — Africa's Talking fallback
- `SENTRY_DSN` — optional; enables error tracking
- `SLACK_WEBHOOK_URL` / `DISCORD_WEBHOOK_URL` — optional alerts

## Running Locally (Docker)
```bash
cp .env.dev .env
docker compose up --build
# Frontend: http://localhost:80
# Backend:  http://localhost:5000
# API Docs: http://localhost:5000/apidocs
```

## Running Locally (Dev)
```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements-test.txt
alembic upgrade head
flask run

# Frontend
npm install
npm run dev
```

## Database Migrations
```bash
cd backend
# Apply all migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "describe your change"

# Rollback one step
alembic downgrade -1
```

## Running Tests
```bash
cd backend
pytest                          # all tests
pytest tests/unit/              # unit only
pytest --cov=app -v             # with coverage
```

## CI/CD
- **CI** triggers on every push and PR — runs backend tests, flake8, bandit, frontend build, and Docker build check.
- **CD** triggers on push to `main` — builds Docker images, runs `alembic upgrade head` on the prod DB, then restarts containers via SSH.
- Required GitHub secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `SLACK_WEBHOOK_URL` (optional).

## Adding a New Feature
1. Add/update models in `backend/app/models.py`
2. Run `alembic revision --autogenerate -m "your change"` — review the generated file
3. Add routes in the appropriate blueprint (`routes.py`)
4. Write unit tests in `backend/tests/unit/` and integration tests in `backend/tests/integration/`
5. CI runs automatically on push

## Key Design Decisions
- **Rate limiting** is applied per-endpoint via `@limiter.limit()` decorators; default is 200/day, 60/hour.
- **Sensitive data** (passwords, OTP codes, tokens) is redacted in both logs (`_SanitizingFilter`) and Sentry (`_before_send`).
- **SMS fallback**: Twilio is tried first; if it fails, Africa's Talking is used automatically.
- **JWT claims**: MFA-pending state is carried in `mfa_pending=True` custom claim; protected routes check this.
- **Subscription checks**: `subscription/middleware.py` enforces plan limits before OTP operations.
