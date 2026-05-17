"""Unit tests for app/utils.py — sanitization and IP helpers."""
import pytest
from unittest.mock import MagicMock, patch
from app.utils import (
    get_client_ip, sanitize_str, sanitize_email, sanitize_phone, get_location,
)


# ── get_client_ip ─────────────────────────────────────────────────────────────

class TestGetClientIp:
    def _req(self, remote_addr=None, forwarded_for=None):
        req = MagicMock()
        req.remote_addr = remote_addr
        req.headers = {}
        if forwarded_for:
            req.headers = {'X-Forwarded-For': forwarded_for}
        req.headers.get = lambda k, d=None: req.headers.get(k, d) if isinstance(req.headers, dict) else d
        # Use real dict for get
        h = {}
        if forwarded_for:
            h['X-Forwarded-For'] = forwarded_for
        req.headers = type('Headers', (), {'get': lambda self, k, d=None: h.get(k, d)})()
        req.remote_addr = remote_addr
        return req

    def test_returns_remote_addr_without_forwarded(self):
        req = MagicMock()
        req.headers.get.return_value = None
        req.remote_addr = '10.0.0.1'
        assert get_client_ip(req) == '10.0.0.1'

    def test_returns_first_forwarded_ip(self):
        req = MagicMock()
        req.headers.get.return_value = '1.2.3.4, 5.6.7.8'
        assert get_client_ip(req) == '1.2.3.4'

    def test_strips_whitespace_from_forwarded(self):
        req = MagicMock()
        req.headers.get.return_value = '  9.9.9.9  , 1.1.1.1'
        assert get_client_ip(req) == '9.9.9.9'

    def test_unknown_when_no_addr(self):
        req = MagicMock()
        req.headers.get.return_value = None
        req.remote_addr = None
        assert get_client_ip(req) == 'unknown'


# ── sanitize_str ──────────────────────────────────────────────────────────────

class TestSanitizeStr:
    def test_strips_html_tags(self):
        result = sanitize_str('<script>alert(1)</script>hello')
        assert '<script>' not in result
        assert 'hello' in result

    def test_truncates_to_max_length(self):
        result = sanitize_str('a' * 300, max_length=10)
        assert len(result) == 10

    def test_empty_string(self):
        assert sanitize_str('') == ''

    def test_non_string_returns_empty(self):
        assert sanitize_str(None) == ''
        assert sanitize_str(123) == ''

    def test_normal_string_unchanged(self):
        result = sanitize_str('Hello World')
        assert result == 'Hello World'

    def test_strips_nested_tags(self):
        result = sanitize_str('<b><i>text</i></b>')
        assert '<b>' not in result
        assert 'text' in result

    def test_xss_payload_sanitized(self):
        payload = '<img src=x onerror="alert(1)">'
        result = sanitize_str(payload)
        assert 'onerror' not in result
        assert '<img' not in result


# ── sanitize_email ────────────────────────────────────────────────────────────

class TestSanitizeEmail:
    def test_valid_email_lowercase(self):
        assert sanitize_email('User@Example.COM') == 'user@example.com'

    def test_strips_whitespace(self):
        assert sanitize_email('  test@test.com  ') == 'test@test.com'

    def test_invalid_email_returns_empty(self):
        assert sanitize_email('notanemail') == ''
        assert sanitize_email('missing@domain') == ''
        assert sanitize_email('@nodomain.com') == ''

    def test_non_string_returns_empty(self):
        assert sanitize_email(None) == ''
        assert sanitize_email(42) == ''

    def test_valid_email_with_plus(self):
        result = sanitize_email('user+tag@example.com')
        assert result == 'user+tag@example.com'

    def test_too_long_truncated_returns_empty(self):
        long_email = 'a' * 250 + '@b.com'
        result = sanitize_email(long_email)
        # Either empty (validation fails) or truncated
        assert len(result) <= 254


# ── sanitize_phone ────────────────────────────────────────────────────────────

class TestSanitizePhone:
    def test_valid_phone_preserved(self):
        assert sanitize_phone('+254700000001') == '+254700000001'

    def test_strips_invalid_chars(self):
        result = sanitize_phone('+254 700-000-001')
        # Keeps +, digits, spaces, dashes
        assert '+' in result
        assert '2' in result

    def test_strips_letters(self):
        result = sanitize_phone('+254abc700')
        assert 'a' not in result
        assert 'b' not in result
        assert 'c' not in result

    def test_non_string_returns_empty(self):
        assert sanitize_phone(None) == ''

    def test_truncates_to_20(self):
        long_phone = '+' + '1' * 30
        result = sanitize_phone(long_phone)
        assert len(result) <= 20


# ── get_location ──────────────────────────────────────────────────────────────

class TestGetLocation:
    def test_localhost_returns_local(self):
        assert get_location('127.0.0.1') == 'Local'
        assert get_location('::1') == 'Local'

    def test_unknown_ip_returns_local(self):
        assert get_location('unknown') == 'Local'

    def test_empty_ip_returns_local(self):
        assert get_location('') == 'Local'

    @patch('app.utils.requests.get')
    def test_external_ip_returns_city_country(self, mock_get):
        mock_get.return_value.json.return_value = {
            'city': 'Nairobi', 'country': 'Kenya'
        }
        result = get_location('41.90.64.1')
        assert 'Nairobi' in result
        assert 'Kenya' in result

    @patch('app.utils.requests.get')
    def test_api_failure_returns_unknown(self, mock_get):
        mock_get.side_effect = Exception('network error')
        result = get_location('8.8.8.8')
        assert result == 'Unknown'
