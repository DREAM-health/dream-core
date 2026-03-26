"""
dream_core/facilities/mixins.py

View mixins for facility-scoped data isolation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 vs PHASE 2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 1 (current):
  FACILITY_ENFORCEMENT_ENABLED = False (default).
  Mixins are imported and applied on views, but get_facility_queryset()
  returns the full queryset unchanged. No behaviour difference from today.

Phase 2 activation:
  Set FACILITY_ENFORCEMENT_ENABLED = True in settings.
  All views using FacilityFilterMixin will automatically scope their
  querysets to the requesting user's permitted facilities.
  No view code needs to change — only the setting.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Apply FacilityFilterMixin to any view whose model has a `facility` FK:

    class PatientListView(FacilityFilterMixin, generics.ListCreateAPIView):
        def get_queryset(self):
            return self.get_facility_queryset(Patient.objects.all())

Apply FacilityRequiredMixin to any view that creates records. It injects
the facility into the serializer's save() call:

    class PatientCreateView(FacilityRequiredMixin, generics.CreateAPIView):
        def perform_create(self, serializer):
            serializer.save(**self.get_facility_create_kwargs())
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

from dream_core.accounts.accounts_utils import RoleType
from dream_core.facilities.models import Facility, FacilityMembership


# ── Helpers ───────────────────────────────────────────────────────────────────

def enforcement_active() -> bool:
    """Return True if facility-scoped isolation is enabled."""
    return bool(getattr(settings, "FACILITY_ENFORCEMENT_ENABLED", False))


def get_user_facility_ids(request: Request) -> list[str]:
    """
    Return all facility IDs the requesting user is a member of.
    Result is cached on the request object to avoid repeated DB hits.
    """
    cache_attr = "_facility_ids"
    if hasattr(request, cache_attr):
        return getattr(request, cache_attr)  # type: ignore[return-value]

    ids: list[str] = list(
        FacilityMembership.objects
        .filter(user=request.user)
        .values_list("facility_id", flat=True)
    )
    setattr(request, cache_attr, ids)
    return ids


def get_user_primary_facility(request: Request) -> Facility | None:
    """
    Return the user's primary facility, or the first membership if none
    is marked primary, or None if the user has no memberships.
    """
    memberships = (
        FacilityMembership.objects
        .filter(user=request.user)
        .select_related("facility")
        .order_by("-is_primary")
    )
    first = memberships.first()
    return first.facility if first else None


# ── Mixins ────────────────────────────────────────────────────────────────────

class FacilityFilterMixin:
    """
    Scope read querysets to the user's permitted facilities.

    Phase 1: passes through (no-op) when enforcement is disabled.
    Phase 2: filters queryset to facility__in=user_facility_ids.

    The model's queryset must have a `facility` FK field for this to work.
    Models without a facility field are unaffected (no filter is applied).
    """

    request: Request  # set by DRF view

    def get_facility_queryset(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        if not enforcement_active():
            return queryset

        # SUPERADMIN and is_superuser bypass facility scoping entirely.
        user = self.request.user
        if getattr(user, "is_superuser", False) or getattr(user, "has_role", lambda r: False)(RoleType.SUPERADMIN):
            return queryset

        facility_ids = get_user_facility_ids(self.request)
        if not facility_ids:
            # User has no facility memberships — deny all access.
            return queryset.none()

        # Only apply if the model actually has a facility field.
        model = queryset.model
        if hasattr(model, "facility_id"):
            return queryset.filter(facility_id__in=facility_ids)

        return queryset


class FacilityRequiredMixin:
    """
    Inject the user's primary facility into record creation.

    Phase 1: returns an empty dict (no-op injection).
    Phase 2: returns {'facility': <Facility>}; if the user has no primary
             facility, raises PermissionDenied to prevent orphaned records.

    Usage:
        def perform_create(self, serializer):
            serializer.save(**self.get_facility_create_kwargs())
    """

    request: Request  # set by DRF view

    def get_facility_create_kwargs(self) -> dict[str, Any]:
        if not enforcement_active():
            return {}

        facility = get_user_primary_facility(self.request)
        if facility is None:
            raise PermissionDenied(
                "You must be assigned to a facility before creating records."
            )
        return {"facility": facility}