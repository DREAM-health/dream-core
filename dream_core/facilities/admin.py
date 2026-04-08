"""dream_core/facilities/admin.py"""
from django.contrib import admin

from dream_core.facilities.models import Facility, FacilityMembership


class FacilityMembershipInline(admin.TabularInline):
    model = FacilityMembership
    extra = 0
    fields = ("user", "role_override", "is_primary")
    autocomplete_fields = ["user"]


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "facility_type", "is_active", "parent_facility", "created_at")
    list_filter = ("facility_type", "is_active")
    search_fields = ("name", "short_name", "code", "tax_id")
    readonly_fields = ("created_at", "updated_at")
    inlines = [FacilityMembershipInline]

    fieldsets = (
        ("Identity", {
            "fields": ("name", "short_name", "code", "facility_type", "parent_facility"),
        }),
        ("Contact", {
            "fields": ("address", "phone", "email", "website"),
        }),
        ("Regulatory / Interoperability", {
            "fields": ("tax_id", "oid", "fhir_organization_id"),
            "classes": ("collapse",),
        }),
        ("Operation", {
            "fields": ("is_active", "timezone"),
        }),
        ("Audit", {
            "fields": ("created_at", "updated_at", "created_by", "updated_by"),
            "classes": ("collapse",),
        }),
    )


@admin.register(FacilityMembership)
class FacilityMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "facility", "is_primary", "role_override")
    list_filter = ("facility", "is_primary")
    search_fields = ("user__email", "facility__name", "facility__code")