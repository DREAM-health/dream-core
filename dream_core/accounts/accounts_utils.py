
# class _Roles:
#     """Increases type safety by preventing typos while using literal strings."""
#     SUPERADMIN   = "SUPERADMIN"
#     ADMIN        = "ADMIN"
#     CLINICIAN    = "CLINICIAN"
#     LAB_MANAGER  = "LAB_MANAGER"
#     LAB_ANALYST  = "LAB_ANALYST"
#     FRONT_DESK   = "FRONT_DESK"
#     RECEPTIONIST = "RECEPTIONIST"
#     AUDITOR      = "AUDITOR"

# Roles = _Roles()

from django.db import models

class RoleType(models.TextChoices):
    # VARIABLE_NAME = "DATABASE_VALUE", "Human Readable Label"
    SUPERADMIN = "SUPERADMIN", "Super Administrator"
    ADMIN = "ADMIN", "Administrator"
    CLINICIAN = "CLINICIAN", "Clinician"
    LAB_MANAGER = "LAB_MANAGER", "Laboratory Manager"
    LAB_ANALYST = "LAB_ANALYST", "Laboratory Analyst"
    FRONT_DESK = "FRONT_DESK", "Front Desk"
    RECEPTIONIST = "RECEPTIONIST", "Receptionist"
    AUDITOR = "AUDITOR", "Compliance Auditor"