"""
dream_core/facilities/views.py

Facility API endpoints:

  Facilities (SUPERADMIN only for create/delete; ADMIN+ for read/update):
    GET/POST        /api/core/v1/facilities/
    GET/PUT/PATCH   /api/core/v1/facilities/{id}/
    DELETE          /api/core/v1/facilities/{id}/   → soft-delete

  Memberships (SUPERADMIN or own-facility ADMIN):
    GET/POST        /api/core/v1/facilities/{facility_pk}/members/
    GET/PATCH/DELETE /api/core/v1/facilities/{facility_pk}/members/{id}/

  Cross-facility access (SUPERADMIN only):
    POST            /api/core/v1/facilities/{facility_pk}/access/grant/
    POST            /api/core/v1/facilities/{facility_pk}/access/revoke/
"""
from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dream_core.accounts.models import User
from dream_core.accounts.permissions import IsAdmin
from dream_core.facilities.models import Facility, FacilityMembership
from dream_core.facilities.permissions import (
    IsSuperAdmin,
    IsOwnFacilityAdmin,
    grant_cross_facility_access,
    revoke_cross_facility_access,
)
from dream_core.facilities.serializers import (
    CrossFacilityGrantSerializer,
    FacilityDetailSerializer,
    FacilityListSerializer,
    FacilityMembershipSerializer,
    FacilityWriteSerializer,
)


# ── Facilities ────────────────────────────────────────────────────────────────

@extend_schema(tags=["facilities"])
@extend_schema_view(
    get=extend_schema(summary="List facilities"),
    post=extend_schema(summary="Create facility"),
)
class FacilityListCreateView(generics.ListCreateAPIView[Facility]):
    search_fields = ["name", "short_name", "code"]
    filterset_fields = ["facility_type", "is_active"]
    ordering_fields = ["name", "created_at"]

    def get_permissions(self) -> list[Any]:
        if self.request.method == "POST":
            self.permission_classes = [IsAuthenticated, IsSuperAdmin]
        else:
            self.permission_classes = [IsAuthenticated, IsAdmin]
        return super().get_permissions()

    def get_queryset(self) -> QuerySet[Facility]:
        user: User = self.request.user  # type: ignore[assignment]
        if user.is_superuser or user.has_role("SUPERADMIN"):
            return Facility.objects.select_related("parent_facility").all()
        # ADMIN sees only their own facilities
        from dream_core.facilities.mixins import get_user_facility_ids
        ids = get_user_facility_ids(self.request)
        return Facility.objects.filter(pk__in=ids).select_related("parent_facility")

    def get_serializer_class(self) -> Any:
        if self.request.method == "POST":
            return FacilityWriteSerializer
        return FacilityListSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = FacilityWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        facility: Facility = serializer.save()
        return Response(
            FacilityDetailSerializer(facility).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["facilities"])
@extend_schema_view(
    get=extend_schema(summary="Retrieve facility"),
    put=extend_schema(summary="Update facility"),
    patch=extend_schema(summary="Partial update facility"),
    delete=extend_schema(summary="Soft-delete facility"),
)
class FacilityDetailView(generics.RetrieveUpdateDestroyAPIView[Facility]):

    def get_permissions(self) -> list[Any]:
        if self.request.method in ("PUT", "PATCH"):
            # ADMIN can update their own facility; SUPERADMIN can update any
            self.permission_classes = [IsAuthenticated, IsAdmin]
        elif self.request.method == "DELETE":
            self.permission_classes = [IsAuthenticated, IsSuperAdmin]
        else:
            self.permission_classes = [IsAuthenticated, IsAdmin]
        return super().get_permissions()

    def get_queryset(self) -> QuerySet[Facility]:
        user: User = self.request.user  # type: ignore[assignment]
        if user.is_superuser or user.has_role("SUPERADMIN"):
            return Facility.objects.all()
        from dream_core.facilities.mixins import get_user_facility_ids
        ids = get_user_facility_ids(self.request)
        return Facility.objects.filter(pk__in=ids)

    def get_serializer_class(self) -> Any:
        if self.request.method in ("PUT", "PATCH"):
            return FacilityWriteSerializer
        return FacilityDetailSerializer

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial: bool = kwargs.pop("partial", False)
        facility = self.get_object()
        serializer = FacilityWriteSerializer(
            facility, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return Response(FacilityDetailSerializer(updated).data)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        facility: Facility = self.get_object()
        facility.delete(
            deleted_by=request.user,
            reason=request.data.get("reason", "Soft-deleted via API"),
        )
        return Response(
            {"detail": f"Facility '{facility.code}' deactivated."},
            status=status.HTTP_200_OK,
        )


# ── Memberships ───────────────────────────────────────────────────────────────

@extend_schema(tags=["facilities"])
@extend_schema_view(
    get=extend_schema(summary="List facility members"),
    post=extend_schema(summary="Add member to facility"),
)
class FacilityMemberListCreateView(generics.ListCreateAPIView[FacilityMembership]):
    permission_classes = [IsAuthenticated, IsOwnFacilityAdmin]
    serializer_class = FacilityMembershipSerializer

    def _get_facility(self) -> Facility:
        return Facility.objects.get(pk=self.kwargs["facility_pk"])

    def get_queryset(self) -> QuerySet[FacilityMembership]:
        return (
            FacilityMembership.objects
            .filter(facility_id=self.kwargs["facility_pk"])
            .select_related("user", "facility", "role_override")
        )

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        ctx["facility"] = self._get_facility()
        return ctx

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        facility = self._get_facility()
        serializer = FacilityMembershipSerializer(
            data=request.data, context={"request": request, "facility": facility}
        )
        serializer.is_valid(raise_exception=True)
        membership: FacilityMembership = serializer.save()
        return Response(
            FacilityMembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["facilities"])
@extend_schema_view(
    get=extend_schema(summary="Retrieve facility member"),
    patch=extend_schema(summary="Update facility member"),
    delete=extend_schema(summary="Remove member from facility"),
)
class FacilityMemberDetailView(generics.RetrieveUpdateDestroyAPIView[FacilityMembership]):
    permission_classes = [IsAuthenticated, IsOwnFacilityAdmin]
    serializer_class = FacilityMembershipSerializer

    def get_queryset(self) -> QuerySet[FacilityMembership]:
        return FacilityMembership.objects.filter(
            facility_id=self.kwargs["facility_pk"]
        ).select_related("user", "facility", "role_override")

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        ctx["facility"] = Facility.objects.get(pk=self.kwargs["facility_pk"])
        return ctx

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        membership: FacilityMembership = self.get_object()
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Cross-facility access ─────────────────────────────────────────────────────

@extend_schema(tags=["facilities"])
class CrossFacilityGrantView(APIView):
    """
    POST /api/core/v1/facilities/{facility_pk}/access/grant/

    Grant a user cross-facility read access to this facility's patient data
    via django-guardian object permission (codename: access_facility).
    SUPERADMIN only.
    """

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        summary="Grant cross-facility access to a user",
        request=CrossFacilityGrantSerializer,
        responses={200: {"type": "object", "properties": {"detail": {"type": "string"}}}},
    )
    def post(self, request: Request, facility_pk: str, *args: Any, **kwargs: Any) -> Response:
        from django.http import Http404
        try:
            facility = Facility.objects.get(pk=facility_pk)
        except Facility.DoesNotExist:
            raise Http404
        print("FACILITY", facility)

        serializer = CrossFacilityGrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            target_user = User.objects.get(pk=serializer.validated_data["user_id"])
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        print("target_user", target_user)

        actor: User = request.user
        print("actor", actor)
        grant_cross_facility_access(actor, target_user, facility)
        return Response(
            {"detail": f"Cross-facility access granted to {target_user.email} for {facility.code}."}
        )


@extend_schema(tags=["facilities"])
class CrossFacilityRevokeView(APIView):
    """
    POST /api/core/v1/facilities/{facility_pk}/access/revoke/

    Revoke a user's cross-facility read access. SUPERADMIN only.
    """

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    @extend_schema(
        summary="Revoke cross-facility access from a user",
        request=CrossFacilityGrantSerializer,
        responses={200: {"type": "object", "properties": {"detail": {"type": "string"}}}},
    )
    def post(self, request: Request, facility_pk: str, *args: Any, **kwargs: Any) -> Response:
        from django.http import Http404
        try:
            facility = Facility.objects.get(pk=facility_pk)
        except Facility.DoesNotExist:
            raise Http404

        serializer = CrossFacilityGrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            target_user = User.objects.get(pk=serializer.validated_data["user_id"])
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        actor: User = request.user  # type: ignore[assignment]
        revoke_cross_facility_access(actor, target_user, facility)
        return Response(
            {"detail": f"Cross-facility access revoked from {target_user.email} for {facility.code}."}
        )