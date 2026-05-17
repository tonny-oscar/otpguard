import os
import time
import logging
import traceback
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from config import config
from app.extensions import db, jwt, mail, limiter
from flask_cors import CORS
from flasgger import Swagger

BASE_DIR    = os.path.abspath(os.path.dirname(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, '..', '.env')
load_dotenv(DOTENV_PATH)

IS_PROD = os.getenv('FLASK_ENV', 'development') == 'production'
logger  = logging.getLogger(__name__)


def create_app(env=None):
    app = Flask(__name__)

    env = env or os.getenv('FLASK_ENV', 'development')
    app.config.from_object(config.get(env, config['default']))

    # ── Security config ───────────────────────────────────────────
    app.config.update(
        SESSION_COOKIE_SECURE    = IS_PROD,
        SESSION_COOKIE_HTTPONLY  = True,
        SESSION_COOKIE_SAMESITE  = 'Lax',
        REMEMBER_COOKIE_SECURE   = IS_PROD,
        REMEMBER_COOKIE_HTTPONLY = True,
        MAX_CONTENT_LENGTH       = 2 * 1024 * 1024,
        JWT_COOKIE_SECURE        = IS_PROD,
        JWT_COOKIE_SAMESITE      = 'Lax',
    )

    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    # ── Structured logging + Sentry + Metrics ────────────────────
    from app.logging_config import setup_logging
    from app.sentry import init_sentry
    from app.metrics import init_metrics
    setup_logging(app)
    init_sentry(app)
    init_metrics(app)

    # ── CORS ──────────────────────────────────────────────────────
    CORS(app,
         resources={r'/api/*': {'origins': [
             'http://localhost:5173',
             'http://localhost:3000',
             os.getenv('FRONTEND_URL', 'https://otpguard.onrender.com'),
         ]}},
         supports_credentials=False,
         allow_headers=['Content-Type', 'Authorization', 'X-API-Key'],
         methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
         max_age=600)

    # ── Request timing ────────────────────────────────────────────
    @app.before_request
    def _req_start():
        request._t = time.monotonic()

    # ── OPTIONS preflight ─────────────────────────────────────────
    @app.before_request
    def _handle_preflight():
        if request.method == 'OPTIONS':
            resp = jsonify({'ok': True})
            resp.headers['Access-Control-Allow-Origin']  = '*'
            resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, PATCH, OPTIONS'
            resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
            resp.headers['Access-Control-Max-Age']       = '600'
            return resp, 200

    # ── Security headers + request logging ────────────────────────
    @app.after_request
    def _after(response):
        # CORS
        response.headers['Access-Control-Allow-Origin']  = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, PATCH, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
        # Security
        response.headers['X-Frame-Options']        = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection']       = '1; mode=block'
        response.headers['Referrer-Policy']         = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy']      = 'camera=(), microphone=(), geolocation=(), payment=()'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src *; frame-ancestors 'none'; base-uri 'self'; form-action 'self';"
        if IS_PROD:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        response.headers.pop('Server', None)
        response.headers.pop('X-Powered-By', None)

        # Request log (skip health/static noise)
        skip = {'/api/health', '/health', '/favicon.ico'}
        if request.path not in skip and hasattr(request, '_t'):
            ms = round((time.monotonic() - request._t) * 1000, 1)
            logger.info('http', extra={
                'method': request.method,
                'path':   request.path,
                'status': response.status_code,
                'ms':     ms,
                'ip':     request.remote_addr,
            })
        return response

    # ── Error handlers ────────────────────────────────────────────
    @app.errorhandler(429)
    def _too_many(e):
        from app.audit import log_rate_limit_hit
        log_rate_limit_hit(ip=request.remote_addr or '', endpoint=request.path)
        return jsonify({
            'error': 'Too many requests. Please slow down.',
            'code':  'RATE_LIMIT_EXCEEDED',
            'retry_after': getattr(e, 'retry_after', 60),
        }), 429

    @app.errorhandler(413)
    def _too_large(e):
        return jsonify({'error': 'Request body too large. Max 2 MB.'}), 413

    @app.errorhandler(404)
    def _not_found(e):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def _server_error(e):
        logger.error('server_error', extra={
            'path':  request.path,
            'method': request.method,
            'ip':    request.remote_addr,
            'error': str(e),
            'trace': traceback.format_exc(),
        })
        return jsonify({'error': 'Internal server error'}), 500

    # ── Swagger ───────────────────────────────────────────────────
    Swagger(app, template={
        'swagger': '2.0',
        'info': {
            'title':       'OTPGuard API',
            'description': 'Multi-factor authentication OTP service API',
            'version':     '1.0.0',
        },
        'host':     'localhost:5000',
        'basePath': '/api',
        'schemes':  ['http', 'https'],
        'consumes': ['application/json'],
        'produces': ['application/json'],
        'securityDefinitions': {
            'Bearer': {'type': 'apiKey', 'name': 'Authorization', 'in': 'header'}
        },
    })

    # ── Blueprints ────────────────────────────────────────────────
    from app.auth.routes         import auth_bp
    from app.mfa.routes          import mfa_bp
    from app.users.routes        import users_bp
    from app.admin.routes        import admin_bp
    from app.subscription.routes import subscription_bp
    from app.support.routes      import support_bp

    app.register_blueprint(auth_bp,         url_prefix='/api/auth')
    app.register_blueprint(mfa_bp,          url_prefix='/api/mfa')
    app.register_blueprint(users_bp,        url_prefix='/api/users')
    app.register_blueprint(admin_bp,        url_prefix='/api/admin')
    app.register_blueprint(subscription_bp, url_prefix='/api/subscription')
    app.register_blueprint(support_bp,      url_prefix='/api/support')

    @app.route('/')
    def index():
        return {'message': 'OTPGuard API', 'version': '1.0.0', 'docs': '/apidocs'}, 200

    @app.route('/api/health')
    def health():
        return {'status': 'ok', 'env': env}, 200

    @app.route('/api/health/detailed')
    def health_detailed():
        """Detailed health check for uptime monitoring tools."""
        import time
        from sqlalchemy import text
        checks = {}

        # Database check
        t0 = time.monotonic()
        try:
            db.session.execute(text('SELECT 1'))
            checks['database'] = {'status': 'ok', 'latency_ms': round((time.monotonic() - t0) * 1000, 1)}
        except Exception as e:
            checks['database'] = {'status': 'error', 'error': str(e)}

        # Mail config check
        checks['email'] = {
            'status': 'ok' if app.config.get('MAIL_USERNAME') else 'unconfigured'
        }

        # SMS config check
        checks['sms'] = {
            'status': 'ok' if (app.config.get('TWILIO_ACCOUNT_SID') or app.config.get('AT_API_KEY')) else 'unconfigured'
        }

        overall = 'ok' if all(v.get('status') == 'ok' for v in checks.values()) else 'degraded'

        return {
            'status': overall,
            'env': env,
            'version': os.getenv('APP_VERSION', '1.0.0'),
            'timestamp': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
            'checks': checks
        }, 200 if overall == 'ok' else 207

    with app.app_context():
        db.create_all()
        from app.subscription.service import SubscriptionService
        SubscriptionService.initialize_default_plans()
        from app.support.routes import seed_support_data
        seed_support_data()

    return app
