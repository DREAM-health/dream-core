from django.contrib import admin
from apps.catalog.models import ReferenceRange, TestDefinition, TestPanel, Unit


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["symbol", "name", "ucum_code"]
    search_fields = ["name", "symbol", "ucum_code"]


class ReferenceRangeInline(admin.TabularInline):  # type: ignore[type-arg]
    model = ReferenceRange
    extra = 1
    fields = [
        "sex", "label", "age_min_days", "age_max_days",
        "low_normal", "high_normal",
        "low_critical", "high_critical",
        "is_active",
    ]


class TestDefinitionInline(admin.TabularInline):  # type: ignore[type-arg]
    model = TestDefinition
    extra = 0
    fields = ["code", "name", "result_type", "unit", "is_active", "sort_order"]
    show_change_link = True


@admin.register(TestPanel)
class TestPanelAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["code", "name", "category", "specimen_type", "is_active", "sort_order"]
    list_filter = ["category", "is_active", "specimen_type", "fasting_required"]
    search_fields = ["code", "name", "loinc_code"]
    ordering = ["sort_order", "name"]
    inlines = [TestDefinitionInline]


@admin.register(TestDefinition)
class TestDefinitionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = [
        "code", "name", "panel", "result_type",
        "unit", "specimen_type", "is_active",
    ]
    list_filter = ["result_type", "specimen_type", "is_active", "requires_validation", "panel"]
    search_fields = ["code", "name", "loinc_code", "snomed_code"]
    ordering = ["panel__name", "sort_order", "name"]
    inlines = [ReferenceRangeInline]
    raw_id_fields = ["panel", "unit"]
