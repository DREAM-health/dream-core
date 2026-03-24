from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dream_core.accounts"
    verbose_name = "Accounts"

    def ready(self) -> None:
        import dream_core.accounts.signals  # noqa: F401
