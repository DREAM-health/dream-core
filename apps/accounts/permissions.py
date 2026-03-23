"""
apps/accounts/permissions.py

Custom DRF permission classes for dream-core RBAC.

Usage in views:
    permission_classes = [IsAuthenticated, HasRole("LAB_MANAGER")]
    permission_classes = [IsAuthenticated, HasAnyRole("LAB_MANAGER", "LAB_ANALYST")]

Design note:
    HasRole() and HasAnyRole() are factory functions that return a *class*,
    not an instance. DRF calls permission() on each item in permission_classes,
    so every item must be a class. The factories create a fresh class each call
    with the role names baked in as class attributes.
"""
from typing import Type

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.models import User


class IsSuperAdmin(BasePermission):
    """Full platform access — superuser or SUPERADMIN role."""

    message = "Superadmin access required."

    def has_permission(self, request: Request, _view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)
        return user.is_superuser or user.has_role("SUPERADMIN")


class IsAdmin(BasePermission):
    """Facility admin access — ADMIN or SUPERADMIN."""

    message = "Admin access required."

    def has_permission(self, request: Request, _view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)
        return user.is_superuser or user.has_role("SUPERADMIN") or user.has_role("ADMIN")


class IsAuditor(BasePermission):
    """Read-only access to audit logs — AUDITOR, ADMIN, or SUPERADMIN."""

    message = "Auditor role required."

    def has_permission(self, request: Request, _view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)
        return (
            user.is_superuser
            or user.has_role("AUDITOR")
            or user.has_role("ADMIN")
            or user.has_role("SUPERADMIN")
        )


class ReadOnly(BasePermission):
    """Allow safe methods (GET, HEAD, OPTIONS) only."""

    def has_permission(self, request: Request, _view: APIView) -> bool:
        return request.method in ("GET", "HEAD", "OPTIONS")


def HasRole(role_name: str) -> BasePermission:
    """
    Factory that returns a DRF permission *class* requiring a specific role.

    Usage:
        permission_classes = [IsAuthenticated, HasRole("LAB_MANAGER")]
    """

    class _HasRole(BasePermission):
        _role_name = role_name
        message = f"Role '{role_name}' required."

        def has_permission(self, request: Request, _view: APIView) -> bool:
            user = request.user
            if not user or not user.is_authenticated:
                return False
            assert isinstance(user, User)
            if user.is_superuser:
                return True
            return user.has_role(self._role_name)

    _HasRole.__name__ = f"HasRole_{role_name}"
    _HasRole.__qualname__ = f"HasRole_{role_name}"
    return _HasRole()


def HasAnyRole(*role_names: str) -> BasePermission:
    """
    Factory that returns a DRF permission *class* requiring at least one
    of the specified roles.

    Usage:
        permission_classes = [IsAuthenticated, HasAnyRole("LAB_MANAGER", "LAB_ANALYST")]
    """

    class _HasAnyRole(BasePermission):
        _role_names = role_names
        message = f"One of these roles required: {', '.join(role_names)}."

        def has_permission(self, request: Request, _view: APIView) -> bool:
            user = request.user
            if not user or not user.is_authenticated:
                return False
            assert isinstance(user, User)
            if user.is_superuser:
                return True
            return any(user.has_role(r) for r in self._role_names)

    _HasAnyRole.__name__ = f"HasAnyRole_{'_'.join(role_names)}"
    _HasAnyRole.__qualname__ = f"HasAnyRole_{'_'.join(role_names)}"
    return _HasAnyRole()