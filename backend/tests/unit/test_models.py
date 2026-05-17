"""Unit tests for SQLAlchemy models — properties, helpers, serialization."""
import pytest
import bcrypt
from datetime import datetime, timezone, timedelta
from app.models import (
    User, APIKey, OTPLog, Plan, Subscription, UsageLog
)


# ── User ─────────────────────────────────────────────────────────────────────

class TestUserModel:
    def test_to_dict_exposes_safe_fields(self, regular_user):
        d = regular_user.to_dict()
        assert d['email'] == 'user@test.com'
        assert d['role'] == 'user'
        assert 'password_hash' not in d

    def test_starter_allows_email_only(self, regular_user, user_subscription):
        assert regular_user.can_use_channel('email') is True
        assert regular_user.can_use_channel('sms') is False
        assert regular_user.can_use_channel('totp') is False

    def test_growth_allows_email_and_sms(self, app, growth_plan):
        from app.extensions import db
        pw = bcrypt.hashpw(b'x', bcrypt.gensalt()).decode()
        user = User(email='g@test.com', password_hash=pw, plan='growth')
        db.session.add(user)
        sub = Subscription(user_id=None, plan_id=growth_plan.id, status='active')
        db.session.flush()
        sub.user_id = user.id
        db.session.add(sub)
        db.session.commit()

        assert user.can_use_channel('email') is True
        assert user.can_use_channel('sms') is True
        assert user.can_use_channel('totp') is False

    def test_has_feature_basic_dashboard(self, regular_user, user_subscription):
        assert regular_user.has_feature('basic_dashboard') is True
        assert regular_user.has_feature('admin_dashboard') is False

    def test_no_subscription_defaults_email(self, regular_user):
        # No subscription — falls back to plan name field
        assert regular_user.can_use_channel('email') is True

    def test_current_subscription_none_when_no_sub(self, regular_user):
        assert regular_user.current_subscription is None

    def test_current_subscription_returns_active(self, regular_user, user_subscription):
        sub = regular_user.current_subscription
        assert sub is not None
        assert sub.status == 'active'

    def test_is_active_default_true(self, regular_user):
        assert regular_user.is_active is True

    def test_to_dict_created_at_is_isoformat(self, regular_user):
        d = regular_user.to_dict()
        assert 'T' in d['created_at']  # ISO 8601 contains 'T'


# ── APIKey ────────────────────────────────────────────────────────────────────

class TestAPIKeyModel:
    def test_generate_prefix(self):
        key = APIKey.generate()
        assert key.startswith('otpg_')

    def test_generate_length(self):
        key = APIKey.generate()
        # 'otpg_' + 56 hex chars = 61 chars
        assert len(key) == 61

    def test_generate_uniqueness(self):
        keys = {APIKey.generate() for _ in range(20)}
        assert len(keys) == 20

    def test_to_dict_masks_full_key(self, api_key):
        d = api_key.to_dict()
        assert 'key' not in d
        assert d['key_preview'].endswith('••••••••••••••••••••')

    def test_to_dict_preview_starts_with_prefix(self, api_key):
        d = api_key.to_dict()
        assert d['key_preview'].startswith('otpg_')

    def test_to_dict_no_last_used_when_none(self, api_key):
        d = api_key.to_dict()
        assert d['last_used'] is None


# ── Plan ─────────────────────────────────────────────────────────────────────

class TestPlanModel:
    def test_otp_channels_returns_list(self, starter_plan):
        assert isinstance(starter_plan.otp_channels, list)

    def test_features_returns_list(self, starter_plan):
        assert isinstance(starter_plan.features, list)

    def test_corrupted_otp_channels_falls_back(self, app, starter_plan):
        from app.extensions import db
        original = starter_plan._otp_channels
        starter_plan._otp_channels = 'INVALID_JSON'
        db.session.commit()
        assert starter_plan.otp_channels == ['email']
        # Restore
        starter_plan._otp_channels = original
        db.session.commit()

    def test_corrupted_features_falls_back(self, app, starter_plan):
        from app.extensions import db
        original = starter_plan._features
        starter_plan._features = '{bad}'
        db.session.commit()
        assert starter_plan.features == ['basic_dashboard']
        starter_plan._features = original
        db.session.commit()

    def test_to_dict_fields(self, starter_plan):
        d = starter_plan.to_dict()
        assert d['name'] == 'starter'
        assert isinstance(d['otp_channels'], list)
        assert isinstance(d['features'], list)
        assert 'price_kes' in d
        assert 'price_usd' in d

    def test_four_default_plans_seeded(self, app):
        plans = Plan.query.filter_by(is_active=True).all()
        names = {p.name for p in plans}
        assert names == {'starter', 'growth', 'business', 'enterprise'}


# ── Subscription ─────────────────────────────────────────────────────────────

class TestSubscriptionModel:
    def test_active_status_is_active(self, app, regular_user, starter_plan):
        from app.extensions import db
        sub = Subscription(user_id=regular_user.id, plan_id=starter_plan.id, status='active')
        db.session.add(sub)
        db.session.commit()
        assert sub.is_active is True

    def test_cancelled_status_not_active(self, app, regular_user, starter_plan):
        from app.extensions import db
        sub = Subscription(user_id=regular_user.id, plan_id=starter_plan.id, status='cancelled')
        db.session.add(sub)
        db.session.commit()
        assert sub.is_active is False

    def test_trial_active_before_end(self, app, regular_user, starter_plan):
        from app.extensions import db
        sub = Subscription(
            user_id=regular_user.id, plan_id=starter_plan.id,
            status='trial', trial_ends=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.session.add(sub)
        db.session.commit()
        assert sub.is_active is True

    def test_trial_expired_not_active(self, app, regular_user, starter_plan):
        from app.extensions import db
        sub = Subscription(
            user_id=regular_user.id, plan_id=starter_plan.id,
            status='trial', trial_ends=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db.session.add(sub)
        db.session.commit()
        assert sub.is_active is False

    def test_to_dict_contains_status(self, app, regular_user, starter_plan):
        from app.extensions import db
        sub = Subscription(user_id=regular_user.id, plan_id=starter_plan.id, status='active')
        db.session.add(sub)
        db.session.commit()
        d = sub.to_dict()
        assert d['status'] == 'active'
        assert 'created_at' in d


# ── OTPLog ────────────────────────────────────────────────────────────────────

class TestOTPLogModel:
    def test_to_dict_fields(self, app, regular_user):
        from app.extensions import db
        log = OTPLog(
            user_id=regular_user.id, code='123456', method='email',
            status='pending', ip_address='127.0.0.1',
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db.session.add(log)
        db.session.commit()
        d = log.to_dict()
        assert d['method'] == 'email'
        assert d['status'] == 'pending'
        assert 'code' not in d  # OTP code never serialized

    def test_expires_at_isoformat(self, app, regular_user):
        from app.extensions import db
        log = OTPLog(
            user_id=regular_user.id, code='654321', method='email',
            status='pending', expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        db.session.add(log)
        db.session.commit()
        d = log.to_dict()
        assert 'T' in d['expires_at']
