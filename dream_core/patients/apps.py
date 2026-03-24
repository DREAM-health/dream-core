from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dream_core.patients"
    verbose_name = "Patient Registry"
