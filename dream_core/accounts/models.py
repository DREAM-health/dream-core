"""
dream_core/accounts/models.py

Custom User model + Role/Permission model for dream-core RBAC.

Design:
- Custom AbstractBaseUser so we own the auth model from day one.
- Roles are defined as DB records — new roles can be added without a code deployment.
- Each Role carries a set of Django Permission objects (reuses Django's
  built-in permission infrastructure).
- django-guardian provides *object-level* permissions on top of this.
- django-auditlog is registered below for all mutations.
"""
import uuid
from typing import TYPE_CHECKING

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone
from auditlog.registry import auditlog

from dream_core.core.models import UUIDModel, TimeStampedModel

if TYPE_CHECKING:
    pass


# ── Role ──────────────────────────────────────────────────────────────────────

class Role(TimeStampedModel):
    """
    A named role that groups Django Permissions.

    Predefined roles (created via data migration):
      SUPERADMIN  – platform admin.
      ADMIN       – facility admin.
      CLINICIAN   – doctors / nurses (dream-cen scope)
      LAB_MANAGER – lab supervisor (dream-lab scope)
      LAB_ANALYST – bench analyst (dream-lab scope)
      FRONT_DESK  – Receptionist or secretary
      AUDITOR     – read-only access
    """

    name: models.CharField = models.CharField(max_length=100, unique=True)
    description: models.TextField = models.TextField(blank=True)
    permissions: models.ManyToManyField = models.ManyToManyField(
        "auth.Permission",
        blank=True,
        related_name="roles",
        help_text="Django permissions granted to users with this role.",
    )
    is_system: models.BooleanField = models.BooleanField(
        default=False,
        help_text="System roles cannot be deleted.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self) -> str:
        return self.name


# ── User Manager ──────────────────────────────────────────────────────────────

class UserManager(BaseUserManager["User"]):
    def _create_user(
        self,
        email: str,
        password: str | None,
        **extra_fields: object,
    ) -> "User":
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        user: User = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: object,
    ) -> "User":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: object,
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


# ── User ──────────────────────────────────────────────────────────────────────

class User(AbstractBaseUser, PermissionsMixin):
    """
    Platform user. Email is the login identifier.

    PermissionsMixin provides groups, user_permissions, is_superuser,
    has_perm, has_module_perms.
    """

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    email: models.EmailField = models.EmailField(unique=True, db_index=True)
    first_name: models.CharField = models.CharField(max_length=150)
    last_name: models.CharField = models.CharField(max_length=150)

    # Professional info
    professional_id: models.CharField = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g. CRM/CRF/CRBio registration number.",
    )
    department: models.CharField = models.CharField(max_length=200, blank=True)
    phone: models.CharField = models.CharField(max_length=30, blank=True)

    # RBAC
    roles: models.ManyToManyField = models.ManyToManyField(
        Role,
        blank=True,
        related_name="users",
        help_text="Roles assigned to this user.",
    )

    # Status
    is_active: models.BooleanField = models.BooleanField(default=True)
    is_staff: models.BooleanField = models.BooleanField(default=False)

    # Compliance
    must_change_password: models.BooleanField = models.BooleanField(
        default=True,
        help_text="Forces password change on next login.",
    )
    password_changed_at: models.DateTimeField = models.DateTimeField(null=True, blank=True)
    last_login_ip: models.GenericIPAddressField = models.GenericIPAddressField(
        null=True, blank=True
    )
    failed_login_attempts: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        default=0
    )
    locked_until: models.DateTimeField = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    objects: UserManager = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["last_name", "first_name"]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        return timezone.now() < self.locked_until

    def get_all_permissions(self, obj: object = None) -> set[str]:  # type: ignore[override]
        """Return all permissions from Django groups + assigned roles."""
        perms: set[str] = super().get_all_permissions(obj)
        for role in self.roles.prefetch_related("permissions").all():
            for perm in role.permissions.all():
                perms.add(f"{perm.content_type.app_label}.{perm.codename}")
        return perms

    def has_role(self, role_name: str) -> bool:
        return self.roles.filter(name=role_name).exists()

    def record_failed_login(self) -> None:
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=15)
        self.save(update_fields=["failed_login_attempts", "locked_until"])

    def record_successful_login(self, ip: str | None = None) -> None:
        self.failed_login_attempts = 0
        self.locked_until = None
        if ip:
            self.last_login_ip = ip
        self.save(update_fields=["failed_login_attempts", "locked_until", "last_login_ip"])


# ── Auditlog registration ──────────────────────────────────────────────────────
auditlog.register(User, exclude_fields=["password", "last_login"])
auditlog.register(Role)
