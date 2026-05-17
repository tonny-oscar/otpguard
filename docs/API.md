# OTPGuard API Reference

Full interactive docs: `GET /apidocs` (Swagger UI)

## Authentication

All protected endpoints require a Bearer token:
```
Authorization: Bearer <access_token>
```

Some endpoints also accept API key authentication:
```
X-API-Key: otpg_<your_key>
```

---

## Auth — `/api/auth`

### POST /api/auth/register
Create a new user account.

**Body:**
```json
{
  "email": "user@example.com",
  "password": "StrongPass123!",
  "full_name": "Jane Doe",
  "phone": "+254700000000"
}
```

**Response 201:**
```json
{ "message": "Account created", "user_id": 42 }
```

---

### POST /api/auth/login
Login and receive JWT tokens.

**Body:**
```json
{ "email": "user@example.com", "password": "StrongPass123!" }
```

**Response 200:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "mfa_required": true,
  "pre_auth_token": "eyJ..."
}
```

If `mfa_required` is true, use `pre_auth_token` to call `/api/mfa/request-otp`.

---

## MFA — `/api/mfa`

### POST /api/mfa/request-otp
Request an OTP code (requires pre-auth or full JWT).

**Body:**
```json
{ "method": "email" }
```
Methods: `email`, `sms`, `totp`

**Response 200:**
```json
{ "message": "OTP sent", "expires_in": 300 }
```

---

### POST /api/mfa/verify-otp
Verify an OTP code.

**Body:**
```json
{ "code": "847291" }
```

**Response 200:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ..."
}
```

---

### POST /api/mfa/setup-totp
Initialize TOTP authenticator setup.

**Response 200:**
```json
{
  "secret": "BASE32SECRET",
  "qr_url": "otpauth://totp/OTPGuard:user@example.com?secret=..."
}
```

---

### POST /api/mfa/verify-totp
Confirm TOTP setup with a code from the authenticator app.

**Body:**
```json
{ "code": "123456" }
```

---

## Users — `/api/users`

### GET /api/users/profile
Get the current user's profile.

### PUT /api/users/profile
Update profile fields (`full_name`, `phone`, `mfa_method`).

### GET /api/users/devices
List all tracked devices.

### POST /api/users/devices
Mark a device as trusted.

### GET /api/users/api-keys
List all API keys (keys are masked, showing only first 12 chars).

### POST /api/users/api-keys
Create a new API key.

**Body:**
```json
{ "name": "My Integration" }
```

**Response 201:**
```json
{
  "key": "otpg_abc123...",
  "name": "My Integration",
  "id": 5
}
```

### DELETE /api/users/api-keys/:id
Revoke an API key.

---

## Subscription — `/api/subscription`

### GET /api/subscription/plans
List all available plans with pricing.

### GET /api/subscription/current
Get the current user's active subscription.

### POST /api/subscription/subscribe
Subscribe to a plan.

**Body:**
```json
{ "plan_id": 2 }
```

### POST /api/subscription/cancel
Cancel the current subscription.

---

## Support — `/api/support`

### POST /api/support/contact
Submit a contact form message.

### POST /api/support/tickets
Create a support ticket.

**Body:**
```json
{
  "subject": "Can't receive SMS OTP",
  "category": "technical",
  "priority": "high",
  "message": "I've been trying..."
}
```

### GET /api/support/tickets
List tickets for the current user.

### GET /api/support/kb/categories
List knowledge base categories.

### GET /api/support/kb/articles?category=&search=
Search knowledge base articles.

### GET /api/support/kb/articles/:slug
Get a full article by slug.

### GET /api/support/forum/posts
List forum posts.

### POST /api/support/forum/posts
Create a new forum post.

---

## Health & Monitoring

### GET /api/health
```json
{ "status": "ok", "env": "production" }
```

### GET /api/health/detailed
```json
{
  "status": "ok",
  "checks": {
    "database": { "status": "ok", "latency_ms": 2.1 },
    "email":    { "status": "ok" },
    "sms":      { "status": "ok" }
  }
}
```

### GET /metrics
Prometheus metrics endpoint.

---

## Error Codes

| HTTP | Code | Meaning |
|------|------|---------|
| 400 | `VALIDATION_ERROR` | Invalid request body |
| 401 | `UNAUTHORIZED` | Missing or expired token |
| 403 | `FORBIDDEN` | Insufficient permissions |
| 404 | `NOT_FOUND` | Resource not found |
| 429 | `RATE_LIMIT_EXCEEDED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Server error |

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| Default | 200/day, 60/hour |
| POST /auth/register | 5/min, 20/hour |
| POST /auth/login | 10/min, 50/hour |
| POST /mfa/request-otp | 3/min, 10/hour |
| POST /mfa/verify-otp | 5/min, 20/hour |
