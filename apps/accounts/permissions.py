"""
apps/accounts/permissions.py

Custom DRF permission classes for dream-core RBAC.

Usage in views:
    permission_classes = [IsAuthenticated, HasRole("LAB_MANAGER")]
    permission_classes = [IsAuthenticated, HasAnyRole("LAB_MANAGER", "LAB_ANALYST")]
"""
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.models import User


class IsSuperAdmin(BasePermission):
    """Full platform access — superuser or SUPERADMIN role."""

    message = "Superadmin access required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)
        return user.is_superuser or user.has_role("SUPERADMIN")


class IsAdmin(BasePermission):
    """Facility admin access."""

    message = "Admin access required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)
        return user.is_superuser or user.has_role("SUPERADMIN") or user.has_role("ADMIN")


class HasRole(BasePermission):
    """Require the user to have a specific role."""

    def __init__(self, role_name: str) -> None:
        self.role_name = role_name
        self.message = f"Role '{role_name}' required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)
        if user.is_superuser:
            return True
        return user.has_role(self.role_name)


class HasAnyRole(BasePermission):
    """Require the user to have at least one of the specified roles."""

    def __init__(self, *role_names: str) -> None:
        self.role_names = role_names
        self.message = f"One of the following roles required: {', '.join(role_names)}."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)
        if user.is_superuser:
            return True
        return any(user.has_role(r) for r in self.role_names)


class IsAuditor(BasePermission):
    """Read-only access to audit logs."""

    message = "Auditor role required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)
        return user.is_superuser or user.has_role("AUDITOR") or user.has_role("SUPERADMIN")


class ReadOnly(BasePermission):
    """Allow safe methods (GET, HEAD, OPTIONS) only."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        return request.method in ("GET", "HEAD", "OPTIONS")
