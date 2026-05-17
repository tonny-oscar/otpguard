"""
Root conftest — provides all shared fixtures for backend test suite.
Run from the backend/ directory: pytest
"""
import os
import pytest
import bcrypt
from datetime import datetime, timezone, timedelta

os.environ.setdefault('FLASK_ENV', 'testing')


# ── Application & DB ─────────────────────────────────────────────────────────

@pytest.fixture(scope='session')
def app():
    """Single Flask app instance for the entire test session."""
    from app import create_app
    from app.extensions import db

    application = create_app('testing')
    application.config['RATELIMIT_ENABLED'] = False

    ctx = application.app_context()
    ctx.push()

    # Re-create tables in this persistent context (create_app's own context
    # is already gone; SQLite in-memory is per-connection via SingletonThreadPool)
    db.create_all()
    from app.subscription.service import SubscriptionService
    SubscriptionService.initialize_default_plans()

    yield application

    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture(autouse=True)
def clean_db(app):
    """Delete all user-generated data after every test (plans are preserved)."""
    yield
    from app.extensions import db
    from app.models import (
        User, APIKey, OTPLog, Device,
        Subscription, UsageLog, UsageSummary, ContactMessage,
        SupportTicket, TicketMessage,
        KnowledgeBaseArticle, KnowledgeBaseCategory,
        ForumPost, ForumReply,
    )
    try:
        db.session.query(TicketMessage).delete()
        db.session.query(SupportTicket).delete()
        db.session.query(ForumReply).delete()
        db.session.query(ForumPost).delete()
        db.session.query(KnowledgeBaseArticle).delete()
        db.session.query(KnowledgeBaseCategory).delete()
        db.session.query(OTPLog).delete()
        db.session.query(UsageLog).delete()
        db.session.query(UsageSummary).delete()
        db.session.query(ContactMessage).delete()
        db.session.query(APIKey).delete()
        db.session.query(Device).delete()
        db.session.query(Subscription).delete()
        db.session.query(User).delete()
        db.session.commit()
    except Exception:
        db.session.rollback()


@pytest.fixture
def client(app):
    return app.test_client()


# ── User fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def regular_user(app):
    from app.extensions import db
    from app.models import User
    pw = bcrypt.hashpw(b'password123', bcrypt.gensalt()).decode()
    user = User(
        email='user@test.com', password_hash=pw, full_name='Test User',
        phone='+254700000001', role='user', plan='starter', mfa_enabled=False,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def mfa_user(app):
    from app.extensions import db
    from app.models import User
    pw = bcrypt.hashpw(b'password123', bcrypt.gensalt()).decode()
    user = User(
        email='mfa@test.com', password_hash=pw, full_name='MFA User',
        phone='+254700000002', role='user', plan='starter',
        mfa_enabled=True, mfa_method='email',
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def admin_user(app):
    from app.extensions import db
    from app.models import User
    pw = bcrypt.hashpw(b'adminpass123', bcrypt.gensalt()).decode()
    user = User(
        email='admin@test.com', password_hash=pw, full_name='Admin User',
        role='admin', plan='enterprise', mfa_enabled=False,
    )
    db.session.add(user)
    db.session.commit()
    return user


# ── Token / header fixtures ───────────────────────────────────────────────────

@pytest.fixture
def user_token(client, regular_user):
    resp = client.post('/api/auth/login', json={
        'email': 'user@test.com', 'password': 'password123'
    })
    return resp.get_json()['access_token']


@pytest.fixture
def auth_headers(user_token):
    return {'Authorization': f'Bearer {user_token}'}


@pytest.fixture
def admin_token(client, admin_user):
    resp = client.post('/api/auth/login', json={
        'email': 'admin@test.com', 'password': 'adminpass123'
    })
    return resp.get_json()['access_token']


@pytest.fixture
def admin_headers(admin_token):
    return {'Authorization': f'Bearer {admin_token}'}


@pytest.fixture
def pre_auth_token(app, mfa_user):
    """Pre-authentication JWT with mfa_pending=True claim."""
    from flask_jwt_extended import create_access_token
    return create_access_token(
        identity=str(mfa_user.id),
        additional_claims={'mfa_pending': True},
        expires_delta=timedelta(minutes=10),
    )


@pytest.fixture
def pre_auth_headers(pre_auth_token):
    return {'Authorization': f'Bearer {pre_auth_token}'}


# ── Resource fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def api_key(app, regular_user):
    from app.extensions import db
    from app.models import APIKey
    val = APIKey.generate()
    key = APIKey(user_id=regular_user.id, name='Test Key', key=val, is_active=True)
    db.session.add(key)
    db.session.commit()
    return key


@pytest.fixture
def starter_plan(app):
    from app.models import Plan
    return Plan.query.filter_by(name='starter').first()


@pytest.fixture
def growth_plan(app):
    from app.models import Plan
    return Plan.query.filter_by(name='growth').first()


@pytest.fixture
def user_subscription(app, regular_user, starter_plan):
    from app.extensions import db
    from app.models import Subscription
    sub = Subscription(user_id=regular_user.id, plan_id=starter_plan.id, status='active')
    db.session.add(sub)
    db.session.commit()
    return sub
