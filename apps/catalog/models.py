"""
apps/catalog/models.py

Lab Test Catalog — the definitive registry of laboratory tests available
in dream-lab (and orderable from dream-cen).

Model hierarchy:
    LabTestCategory         — e.g. "Haematology", "Biochemistry", "Immunology"
        LabTestPanel           — e.g. "Complete Blood Count", "Lipid Panel"
            LabTestDefinition    — e.g. "Haemoglobin", "LDL Cholesterol"
            ReferenceRange    — age/gender/condition-specific expected ranges

Additional:
  MeasurementUnit                   — controlled vocabulary of measurement units (UCUM)

Design decisions:
  - All entities soft-deletable and fully audited.
  - category on LabTestPanel and LabTestDefinition is a plain CharField (free text /
    controlled at the application layer) rather than a FK to LabTestCategory.
    This removes a join dependency and lets each downstream product manage its
    own category taxonomy without a shared DB table.
  - ReferenceRange is separate from LabTestDefinition so multiple
    population-specific ranges can coexist (paediatric vs adult, M vs F).
  - LOINC and SNOMED codes stored where known for interoperability.
  - LabTestDefinition has a direct FK to LabTestPanel (one primary panel per lab test).
  - TAT stored as a single turnaround_hours IntegerField for simplicity.
  - ReferenceRange.interpret() encapsulates the flag logic so the view and
    model lab tests share a single implementation.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import models
from auditlog.registry import auditlog

from apps.core.models import SoftDeleteModel, TimeStampedModel


class MeasurementUnit(SoftDeleteModel):
    """
    Controlled vocabulary of measurement units.
    Aligns with the Unified Code for Units of Measure (UCUM).
    """
    name: models.CharField = models.CharField(
        max_length=100, unique=True,
        help_text="Human-readable name, e.g. 'grams per decilitre'.",
    )
    symbol: models.CharField = models.CharField(
        max_length=50, unique=True,
        help_text="UCUM symbol, e.g. 'g/dL'.",
    )
    ucum_code: models.CharField = models.CharField(
        max_length=100, blank=True,
        help_text="Official UCUM code if different from symbol.",
    )
    description: models.TextField = models.TextField(blank=True)

    class Meta:
        ordering = ["symbol"]
        verbose_name = "Unit"
        verbose_name_plural = "Units"

    def __str__(self) -> str:
        return self.symbol


class SampleType(SoftDeleteModel):
    """
    Biological specimen types.
    e.g. Serum, EDTA Whole Blood, Urine (midstream), CSF, Swab.
    """
    name: models.CharField = models.CharField(max_length=150, unique=True)
    code: models.CharField = models.CharField(
        max_length=30, unique=True,
        help_text="Short code used in order forms and labels, e.g. 'SER', 'EDTA'.",
    )
    description: models.TextField = models.TextField(blank=True)
    handling_instructions: models.TextField = models.TextField(
        blank=True,
        help_text="Storage temperature, transport requirements, etc.",
    )
    container_color: models.CharField = models.CharField(
        max_length=50, blank=True,
        help_text="Vacutainer/tube cap colour, e.g. 'Red', 'Lavender'.",
    )
    minimum_volume_ml: models.DecimalField = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Minimum required volume in millilitres.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Sample Type"
        verbose_name_plural = "Sample Types"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class LabTestCategory(SoftDeleteModel):
    """
    High-level grouping of laboratory tests.
    e.g. Haematology, Biochemistry, Immunology, Microbiology, Coagulation.
    """
    name: models.CharField = models.CharField(max_length=150, unique=True)
    code: models.CharField = models.CharField(
        max_length=30, unique=True,
        help_text="Short alphanumeric code, e.g. 'HEM', 'BIO'.",
    )
    description: models.TextField = models.TextField(blank=True)
    sort_order: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Lab Test Category"
        verbose_name_plural = "Lab Test Categories"

    def __str__(self) -> str:
        return self.name


class LabTestPanel(SoftDeleteModel):
    """
    A named group of laboratory tests ordered together.
    e.g. Complete Blood Count, Comprehensive Metabolic Panel, Lipid Panel.

    category is a free-text CharField managed at the application layer rather
    than a FK — keeps the catalog self-contained and avoids requiring a
    LabTestCategory record before creating a panel.
    """
    name: models.CharField = models.CharField(max_length=200)
    code: models.CharField = models.CharField(
        max_length=50, unique=True,
        help_text="Unique order code for this panel, e.g. 'FBC', 'CMP'.",
    )
    description: models.TextField = models.TextField(blank=True)

    # Classification
    category: models.CharField = models.CharField(
        max_length=150, blank=True, db_index=True,
        help_text="Discipline label, e.g. 'Haematology', 'Biochemistry'.",
    )
    loinc_code: models.CharField = models.CharField(
        max_length=20, blank=True,
        help_text="LOINC panel code for interoperability.",
    )

    # Flags
    is_active: models.BooleanField = models.BooleanField(default=True)

    # Pricing
    price: models.DecimalField = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Lab Test Panel"
        verbose_name_plural = "Lab Test Panels"

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class LabTestDefinition(SoftDeleteModel):
    """
    A single laboratory test (analyte).
    e.g. Haemoglobin, Serum Creatinine, TSH.
    """

    class ResultTypeChoices(models.TextChoices):
        NUMERIC = "numeric", "Numeric"
        TEXT = "text", "Free text"
        CODED = "coded", "Coded (from value set)"
        SEMI_QUANTITATIVE = "semi_quant", "Semi-quantitative"

    # Identification
    name: models.CharField = models.CharField(max_length=200, db_index=True)
    full_name: models.CharField = models.CharField(
        max_length=300, blank=True,
        help_text="Full official name if different from the display name.",
    )
    code: models.CharField = models.CharField(
        max_length=50, unique=True,
        help_text="Unique order code, e.g. 'HGB', 'CREAT'.",
    )
    abbreviation: models.CharField = models.CharField(max_length=20, blank=True)
    loinc_code: models.CharField = models.CharField(
        max_length=20, blank=True,
        help_text="LOINC code, e.g. '718-7' for Haemoglobin.",
    )
    snomed_code: models.CharField = models.CharField(
        max_length=30, blank=True,
        help_text="SNOMED CT concept code.",
    )
    description: models.TextField = models.TextField(blank=True)

    # Classification
    category: models.CharField = models.CharField(
        max_length=150, blank=True, db_index=True,
    )

    container_type: models.CharField = models.CharField(
        max_length=100, blank=True,
    )
    minimum_volume_ml: models.DecimalField = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )

    # Result configuration
    result_type: models.CharField = models.CharField(
        max_length=20,
        choices=ResultTypeChoices.choices,
        default=ResultTypeChoices.NUMERIC,
    )
    unit: models.ForeignKey = models.ForeignKey(
        MeasurementUnit,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="tests",
    )
    decimal_places: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(default=2)
    # Allowed coded values for result_type='coded'
    allowed_values: models.JSONField = models.JSONField(
        default=list, blank=True,
        help_text="Allowed coded result values, e.g. ['Positive', 'Negative'].",
    )

    # Analytical method
    method: models.CharField = models.CharField(max_length=200, blank=True)
    instrument: models.CharField = models.CharField(max_length=200, blank=True)

    # Turnaround
    turnaround_hours: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Routine turnaround time in hours.",
    )

    # Workflow flags
    requires_validation: models.BooleanField = models.BooleanField(
        default=True,
        help_text="Result requires lab manager validation before release.",
    )
    reportable: models.BooleanField = models.BooleanField(
        default=True,
        help_text="Result is included in the patient report.",
    )
    requires_fasting: models.BooleanField = models.BooleanField(default=False)
    is_active: models.BooleanField = models.BooleanField(default=True)

    price: models.DecimalField = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    sort_order: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Test Definition"
        verbose_name_plural = "Test Definitions"
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["loinc_code"]),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    @property
    def tat_display(self) -> str:
        if self.turnaround_hours:
            return f"{self.turnaround_hours} h"
        return "—"


class LabTestPanelMembership(models.Model):
    """Through table for LabTestPanel ↔ LabTestDefinition M2M with ordering."""

    panel: models.ForeignKey = models.ForeignKey(
        LabTestPanel, on_delete=models.CASCADE, related_name="memberships",
    )
    lab_test: models.ForeignKey = models.ForeignKey(
        LabTestDefinition, on_delete=models.CASCADE, related_name="panel_memberships",
    )
    sort_order: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(default=0)
    is_optional: models.BooleanField = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order"]
        unique_together = [("panel", "lab_test")]
        verbose_name = "Panel Membership"

    def __str__(self) -> str:
        return f"{self.panel.code} → {self.lab_test.code}"


class LabTestSampleMembership(models.Model):
    """Through table for SampleType ↔ LabTestDefinition M2M."""
    lab_test = models.ForeignKey(LabTestDefinition, on_delete=models.CASCADE,
                             related_name="sample_requirements")
    sample_type = models.ForeignKey(SampleType, on_delete=models.PROTECT,
                                    related_name="test_requirements")
    is_preferred = models.BooleanField(default=True)
    minimum_volume_ml = models.DecimalField(  # override at labtest level if needed
        max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = [("lab_test", "sample_type")]


class ReferenceRange(TimeStampedModel):
    """
    Population-specific reference ranges for a TestDefinition.
    Multiple ranges per test cover gender, age bracket, and condition variants.

    interpret(value) returns a flag string:
      N  = Normal
      L  = Low
      H  = High
      LL = Critical Low
      HH = Critical High
      ?  = Outside reportable range or undetermined
    """

    class GenderChoices(models.TextChoices):
        """
        Biological sex with clinical applicability.
        Not to be confused with apps.core.choices.FHIRGender
        """
        ANY = "any", "Any / Not specified"
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    test: models.ForeignKey = models.ForeignKey(
        LabTestDefinition, on_delete=models.CASCADE, related_name="reference_ranges",
    )

    # Population selectors
    gender: models.CharField = models.CharField(
        max_length=10, choices=GenderChoices.choices, default=GenderChoices.ANY,
    )
    age_min_days: models.PositiveIntegerField = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Minimum age in days (inclusive). Null = no lower bound.",
    )
    age_max_days: models.PositiveIntegerField = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Maximum age in days (exclusive). Null = no upper bound.",
    )
    label: models.CharField = models.CharField(
        max_length=100, blank=True,
        help_text="Human-readable label, e.g. 'Adult', 'Neonate', 'Pregnant'.",
    )

    # Normal range
    low_normal: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )
    high_normal: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )

    # Critical / panic range
    low_critical: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )
    high_critical: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )

    # Analytical measurement range (reportable range)
    low_reportable: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
        help_text="Lower limit of the analytical measurement range.",
    )
    high_reportable: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
        help_text="Upper limit of the analytical measurement range.",
    )

    notes: models.TextField = models.TextField(blank=True)
    is_active: models.BooleanField = models.BooleanField(default=True)

    class Meta:
        ordering = ["test", "gender", "age_min_days"]
        verbose_name = "Reference Range"
        verbose_name_plural = "Reference Ranges"

    def __str__(self) -> str:
        parts = [self.test.code, self.gender]
        if self.low_normal is not None and self.high_normal is not None:
            parts.append(f"[{self.low_normal}–{self.high_normal}]")
        return " | ".join(parts)

    @property
    def age_label(self) -> str:
        if self.age_min_days is None and self.age_max_days is None:
            return "All ages"
        lo = f"{self.age_min_days}d" if self.age_min_days is not None else "0d"
        hi = f"{self.age_max_days}d" if self.age_max_days is not None else "∞"
        return f"{lo} – {hi}"

    def interpret(self, value: Decimal) -> str:
        """
        Evaluate a numeric result value against this reference range and
        return the appropriate flag.

        Flag hierarchy (checked in order of clinical severity):
          ?  — value is outside the reportable/analytical measurement range
          LL — value is at or below the critical low threshold
          HH — value is at or above the critical high threshold
          L  — value is below the normal low
          H  — value is above the normal high
          N  — value is within the normal range (inclusive of boundaries)
        """
        # Outside reportable range — result cannot be reported
        if self.low_reportable is not None and value < self.low_reportable:
            return "?"
        if self.high_reportable is not None and value > self.high_reportable:
            return "?"

        # Critical thresholds (panic values)
        if self.low_critical is not None and value < self.low_critical:
            return "LL"
        if self.high_critical is not None and value > self.high_critical:
            return "HH"

        # Normal range boundaries (inclusive)
        if self.low_normal is not None and value < self.low_normal:
            return "L"
        if self.high_normal is not None and value > self.high_normal:
            return "H"

        return "N"


class LabTestMethod(TimeStampedModel):
    """Analytical method used to perform a lab test (per instrument/analyser)."""

    test: models.ForeignKey = models.ForeignKey(
        LabTestDefinition, on_delete=models.CASCADE, related_name="methods",
    )
    name: models.CharField = models.CharField(max_length=200)
    instrument: models.CharField = models.CharField(max_length=200, blank=True)
    is_default: models.BooleanField = models.BooleanField(default=False)
    precision_cv: models.DecimalField = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Coefficient of variation (%) for QC.",
    )
    detection_limit: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )
    linearity_low: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )
    linearity_high: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )
    notes: models.TextField = models.TextField(blank=True)

    class Meta:
        ordering = ["-is_default", "name"]
        verbose_name = "Lab Test Method"
        verbose_name_plural = "Lab Test Methods"

    def __str__(self) -> str:
        return f"{self.test.code} / {self.name}"


# ── Auditlog registration ─────────────────────────────────────────────────────
auditlog.register(LabTestCategory)
auditlog.register(LabTestPanel)
auditlog.register(LabTestDefinition)
auditlog.register(ReferenceRange)
auditlog.register(LabTestMethod)
auditlog.register(MeasurementUnit)
auditlog.register(SampleType)
