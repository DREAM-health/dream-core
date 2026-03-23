from django.contrib import admin

from apps.catalog.models import (
    ReferenceRange,
    SampleType,
    LabTestCategory,
    LabTestDefinition,
    LabTestMethod,
    LabTestPanel,
    LabTestPanelMembership,
    MeasurementUnit,
    LabTestSampleMembership,
)


# ── Unit ──────────────────────────────────────────────────────────────────────

@admin.register(MeasurementUnit)
class UnitAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["symbol", "name", "ucum_code"]
    search_fields = ["name", "symbol", "ucum_code"]


# ── SampleType ────────────────────────────────────────────────────────────────

@admin.register(SampleType)
class SampleTypeAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["code", "name", "minimum_volume_ml"]
    search_fields = ["code", "name"]


class LabTestPanelMembership(admin.ModelAdmin):  # type: ignore[type-arg]
    model = LabTestSampleMembership
    extra = 1
    fields = ["lab_test", "sample_type", "is_preferred", "minimum_volume_ml"]
    autocomplete_fields = ["lab_test"]


# ── LabTestCategory ──────────────────────────────────────────────────────────────

@admin.register(LabTestCategory)
class LabTestCategoryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["code", "name", "sort_order"]
    search_fields = ["code", "name"]
    ordering = ["sort_order", "name"]


# ── LabTestPanel ─────────────────────────────────────────────────────────────────

class LabTestPanelMembershipInline(admin.TabularInline):  # type: ignore[type-arg]
    model = LabTestPanelMembership
    extra = 1
    fields = ["lab_test", "sort_order", "is_optional"]
    autocomplete_fields = ["lab_test"]


@admin.register(LabTestPanel)
class LabTestPanelAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["code", "name", "category", "is_active", "price"]
    list_filter = ["category", "is_active"]
    search_fields = ["code", "name", "loinc_code"]
    ordering = ["category", "name"]
    inlines = [LabTestPanelMembershipInline]


# ── LabTestDefinition ────────────────────────────────────────────────────────────

class ReferenceRangeInline(admin.TabularInline):  # type: ignore[type-arg]
    model = ReferenceRange
    extra = 1
    fields = [
        "gender", "age_min_days", "age_max_days",
        "low", "high",
        "critical_low", "critical_high",
        "range_type",
    ]


class LabTestMethodInline(admin.TabularInline):  # type: ignore[type-arg]
    model = LabTestMethod
    extra = 0
    fields = ["name", "instrument", "is_default", "precision_cv"]


@admin.register(LabTestDefinition)
class LabTestDefinitionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = [
        "code", "name", "category", "result_type",
        "unit", "is_active", "requires_fasting",
    ]
    list_filter = ["result_type", "is_active", "requires_fasting", "category"]
    search_fields = ["code", "name", "loinc_code", "abbreviation"]
    ordering = ["category", "name"]
    inlines = [ReferenceRangeInline, LabTestMethodInline]
    raw_id_fields = ["unit"]