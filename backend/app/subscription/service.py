from datetime import datetime, timezone, timedelta
from sqlalchemy import func, distinct
from app.extensions import db
from app.models import Plan, Subscription, UsageLog, UsageSummary, User, OTPLog


class SubscriptionService:
    """Service for managing subscriptions, plans, and usage tracking"""

    @staticmethod
    def initialize_default_plans():
        """Create default subscription plans if they don't exist"""
        plans_data = [
            {
                'name': 'starter',
                'display_name': 'Starter',
                'price_kes': 0,
                'price_usd': 0,
                'max_users': 50,
                'otp_channels': ['email'],
                'features': ['basic_dashboard'],
                'sms_enabled': False,
                'sms_cost_min': 0,
                'sms_cost_max': 0
            },
            {
                'name': 'growth',
                'display_name': 'Growth (Most Popular)',
                'price_kes': 150000,  # 1500 KES in cents
                'price_usd': 1000,    # $10 in cents
                'max_users': 1000,
                'otp_channels': ['email', 'sms'],
                'features': ['basic_dashboard', 'full_dashboard', 'login_analytics'],
                'sms_enabled': True,
                'sms_cost_min': 200,  # 2 KES in cents
                'sms_cost_max': 500   # 5 KES in cents
            },
            {
                'name': 'business',
                'display_name': 'Business',
                'price_kes': 500000,  # 5000 KES in cents
                'price_usd': 3500,    # $35 in cents
                'max_users': -1,      # Unlimited
                'otp_channels': ['email', 'sms', 'totp'],
                'features': ['basic_dashboard', 'full_dashboard', 'login_analytics', 
                           'admin_dashboard', 'device_tracking', 'geolocation', 'custom_branding'],
                'sms_enabled': True,
                'sms_cost_min': 100,  # 1 KES in cents
                'sms_cost_max': 300   # 3 KES in cents
            },
            {
                'name': 'enterprise',
                'display_name': 'Enterprise (Custom)',
                'price_kes': 0,       # Custom pricing
                'price_usd': 0,
                'max_users': -1,      # Unlimited
                'otp_channels': ['email', 'sms', 'totp'],
                'features': ['basic_dashboard', 'full_dashboard', 'login_analytics',
                           'admin_dashboard', 'device_tracking', 'geolocation', 'custom_branding',
                           'white_label', 'dedicated_support', 'custom_limits'],
                'sms_enabled': True,
                'sms_cost_min': 50,   # 0.5 KES in cents
                'sms_cost_max': 200   # 2 KES in cents
            }
        ]

        for plan_data in plans_data:
            existing = Plan.query.filter_by(name=plan_data['name']).first()
            if not existing:
                plan = Plan(**plan_data)
                db.session.add(plan)
        
        db.session.commit()

    @staticmethod
    def create_subscription(user_id, plan_name, trial_days=None):
        """Create a new subscription for a user"""
        plan = Plan.query.filter_by(name=plan_name, is_active=True).first()
        if not plan:
            raise ValueError(f"Plan '{plan_name}' not found")

        # Cancel existing active subscriptions
        Subscription.query.filter_by(user_id=user_id, status='active').update({'status': 'cancelled'})
        
        subscription = Subscription(
            user_id=user_id,
            plan_id=plan.id,
            status='trial' if trial_days else 'active',
            trial_ends=datetime.now(timezone.utc) + timedelta(days=trial_days) if trial_days else None
        )
        
        db.session.add(subscription)
        db.session.commit()
        return subscription

    @staticmethod
    def get_user_subscription(user_id):
        """Get user's current active subscription"""
        return Subscription.query.filter_by(
            user_id=user_id, 
            status='active'
        ).order_by(Subscription.created_at.desc()).first()

    @staticmethod
    def check_user_limit(user_id):
        """Check if user has reached their user limit"""
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"
        
        subscription = user.current_subscription
        if not subscription:
            return False, "No active subscription"
        
        plan = subscription.plan
        if plan.max_users == -1:  # Unlimited
            return True, "Unlimited users"
        
        current_count = user.get_user_count()
        if current_count >= plan.max_users:
            return False, f"User limit reached ({current_count}/{plan.max_users})"
        
        return True, f"Within limit ({current_count}/{plan.max_users})"

    @staticmethod
    def check_otp_channel(user_id, channel):
        """Check if user's plan allows specific OTP channel"""
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"
        
        if not user.can_use_channel(channel):
            return False, f"Channel '{channel}' not available in your plan"
        
        return True, f"Channel '{channel}' allowed"

    @staticmethod
    def check_feature_access(user_id, feature):
        """Check if user's plan includes a specific feature"""
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"
        
        if not user.has_feature(feature):
            return False, f"Feature '{feature}' not available in your plan"
        
        return True, f"Feature '{feature}' available"

    @staticmethod
    def log_usage(user_id, usage_type, quantity=1, cost_kes=0, extra_data=None):
        """Log usage for billing and analytics"""
        usage_log = UsageLog(
            user_id=user_id,
            usage_type=usage_type,
            quantity=quantity,
            cost_kes=int(cost_kes * 100),  # Convert to cents
            extra_data=extra_data or {}
        )
        db.session.add(usage_log)
        db.session.commit()
        
        # Update monthly summary
        SubscriptionService._update_usage_summary(user_id, usage_type, quantity, cost_kes)
        
        return usage_log

    @staticmethod
    def _update_usage_summary(user_id, usage_type, quantity, cost_kes):
        """Update monthly usage summary"""
        current_month = datetime.now(timezone.utc).strftime('%Y-%m')
        
        summary = UsageSummary.query.filter_by(
            user_id=user_id, 
            month=current_month
        ).first()
        
        if not summary:
            summary = UsageSummary(
                user_id=user_id,
                month=current_month,
                email_otp_count=0,
                sms_otp_count=0,
                totp_count=0,
                total_users=0,
                total_cost_kes=0,
            )
            db.session.add(summary)
        
        # Update counters based on usage type
        if usage_type == 'email_otp':
            summary.email_otp_count += quantity
        elif usage_type == 'sms_otp':
            summary.sms_otp_count += quantity
        elif usage_type == 'totp_verify':
            summary.totp_count += quantity
        elif usage_type == 'user_added':
            summary.total_users += quantity
        
        summary.total_cost_kes += int(cost_kes * 100)  # Convert to cents
        summary.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()

    @staticmethod
    def get_usage_stats(user_id, month=None):
        """Get usage statistics for a user"""
        if not month:
            month = datetime.now(timezone.utc).strftime('%Y-%m')
        
        summary = UsageSummary.query.filter_by(
            user_id=user_id, 
            month=month
        ).first()
        
        if not summary:
            return {
                'month': month,
                'total_users': 0,
                'email_otp_count': 0,
                'sms_otp_count': 0,
                'totp_count': 0,
                'total_cost_kes': 0
            }
        
        return summary.to_dict()

    @staticmethod
    def calculate_sms_cost(user_id):
        """Calculate SMS cost based on user's plan"""
        user = User.query.get(user_id)
        if not user or not user.current_plan:
            return 0
        
        plan = user.current_plan
        if not plan.sms_enabled:
            return 0
        
        # Use average of min/max cost
        return (plan.sms_cost_min + plan.sms_cost_max) / 200  # Convert from cents to KES

    @staticmethod
    def upgrade_subscription(user_id, new_plan_name):
        """Upgrade user's subscription to a new plan"""
        current_sub = SubscriptionService.get_user_subscription(user_id)
        if not current_sub:
            return SubscriptionService.create_subscription(user_id, new_plan_name)
        
        new_plan = Plan.query.filter_by(name=new_plan_name, is_active=True).first()
        if not new_plan:
            raise ValueError(f"Plan '{new_plan_name}' not found")
        
        # End current subscription
        current_sub.status = 'cancelled'
        current_sub.end_date = datetime.now(timezone.utc)
        
        # Create new subscription
        new_subscription = Subscription(
            user_id=user_id,
            plan_id=new_plan.id,
            status='active'
        )
        
        db.session.add(new_subscription)
        db.session.commit()
        
        return new_subscription

    @staticmethod
    def ensure_user_subscription(user_id):
        """Ensure user has an active subscription, create starter if missing."""
        user = User.query.get(user_id)
        if not user:
            return None
        existing = Subscription.query.filter(
            Subscription.user_id == user_id,
            Subscription.status.in_(['active', 'trial'])
        ).first()
        if existing:
            return existing
        # Create starter subscription based on user.plan field
        plan_name = user.plan or 'starter'
        try:
            return SubscriptionService.create_subscription(user_id, plan_name)
        except Exception:
            return None

    @staticmethod
    def start_trial(user_id, plan_name='growth', trial_days=14):
        """Start a trial subscription"""
        return SubscriptionService.create_subscription(user_id, plan_name, trial_days)