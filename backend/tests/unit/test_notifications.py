"""Unit tests for app/notifications/service.py — all external calls mocked."""
import pytest
from unittest.mock import patch, MagicMock


class TestSendEmailOtp:
    def test_sends_email_when_credentials_configured(self, app):
        app.config['MAIL_USERNAME'] = 'test@gmail.com'
        app.config['MAIL_PASSWORD'] = 'testpass'

        with patch('app.notifications.service.mail') as mock_mail:
            from app.notifications.service import send_email_otp
            send_email_otp('recipient@test.com', '123456')
            mock_mail.send.assert_called_once()

        # Reset to prevent affecting other tests
        app.config['MAIL_USERNAME'] = None
        app.config['MAIL_PASSWORD'] = None

    def test_skips_send_without_credentials(self, app):
        app.config['MAIL_USERNAME'] = ''
        app.config['MAIL_PASSWORD'] = ''

        with patch('app.notifications.service.mail') as mock_mail:
            from app.notifications.service import send_email_otp
            send_email_otp('recipient@test.com', '999999')
            mock_mail.send.assert_not_called()

    def test_raises_on_smtp_failure(self, app):
        app.config['MAIL_USERNAME'] = 'test@gmail.com'
        app.config['MAIL_PASSWORD'] = 'testpass'

        with patch('app.notifications.service.mail') as mock_mail:
            mock_mail.send.side_effect = Exception('SMTP error')
            from app.notifications.service import send_email_otp
            with pytest.raises(Exception, match='SMTP error'):
                send_email_otp('bad@test.com', '111111')

        app.config['MAIL_USERNAME'] = None
        app.config['MAIL_PASSWORD'] = None


class TestSendSmsOtp:
    def test_uses_twilio_when_configured(self, app):
        app.config['TWILIO_ACCOUNT_SID'] = 'ACtest'
        app.config['TWILIO_AUTH_TOKEN'] = 'authtoken'
        app.config['TWILIO_PHONE_NUMBER'] = '+15005550006'

        with patch('app.notifications.service._send_twilio') as mock_twilio:
            from app.notifications.service import send_sms_otp
            send_sms_otp('+254700000001', '654321')
            mock_twilio.assert_called_once()

        app.config['TWILIO_ACCOUNT_SID'] = None
        app.config['TWILIO_AUTH_TOKEN'] = None

    def test_falls_back_to_africas_talking_when_twilio_fails(self, app):
        app.config['TWILIO_ACCOUNT_SID'] = 'ACtest'
        app.config['TWILIO_AUTH_TOKEN'] = 'authtoken'
        app.config['TWILIO_PHONE_NUMBER'] = '+15005550006'
        app.config['AT_API_KEY'] = 'at_key'
        app.config['AT_USERNAME'] = 'sandbox'

        with patch('app.notifications.service._send_twilio') as mock_twilio, \
             patch('app.notifications.service._send_africas_talking') as mock_at:
            mock_twilio.side_effect = Exception('Twilio down')
            from app.notifications.service import send_sms_otp
            send_sms_otp('+254700000001', '111222')
            mock_at.assert_called_once()

        app.config['TWILIO_ACCOUNT_SID'] = None
        app.config['AT_API_KEY'] = None

    def test_logs_warning_when_no_providers_configured(self, app):
        app.config['TWILIO_ACCOUNT_SID'] = None
        app.config['AT_API_KEY'] = None

        with patch('app.notifications.service._send_twilio') as mock_twilio, \
             patch('app.notifications.service._send_africas_talking') as mock_at:
            from app.notifications.service import send_sms_otp
            send_sms_otp('+254700000001', '000000')
            mock_twilio.assert_not_called()
            mock_at.assert_not_called()
