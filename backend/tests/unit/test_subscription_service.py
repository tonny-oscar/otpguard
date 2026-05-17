"""Unit tests for SubscriptionService business logic."""
import pytest
from datetime import datetime, timezone, timedelta
from app.subscription.service import SubscriptionService
from app.models import Plan, Subscription, UsageLog, UsageSummary


class TestInitializeDefaultPlans:
    def test_creates_four_plans(self, app):
        plans = Plan.query.filter_by(is_active=True).all()
        assert len(plans) == 4

    def test_plan_names(self, app):
        names = {p.name for p in Plan.query.all()}
        assert {'starter', 'growth', 'business', 'enterprise'}.issubset(names)

    def test_idempotent_double_call(self, app):
        from app.extensions import db
        SubscriptionService.initialize_default_plans()
        count = Plan.query.filter_by(name='starter').count()
        assert count == 1


class TestCreateSubscription:
    def test_creates_active_subscription(self, app, regular_user):
        sub = SubscriptionService.create_subscription(regular_user.id, 'starter')
        assert sub.status == 'active'
        assert sub.user_id == regular_user.id

    def test_creates_trial_subscription_with_days(self, app, regular_user):
        sub = SubscriptionService.create_subscription(regular_user.id, 'growth', trial_days=14)
        assert sub.status == 'trial'
        assert sub.trial_ends is not None

    def test_trial_ends_approximately_correct(self, app, regular_user):
        sub = SubscriptionService.create_subscription(regular_user.id, 'growth', trial_days=14)
        expected = datetime.now(timezone.utc) + timedelta(days=14)
        te = sub.trial_ends
        if te.tzinfo is None:
            te = te.replace(tzinfo=timezone.utc)
        diff = abs((te - expected).total_seconds())
        assert diff < 60  # within a minute

    def test_cancels_existing_active_subscription(self, app, regular_user, user_subscription):
        SubscriptionService.create_subscription(regular_user.id, 'growth')
        old_sub = Subscription.query.get(user_subscription.id)
        assert old_sub.status == 'cancelled'

    def test_raises_for_unknown_plan(self, app, regular_user):
        with pytest.raises(ValueError, match="Plan 'nonexistent' not found"):
            SubscriptionService.create_subscription(regular_user.id, 'nonexistent')


class TestGetUserSubscription:
    def test_returns_active_subscription(self, app, regular_user, user_subscription):
        sub = SubscriptionService.get_user_subscription(regular_user.id)
        assert sub is not None
        assert sub.status == 'active'

    def test_returns_none_without_subscription(self, app, regular_user):
        sub = SubscriptionService.get_user_subscription(regular_user.id)
        assert sub is None


class TestCheckUserLimit:
    def test_within_limit_returns_true(self, app, regular_user, user_subscription):
        ok, msg = SubscriptionService.check_user_limit(regular_user.id)
        assert ok is True

    def test_no_subscription_returns_false(self, app, regular_user):
        ok, msg = SubscriptionService.check_user_limit(regular_user.id)
        assert ok is False
        assert 'subscription' in msg.lower()

    def test_unknown_user_returns_false(self, app):
        ok, msg = SubscriptionService.check_user_limit(99999)
        assert ok is False

    def test_unlimited_plan_always_allowed(self, app, regular_user):
        from app.extensions import db
        biz_plan = Plan.query.filter_by(name='business').first()
        sub = Subscription(user_id=regular_user.id, plan_id=biz_plan.id, status='active')
        db.session.add(sub)
        db.session.commit()
        ok, msg = SubscriptionService.check_user_limit(regular_user.id)
        assert ok is True
        assert 'Unlimited' in msg


class TestCheckOtpChannel:
    def test_email_allowed_on_starter(self, app, regular_user, user_subscription):
        ok, msg = SubscriptionService.check_otp_channel(regular_user.id, 'email')
        assert ok is True

    def test_sms_not_allowed_on_starter(self, app, regular_user, user_subscription):
        ok, msg = SubscriptionService.check_otp_channel(regular_user.id, 'sms')
        assert ok is False

    def test_unknown_user_returns_false(self, app):
        ok, _ = SubscriptionService.check_otp_channel(99999, 'email')
        assert ok is False


class TestCheckFeatureAccess:
    def test_basic_dashboard_allowed_on_starter(self, app, regular_user, user_subscription):
        ok, _ = SubscriptionService.check_feature_access(regular_user.id, 'basic_dashboard')
        assert ok is True

    def test_admin_dashboard_not_allowed_on_starter(self, app, regular_user, user_subscription):
        ok, _ = SubscriptionService.check_feature_access(regular_user.id, 'admin_dashboard')
        assert ok is False


class TestLogUsage:
    def test_creates_usage_log(self, app, regular_user):
        log = SubscriptionService.log_usage(regular_user.id, 'email_otp', 1, 0)
        from app.extensions import db
        assert UsageLog.query.filter_by(user_id=regular_user.id).count() == 1

    def test_updates_monthly_summary(self, app, regular_user):
        SubscriptionService.log_usage(regular_user.id, 'email_otp', 1, 0)
        from app.extensions import db
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        summary = UsageSummary.query.filter_by(user_id=regular_user.id, month=month).first()
        assert summary is not None
        assert summary.email_otp_count == 1

    def test_sms_usage_increments_sms_count(self, app, regular_user):
        SubscriptionService.log_usage(regular_user.id, 'sms_otp', 1, 2.5)
        month = datetime.now(timezone.utc).strftime('%Y-%m')
        summary = UsageSummary.query.filter_by(user_id=regular_user.id, month=month).first()
        assert summary.sms_otp_count == 1


class TestUpgradeSubscription:
    def test_cancels_old_creates_new(self, app, regular_user, user_subscription):
        old_id = user_subscription.id
        new_sub = SubscriptionService.upgrade_subscription(regular_user.id, 'growth')
        old = Subscription.query.get(old_id)
        assert old.status == 'cancelled'
        assert new_sub.status == 'active'
        growth = Plan.query.filter_by(name='growth').first()
        assert new_sub.plan_id == growth.id

    def test_raises_for_invalid_plan(self, app, regular_user, user_subscription):
        with pytest.raises(ValueError):
            SubscriptionService.upgrade_subscription(regular_user.id, 'nonexistent')


class TestCalculateSmsCost:
    def test_zero_for_starter_plan(self, app, regular_user, user_subscription):
        cost = SubscriptionService.calculate_sms_cost(regular_user.id)
        assert cost == 0

    def test_nonzero_for_growth_plan(self, app, regular_user):
        from app.extensions import db
        growth = Plan.query.filter_by(name='growth').first()
        sub = Subscription(user_id=regular_user.id, plan_id=growth.id, status='active')
        db.session.add(sub)
        db.session.commit()
        cost = SubscriptionService.calculate_sms_cost(regular_user.id)
        assert cost > 0
