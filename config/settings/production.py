"""
Production settings.
All secrets MUST come from environment variables — never hardcode.
"""
from .base import *  # noqa: F401, F403
from decouple import config  # type: ignore[import-untyped]

DEBUG = False

SECRET_KEY: str = config("SECRET_KEY")  # no default — will crash if unset

ALLOWED_HOSTS: list[str] = config("ALLOWED_HOSTS", cast=lambda v: v.split(","))

# ── Database (production PostgreSQL) ─────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST"),
        "PORT": config("DB_PORT", default="5432"),
        "OPTIONS": {
            "connect_timeout": 10,
            "sslmode": "require",
        },
        "CONN_MAX_AGE": 60,
    }
}

# ── Security headers ──────────────────────────────────────────────────────────
SECURE_HSTS_SECONDS: int = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS: bool = True
SECURE_HSTS_PRELOAD: bool = True
SECURE_SSL_REDIRECT: bool = True
SESSION_COOKIE_SECURE: bool = True
CSRF_COOKIE_SECURE: bool = True
SECURE_BROWSER_XSS_FILTER: bool = True
SECURE_CONTENT_TYPE_NOSNIFF: bool = True
X_FRAME_OPTIONS: str = "DENY"

# ── CORS (tighten for production) ─────────────────────────────────────────────
CORS_ALLOWED_ORIGINS: list[str] = config(
    "CORS_ALLOWED_ORIGINS", cast=lambda v: v.split(","), default=""
)

LOGGING: dict = {  # type: ignore[type-arg]
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "django.utils.log.ServerFormatter",
            "format": '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}',
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        "django.security": {"handlers": ["console"], "level": "ERROR"},
        "dream_core": {"handlers": ["console"], "level": "WARNING"},
    },
}
