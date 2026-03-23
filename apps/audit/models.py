"""
apps/audit/models.py

AuditEvent — a proxy model over django-auditlog's LogEntry.

Why a proxy and not a concrete model?
  django-auditlog already captures all mutations via signals and middleware.
  Duplicating that data into a separate table would create synchronisation risk
  and double the write load on every audited mutation.

  A proxy model gives us:
    - A named, first-class Django model we fully own (custom managers,
      properties, admin registration, future annotations).
    - A migration-controlled place to add facility-scoped filtering once the
      Facility model lands (Phase 2).
    - A stable import path (`from apps.audit.models import AuditEvent`) that
      will never break even if django-auditlog changes its own model name.
    - The ability to add retention policy methods (e.g. `purge_before()`)
      without touching upstream code.

Retention notes:
  Audit entries are NEVER soft-deleted or hard-deleted through the API.
  `AuditEventManager.purge_before()` exists for DPA/LGPD-compliant bulk
  purges authorised by a data controller — it must only be called from a
  privileged management command, never from a view.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from auditlog.models import LogEntry  # type: ignore[import-untyped]
from django.db import models
from django.db.models import QuerySet

if TYPE_CHECKING:
    from apps.accounts.models import User


# ── Action constants (mirrors LogEntry.Action) ────────────────────────────────

class AuditAction:
    """Human-readable constants for LogEntry.action integer codes."""
    CREATE = 0
    UPDATE = 1
    DELETE = 2
    ACCESS = 3

    CHOICES: dict[int, str] = {
        CREATE: "CREATE",
        UPDATE: "UPDATE",
        DELETE: "DELETE",
        ACCESS: "ACCESS",
    }

    @classmethod
    def display(cls, code: int) -> str:
        return cls.CHOICES.get(code, "UNKNOWN")


# ── Custom manager ────────────────────────────────────────────────────────────

class AuditEventManager(models.Manager["AuditEvent"]):
    """
    Manager with domain-oriented query helpers.

    All methods return QuerySets so callers can chain further filters,
    paginate, or annotate freely.
    """

    def for_object(self, obj: models.Model) -> QuerySet["AuditEvent"]:
        """All events for a specific model instance."""
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(obj)
        return self.get_queryset().filter(
            content_type=ct,
            object_pk=str(obj.pk),
        )

    def for_actor(self, user: "User") -> QuerySet["AuditEvent"]:
        """All events performed by a specific user."""
        return self.get_queryset().filter(actor=user)

    def for_model(self, app_label: str, model_name: str) -> QuerySet["AuditEvent"]:
        """All events for every instance of a given model class."""
        return self.get_queryset().filter(
            content_type__app_label=app_label,
            content_type__model=model_name.lower(),
        )

    def creates(self) -> QuerySet["AuditEvent"]:
        return self.get_queryset().filter(action=AuditAction.CREATE)

    def updates(self) -> QuerySet["AuditEvent"]:
        return self.get_queryset().filter(action=AuditAction.UPDATE)

    def deletes(self) -> QuerySet["AuditEvent"]:
        return self.get_queryset().filter(action=AuditAction.DELETE)

    def in_range(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> QuerySet["AuditEvent"]:
        """Filter by timestamp range. Either bound may be omitted."""
        qs = self.get_queryset()
        if date_from:
            qs = qs.filter(timestamp__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__lte=date_to)
        return qs

    def purge_before(self, cutoff: datetime) -> int:
        """
        Permanently delete audit entries older than `cutoff`.

        COMPLIANCE WARNING: This is a destructive, irreversible operation.
        Call only from a privileged management command after obtaining
        appropriate data-controller authorisation (e.g. DPA/LGPD retention
        policy). Never expose this through any API endpoint.

        Returns the number of deleted rows.
        """
        count, _ = self.get_queryset().filter(timestamp__lt=cutoff).delete()
        return count


# ── Proxy model ───────────────────────────────────────────────────────────────

class AuditEvent(LogEntry):
    """
    Domain proxy over django-auditlog's LogEntry.

    Adds:
      - Named manager with query helpers (AuditEventManager).
      - Computed properties for clean display.
      - A stable import path decoupled from the upstream library.
      - A migration hook for facility-scoping (Phase 2).

    This model adds NO new database columns — it is a proxy, so no
    data migration is needed and the underlying table is shared with
    LogEntry. All django-auditlog signals write directly to that table
    and are immediately visible through this proxy.
    """

    objects: AuditEventManager = AuditEventManager()  # type: ignore[assignment]

    class Meta:
        proxy = True
        verbose_name = "Audit Event"
        verbose_name_plural = "Audit Events"
        # LogEntry is already ordered by -timestamp; we inherit that.
        ordering = ["-timestamp"]

    # ── Convenience properties ─────────────────────────────────────────────

    @property
    def action_display(self) -> str:
        """Human-readable action label: CREATE / UPDATE / DELETE / ACCESS."""
        return AuditAction.display(self.action)

    @property
    def resource_label(self) -> str:
        """
        Dotted string identifying the audited resource type.
        e.g. "patients.patient", "catalog.labtestdefinition"
        """
        return f"{self.content_type.app_label}.{self.content_type.model}"

    @property
    def actor_display(self) -> str:
        """Best-effort display of the actor; graceful when actor is deleted."""
        if self.actor:
            email = getattr(self.actor, "email", None)
            return str(email) if email else str(self.actor)
        return "(system)"

    @property
    def changed_fields(self) -> list[str]:
        """List of field names that were mutated (UPDATE events only)."""
        if not self.changes:
            return []
        return list(self.changes.keys())

    def __str__(self) -> str:
        return (
            f"[{self.timestamp:%Y-%m-%d %H:%M:%S UTC}] "
            f"{self.action_display} {self.resource_label} "
            f"pk={self.object_pk} by {self.actor_display}"
        )
