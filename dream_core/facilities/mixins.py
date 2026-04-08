"""
dream_core/facilities/mixins.py

View mixins for facility-scoped data isolation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 2: full facility-scoped data isolation.
 
Queryset scoping combines two sources of permitted facility IDs:
  1. FacilityMembership rows (direct membership)
  2. django-guardian object permissions on Facility instances
     (cross-facility grants: codename = "access_facility")
 
The combined set is used as the facility__in filter. null facility entries
are NOT included (Decision 2: global catalog entries are exempt via C1 —
catalog views do not apply FacilityFilterMixin).
 
SUPERADMIN and is_superuser bypass all scoping.

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
    Return facility IDs from direct FacilityMembership rows.
    Cached on the request object per Django request lifecycle.
    """
    cache_attr = "_facility_ids"
    if hasattr(request, cache_attr):
        val = getattr(request, cache_attr)
        if isinstance(val, list):
            return val
        
    ids: list[str] = list(
        FacilityMembership.objects
        .filter(user=request.user)
        .values_list("facility_id", flat=True)
    )
    setattr(request, cache_attr, ids)
    return ids



def get_guardian_facility_ids(request: Request) -> list[str]:
    """
    Return facility IDs the user has been granted cross-facility access to
    via django-guardian object permission (codename: "access_facility").
 
    These are facilities the user is NOT a member of but has been explicitly
    granted read access to (e.g. a shared lab serving multiple clinics).
 
    Cached on the request object.
    """
    cache_attr = "_guardian_facility_ids"
    if hasattr(request, cache_attr):
        val = getattr(request, cache_attr)
        if isinstance(val, list):
            return val
 
    try:
        from guardian.shortcuts import get_objects_for_user
        qs = get_objects_for_user(
            request.user,
            "facilities.access_facility",
            klass=Facility,
            accept_global_perms=False,
        )
        ids: list[str] = list(qs.values_list("pk", flat=True))
    except Exception:
        ids = []
 
    setattr(request, cache_attr, ids)
    return ids
 
 
def get_all_permitted_facility_ids(request: Request) -> list[str]:
    """Union of membership IDs and guardian-granted IDs."""
    membership = get_user_facility_ids(request)
    guardian = get_guardian_facility_ids(request)
    return list(set(membership) | set(guardian))

def get_user_primary_facility(request: Request) -> Facility | None:
    """
    Return the user's primary facility (is_primary=True), or the first
    membership if none is primary, or None if no memberships exist.
    """
    memberships = (
        FacilityMembership.objects
        .filter(user=request.user)
        .select_related("facility")
        .order_by("-is_primary")
    )
    first = memberships.first()
    return first.facility if first else None
 
def _is_superuser_or_superadmin(request: Request) -> bool:
    user = request.user
    if getattr(user, "is_superuser", False):
        return True
    return getattr(user, "has_role", lambda r: False)(RoleType.SUPERADMIN)


# ── Mixins ────────────────────────────────────────────────────────────────────

class FacilityFilterMixin:
    """
    Scope read querysets to the user's permitted facilities.
 
    Permitted = FacilityMembership rows + guardian "access_facility" grants.
    SUPERADMIN / is_superuser bypass scoping entirely.
    Models without a `facility` FK field are returned unfiltered.
    null facility entries are NOT included.
    """
    request: Request  # set by DRF view

    def get_facility_queryset(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        if not enforcement_active():
            return queryset
        
        # Only apply if the model actually has a facility field.
        model = queryset.model
        opts = model._meta
        has_facility = False
        for f in opts.get_fields():
            if f.name == "facility":
                has_facility = True
                break

        if not has_facility:
            return queryset

        # SUPERADMIN and is_superuser bypass facility scoping entirely.
        user = self.request.user
        if getattr(user, "is_superuser", False) or getattr(user, "has_role", lambda r: False)(RoleType.SUPERADMIN):
            return queryset

        facility_ids = get_all_permitted_facility_ids(self.request)
        if not facility_ids:
            # User has no facility memberships — deny all access.
            return queryset.none()

        return queryset.filter(facility_id__in=facility_ids)


class FacilityRequiredMixin:
    """
    Inject the user's primary facility into record creation.
 
    Raises PermissionDenied if enforcement is active and the user has no
    primary facility (prevents orphaned records).
    SUPERADMIN bypasses the check and may pass facility explicitly.

    Usage:
        def perform_create(self, serializer):
            serializer.save(**self.get_facility_create_kwargs())
    """

    request: Request  # set by DRF view

    def get_facility_create_kwargs(self) -> dict[str, Any]:
        if not enforcement_active():
            return {}

        if _is_superuser_or_superadmin(self.request):
            # Superadmin must pass facility explicitly in the request payload;
            # we don't inject a default for them.
            return {}

        facility = get_user_primary_facility(self.request)
        if facility is None:
            raise PermissionDenied(
                "You must be assigned to a facility before creating records."
            )
        return {"facility": facility}
