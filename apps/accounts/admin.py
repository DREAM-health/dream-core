from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.accounts.models import Role, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "full_name", "department", "is_active", "is_staff", "created_at"]
    list_filter = ["is_active", "is_staff", "roles"]
    search_fields = ["email", "first_name", "last_name", "professional_id"]
    ordering = ["email"]
    filter_horizontal = ["roles", "groups", "user_permissions"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone", "professional_id", "department")}),
        ("Roles & Permissions", {"fields": ("roles", "groups", "user_permissions", "is_active", "is_staff", "is_superuser")}),
        ("Compliance", {"fields": ("must_change_password", "password_changed_at", "last_login_ip", "failed_login_attempts", "locked_until")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "password1", "password2"),
        }),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ["name", "description", "is_system", "created_at"]
    filter_horizontal = ["permissions"]
    search_fields = ["name"]
