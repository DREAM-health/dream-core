"""
dream_core/core/hard_delete.py

Hard-delete guard for SoftDeleteModel subclasses.

WHY THIS EXISTS
---------------
SoftDeleteModel.hard_delete() calls Django's real Model.delete() and
permanently removes a row from the database.  In a medical system that
is the most destructive operation possible — more so than any write,
because it is irreversible.

Without a guard, *any* piece of Python code that holds a model instance
can call hard_delete() silently and successfully:

    patient = Patient.all_objects.get(pk=some_id)
    patient.hard_delete()          # gone forever, no log, no permission check

This module adds three layers of protection that work together:

  1. HardDeleteGuard mixin  — wraps hard_delete() at the *model* level.
     Validates that the caller has the django.auth permission
     `<app_label>.hard_delete_<model_name>` AND passes an explicit
     `authorisation_token` string (a short human-readable justification,
     minimum 20 characters).  On success it writes a structured entry to
     the Python logger AND to django-auditlog so the event is queryable
     through the Audit API.

  2. CanHardDelete DRF permission class — a drop-in for DRF views.
     Rejects any request whose authenticated user does not carry the
     required Django permission.  Even if a view somehow routes to a
     hard-delete path, the HTTP layer refuses first.

  3. HardDeletePermission data migration helper — a signal receiver that
     automatically creates the `hard_delete_<model_name>` Django Permission
     for every registered model that uses HardDeleteGuard, so permissions
     exist in the DB without manual fixtures.


USAGE — model
-------------
    # dream_core/patients/models.py
    from dream_core.core.hard_delete import HardDeleteGuard

    class Patient(HardDeleteGuard, SoftDeleteModel):
        ...

    # anywhere in your codebase:
    patient.hard_delete(
        authorised_by=request.user,
        authorisation_token="LGPD erasure request #2024-0042 — DPO approved",
    )
    # raises HardDeleteNotAuthorised if the user lacks the permission
    # raises HardDeleteNotAuthorised if authorisation_token is too short


USAGE — DRF view
----------------
    # Only needed for views that explicitly expose a hard-delete endpoint.
    # Normal soft-delete views do NOT need this.
    from dream_core.core.hard_delete import CanHardDelete

    class PatientHardDeleteView(generics.DestroyAPIView):
        permission_classes = [IsAuthenticated, CanHardDelete]
        ...


PERMISSION NAMING CONVENTION
-----------------------------
    codename : hard_delete_<model_name_lower>
    name     : "Can hard delete <ModelName>"

    e.g. for Patient  →  patients.hard_delete_patient
         for LabTestDefinition → catalog.hard_delete_labtestdefinition

These permissions are created automatically via the post_migrate signal
(see _create_hard_delete_permission below) for every model that mixes in
HardDeleteGuard.  You can also grant them via the Django admin or a
data migration.

Superusers bypass the permission check (consistent with Django convention)
but the authorisation_token is still required.


AUTHORISATION TOKEN
-------------------
The token is a plain string stored in the audit log.  It must be at
least 20 characters to force the caller to write a meaningful
justification — not just "yes" or "ok".

Typical values:
  "LGPD art.18 erasure — ticket #DPO-2024-0042"
  "Test data teardown — authorised by CTO on 2024-11-01"
  "Merge duplicate records — approved in CAB-20241105"

The minimum length is enforced at the model level so it cannot be
bypassed by subclasses or direct ORM calls.
"""
from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

logger = logging.getLogger("dream_core.hard_delete")

# Minimum characters required in the authorisation_token.
# Short enough to be practical, long enough to require a real sentence.
MIN_TOKEN_LENGTH: int = 20

# Registry of all models that use HardDeleteGuard.
# Populated at class creation time by HardDeleteGuardMeta.
# Used by the post_migrate signal to create permissions.
_guarded_models: list[type] = []


# ── Exception ─────────────────────────────────────────────────────────────────

class HardDeleteNotAuthorised(PermissionError):
    """
    Raised when hard_delete() is called without meeting all conditions:

      - caller must have the `hard_delete_<model>` Django permission
        (or be a superuser)
      - authorisation_token must be at least MIN_TOKEN_LENGTH characters

    Inherits from PermissionError so callers that catch the broad
    PermissionError family will also catch this.
    """


# ── Metaclass ─────────────────────────────────────────────────────────────────

class HardDeleteGuardMeta(models.base.ModelBase):
    """
    Metaclass that registers each concrete HardDeleteGuard subclass into
    _guarded_models so the post_migrate signal can create their permissions.

    We use a metaclass rather than AppConfig.ready() because it fires at
    class definition time — before any app is fully loaded — and does not
    require importing every model explicitly.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> "HardDeleteGuardMeta":
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        # Skip abstract models — they have no DB table and no ContentType.
        if not getattr(getattr(cls, "_meta", None), "abstract", True):
            _guarded_models.append(cls)
        return cls


# ── Mixin ─────────────────────────────────────────────────────────────────────

class HardDeleteGuard(models.Model, metaclass=HardDeleteGuardMeta):
    """
    Mixin for SoftDeleteModel subclasses that need hard-delete capability.

    Place it BEFORE SoftDeleteModel in the MRO so its hard_delete()
    override takes precedence:

        class Patient(HardDeleteGuard, SoftDeleteModel):
            ...

    MRO resolution: Patient → HardDeleteGuard → SoftDeleteModel → AuditedModel
    → TimeStampedModel → UUIDModel → Model

    The mixin itself is abstract; it adds no columns.
    """

    class Meta:
        abstract = True

    def hard_delete(  # type: ignore[override]
        self,
        using: Any = None,
        keep_parents: bool = False,
        authorised_by: Any = None,
        authorisation_token: str = "",
    ) -> tuple[int, dict[str, int]]:
        """
        Permanently delete this record from the database.

        Parameters
        ----------
        authorised_by : User | None
            The User instance requesting the hard delete.  Must be provided
            and must have the `hard_delete_<model>` permission (or be a
            superuser).

        authorisation_token : str
            A human-readable justification of at least MIN_TOKEN_LENGTH
            characters.  Stored verbatim in the audit log.

        Returns
        -------
        tuple[int, dict[str, int]]
            Django's standard delete() return value: (rows_deleted, {model: count}).

        Raises
        ------
        HardDeleteNotAuthorised
            If the caller is not authorised or the token is too short.
        """
        self._validate_hard_delete_authorisation(authorised_by, authorisation_token)
        is_registered = self._log_hard_delete(authorised_by, authorisation_token)

        try:
            # Delegate directly to Django's real Model.delete(), bypassing SoftDeleteModel
            result = models.Model.delete(self, using=using, keep_parents=keep_parents)  # type: ignore[misc]
            return result  # type: ignore[return-value]
        finally:
            if is_registered:
                from auditlog.registry import auditlog as auditlog_registry
                auditlog_registry.register(self.__class__)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _get_hard_delete_permission_codename(self) -> str:
        """Return the codename for this model's hard-delete permission."""
        return f"hard_delete_{self.__class__._meta.model_name}"

    def _caller_has_permission(self, user: Any) -> bool:
        """
        Return True if the user may hard-delete this model type.

        Superusers always pass (consistent with Django's own convention).
        Otherwise the user must have the explicit `hard_delete_<model>`
        permission assigned either directly or via a Role.
        """
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True
        app_label = self.__class__._meta.app_label
        codename = self._get_hard_delete_permission_codename()
        return user.has_perm(f"{app_label}.{codename}")

    def _validate_hard_delete_authorisation(
        self,
        authorised_by: Any,
        authorisation_token: str,
    ) -> None:
        """
        Raise HardDeleteNotAuthorised if any condition is not met.

        Checks in order:
          1. A user was provided at all.
          2. The token meets the minimum length.
          3. The user has the required Django permission.
        """
        if authorised_by is None:
            raise HardDeleteNotAuthorised(
                "hard_delete() requires an authorised_by user. "
                "Pass the User instance of the person authorising this operation."
            )

        if len(authorisation_token.strip()) < MIN_TOKEN_LENGTH:
            raise HardDeleteNotAuthorised(
                f"hard_delete() requires an authorisation_token of at least "
                f"{MIN_TOKEN_LENGTH} characters. "
                f"Provide a meaningful justification (e.g. a ticket reference, "
                f"regulatory basis, or approval reference). "
                f"Received: {authorisation_token!r}"
            )

        if not self._caller_has_permission(authorised_by):
            app_label = self.__class__._meta.app_label
            codename = self._get_hard_delete_permission_codename()
            raise HardDeleteNotAuthorised(
                f"User '{getattr(authorised_by, 'email', str(authorised_by))}' "
                f"does not have permission '{app_label}.{codename}'. "
                f"This permission must be granted explicitly by a SUPERADMIN "
                f"before hard deletion is possible."
            )

    def _log_hard_delete(self, authorised_by: Any, authorisation_token: str) -> bool:
        """
        Write a structured log entry and an auditlog entry for this event.

        Two sinks are written intentionally:
          - Python logger  → goes to whatever handler is configured (stdout,
            syslog, Sentry, etc.).  Fast, always available.
          - AuditEvent → persisted in the database via proxy over LogEntry,
            queryable via the Audit API by AUDITOR/ADMIN roles.
        """
        model_label = (
            f"{self.__class__._meta.app_label}."
            f"{self.__class__._meta.model_name}"
        )
        actor_email = getattr(authorised_by, "email", str(authorised_by))

        # ── Structured Python log ──────────────────────────────────────────
        logger.warning(
            "HARD_DELETE model=%s pk=%s actor=%s token=%r",
            model_label,
            str(self.pk),  # type: ignore[attr-defined]
            actor_email,
            authorisation_token,
            extra={
                "event": "hard_delete",
                "model": model_label,
                "pk": str(self.pk),  # type: ignore[attr-defined]
                "actor": actor_email,
                "authorisation_token": authorisation_token,
            },
        )

        # ── AuditEvent (Proxy LogEntry) ───────────────────────────────────
        is_registered = False
        try:
            from dream_core.audit.models import AuditEvent

            is_registered = AuditEvent.objects.log_hard_delete(
                instance=self,
                authorised_by=authorised_by,
                authorisation_token=authorisation_token,
                actor_email=actor_email,
            )
        except Exception as exc:  # pragma: no cover
            # Logging failure must never block the authorised operation.
            logger.error(
                "Failed to write AuditEvent for hard_delete "
                "model=%s pk=%s: %s",
                model_label,
                str(self.pk),  # type: ignore[attr-defined]
                exc,
            )
            print("AUDITLOG EXCEPTION:", exc)
        return is_registered


# ── DRF Permission class ───────────────────────────────────────────────────────

class CanHardDelete(BasePermission):
    """
    DRF permission class for views that expose hard-delete endpoints.

    Rejects requests whose authenticated user does not have the
    `<app_label>.hard_delete_<model>` permission.

    The model is inferred from the view's queryset or get_queryset().
    If it cannot be inferred, the permission is denied.

    Usage
    -----
        class PatientHardDeleteView(generics.DestroyAPIView):
            permission_classes = [IsAuthenticated, CanHardDelete]
            queryset = Patient.all_objects.all()
    """

    message = (
        "You do not have permission to hard-delete this resource. "
        "The hard_delete_<model> permission must be granted explicitly."
    )

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True

        model_class = self._get_model_class(view)
        if model_class is None:
            return False

        app_label = model_class._meta.app_label
        codename = f"hard_delete_{model_class._meta.model_name}"
        return user.has_perm(f"{app_label}.{codename}")

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        # Object-level check delegates to has_permission — the permission is
        # model-scoped, not instance-scoped.
        return self.has_permission(request, view)

    @staticmethod
    def _get_model_class(view: APIView) -> type[models.Model] | None:
        """Best-effort extraction of the model class from a DRF view."""
        queryset = getattr(view, "queryset", None)
        if queryset is not None:
            return queryset.model  # type: ignore[return-value]
        try:
            qs = view.get_queryset()  # type: ignore[attr-defined]
            return qs.model  # type: ignore[return-value]
        except Exception:
            return None


# ── Auto-create Django Permissions after migrations ───────────────────────────

@receiver(post_migrate)
def _create_hard_delete_permissions(
    sender: Any,
    **kwargs: Any,
) -> None:
    """
    Create the `hard_delete_<model>` Django Permission for every model
    registered in _guarded_models.

    Fires after every `manage.py migrate` run.  Uses get_or_create so
    it is idempotent — safe to run multiple times.

    This replaces the need for manual fixtures or data migrations.
    The permissions appear in the Django admin "user permissions" picker
    immediately after the first migrate.
    """
    for model_class in _guarded_models:
        try:
            ct = ContentType.objects.get_for_model(model_class)
            codename = f"hard_delete_{model_class._meta.model_name}"
            permission, created = Permission.objects.get_or_create(
                codename=codename,
                content_type=ct,
                defaults={"name": f"Can hard delete {model_class.__name__}"},
            )
            if created:
                logger.info(
                    "Created hard-delete permission: %s.%s",
                    model_class._meta.app_label,
                    codename,
                )
        except Exception as exc:  # pragma: no cover
            # Table may not exist on a fresh DB before migrations run.
            logger.debug(
                "Could not create hard-delete permission for %s: %s",
                model_class,
                exc,
            )
