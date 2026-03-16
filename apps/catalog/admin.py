from django.contrib import admin

from apps.catalog.models import (
    ReferenceRange,
    SampleType,
    TestCategory,
    TestDefinition,
    TestMethod,
    TestPanel,
    TestPanelMembership,
    Unit,
)


# ── Unit ──────────────────────────────────────────────────────────────────────

@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["symbol", "name", "ucum_code"]
    search_fields = ["name", "symbol", "ucum_code"]


# ── SampleType ────────────────────────────────────────────────────────────────

@admin.register(SampleType)
class SampleTypeAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["code", "name", "minimum_volume_ml"]
    search_fields = ["code", "name"]


# ── TestCategory ──────────────────────────────────────────────────────────────

@admin.register(TestCategory)
class TestCategoryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["code", "name", "sort_order"]
    search_fields = ["code", "name"]
    ordering = ["sort_order", "name"]


# ── TestPanel ─────────────────────────────────────────────────────────────────

class TestPanelMembershipInline(admin.TabularInline):  # type: ignore[type-arg]
    model = TestPanelMembership
    extra = 1
    fields = ["test", "sort_order", "is_optional"]
    autocomplete_fields = ["test"]


@admin.register(TestPanel)
class TestPanelAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["code", "name", "category", "is_active", "price"]
    list_filter = ["category", "is_active"]
    search_fields = ["code", "name", "loinc_code"]
    ordering = ["category", "name"]
    inlines = [TestPanelMembershipInline]
    raw_id_fields = ["category"]


# ── TestDefinition ────────────────────────────────────────────────────────────

class ReferenceRangeInline(admin.TabularInline):  # type: ignore[type-arg]
    model = ReferenceRange
    extra = 1
    fields = [
        "gender", "age_min_days", "age_max_days",
        "low", "high",
        "critical_low", "critical_high",
        "range_type",
    ]


class TestMethodInline(admin.TabularInline):  # type: ignore[type-arg]
    model = TestMethod
    extra = 0
    fields = ["name", "instrument", "is_default", "precision_cv"]


@admin.register(TestDefinition)
class TestDefinitionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = [
        "code", "name", "category", "result_type",
        "unit", "is_active", "requires_fasting",
    ]
    list_filter = ["result_type", "is_active", "requires_fasting", "category"]
    search_fields = ["code", "name", "loinc_code", "abbreviation"]
    ordering = ["category", "name"]
    inlines = [ReferenceRangeInline, TestMethodInline]
    raw_id_fields = ["category", "unit"]
    filter_horizontal = ["sample_types"]