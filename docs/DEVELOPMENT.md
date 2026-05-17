# Development Guide

## Local Setup

### Option A — Docker (recommended)
```bash
git clone https://github.com/your-org/OTPGuard.git
cd OTPGuard
cp .env.dev .env
docker compose up --build
```

Services:
- Frontend: http://localhost:80
- Backend API: http://localhost:5000
- API Docs: http://localhost:5000/apidocs
- Metrics: http://localhost:5000/metrics

### Option B — Native

**Backend:**
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements-test.txt

# Set env vars (copy and edit)
cp .env.example .env

# Run migrations
alembic upgrade head

# Start dev server
flask run --reload
```

**Frontend:**
```bash
# From project root
npm install
npm run dev
# Runs at http://localhost:5173
```

## Project Structure

See `CLAUDE.md` for full layout. Key files to know:

| File | Purpose |
|------|---------|
| `backend/app/__init__.py` | App factory — all wiring happens here |
| `backend/app/models.py` | Single source of truth for all DB schemas |
| `backend/app/extensions.py` | Flask extension singletons |
| `backend/config.py` | Config classes per environment |
| `backend/conftest.py` | All pytest fixtures |

## Making a Code Change

### Adding a model field
1. Edit `backend/app/models.py`
2. `alembic revision --autogenerate -m "add X to users"`
3. Review `migrations/versions/<timestamp>_add_x_to_users.py`
4. `alembic upgrade head`

### Adding an API endpoint
1. Find the right blueprint in `backend/app/<module>/routes.py`
2. Add the route with a Flasgger docstring for auto-docs
3. Add rate limiting with `@limiter.limit("20/minute")`
4. Write an integration test in `backend/tests/integration/`

### Adding an email template
1. Create `backend/app/templates/email/your_template.html` (extends `base.html`)
2. Add a renderer function in `backend/app/email_templates.py`
3. Call it from `backend/app/notifications/service.py`

## Testing

```bash
cd backend

# Run all tests
pytest

# With coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html

# Run a specific test file
pytest tests/unit/test_models.py -v

# Run tests matching a name pattern
pytest -k "test_otp" -v
```

### Test Database
Tests use SQLite in-memory (`sqlite:///:memory:`). The `conftest.py` creates all tables, seeds plans, and provides fixtures:
- `regular_user`, `mfa_user`, `admin_user` — pre-created users
- `auth_headers`, `admin_headers` — ready-to-use JWT header dicts
- `api_key`, `user_subscription` — billing fixtures

### Writing Tests
```python
def test_my_endpoint(client, auth_headers):
    resp = client.post('/api/mfa/request-otp',
                       json={'method': 'email'},
                       headers=auth_headers)
    assert resp.status_code == 200
```

## Code Style

- Max line length: 120 (flake8 config)
- No trailing whitespace
- Import order: stdlib → third-party → local (separated by blank lines)
- Use `sanitize_str()` / `sanitize_email()` from `app/utils.py` on all user input

Run linters:
```bash
pip install flake8 bandit
flake8 app --max-line-length=120
bandit -r app -ll
```

## Environment Variables

| Variable | Dev default | Notes |
|----------|-------------|-------|
| `FLASK_ENV` | `development` | |
| `DATABASE_URL` | `sqlite:///otpguard.db` | Use PostgreSQL URL in production |
| `SECRET_KEY` | `otpguard-secret-key-change-in-prod` | Change in prod |
| `JWT_SECRET_KEY` | `otpguard-jwt-secret-change-in-prod` | Change in prod |
| `MAIL_USERNAME` | (empty) | Gmail address |
| `MAIL_PASSWORD` | (empty) | Gmail App Password |
| `TWILIO_ACCOUNT_SID` | (empty) | Optional in dev |
| `AT_API_KEY` | (empty) | Africa's Talking fallback |
| `SENTRY_DSN` | (empty) | Optional |
| `SLACK_WEBHOOK_URL` | (empty) | Optional alerts |

Without `MAIL_USERNAME`/`MAIL_PASSWORD`, emails are logged to console instead of sent.
Without `TWILIO_*`, SMS sends are logged to console instead of sent.

## Common Issues

**`alembic: command not found`** — activate your venv first: `source .venv/bin/activate`

**`psycopg2` install failure on Mac** — install libpq first: `brew install libpq`

**CORS errors in browser** — ensure `FRONTEND_URL` in `.env` matches your dev URL exactly (including port)

**JWT token expired** — access tokens expire in 2 hours; use `POST /api/auth/refresh` with your refresh token
