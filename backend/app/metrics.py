from prometheus_flask_exporter import PrometheusMetrics

metrics = PrometheusMetrics.for_app_factory()

_OTP_COUNTER   = None
_AUTH_COUNTER  = None
_ERROR_COUNTER = None


def init_metrics(app):
    global _OTP_COUNTER, _AUTH_COUNTER, _ERROR_COUNTER

    metrics.init_app(app)
    metrics.info('otpguard_info', 'OTPGuard application info',
                 version=app.config.get('APP_VERSION', '1.0.0'))

    _OTP_COUNTER = metrics.counter(
        'otpguard_otp_requests_total',
        'Total OTP requests by method and status',
        labels={'method': lambda: 'unknown', 'status': lambda: 'unknown'},
    )
    _AUTH_COUNTER = metrics.counter(
        'otpguard_auth_attempts_total',
        'Total authentication attempts by outcome',
        labels={'outcome': lambda: 'unknown'},
    )
    _ERROR_COUNTER = metrics.counter(
        'otpguard_errors_total',
        'Total application errors by type',
        labels={'error_type': lambda: 'unknown'},
    )


def record_otp_request(method: str, status: str):
    """Call after each OTP send/verify to track metrics."""
    if _OTP_COUNTER:
        _OTP_COUNTER.labels(method=method, status=status).inc()


def record_auth_attempt(outcome: str):
    """Call after each login attempt."""
    if _AUTH_COUNTER:
        _AUTH_COUNTER.labels(outcome=outcome).inc()


def record_error(error_type: str):
    """Call when a tracked error occurs."""
    if _ERROR_COUNTER:
        _ERROR_COUNTER.labels(error_type=error_type).inc()
