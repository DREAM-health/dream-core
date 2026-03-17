"""
apps/catalog/models.py

Test Catalog — the definitive registry of laboratory tests available
in MedLIMS (and orderable from MedClinic).

Model hierarchy:
  TestCategory          — e.g. "Haematology", "Biochemistry", "Microbiology"
    TestPanel           — e.g. "Complete Blood Count", "Lipid Panel"
      TestDefinition    — e.g. "Haemoglobin", "LDL Cholesterol"
        ReferenceRange  — age/gender/condition-specific expected ranges
        TestMethod      — analytical method used (can vary by instrument)

Additional:
  Unit                  — controlled vocabulary of measurement units (UCUM)
  SampleType            — e.g. "Serum", "EDTA Whole Blood", "Urine"

Design decisions:
  - All entities soft-deletable and fully audited.
  - ReferenceRange is separate from TestDefinition so multiple
    population-specific ranges can coexist (paediatric vs adult, M vs F).
  - LOINC codes stored where known for interoperability.
  - TAT (turnaround time) tracked at the TestDefinition level.
"""
from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models
from auditlog.registry import auditlog

from apps.core.models import SoftDeleteModel, TimeStampedModel


class Unit(TimeStampedModel):
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


class SampleType(TimeStampedModel):
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


class TestCategory(SoftDeleteModel):
    """
    High-level grouping of tests.
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
        verbose_name = "Test Category"
        verbose_name_plural = "Test Categories"

    def __str__(self) -> str:
        return self.name


class TestPanel(SoftDeleteModel):
    """
    A named group of tests ordered together.
    e.g. Complete Blood Count, Comprehensive Metabolic Panel, Lipid Panel.
    """
    category: models.ForeignKey = models.ForeignKey(
        TestCategory,
        on_delete=models.PROTECT,
        related_name="panels",
    )
    name: models.CharField = models.CharField(max_length=200)
    code: models.CharField = models.CharField(
        max_length=50, unique=True,
        help_text="Unique order code for this panel.",
    )
    description: models.TextField = models.TextField(blank=True)
    loinc_code: models.CharField = models.CharField(
        max_length=20, blank=True,
        help_text="LOINC panel code for interoperability.",
    )
    is_active: models.BooleanField = models.BooleanField(default=True)
    price: models.DecimalField = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )

    class Meta:
        ordering = ["category", "name"]
        verbose_name = "Test Panel"
        verbose_name_plural = "Test Panels"

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class TestDefinition(SoftDeleteModel):
    """
    A single laboratory test (analyte).
    e.g. Haemoglobin, Serum Creatinine, TSH, Blood Culture.
    """

    class ResultTypeChoices(models.TextChoices):
        NUMERIC = "numeric", "Numeric"
        TEXT = "text", "Free text"
        CODED = "coded", "Coded (from value set)"
        SEMI_QUANTITATIVE = "semi_quant", "Semi-quantitative"

    class SpecimenTypeChoices(models.TextChoices):
        HAEMOGLOBIN = "haemoglobin", "Haemoglobin"
        SERUM = "serum", "Serum"
        TSH = "tsh", "Thyroid-Stimulating Hormone"
        BLOOD = "blood", "Blood culture"

    class TATUnitChoices(models.TextChoices):
        MINUTES = "min", "Minutes"
        HOURS = "hours", "Hours"
        DAYS = "days", "Days"

    category: models.ForeignKey = models.ForeignKey(
        TestCategory,
        on_delete=models.PROTECT,
        related_name="tests",
    )
    panels: models.ManyToManyField = models.ManyToManyField(
        TestPanel,
        through="TestPanelMembership",
        related_name="tests",
        blank=True,
    )

    # Identification
    name: models.CharField = models.CharField(max_length=200, db_index=True)
    code: models.CharField = models.CharField(
        max_length=50, unique=True,
        help_text="Unique order code, e.g. 'HGB', 'CREAT'.",
    )
    abbreviation: models.CharField = models.CharField(max_length=20, blank=True)
    loinc_code: models.CharField = models.CharField(
        max_length=20, blank=True,
        help_text="LOINC code, e.g. '718-7' for Haemoglobin.",
    )
    description: models.TextField = models.TextField(blank=True)
    clinical_notes: models.TextField = models.TextField(blank=True)

    # Sample requirements
    sample_types: models.ManyToManyField = models.ManyToManyField(
        SampleType, related_name="tests", blank=True,
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
        Unit,
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name="tests",
    )
    decimal_places: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(default=2)

    # Turnaround time
    tat_value: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
    )
    tat_unit: models.CharField = models.CharField(
        max_length=10, choices=TATUnitChoices.choices, default=TATUnitChoices.HOURS,
    )
    critical_tat_value: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(
        null=True, blank=True,
    )
    critical_tat_unit: models.CharField = models.CharField(
        max_length=10, choices=TATUnitChoices.choices, default=TATUnitChoices.HOURS,
    )

    price: models.DecimalField = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
    )
    is_active: models.BooleanField = models.BooleanField(default=True)
    requires_fasting: models.BooleanField = models.BooleanField(default=False)

    class Meta:
        ordering = ["category", "name"]
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
        if self.tat_value:
            return f"{self.tat_value} {self.get_tat_unit_display()}"
        return "—"


class TestPanelMembership(models.Model):
    """Through table for TestPanel ↔ TestDefinition M2M with ordering."""

    panel: models.ForeignKey = models.ForeignKey(
        TestPanel, on_delete=models.CASCADE, related_name="memberships",
    )
    test: models.ForeignKey = models.ForeignKey(
        TestDefinition, on_delete=models.CASCADE, related_name="panel_memberships",
    )
    sort_order: models.PositiveSmallIntegerField = models.PositiveSmallIntegerField(default=0)
    is_optional: models.BooleanField = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order"]
        unique_together = [("panel", "test")]
        verbose_name = "Panel Membership"

    def __str__(self) -> str:
        return f"{self.panel.code} → {self.test.code}"


class ReferenceRange(TimeStampedModel):
    """
    Population-specific reference ranges for a TestDefinition.
    Multiple ranges per test cover gender, age bracket, and condition variants.
    """

    class GenderChoices(models.TextChoices):
        ANY = "any", "Any / Not specified"
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    class RangeTypeChoices(models.TextChoices):
        NORMAL = "normal", "Normal"
        THERAPEUTIC = "therapeutic", "Therapeutic"
        TOXIC = "toxic", "Toxic"
        CRITICAL_LOW = "critical_low", "Critical Low"
        CRITICAL_HIGH = "critical_high", "Critical High"

    test: models.ForeignKey = models.ForeignKey(
        TestDefinition, on_delete=models.CASCADE, related_name="reference_ranges",
    )
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
    condition: models.CharField = models.CharField(max_length=100, blank=True)

    # Numeric range
    low: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )
    high: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )
    critical_low: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )
    critical_high: models.DecimalField = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True,
    )
    text_interpretation: models.TextField = models.TextField(blank=True)
    range_type: models.CharField = models.CharField(
        max_length=20, choices=RangeTypeChoices.choices, default=RangeTypeChoices.NORMAL,
    )
    notes: models.TextField = models.TextField(blank=True)

    class Meta:
        ordering = ["test", "gender", "age_min_days"]
        verbose_name = "Reference Range"
        verbose_name_plural = "Reference Ranges"

    def __str__(self) -> str:
        parts = [self.test.code, self.gender]
        if self.low is not None and self.high is not None:
            parts.append(f"[{self.low}–{self.high}]")
        return " | ".join(parts)

    @property
    def age_label(self) -> str:
        if self.age_min_days is None and self.age_max_days is None:
            return "All ages"
        lo = f"{self.age_min_days}d" if self.age_min_days is not None else "0d"
        hi = f"{self.age_max_days}d" if self.age_max_days is not None else "∞"
        return f"{lo} – {hi}"


class TestMethod(TimeStampedModel):
    """Analytical method used to perform a test (per instrument/analyser)."""

    test: models.ForeignKey = models.ForeignKey(
        TestDefinition, on_delete=models.CASCADE, related_name="methods",
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
        verbose_name = "Test Method"
        verbose_name_plural = "Test Methods"

    def __str__(self) -> str:
        return f"{self.test.code} / {self.name}"


# ── Auditlog registration ─────────────────────────────────────────────────────
auditlog.register(TestCategory)
auditlog.register(TestPanel)
auditlog.register(TestDefinition)
auditlog.register(ReferenceRange)
auditlog.register(TestMethod)
auditlog.register(Unit)
auditlog.register(SampleType)
