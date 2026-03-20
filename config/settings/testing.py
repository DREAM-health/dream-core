"""Test settings — fast, isolated, in-memory where possible."""
from .base import *

DEBUG = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "dream_core_test.sqlite3", # type: ignore[name-defined]  # noqa: F405
    }
}

# Fastest hasher for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable throttling in tests
# REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # type: ignore[name-defined]  # noqa: F405

# Disable auditlog middleware in unit tests (integration tests opt-in)
# MIDDLEWARE = [m for m in MIDDLEWARE if "auditlog" not in m.lower()]  # type: ignore[name-defined]  # noqa: F405

# EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
LOGGING = {}