"""Development settings — never use in production."""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# Use SQLite for local dev without PostgreSQL running
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "dream_core_dev.sqlite3", # type: ignore[name-defined]  # noqa: F405
    }
}

CORS_ALLOW_ALL_ORIGINS = True

# Faster password hashing in dev
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

LOGGING: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "DEBUG"},
    "loggers": {
        "django.db.backends": {"level": "INFO"},  # set DEBUG to see SQL
    },
}
