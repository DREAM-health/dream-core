"""
apps/patients/models.py

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
from django.db import models
from auditlog.registry import auditlog

from apps.core.hard_delete import HardDeleteGuard
from apps.core.models import SoftDeleteModel
from apps.core.choices import FHIRGender

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

    # TODO: override in Patient.delete() that cascades the soft-delete to related objects.
    def delete(self, using = None, keep_parents = False, deleted_by = None, reason = ""):
        return super().delete(using, keep_parents, deleted_by, reason)



class PatientIdentifier(models.Model):
    """
    External identifiers for a patient.
    Maps to FHIR R4 Identifier datatype.

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


class PatientContact(models.Model):
    """
    Phone and telecom contacts for a patient.
    Maps to FHIR R4 ContactPoint datatype.
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


# ── Auditlog registration ─────────────────────────────────────────────────────
auditlog.register(Patient)
auditlog.register(PatientIdentifier)
auditlog.register(PatientContact)
