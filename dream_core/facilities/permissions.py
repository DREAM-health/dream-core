"""
dream_core/facilities/permissions.py

DRF permission classes for the Facility API.

  IsSuperAdmin       — already in accounts.permissions; re-exported for convenience
  IsOwnFacilityAdmin — ADMIN can only manage memberships for facilities they
                       belong to. SUPERADMIN bypasses.
  GrantCrossFacilityAccess / RevokeCrossFacilityAccess — views for guardian
                       object permission management.

Guardian permission codename used for cross-facility access:
  "access_facility"  — grants read access to another facility's patient data.

This permission is object-level (per Facility instance), never global.
"""
from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from dream_core.accounts.accounts_utils import RoleType
from dream_core.accounts.models import User
from dream_core.facilities.mixins import get_user_facility_ids


# ── Codename constant ─────────────────────────────────────────────────────────

CROSS_FACILITY_CODENAME = "access_facility"


# ── Permission classes ────────────────────────────────────────────────────────

class IsSuperAdmin(BasePermission):
    """Superuser or SUPERADMIN role required."""

    message = "Superadmin access required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)
        return user.is_superuser or user.has_role(RoleType.SUPERADMIN)


class IsOwnFacilityAdmin(BasePermission):
    """
    ADMIN can manage memberships only for facilities they themselves belong to.
    SUPERADMIN bypasses this restriction.

    Used on FacilityMemberListCreateView and FacilityMemberDetailView where
    the facility pk is available as a URL kwarg named `facility_pk`.
    """

    message = "You can only manage memberships for facilities you belong to."

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        assert isinstance(user, User)

        if user.is_superuser or user.has_role(RoleType.SUPERADMIN):
            return True

        if not user.has_role(RoleType.ADMIN):
            return False

        facility_pk = view.kwargs.get("facility_pk")  # type: ignore[attr-defined]
        if not facility_pk:
            return False

        return str(facility_pk) in [str(fid) for fid in get_user_facility_ids(request)]

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        return self.has_permission(request, view)


# ── Guardian helpers ──────────────────────────────────────────────────────────

def grant_cross_facility_access(actor: User, target_user: User, facility: Any) -> None:
    """
    Grant target_user the "access_facility" object permission on facility.
    Actor must be SUPERADMIN or ADMIN of that facility.
    """
    from guardian.shortcuts import assign_perm
    assign_perm(CROSS_FACILITY_CODENAME, target_user, facility)


def revoke_cross_facility_access(actor: User, target_user: User, facility: Any) -> None:
    """
    Revoke target_user's "access_facility" object permission on facility.
    """
    from guardian.shortcuts import remove_perm
    remove_perm(CROSS_FACILITY_CODENAME, target_user, facility)


def get_facilities_user_can_access(user: User) -> Any:
    """
    Return all Facility instances accessible to a user via guardian grant.
    Excludes memberships (use FacilityMembership for those).
    """
    from guardian.shortcuts import get_objects_for_user
    from dream_core.facilities.models import Facility
    return get_objects_for_user(
        user,
        f"facilities.{CROSS_FACILITY_CODENAME}",
        klass=Facility,
        accept_global_perms=False,
    )