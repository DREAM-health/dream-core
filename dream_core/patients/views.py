"""
dream_core/patients/views.py

Phase 2: Facility-scoped - PatientQuerysetMixin now inherits FacilityFilterMixin;
PatientListCreateView inherits FacilityRequiredMixin and calls get_facility_create_kwargs() 
on serializer.save()

Patient Registry endpoints:

Standard REST:
  GET    /api/core/v1/patients/              — list (paginated, searchable)
  POST   /api/core/v1/patients/              — create
  GET    /api/core/v1/patients/{id}/         — retrieve
  PUT    /api/core/v1/patients/{id}/         — full update
  PATCH  /api/core/v1/patients/{id}/         — partial update
  DELETE /api/core/v1/patients/{id}/         — soft-delete (requires reason)

FHIR R4:
  GET    /api/core/v1/patients/{id}/fhir/    — retrieve as FHIR R4 Patient
  POST   /api/core/v1/patients/fhir/         — create from FHIR R4 Patient document
  PUT    /api/core/v1/patients/{id}/fhir/    — update from FHIR R4 Patient document

DataConsent:
  GET    /api/core/v1/patients/{id}/consents/                — list consents
  POST   /api/core/v1/patients/{id}/consents/                — create consent
  POST   /api/core/v1/patients/consents/{consent_id}/revoke/ — revoke consent  

Admin:
  GET    /api/core/v1/patients/deleted/      — list soft-deleted patients
  POST   /api/core/v1/patients/{id}/restore/ — restore soft-deleted patient
"""
from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dream_core.accounts.permissions import HasAnyRole, IsAdmin
from dream_core.facilities.mixins import FacilityFilterMixin, FacilityRequiredMixin
from dream_core.patients.models import DataConsent, Patient
from dream_core.patients.serializers import (
    DataConsentRevokeSerializer,
    DataConsentSerializer,
    DataConsentWriteSerializer,
    FHIRPatientSerializer,
    PatientDetailSerializer,
    PatientListSerializer,
    PatientSoftDeleteSerializer,
    PatientWriteSerializer,
)

from dream_core.accounts.accounts_utils import RoleType


# ── Mixins ────────────────────────────────────────────────────────────────────

class PatientQuerysetMixin(FacilityFilterMixin):
    """Shared queryset with prefetch for list and detail views."""

    request: Request

    def get_queryset(self) -> QuerySet[Patient]:
        base = (
            Patient.objects
            .prefetch_related("identifiers", "contacts")
            .select_related("created_by", "updated_by", "facility")
        )
        return self.get_facility_queryset(base)


# ── Standard REST views ───────────────────────────────────────────────────────

@extend_schema(tags=["patients"])
@extend_schema_view(
    get=extend_schema(
        summary="List patients",
        parameters=[
            OpenApiParameter("search", str, description="Search by name, email, id_patient, or id_dream"),
            OpenApiParameter("is_active", bool, description="Filter by active status"),
            OpenApiParameter("is_pregnant", bool, description="Filter by pregnancy status"),
            OpenApiParameter("is_breastfeeding", bool, description="Filter by breastfeeding status"),
        ],
    ),
    post=extend_schema(summary="Create patient"),
)
class PatientListCreateView(FacilityRequiredMixin, PatientQuerysetMixin, generics.ListCreateAPIView[Patient]):
    """
    List all active patients or create a new one.
    Roles required: any authenticated clinical role.
    """

    def get_permissions(self):
        if self.request.method == "POST":
            self.permission_classes = [
                IsAuthenticated,
                HasAnyRole(RoleType.SUPERADMIN, RoleType.ADMIN, RoleType.CLINICIAN, RoleType.RECEPTIONIST),
            ]
        else:
            self.permission_classes = [
                IsAuthenticated,
                HasAnyRole(RoleType.SUPERADMIN, RoleType.ADMIN, RoleType.CLINICIAN, RoleType.LAB_MANAGER, RoleType.LAB_ANALYST, RoleType.RECEPTIONIST),
            ]
        return super().get_permissions()
    
    filterset_fields = ["gender", "is_active", "blood_type", "is_pregnant", "is_breastfeeding"]
    search_fields = [
        "family_name", "given_names", "email",
        "id_patient", "id_dream",
        "identifiers__value",
    ]
    ordering_fields = ["family_name", "birth_date", "created_at"]

    def get_serializer_class(self) -> Any:
        if self.request.method == "POST":
            return PatientWriteSerializer
        return PatientListSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = PatientWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        patient: Patient = serializer.save(**self.get_facility_create_kwargs())
        output = PatientDetailSerializer(patient, context={"request": request})
        return Response(output.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["patients"])
@extend_schema_view(
    get=extend_schema(summary="Retrieve patient"),
    put=extend_schema(summary="Update patient (full)"),
    patch=extend_schema(summary="Update patient (partial)"),
    delete=extend_schema(summary="Soft-delete patient"),
)
class PatientDetailView(PatientQuerysetMixin, generics.RetrieveUpdateDestroyAPIView[Patient]):
    """
    Retrieve, update, or soft-delete a single patient record.

    DELETE requires a reason in the request body (regulatory requirement).
    """
    permission_classes = [
        IsAuthenticated,
        HasAnyRole(RoleType.SUPERADMIN, RoleType.ADMIN, RoleType.CLINICIAN, RoleType.LAB_MANAGER, RoleType.RECEPTIONIST),
    ]

    def get_serializer_class(self) -> Any:
        if self.request.method in ("PUT", "PATCH"):
            return PatientWriteSerializer
        return PatientDetailSerializer

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        patient = self.get_object()
        serializer = PatientDetailSerializer(patient, context={"request": request})
        return Response(serializer.data)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial: bool = kwargs.pop("partial", False)
        patient = self.get_object()
        serializer = PatientWriteSerializer(
            patient, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        output = PatientDetailSerializer(updated, context={"request": request})
        return Response(output.data)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Soft-delete — requires a mandatory reason."""
        patient = self.get_object()

        reason_serializer = PatientSoftDeleteSerializer(data=request.data)
        reason_serializer.is_valid(raise_exception=True)
        reason: str = reason_serializer.validated_data["reason"]

        patient.delete(
            deleted_by=request.user,
            reason=reason,
        )
        return Response(
            {"detail": "Patient record deactivated.", "id": str(patient.id)},
            status=status.HTTP_200_OK,
        )


# ── FHIR endpoints ────────────────────────────────────────────────────────────

@extend_schema(tags=["patients"])
class FHIRPatientCreateView(APIView):
    """
    POST /api/core/v1/patients/fhir/

    Create a patient from a FHIR R4 Patient resource document.
    The request body must be a valid FHIR R4 Patient JSON resource.
    """

    permission_classes = [
        IsAuthenticated,
        HasAnyRole(RoleType.SUPERADMIN, RoleType.ADMIN, RoleType.CLINICIAN, RoleType.RECEPTIONIST),
    ]

    @extend_schema(
        summary="Create patient from FHIR R4 resource",
        request={"application/fhir+json": FHIRPatientSerializer},
        responses={201: FHIRPatientSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        from dream_core.facilities.mixins import FacilityRequiredMixin as _FRM
        mixin = _FRM()
        mixin.request = request
        facility_kwargs = mixin.get_facility_create_kwargs()

        serializer = FHIRPatientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient: Patient = serializer.save(**facility_kwargs)
        output = FHIRPatientSerializer(patient)
        return Response(output.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["patients"])
class FHIRPatientDetailView(APIView):
    """
    GET  /api/core/v1/patients/{id}/fhir/  — Return patient as FHIR R4 resource
    PUT  /api/core/v1/patients/{id}/fhir/  — Update patient from FHIR R4 resource
    """

    permission_classes = [
        IsAuthenticated,
        HasAnyRole(RoleType.SUPERADMIN, RoleType.ADMIN, RoleType.CLINICIAN, RoleType.LAB_MANAGER, RoleType.LAB_ANALYST, RoleType.RECEPTIONIST),
    ]

    def _get_patient(self, pk: str) -> Patient:
        from dream_core.facilities.mixins import get_all_permitted_facility_ids
        qs = Patient.objects.prefetch_related("identifiers", "contacts")
        user = self.request.user
        if not (getattr(user, "is_superuser", False) or user.has_role(RoleType.SUPERADMIN)):
            ids = get_all_permitted_facility_ids(self.request)
            qs = qs.filter(facility_id__in=ids)
        return qs.get(pk=pk)

    @extend_schema(
        summary="Retrieve patient as FHIR R4 resource",
        responses={200: FHIRPatientSerializer},
    )
    def get(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        from django.http import Http404
        try:
            patient = self._get_patient(pk)
        except Patient.DoesNotExist:
            raise Http404
        serializer = FHIRPatientSerializer(patient)
        return Response(serializer.data)

    @extend_schema(
        summary="Update patient from FHIR R4 resource",
        request={"application/fhir+json": FHIRPatientSerializer},
        responses={200: FHIRPatientSerializer},
    )
    def put(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        from django.http import Http404
        try:
            patient = self._get_patient(pk)
        except Patient.DoesNotExist:
            raise Http404
        serializer = FHIRPatientSerializer(patient, data=request.data)
        serializer.is_valid(raise_exception=True)
        updated: Patient = serializer.save()
        output = FHIRPatientSerializer(updated)
        return Response(output.data)

 
# ── DataConsent views ─────────────────────────────────────────────────────────
 
@extend_schema(tags=["patients"])
@extend_schema_view(
    get=extend_schema(summary="List consents for a patient"),
    post=extend_schema(summary="Record a new consent for a patient"),
)
class DataConsentListCreateView(APIView):
    """
    GET  /api/core/v1/patients/{pk}/consents/
    POST /api/core/v1/patients/{pk}/consents/
    """
 
    permission_classes = [
        IsAuthenticated,
        HasAnyRole(RoleType.SUPERADMIN, RoleType.ADMIN, RoleType.CLINICIAN, RoleType.RECEPTIONIST),
    ]
 
    def _get_patient(self, pk: str) -> Patient:
        return Patient.objects.get(pk=pk)
 
    def get(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        from django.http import Http404
        try:
            patient = self._get_patient(pk)
        except Patient.DoesNotExist:
            raise Http404
        consents = DataConsent.objects.filter(patient=patient).select_related("revoked_by", "collected_by")
        return Response(DataConsentSerializer(consents, many=True).data)
 
    def post(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        from django.http import Http404
        try:
            patient = self._get_patient(pk)
        except Patient.DoesNotExist:
            raise Http404
        serializer = DataConsentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        consent: DataConsent = serializer.save(patient=patient)
        return Response(DataConsentSerializer(consent).data, status=status.HTTP_201_CREATED)
 
 
@extend_schema(tags=["patients"])
class DataConsentRevokeView(APIView):
    """
    POST /api/core/v1/patients/consents/{consent_id}/revoke/
    """
 
    permission_classes = [
        IsAuthenticated,
        HasAnyRole(RoleType.SUPERADMIN, RoleType.ADMIN, RoleType.CLINICIAN),
    ]
 
    @extend_schema(summary="Revoke a patient data consent")
    def post(self, request: Request, consent_id: str, *args: Any, **kwargs: Any) -> Response:
        from django.http import Http404
        try:
            consent = DataConsent.objects.get(pk=consent_id, is_active=True)
        except DataConsent.DoesNotExist:
            raise Http404
        serializer = DataConsentRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        consent.revoke(revoked_by=request.user, reason=serializer.validated_data["reason"])
        return Response(DataConsentSerializer(consent).data)
 
 


# ── Admin views ───────────────────────────────────────────────────────────────

@extend_schema(tags=["patients"])
class DeletedPatientListView(APIView):
    """
    GET /api/core/v1/patients/deleted/

    List soft-deleted patient records. Admin/Auditor only.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @extend_schema(summary="List soft-deleted patients")
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        patients = Patient.all_objects.filter(
            deleted_at__isnull=False
        ).prefetch_related("identifiers")
        serializer = PatientListSerializer(patients, many=True)
        return Response(serializer.data)


@extend_schema(tags=["patients"])
class PatientRestoreView(APIView):
    """
    POST /api/core/v1/patients/{id}/restore/

    Restore a soft-deleted patient record. Admin only.
    """

    permission_classes = [IsAuthenticated, IsAdmin]

    @extend_schema(summary="Restore soft-deleted patient")
    def post(self, request: Request, pk: str, *args: Any, **kwargs: Any) -> Response:
        from django.http import Http404
        try:
            patient = Patient.all_objects.get(pk=pk, deleted_at__isnull=False)
        except Patient.DoesNotExist:
            raise Http404

        patient.restore()
        serializer = PatientDetailSerializer(patient)
        return Response(serializer.data)
