"""Development settings — never use in production."""
from .base import BASE_DIR, LOGGING as BASE_LOGGING

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Use SQLite for local dev without PostgreSQL running
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "dream_core_dev.sqlite3",
    }
}

CORS_ALLOW_ALL_ORIGINS = True

# Faster password hashing in dev
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

LOGGING: dict = {
    **BASE_LOGGING,
    "handlers": {
        **BASE_LOGGING.get("handlers", {}),
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "DEBUG"},
    "loggers": {
        **BASE_LOGGING.get("loggers", {}),
        "django.db.backends": {"level": "INFO"},  # set DEBUG to see SQL
    },
}
