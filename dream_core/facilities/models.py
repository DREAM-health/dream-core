"""
dream_core/facilities/models.py

Facility — the organisational / tenancy unit for dream-core.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT IS A FACILITY?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A Facility is the real-world organisational unit that owns data.
In healthcare deployments this maps naturally to one of:

  • A clinical centre branch (dream-cen)
  • A laboratory unit (dream-lab)
  • A medical infrastructure that has both clinic and lab
  • other

Every future resource — Patient, LabOrder, Appointment, ClinicalNote — will
carry a FK to Facility so that:

  1. Row-level data isolation becomes possible (a user at facility A cannot
     see facility B's patients unless explicitly granted cross-facility access).
  2. Audit filtering by facility is trivial (Phase 2 AuditEventManager hook).
  3. Multi-branch reporting can aggregate across facilities by NETWORK or
     PARENT_FACILITY.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 POSTURE — STUB, NOT ENFORCEMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
In Phase 1 the FK on every resource model is nullable and no permission check
reads it. The migration cost is near-zero (one nullable column per table,
no data backfill required). The intent is purely to:

  • Reserve the column in the schema with the right name and type.
  • Make the Phase 2 migration a simple NOT NULL + backfill, not a schema
    redesign across every app.
  • Give the seed command and fixtures a place to attach a default facility
    so development data is already in the right shape.

Enforcement is gated behind the `FACILITY_ENFORCEMENT_ENABLED` Django setting
(default False). When set to True, the FacilityFilterMixin and
FacilityRequiredMixin become active across all views.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MULTI-TENANCY TOPOLOGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The model supports three deployment topologies via `parent_facility`:

  Topology 1 — Single facility (most common, Phase 1)
    A single Facility record. All resources belong to it.

  Topology 2 — Multi-branch (Phase 2)
    e.g. a hospital with a main campus + satellite labs. Each branch is a
    Facility; the main campus is the parent_facility of the satellites.
    Users at the parent can optionally see children's data.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from auditlog.registry import auditlog

from dream_core.core.models import SoftDeleteModel
from dream_core.core.hard_delete import HardDeleteGuard


class Facility(HardDeleteGuard, SoftDeleteModel):
    """
    An organisational unit that owns clinical and/or laboratory data.

    Phase 1: created and seed-loaded; not yet enforced in queries.
    Phase 2: all resource querysets filter by the requesting user's facility
             (or set of permitted facilities).
    """

    class FacilityType(models.TextChoices):
        CENTER           = "center", "Center"
        LABORATORY       = "laboratory", "Laboratory"
        PLATFORM         = "platform", "Platform" # full center + lab
        OTHER            = "other", "Other"

    # ── Identity ──────────────────────────────────────────────────────────────
    name: models.CharField = models.CharField(
        max_length=255,
        help_text="Full legal / display name of the facility.",
    )
    short_name: models.CharField = models.CharField(
        max_length=80,
        blank=True,
        help_text="Abbreviated name used in reports and labels.",
    )
    code: models.CharField = models.CharField(
        max_length=30,
        unique=True,
        help_text=(
            "Unique alphanumeric code used in order prefixes and identifiers. "
            "e.g. 'HGF', 'LAB01'. Cannot be changed after data is attached."
        ),
    )
    facility_type: models.CharField = models.CharField(
        max_length=30,
        choices=FacilityType.choices,
        default=FacilityType.CENTER,
    )

    # ── Hierarchy ─────────────────────────────────────────────────────────────
    parent_facility: models.ForeignKey = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="branches",
        help_text=(
            "Parent facility in a multi-branch topology. "
            "Null = this facility is a top-level node."
        ),
    )

    # ── Contact & address ─────────────────────────────────────────────────────
    address: models.JSONField = models.JSONField(
        default=dict,
        blank=True,
        help_text="FHIR Address datatype stored as JSON (mirrors Patient.address).",
    )
    phone: models.CharField = models.CharField(max_length=30, blank=True)
    email: models.EmailField = models.EmailField(blank=True)
    website: models.URLField = models.URLField(blank=True)

    # ── Regulatory / interoperability ─────────────────────────────────────────
    tax_id: models.CharField = models.CharField(
        max_length=50,
        blank=True,
        help_text="Tax / fiscal identifier (CNPJ, NIF, etc.).",
    )
    oid: models.CharField = models.CharField(
        max_length=100,
        blank=True,
        help_text=(
            "HL7 OID for this facility, used in FHIR Organization resources "
            "and as an identifier system namespace. e.g. '2.16.840.1.113883.3.x'."
        ),
    )
    fhir_organization_id: models.CharField = models.CharField(
        max_length=100,
        blank=True,
        help_text=(
            "ID of the corresponding FHIR Organization resource on an external "
            "FHIR server, if applicable."
        ),
    )

    # ── Operation ─────────────────────────────────────────────────────────────
    is_active: models.BooleanField = models.BooleanField(
        default=True,
        help_text="Inactive facilities are hidden from user-facing lists but data is retained.",
    )
    timezone: models.CharField = models.CharField(
        max_length=64,
        default="UTC",
        help_text="IANA timezone for report timestamps. e.g. 'America/Sao_Paulo'.",
    )

    # ── Phase 2 enforcement flag (per-facility override) ──────────────────────
    # When the global FACILITY_ENFORCEMENT_ENABLED setting is True, this flag
    # can additionally be toggled per-facility to allow a gradual rollout.
    enforcement_enabled: models.BooleanField = models.BooleanField(
        default=False,
        help_text=(
            "Phase 2: when True AND the global FACILITY_ENFORCEMENT_ENABLED"
            "setting is True, all queries for this facility are scoped."
        ),
    )

    class Meta:
        verbose_name = "Facility"
        verbose_name_plural = "Facilities"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    @property
    def display_name(self) -> str:
        return self.short_name if self.short_name else self.name

    @property
    def is_branch(self) -> bool:
        """True if this facility is a child of another facility."""
        return self.parent_facility_id is not None

    def get_ancestors(self) -> list["Facility"]:
        """
        Return the chain of parent facilities, root first.
        Not cached — use sparingly in hot paths.
        """
        ancestors: list[Facility] = []
        current = self.parent_facility
        while current is not None:
            ancestors.insert(0, current)
            current = current.parent_facility
        return ancestors


# ── FacilityMembership ────────────────────────────────────────────────────────

class FacilityMembership(models.Model):
    """
    Association between a User and a Facility.

    A user can belong to multiple facilities (e.g. a traveling consultant,
    or a LAB_MANAGER overseeing several branches). The `is_primary` flag
    marks the user's home facility for UI defaults.

    Phase 1: the table exists but is not read by any permission check.
    Phase 2: permission mixins will use this to build the user's
             allowed_facility_ids set on each request.
    """

    user: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="facility_memberships",
    )
    facility: models.ForeignKey = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    is_primary: models.BooleanField = models.BooleanField(
        default=False,
        help_text="User's home/default facility. At most one per user.",
    )
    # Allows a per-facility role override: a user might be LAB_MANAGER
    # at their home lab but LAB_ANALYST at an external facility.
    role_override: models.ForeignKey = models.ForeignKey(
        "accounts.Role",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facility_memberships",
        help_text=(
            "Optional per-facility role override. When set, takes precedence "
            "over the user's global roles for requests scoped to this facility."
        ),
    )

    class Meta:
        verbose_name = "Facility membership"
        verbose_name_plural = "Facility memberships"
        unique_together = [("user", "facility")]
        ordering = ["-is_primary", "facility__name"]

    def __str__(self) -> str:
        return f"{self.user} @ {self.facility}"


# ── Auditlog registration ─────────────────────────────────────────────────────
auditlog.register(Facility)
auditlog.register(FacilityMembership)