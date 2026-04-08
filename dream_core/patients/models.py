"""
dream_core/patients/models.py

Patient Registry — Master Patient Index.

Design:
- Patient is the canonical person record, shared across dream-core and other derivative softwares.
- External identifiers (registry number, fiscal code, passport number, insurance card, etc.) are stored in
  PatientIdentifier (one-to-many) to support multiple identifier systems.
- ContactPoint stores phone/email contacts.
- Address is stored inline (JSON field) to allow flexible FHIR address representation.
- All models are soft-delete with full audit trail.
- FHIR R4 serialisation/deserialisation is handled in fhir_utils.py.
- django-auditlog is registered for all models.
"""
from django.conf import settings
from django.db import models
from auditlog.registry import auditlog

from dream_core.core.hard_delete import HardDeleteGuard
from dream_core.core.models import SoftDeleteModel
from dream_core.core.choices import FHIRGender

class Patient(HardDeleteGuard, SoftDeleteModel):
    """
    Master Patient Index record.
    Maps to FHIR R4 Patient resource.

    Hard deletion requires:
      - `patients.hard_delete_patient` Django permission on the acting user
      - An authorisation_token of at least 20 characters
 
    Example:
        patient.hard_delete(
            authorised_by=request.user,
            authorisation_token="LGPD art.18 erasure — ticket #DPO-2024-0042",
        )
    """

    # ── Demographics ──────────────────────────────────────────────────────────
    family_name: models.CharField = models.CharField(
        max_length=200, db_index=True,
        help_text="Family / last name."
    )
    given_names: models.CharField = models.CharField(
        max_length=300,
        help_text="Given (first + middle) names, space-separated.",
    )
    birth_date: models.DateField = models.DateField(db_index=True)
    gender: models.CharField = models.CharField(
        max_length=10,
        choices=FHIRGender.choices,
        default=FHIRGender.UNKNOWN,
    )
    deceased_date: models.DateField = models.DateField(
        null=True, blank=True,
        help_text="Date of death if applicable.",
    )

    # ── Project-specific IDs ──────────────────────────────────────────────────
    id_patient: models.CharField = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Internal patient identifier assigned by the clinical system.",
    )
    id_dream: models.CharField = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="DREAM programme identifier for cross-system linkage.",
    )

    # ── Caregiver ─────────────────────────────────────────────────────────────
    caregiver_name: models.CharField = models.CharField(
        max_length=300,
        blank=True,
        help_text="Full name of primary caregiver or legal guardian.",
    )
    caregiver_contact: models.CharField = models.CharField(
        max_length=300,
        blank=True,
        help_text="Phone or email of the caregiver (free-text; use PatientContact for structured data).",
    )

    # ── Contact ───────────────────────────────────────────────────────────────
    email: models.EmailField = models.EmailField(blank=True, db_index=True)

    # ── Address (FHIR Address datatype stored as JSON) ────────────────────────
    address: models.JSONField = models.JSONField(
        default=dict, blank=True,
        help_text="FHIR Address datatype stored as JSON.",
    )

    # ── Clinical ──────────────────────────────────────────────────────────────
    blood_type: models.CharField = models.CharField(max_length=5, blank=True)
    allergies_notes: models.TextField = models.TextField(blank=True)
    notes: models.TextField = models.TextField(
        blank=True,
        help_text="General clinical notes. Sensitive — access controlled.",
    )

    # ── Obstetric status (female patients only) ───────────────────────────────
    # Tri-state: True = yes, False = no, None = not applicable / unknown.
    is_pregnant: models.BooleanField = models.BooleanField(
        null=True,
        blank=True,
        help_text="Current pregnancy status. Null = not applicable or unknown.",
    )
    is_breastfeeding: models.BooleanField = models.BooleanField(
        null=True,
        blank=True,
        help_text="Current breastfeeding status. Null = not applicable or unknown.",
    )

    # ── Facility ─────────────────────────────────────────────────────────────
    # Non-nullable from Phase 2 onwards. Every patient belongs to exactly one
    # facility. Cross-facility access is granted via django-guardian object
    # permissions on the Facility model, not via this FK.
    # See dream_core/facilities/mixins.py — FacilityFilterMixin.
    facility: models.ForeignKey = models.ForeignKey(
        "facilities.Facility",
        on_delete=models.PROTECT,
        related_name="patients",
        help_text="Facility this patient record belongs to.",
    )
 
    # ── Active status ─────────────────────────────────────────────────────────
    is_active: models.BooleanField = models.BooleanField(
        default=True,
        help_text="False = inactive/merged patient. Not the same as soft-deleted.",
    )
    merged_into: models.ForeignKey = models.ForeignKey(
        "self",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="merged_from",
        help_text="If this patient record was merged, points to the surviving record.",
    )

    class Meta:
        verbose_name = "Patient"
        verbose_name_plural = "Patients"
        ordering = ["family_name", "given_names"]
        indexes = [
            models.Index(fields=["family_name", "birth_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.family_name}, {self.given_names} ({self.birth_date})"

    @property
    def full_name(self) -> str:
        return f"{self.given_names} {self.family_name}".strip()

    def delete(self, using = None, keep_parents = False, deleted_by = None, reason = ""):
        result = super().delete(using, keep_parents, deleted_by, reason)
        # Cascade soft-delete to related SoftDeleteModel subclasses.
        # PatientIdentifier and PatientContact: mark active contacts/identifiers as deleted.
        # DataConsent: soft-delete all active consents (retains audit trail).
        for identifier in self.identifiers.filter(deleted_at__isnull=True):
            identifier.delete(deleted_by=deleted_by, reason=reason)
        for contact in self.contacts.filter(deleted_at__isnull=True):
            contact.delete(deleted_by=deleted_by, reason=reason)
        for consent in self.consents.filter(deleted_at__isnull=True):
            consent.delete(deleted_by=deleted_by, reason=reason)
        return result


class PatientIdentifier(SoftDeleteModel):
    """
    External identifiers for a patient.
    Maps to FHIR R4 Identifier datatype.

    Extends SoftDeleteModel so identifiers are never physically removed —
    the audit trail must survive patient merges and corrections.

    Examples:
      system="urn:oid:2.16.840.1.113883.2.4.6.3" value="123456789" (BSN)
      system="https://fhir.hl7.org/fhir/datatypes-examples.html#:~:text=A-,US%20SSN,-%3A"    value="XXX-XX-XXXX"
      system="https://xyz/tax-code"      value="12345678901"
    """

    class UseChoices(models.TextChoices):
        USUAL = "usual", "Usual"
        OFFICIAL = "official", "Official"
        TEMP = "temp", "Temporary"
        SECONDARY = "secondary", "Secondary"
        OLD = "old", "Old"

    patient: models.ForeignKey = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="identifiers",
    )
    use: models.CharField = models.CharField(
        max_length=20,
        choices=UseChoices.choices,
        default=UseChoices.OFFICIAL,
    )
    system: models.CharField = models.CharField(
        max_length=500,
        help_text="URI identifying the namespace for the identifier value.",
    )
    value: models.CharField = models.CharField(
        max_length=200,
        db_index=True,
        help_text="The identifier value within the system.",
    )

    class Meta:
        verbose_name = "Patient Identifier"
        verbose_name_plural = "Patient Identifiers"
        # Enforce uniqueness per system+value (no duplicate IDs in a system)
        unique_together = [("system", "value")]
        ordering = ["system"]

    def __str__(self) -> str:
        return f"{self.system}|{self.value}"


class PatientContact(SoftDeleteModel):
    """
    Phone and telecom contacts for a patient.
    Maps to FHIR R4 ContactPoint datatype.

    Extends SoftDeleteModel so contact history is retained — contact changes
    are clinically significant and must be auditable.
    """

    class SystemChoices(models.TextChoices):
        PHONE = "phone", "Phone"
        FAX = "fax", "Fax"
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"
        OTHER = "other", "Other"

    class UseChoices(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        MOBILE = "mobile", "Mobile"
        OLD = "old", "Old"

    patient: models.ForeignKey = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="contacts",
    )
    system: models.CharField = models.CharField(
        max_length=20,
        choices=SystemChoices.choices,
        default=SystemChoices.PHONE,
    )
    value: models.CharField = models.CharField(max_length=200)
    use: models.CharField = models.CharField(
        max_length=20,
        choices=UseChoices.choices,
        default=UseChoices.HOME,
    )
    rank: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        default=1,
        help_text="Preferred order (1 = highest priority).",
    )
    is_active: models.BooleanField = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Patient Contact"
        verbose_name_plural = "Patient Contacts"
        ordering = ["rank"]

    def __str__(self) -> str:
        return f"{self.get_system_display()}: {self.value}"


class DataConsent(SoftDeleteModel):
    """
    Records a patient's consent to personal data processing.
 
    Design:
    - One active consent per patient at any time; previous consents are retained
      for audit (soft-delete only, never physically removed).
    - `version` tracks the consent document / form revision so that re-consent
      can be triggered when the terms change.
    - `consented_at` is set explicitly (not auto_now_add) to capture the actual
      moment of signing, which may differ from the DB insertion time (e.g. paper
      forms scanned later).
    - Maps loosely to FHIR R4 Consent resource.
 
    Compliance note:
    - GDPR Art. 7 / LGPD Art. 8: consent must be freely given, specific,
      informed, and unambiguous. Revocation must be as easy as giving consent.
    - To revoke: call consent.revoke(revoked_by=user, reason="...") which sets
      `is_active=False` and records the revocation details without deleting the record.
    """
 
    class ConsentScope(models.TextChoices):
        RESEARCH = "research", "Research"
        TREATMENT = "treatment", "Treatment"
        PATIENT_PRIVACY = "patient-privacy", "Patient Privacy"
        FULL = "full", "Full (Research + Treatment + Privacy)"
 
    patient: models.ForeignKey = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="consents",
        help_text="The patient this consent record belongs to.",
    )
 
    # ── Consent details ───────────────────────────────────────────────────────
    scope: models.CharField = models.CharField(
        max_length=30,
        choices=ConsentScope.choices,
        default=ConsentScope.FULL,
        help_text="Scope of data processing covered by this consent.",
    )
    version: models.CharField = models.CharField(
        max_length=50,
        help_text="Consent form / document version (e.g. 'v2.1', '2024-01').",
    )
    consented_at: models.DateTimeField = models.DateTimeField(
        help_text="Datetime when the patient signed / confirmed consent.",
    )
    is_active: models.BooleanField = models.BooleanField(
        default=True,
        db_index=True,
        help_text="False = consent has been revoked.",
    )
 
    # ── Revocation ────────────────────────────────────────────────────────────
    revoked_at: models.DateTimeField = models.DateTimeField(
        null=True, blank=True,
        help_text="Datetime when the consent was revoked.",
    )
    revoked_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="consents_revoked",
        help_text="User who processed the revocation.",
    )
    revocation_reason: models.TextField = models.TextField(
        blank=True,
        help_text="Reason or reference for revocation (e.g. patient request, GDPR Art.7).",
    )
 
    # ── Collection metadata ───────────────────────────────────────────────────
    collected_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="consents_collected",
        help_text="Staff member who collected the consent.",
    )
    collection_method: models.CharField = models.CharField(
        max_length=50,
        blank=True,
        help_text="How consent was obtained (e.g. 'paper', 'electronic', 'verbal').",
    )
    notes: models.TextField = models.TextField(blank=True)
 
    class Meta:
        verbose_name = "Data Consent"
        verbose_name_plural = "Data Consents"
        ordering = ["-consented_at"]
        indexes = [
            models.Index(fields=["patient", "is_active"]),
            models.Index(fields=["patient", "scope", "is_active"]),
        ]
 
    def __str__(self) -> str:
        status = "active" if self.is_active else "revoked"
        return f"Consent [{self.get_scope_display()} v{self.version}] — {self.patient} ({status})"
 
    def revoke(self, revoked_by=None, reason: str = "") -> None:
        """
        Revoke this consent. Does not soft-delete — the record must be retained.
        """
        from django.utils import timezone
        self.is_active = False
        self.revoked_at = timezone.now()
        if revoked_by is not None:
            self.revoked_by = revoked_by
        if reason:
            self.revocation_reason = reason
        self.save(update_fields=[
            "is_active", "revoked_at", "revoked_by", "revocation_reason"
        ])


# ── Auditlog registration ─────────────────────────────────────────────────────
auditlog.register(Patient)
auditlog.register(PatientIdentifier)
auditlog.register(PatientContact)
auditlog.register(DataConsent)