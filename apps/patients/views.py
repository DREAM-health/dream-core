"""
apps/patients/views.py

Patient Registry endpoints:

Standard REST:
  GET    /api/v1/patients/              — list (paginated, searchable)
  POST   /api/v1/patients/              — create
  GET    /api/v1/patients/{id}/         — retrieve
  PUT    /api/v1/patients/{id}/         — full update
  PATCH  /api/v1/patients/{id}/         — partial update
  DELETE /api/v1/patients/{id}/         — soft-delete (requires reason)

FHIR R4:
  GET    /api/v1/patients/{id}/fhir/    — retrieve as FHIR R4 Patient
  POST   /api/v1/patients/fhir/         — create from FHIR R4 Patient document
  PUT    /api/v1/patients/{id}/fhir/    — update from FHIR R4 Patient document

Admin:
  GET    /api/v1/patients/deleted/      — list soft-deleted patients
  POST   /api/v1/patients/{id}/restore/ — restore soft-deleted patient
"""
from typing import Any

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasAnyRole, IsAdmin
from apps.patients.models import Patient
from apps.patients.serializers import (
    FHIRPatientSerializer,
    PatientDetailSerializer,
    PatientListSerializer,
    PatientSoftDeleteSerializer,
    PatientWriteSerializer,
)


# ── Mixins ────────────────────────────────────────────────────────────────────

class PatientQuerysetMixin:
    """Shared queryset with prefetch for list and detail views."""

    def get_queryset(self) -> QuerySet[Patient]:
        return (
            Patient.objects
            .prefetch_related("identifiers", "contacts")
            .select_related("created_by", "updated_by")
        )


# ── Standard REST views ───────────────────────────────────────────────────────

@extend_schema(tags=["patients"])
@extend_schema_view(
    get=extend_schema(
        summary="List patients",
        parameters=[
            OpenApiParameter("search", str, description="Search by name, email, or identifier value"),
            OpenApiParameter("is_active", bool, description="Filter by active status"),
        ],
    ),
    post=extend_schema(summary="Create patient"),
)
class PatientListCreateView(PatientQuerysetMixin, generics.ListCreateAPIView[Patient]):
    """
    List all active patients or create a new one.
    Roles required: any authenticated clinical role.
    """

    permission_classes = [
        IsAuthenticated,
        HasAnyRole("SUPERADMIN", "ADMIN", "CLINICIAN", "LAB_MANAGER", "LAB_ANALYST", "RECEPTIONIST"),
    ]
    filterset_fields = ["gender", "is_active", "blood_type"]
    search_fields = [
        "family_name", "given_names", "email",
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
        patient: Patient = serializer.save()
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
        HasAnyRole("SUPERADMIN", "ADMIN", "CLINICIAN", "LAB_MANAGER", "RECEPTIONIST"),
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
    POST /api/v1/patients/fhir/

    Create a patient from a FHIR R4 Patient resource document.
    The request body must be a valid FHIR R4 Patient JSON resource.
    """

    permission_classes = [
        IsAuthenticated,
        HasAnyRole("SUPERADMIN", "ADMIN", "CLINICIAN", "RECEPTIONIST"),
    ]

    @extend_schema(
        summary="Create patient from FHIR R4 resource",
        request={"application/fhir+json": FHIRPatientSerializer},
        responses={201: FHIRPatientSerializer},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = FHIRPatientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient: Patient = serializer.save()
        output = FHIRPatientSerializer(patient)
        return Response(output.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["patients"])
class FHIRPatientDetailView(APIView):
    """
    GET  /api/v1/patients/{id}/fhir/  — Return patient as FHIR R4 resource
    PUT  /api/v1/patients/{id}/fhir/  — Update patient from FHIR R4 resource
    """

    permission_classes = [
        IsAuthenticated,
        HasAnyRole("SUPERADMIN", "ADMIN", "CLINICIAN", "LAB_MANAGER", "LAB_ANALYST", "RECEPTIONIST"),
    ]

    def _get_patient(self, pk: str) -> Patient:
        return Patient.objects.prefetch_related("identifiers", "contacts").get(pk=pk)

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


# ── Admin views ───────────────────────────────────────────────────────────────

@extend_schema(tags=["patients"])
class DeletedPatientListView(APIView):
    """
    GET /api/v1/patients/deleted/

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
    POST /api/v1/patients/{id}/restore/

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
