"""Test settings — fast, isolated, in-memory where possible."""
from .base import *  # noqa: F401, F403

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Fastest hasher for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable throttling in tests
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # type: ignore[name-defined]  # noqa: F405

# Disable auditlog middleware in unit tests (integration tests opt-in)
MIDDLEWARE = [m for m in MIDDLEWARE if "auditlog" not in m.lower()]  # type: ignore[name-defined]  # noqa: F405

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
