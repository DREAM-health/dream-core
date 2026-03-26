"""
dream_core/audit/models.py

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
    - A stable import path (`from dream_core.audit.models import AuditEvent`) that
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

from auditlog.models import LogEntry, LogEntryManager  # type: ignore[import-untyped]
from django.db import models
from django.db.models import QuerySet

if TYPE_CHECKING:
    from dream_core.accounts.models import User


# ── Custom manager ────────────────────────────────────────────────────────────

class AuditEventManager(LogEntryManager):
    """
    Manager with domain-oriented query helpers.

    All methods return QuerySets so callers can chain further filters,
    paginate, or annotate freely.
    """

    def log_hard_delete(
        self,
        instance: models.Model,
        authorised_by: User | None,
        authorisation_token: str,
        actor_email: str,
    ) -> bool:
        """
        Write a hard-delete audit entry.

        Wraps LogEntry.objects.log_create() so that hard_delete.py never
        needs to import from django-auditlog directly.
        """
        from auditlog.registry import auditlog as auditlog_registry
        from django.contrib.contenttypes.models import ContentType

        # ── Auditlog LogEntry ───────────────────────────────────────
        # We create the entry *before* the actual delete so the content_type
        # and pk are still resolvable.
        ct = ContentType.objects.get_for_model(instance.__class__)
        self.create(
            content_type=ct,
            object_pk=str(instance.pk),
            object_repr=str(instance),
            action=AuditEvent.Action.HARD_DELETE,
            actor=authorised_by if getattr(authorised_by, "pk", None) else None,
            additional_data={
                "hard_delete": True,
                "authorisation_token": authorisation_token,
                "actor_email": actor_email,
            },
        )

        # Temporarily unregister the model from auditlog to prevent duplicate
        # DELETE entries (one from us with additional_data, one from auditlog
        # middleware without it).
        is_registered = instance.__class__ in auditlog_registry._registry
        if is_registered:
            auditlog_registry.unregister(instance.__class__)
        return is_registered

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
    
    def for_facility(self, facility_id: str) -> QuerySet["AuditEvent"]:
        """
        All events whose audited object belongs to a given facility.

        Phase 2 hook: uses `additional_data__facility_id` stored by the
        AuditlogMiddleware once facility-scoping is active. In Phase 1 this
        returns an empty queryset (no additional_data is set yet) so callers
        should guard on FACILITY_ENFORCEMENT_ENABLED.

        Implementation note: django-auditlog stores arbitrary extra data in the
        `additional_data` JSONField. In Phase 2, a custom signal or middleware
        will write {'facility_id': str(obj.facility_id)} there on every audited
        mutation, making this filter efficient via a GIN index.
        """
        from django.conf import settings
        if not getattr(settings, "FACILITY_ENFORCEMENT_ENABLED", False):
            return self.get_queryset().none()
        return self.get_queryset().filter(
            additional_data__facility_id=str(facility_id)
    )

    def creates(self) -> QuerySet["AuditEvent"]:
        return self.get_queryset().filter(action=AuditEvent.Action.CREATE)

    def updates(self) -> QuerySet["AuditEvent"]:
        return self.get_queryset().filter(action=AuditEvent.Action.UPDATE)

    def deletes(self) -> QuerySet["AuditEvent"]:
        return self.get_queryset().filter(action=AuditEvent.Action.DELETE)

    def accesses(self) -> QuerySet["AuditEvent"]:
        return self.get_queryset().filter(action=AuditEvent.Action.ACCESS)

    def hard_deletes(self) -> QuerySet["AuditEvent"]:
        return self.get_queryset().filter(action=AuditEvent.Action.HARD_DELETE)

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

    class Action(LogEntry.Action):
        """
        Extends auditlog's Action constants with dream-core-specific actions.

        HARD_DELETE (4) is stored in the same `action` PositiveSmallIntegerField
        as the standard actions. The field has no upper-bound validator that would
        block it, and auditlog's own choices tuple is not used for DB constraint
        enforcement — only for display in the Django admin.

        Use AuditEvent.Action.HARD_DELETE when writing hard-delete audit entries
        via log_create(). The entry will be visible through AuditEvent.objects
        and all its query helpers, and will display as "hard delete" in the admin.
        """
        HARD_DELETE = 4

        choices = LogEntry.Action.choices + (
            (HARD_DELETE, str("hard_delete")),
        )

        CHOICES = dict((i, str(s)) for i, s in choices)

        @classmethod
        def display(self, code: int) -> str:
            return self.CHOICES.get(code, "UNKNOWN")

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
        """Human-readable action label: CREATE / UPDATE / DELETE / ACCESS / HARD_DELETE."""
        return AuditEvent.Action.display(self.action)

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
