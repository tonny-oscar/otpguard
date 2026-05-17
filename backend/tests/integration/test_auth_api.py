"""Integration tests for /api/auth/* endpoints."""
import pytest


class TestRegister:
    URL = '/api/auth/register'

    def test_register_success(self, client):
        resp = client.post(self.URL, json={
            'email': 'new@test.com', 'password': 'securepass1', 'full_name': 'New User'
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['user']['email'] == 'new@test.com'
        assert 'access_token' in data
        assert 'refresh_token' in data
        assert 'password_hash' not in data['user']

    def test_register_missing_email(self, client):
        resp = client.post(self.URL, json={'password': 'securepass1'})
        assert resp.status_code == 400
        assert 'Email' in resp.get_json()['error']

    def test_register_missing_password(self, client):
        resp = client.post(self.URL, json={'email': 'x@test.com'})
        assert resp.status_code == 400
        assert 'Password' in resp.get_json()['error']

    def test_register_weak_password(self, client):
        resp = client.post(self.URL, json={'email': 'x@test.com', 'password': 'short'})
        assert resp.status_code == 400
        assert '8 characters' in resp.get_json()['error']

    def test_register_duplicate_email(self, client, regular_user):
        resp = client.post(self.URL, json={
            'email': 'user@test.com', 'password': 'newpassword'
        })
        assert resp.status_code == 409
        assert 'already registered' in resp.get_json()['error']

    def test_register_invalid_email_format(self, client):
        resp = client.post(self.URL, json={'email': 'notanemail', 'password': 'password123'})
        assert resp.status_code == 400

    def test_register_with_phone(self, client):
        resp = client.post(self.URL, json={
            'email': 'phone@test.com', 'password': 'password123',
            'phone': '+254711000001',
        })
        assert resp.status_code == 201
        assert resp.get_json()['user']['mfa_method'] == 'sms'

    def test_register_without_phone_uses_email_mfa(self, client):
        resp = client.post(self.URL, json={
            'email': 'noPhone@test.com', 'password': 'password123',
        })
        assert resp.status_code == 201
        assert resp.get_json()['user']['mfa_method'] == 'email'

    def test_register_xss_in_full_name(self, client):
        resp = client.post(self.URL, json={
            'email': 'xss@test.com', 'password': 'password123',
            'full_name': '<script>alert(1)</script>',
        })
        assert resp.status_code == 201
        name = resp.get_json()['user']['full_name']
        assert '<script>' not in name


class TestLogin:
    URL = '/api/auth/login'

    def test_login_success_no_mfa(self, client, regular_user):
        resp = client.post(self.URL, json={
            'email': 'user@test.com', 'password': 'password123'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['mfa_required'] is False
        assert 'access_token' in data

    def test_login_mfa_required(self, client, mfa_user):
        resp = client.post(self.URL, json={
            'email': 'mfa@test.com', 'password': 'password123'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['mfa_required'] is True
        assert 'pre_auth_token' in data
        assert 'access_token' not in data

    def test_login_invalid_password(self, client, regular_user):
        resp = client.post(self.URL, json={
            'email': 'user@test.com', 'password': 'wrongpassword'
        })
        assert resp.status_code == 401
        assert 'Invalid credentials' in resp.get_json()['error']

    def test_login_unknown_email(self, client):
        resp = client.post(self.URL, json={
            'email': 'nobody@test.com', 'password': 'password123'
        })
        assert resp.status_code == 401

    def test_login_disabled_account(self, client, regular_user):
        from app.extensions import db
        regular_user.is_active = False
        db.session.commit()
        resp = client.post(self.URL, json={
            'email': 'user@test.com', 'password': 'password123'
        })
        assert resp.status_code == 403
        assert 'disabled' in resp.get_json()['error']

    def test_login_missing_credentials(self, client):
        resp = client.post(self.URL, json={})
        assert resp.status_code == 400

    def test_login_admin_skips_mfa(self, client, admin_user):
        resp = client.post(self.URL, json={
            'email': 'admin@test.com', 'password': 'adminpass123'
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['mfa_required'] is False
        assert 'access_token' in data

    def test_login_by_phone(self, client, regular_user):
        resp = client.post(self.URL, json={
            'identifier': '+254700000001', 'password': 'password123'
        })
        assert resp.status_code == 200


class TestRefreshToken:
    URL = '/api/auth/refresh'

    def test_refresh_returns_new_access_token(self, client, regular_user):
        login = client.post('/api/auth/login', json={
            'email': 'user@test.com', 'password': 'password123'
        })
        refresh_token = login.get_json()['refresh_token']
        resp = client.post(self.URL, headers={
            'Authorization': f'Bearer {refresh_token}'
        })
        assert resp.status_code == 200
        assert 'access_token' in resp.get_json()

    def test_refresh_fails_with_access_token(self, client, auth_headers):
        resp = client.post(self.URL, headers=auth_headers)
        assert resp.status_code == 422

    def test_refresh_fails_without_token(self, client):
        resp = client.post(self.URL)
        assert resp.status_code == 401


class TestMe:
    URL = '/api/auth/me'

    def test_me_returns_user(self, client, auth_headers, regular_user):
        resp = client.get(self.URL, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json()['user']['email'] == 'user@test.com'

    def test_me_requires_auth(self, client):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_me_invalid_token(self, client):
        resp = client.get(self.URL, headers={'Authorization': 'Bearer invalid.token.here'})
        assert resp.status_code == 422
