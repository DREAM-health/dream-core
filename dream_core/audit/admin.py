"""
dream_core/audit/admin.py

Django admin for AuditEvent (proxy over django-auditlog's LogEntry).

Read-only by design — audit records must never be modified or deleted
through the admin interface. All write operations are disabled at the
ModelAdmin level as a defence-in-depth measure even though the proxy
manager has no save() path.
"""
from django.contrib import admin
from django.http import HttpRequest

from dream_core.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """
    Read-only admin view of audit events.
    Deliberately strips all add / change / delete permissions.
    """

    list_display = (
        "timestamp",
        "action_display",
        "resource_label",
        "object_repr",
        "actor_display",
        "remote_addr",
    )
    list_filter = ("action", "content_type")
    search_fields = ("object_repr", "object_pk")
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)
    readonly_fields = (
        "timestamp",
        "action",
        "actor",
        "content_type",
        "object_pk",
        "object_repr",
        "changes",
        "remote_addr",
        "additional_data",
    )

    # ── Enforce read-only ──────────────────────────────────────────────────

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: object = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: object = None
    ) -> bool:
        return False