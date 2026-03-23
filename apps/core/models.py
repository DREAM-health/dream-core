"""
apps/core/models.py

Base abstract models used across the entire dream-core.

Design decisions:
- UUIDs as primary keys: prevents sequential ID enumeration attacks and also map cleanly to FHIR Resource.id. 
    See more: https://hl7.org/fhir/R4/resource.html#id
- Soft-delete only: medical records must NEVER be physically destroyed
- created_at / updated_at on every model
- created_by / updated_by tracked via middleware (set in save())


UPDATED: 
    Change from the original:
        - SoftDeleteModel.hard_delete() is removed from this file.
        - Models that need hard-delete capability must mix in HardDeleteGuard
            (from apps.core.hard_delete) which provides the guarded version.
        - Models that do NOT mix in HardDeleteGuard have no hard_delete() at all —
            the operation is simply unavailable, not just unguarded.
        
This is intentional: the absence of hard_delete() on plain SoftDeleteModel
forces every callsite to be explicit about whether it needs the capability.
"""
import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone


class UUIDModel(models.Model):
    """Abstract base: UUID primary key."""

    id: models.UUIDField = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Globally unique identifier (UUID v4).",
    )

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    """Abstract base: UUID pk + created/updated timestamps."""

    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class AuditedModel(TimeStampedModel):
    """
    Abstract base: timestamps + who created/updated.

    The created_by / updated_by are nullable FKs to support system-generated
    records (migrations, fixtures, data imports) and to avoid circular imports
    before AUTH_USER_MODEL is resolved.
    """

    created_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created",
        help_text="User who created this record.",
    )
    updated_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_updated",
        help_text="User who last updated this record.",
    )

    class Meta:
        abstract = True


class SoftDeleteManager(models.Manager["SoftDeleteModel"]):
    """Default manager that excludes soft-deleted records."""

    def get_queryset(self) -> models.QuerySet["SoftDeleteModel"]:
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager["SoftDeleteModel"]):
    """Manager that includes soft-deleted records (admin / audit use)."""

    def get_queryset(self) -> models.QuerySet["SoftDeleteModel"]:
        return super().get_queryset()


class SoftDeleteModel(AuditedModel):
    """
    Abstract base with soft-delete capability.

    COMPLIANCE REQUIREMENT:
    Medical records must never be physically deleted.
    Use .delete() to soft-delete.

    Hard deletion is intentionally removed from this base class.
    Models that require hard-delete capability (e.g. for LGPD/GDPR erasure
    under regulatory authorisation) must also mixin HardDeleteGuard from
    apps.core.hard_delete, which adds a guarded hard_delete() method
    requiring an explicit permission and a written authorisation token:
 
        from apps.core.hard_delete import HardDeleteGuard
 
        class Patient(HardDeleteGuard, SoftDeleteModel):
            ...
 
        # Later, with explicit authorisation:
        patient.hard_delete(
            authorised_by=request.user,
            authorisation_token="LGPD erasure request #2024-0042 — DPO approved",
        )
    """

    deleted_at: models.DateTimeField = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="If set, this record has been soft-deleted.",
    )
    deleted_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_deleted",
        help_text="User who deleted this record.",
    )
    deletion_reason: models.TextField = models.TextField(
        blank=True,
        help_text="Mandatory reason for deletion (regulatory requirement).",
    )

    # Managers — order matters: first listed is the default
    objects: SoftDeleteManager = SoftDeleteManager()
    all_objects: AllObjectsManager = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(  # type: ignore[override]
        self,
        using: Any = None,
        keep_parents: bool = False,
        deleted_by: Any = None,
        reason: str = "",
    ) -> tuple[int, dict[str, int]]:
        """
        Soft-delete: set deleted_at and deleted_by.
        Physical deletion is intentionally blocked at this level.
        """
        self.deleted_at = timezone.now()
        if deleted_by is not None:
            self.deleted_by = deleted_by
        if reason:
            self.deletion_reason = reason
        self.save(update_fields=["deleted_at", "deleted_by", "deletion_reason", "updated_at"])
        return 1, {self.__class__.__name__: 1}

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None
        self.deleted_by = None  # type: ignore[assignment]
        self.deletion_reason = ""
        self.save(update_fields=["deleted_at", "deleted_by", "deletion_reason", "updated_at"])

