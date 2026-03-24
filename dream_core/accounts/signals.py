"""
dream_core/accounts/signals.py

Signals for the accounts app.
"""
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)


@receiver(user_logged_in)
def on_user_logged_in(sender: type, request: object, user: object, **kwargs: object) -> None:
    logger.info("LOGIN_SUCCESS user=%s", getattr(user, "email", str(user)))


@receiver(user_logged_out)
def on_user_logged_out(sender: type, request: object, user: object, **kwargs: object) -> None:
    logger.info("LOGOUT user=%s", getattr(user, "email", str(user)))


@receiver(user_login_failed)
def on_user_login_failed(sender: type, credentials: object, request: object, **kwargs: object) -> None:
    logger.warning(
        "LOGIN_FAILED credentials=%s",
        {k: v for k, v in (credentials or {}).items() if k != "password"},  # type: ignore[union-attr]
    )
