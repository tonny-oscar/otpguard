"""
app/email_templates.py
Renders HTML email templates from backend/app/templates/email/.
"""
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates', 'email')
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(['html']),
)

_WELCOME_FEATURES = [
    ('🔐', 'Multi-Factor Authentication', 'Protect every login with OTP via email, SMS, or authenticator app'),
    ('📊', 'Analytics Dashboard',         'Monitor your authentication activity in real-time'),
    ('🔑', 'API Keys',                    'Integrate OTPGuard into your own applications'),
    ('📱', 'Device Management',           'Track and manage trusted devices'),
]

_SUBSCRIPTION_ACTIONS = {
    'upgraded':  ('🎉', 'Plan Upgraded!',         '{plan} plan is now active.'),
    'cancelled': ('😢', 'Subscription Cancelled', '{plan} plan has been cancelled.'),
    'renewed':   ('✅', 'Subscription Renewed',   '{plan} plan has been renewed.'),
}


def otp_email(code: str, method: str = 'email') -> str:
    return _env.get_template('otp.html').render(code=code, method=method)


def welcome_email(full_name: str, plan: str = 'starter') -> str:
    return _env.get_template('welcome.html').render(
        name=full_name or 'there',
        plan=plan,
        features=_WELCOME_FEATURES,
    )


def password_reset_email(reset_link: str, full_name: str = '') -> str:
    return _env.get_template('password_reset.html').render(
        name=full_name or 'there',
        reset_link=reset_link,
    )


def security_alert_email(full_name: str, event: str, ip: str, location: str = 'Unknown') -> str:
    return _env.get_template('security_alert.html').render(
        name=full_name or 'there',
        event=event,
        ip=ip,
        location=location,
    )


def subscription_email(full_name: str, plan: str, action: str = 'upgraded') -> str:
    defaults = ('📋', 'Subscription Updated', '{plan} plan has been updated.')
    icon, title, subtitle_tpl = _SUBSCRIPTION_ACTIONS.get(action, defaults)
    return _env.get_template('subscription.html').render(
        name=full_name or 'there',
        plan=plan,
        icon=icon,
        title=title,
        subtitle=subtitle_tpl.format(plan=plan.capitalize()),
    )


def contact_reply_email(name: str, original_subject: str, reply_body: str, original_message: str) -> str:
    return _env.get_template('contact_reply.html').render(
        name=name,
        original_subject=original_subject,
        reply_body=reply_body,
        original_message=original_message,
    )
