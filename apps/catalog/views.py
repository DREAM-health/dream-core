"""
apps/catalog/views.py

Test Catalog endpoints:

Units:
  GET/POST   /api/v1/catalog/units/
  GET/PUT/PATCH/DELETE  /api/v1/catalog/units/{id}/

Panels:
  GET/POST   /api/v1/catalog/panels/
  GET/PUT/PATCH/DELETE  /api/v1/catalog/panels/{id}/
  DELETE /api/v1/catalog/panels/{id}/  → soft-delete

Tests:
  GET/POST   /api/v1/catalog/tests/
  GET/PUT/PATCH/DELETE  /api/v1/catalog/tests/{id}/
  POST /api/v1/catalog/tests/interpret/  → result interpretation
"""
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q, QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasAnyRole, IsAdmin
from apps.catalog.models import ReferenceRange, TestDefinition, TestPanel, Unit
from apps.catalog.serializers import (
    ResultInterpretationSerializer,
    TestDefinitionDetailSerializer,
    TestDefinitionListSerializer,
    TestDefinitionWriteSerializer,
    TestPanelDetailSerializer,
    TestPanelListSerializer,
    TestPanelWriteSerializer,
    UnitSerializer,
)

# Roles that can READ the catalog (broad — all clinical roles)
_READ_ROLES = HasAnyRole(
    "SUPERADMIN", "ADMIN", "CLINICIAN",
    "LAB_MANAGER", "LAB_ANALYST", "RECEPTIONIST",
)
# Roles that can WRITE the catalog
_WRITE_ROLES = HasAnyRole("SUPERADMIN", "ADMIN", "LAB_MANAGER")


# ── Units ─────────────────────────────────────────────────────────────────────

@extend_schema(tags=["catalog"])
@extend_schema_view(
    get=extend_schema(summary="List measurement units"),
    post=extend_schema(summary="Create measurement unit"),
)
class UnitListCreateView(generics.ListCreateAPIView[Unit]):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer
    search_fields = ["name", "symbol", "ucum_code"]
    ordering_fields = ["symbol", "name"]

    def get_permissions(self) -> list[Any]:
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated(), _READ_ROLES]
        return [IsAuthenticated(), _WRITE_ROLES]


@extend_schema(tags=["catalog"])
@extend_schema_view(
    get=extend_schema(summary="Retrieve unit"),
    put=extend_schema(summary="Update unit"),
    patch=extend_schema(summary="Partial update unit"),
    delete=extend_schema(summary="Delete unit"),
)
class UnitDetailView(generics.RetrieveUpdateDestroyAPIView[Unit]):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer

    def get_permissions(self) -> list[Any]:
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated(), _READ_ROLES]
        return [IsAuthenticated(), _WRITE_ROLES]


# ── Test Panels ───────────────────────────────────────────────────────────────

@extend_schema(tags=["catalog"])
@extend_schema_view(
    get=extend_schema(summary="List test panels"),
    post=extend_schema(summary="Create test panel"),
)
class TestPanelListCreateView(generics.ListCreateAPIView[TestPanel]):
    search_fields = ["code", "name", "category", "loinc_code"]
    filterset_fields = ["category", "is_active", "specimen_type", "fasting_required"]
    ordering_fields = ["sort_order", "name", "category"]

    def get_permissions(self) -> list[Any]:
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated(), _READ_ROLES]
        return [IsAuthenticated(), _WRITE_ROLES]

    def get_queryset(self) -> QuerySet[TestPanel]:
        return (
            TestPanel.objects
            .annotate(test_count=Count("tests"))
            .prefetch_related("tests")
        )

    def get_serializer_class(self) -> Any:
        if self.request.method == "POST":
            return TestPanelWriteSerializer
        return TestPanelListSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = TestPanelWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        panel: TestPanel = serializer.save()
        output = TestPanelDetailSerializer(
            TestPanel.objects.annotate(test_count=Count("tests")).get(pk=panel.pk)
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["catalog"])
@extend_schema_view(
    get=extend_schema(summary="Retrieve test panel"),
    put=extend_schema(summary="Update test panel"),
    patch=extend_schema(summary="Partial update test panel"),
    delete=extend_schema(summary="Soft-delete test panel"),
)
class TestPanelDetailView(generics.RetrieveUpdateDestroyAPIView[TestPanel]):

    def get_permissions(self) -> list[Any]:
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated(), _READ_ROLES]
        return [IsAuthenticated(), _WRITE_ROLES]

    def get_queryset(self) -> QuerySet[TestPanel]:
        return TestPanel.objects.prefetch_related("tests__unit", "tests__reference_ranges")

    def get_serializer_class(self) -> Any:
        if self.request.method in ("PUT", "PATCH"):
            return TestPanelWriteSerializer
        return TestPanelDetailSerializer

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        panel: TestPanel = self.get_object()
        panel.delete(deleted_by=request.user, reason="Catalog soft-delete via API")
        return Response(
            {"detail": f"Panel '{panel.code}' deactivated."},
            status=status.HTTP_200_OK,
        )


# ── Test Definitions ──────────────────────────────────────────────────────────

@extend_schema(tags=["catalog"])
@extend_schema_view(
    get=extend_schema(summary="List test definitions"),
    post=extend_schema(summary="Create test definition"),
)
class TestDefinitionListCreateView(generics.ListCreateAPIView[TestDefinition]):
    search_fields = ["code", "name", "abbreviation", "loinc_code", "snomed_code"]
    filterset_fields = [
        "panel", "result_type", "specimen_type",
        "is_active", "requires_validation", "reportable",
    ]
    ordering_fields = ["sort_order", "name", "code", "turnaround_hours"]

    def get_permissions(self) -> list[Any]:
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated(), _READ_ROLES]
        return [IsAuthenticated(), _WRITE_ROLES]

    def get_queryset(self) -> QuerySet[TestDefinition]:
        return (
            TestDefinition.objects
            .select_related("unit", "panel")
            .prefetch_related("reference_ranges")
        )

    def get_serializer_class(self) -> Any:
        if self.request.method == "POST":
            return TestDefinitionWriteSerializer
        return TestDefinitionListSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = TestDefinitionWriteSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        test: TestDefinition = serializer.save()
        output = TestDefinitionDetailSerializer(
            TestDefinition.objects
            .select_related("unit", "panel")
            .prefetch_related("reference_ranges")
            .get(pk=test.pk)
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["catalog"])
@extend_schema_view(
    get=extend_schema(summary="Retrieve test definition"),
    put=extend_schema(summary="Update test definition"),
    patch=extend_schema(summary="Partial update test definition"),
    delete=extend_schema(summary="Soft-delete test definition"),
)
class TestDefinitionDetailView(generics.RetrieveUpdateDestroyAPIView[TestDefinition]):

    def get_permissions(self) -> list[Any]:
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated(), _READ_ROLES]
        return [IsAuthenticated(), _WRITE_ROLES]

    def get_queryset(self) -> QuerySet[TestDefinition]:
        return (
            TestDefinition.objects
            .select_related("unit", "panel")
            .prefetch_related("reference_ranges")
        )

    def get_serializer_class(self) -> Any:
        if self.request.method in ("PUT", "PATCH"):
            return TestDefinitionWriteSerializer
        return TestDefinitionDetailSerializer

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial: bool = kwargs.pop("partial", False)
        test = self.get_object()
        serializer = TestDefinitionWriteSerializer(
            test, data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        output = TestDefinitionDetailSerializer(
            TestDefinition.objects
            .select_related("unit", "panel")
            .prefetch_related("reference_ranges")
            .get(pk=updated.pk)
        )
        return Response(output.data)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        test: TestDefinition = self.get_object()
        test.delete(deleted_by=request.user, reason="Catalog soft-delete via API")
        return Response(
            {"detail": f"Test '{test.code}' deactivated."},
            status=status.HTTP_200_OK,
        )


# ── Result interpretation ─────────────────────────────────────────────────────

@extend_schema(tags=["catalog"])
class ResultInterpretationView(APIView):
    """
    POST /api/v1/catalog/tests/interpret/

    Given a test code, numeric result value, patient age (days) and sex,
    return the correct reference range interpretation flag.

    Flags:
      N  = Normal
      L  = Low
      H  = High
      LL = Critical Low (panic value)
      HH = Critical High (panic value)
      ?  = Outside reportable range or no matching range found
    """

    permission_classes = [
        IsAuthenticated,
        HasAnyRole("SUPERADMIN", "ADMIN", "CLINICIAN", "LAB_MANAGER", "LAB_ANALYST"),
    ]

    @extend_schema(
        summary="Interpret a result against reference ranges",
        request=ResultInterpretationSerializer,
        responses={200: {"type": "object", "properties": {
            "flag": {"type": "string"},
            "range_used": {"type": "object"},
            "detail": {"type": "string"},
        }}},
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = ResultInterpretationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        test_code: str = serializer.validated_data["test_code"]
        value: Decimal = serializer.validated_data["value"]
        age_days: int | None = serializer.validated_data.get("patient_age_days")
        sex: str = serializer.validated_data.get("patient_sex", "any")

        try:
            test = TestDefinition.objects.get(code=test_code, is_active=True)
        except TestDefinition.DoesNotExist:
            return Response(
                {"detail": f"Test '{test_code}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if test.result_type != TestDefinition.ResultType.NUMERIC:
            return Response(
                {"detail": "Interpretation is only available for numeric result types."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Find the best matching reference range
        ranges = ReferenceRange.objects.filter(test=test, is_active=True)

        # Filter by sex
        ranges = ranges.filter(sex__in=[sex, "any"])

        # Filter by age if provided
        if age_days is not None:
            ranges = ranges.filter(
                models_Q_age(age_days)
            )

        # Prefer most specific match (sex match over 'any', narrower age band)
        range_obj = _best_reference_range(list(ranges), sex, age_days)

        if range_obj is None:
            return Response({
                "flag": "?",
                "range_used": None,
                "detail": "No matching reference range found for this patient profile.",
            })

        flag = range_obj.interpret(value)
        return Response({
            "flag": flag,
            "range_used": ReferenceRangeSerializer(range_obj).data,
            "detail": _flag_description(flag),
        })


def models_Q_age(age_days: int) -> Any:
    """Build a Q filter for age range — handles null bounds."""
    return (
        Q(age_min_days__isnull=True) | Q(age_min_days__lte=age_days)
    ) & (
        Q(age_max_days__isnull=True) | Q(age_max_days__gt=age_days)
    )


def _best_reference_range(
    ranges: list[ReferenceRange],
    sex: str,
    age_days: int | None,
) -> ReferenceRange | None:
    """
    Select the most specific matching reference range.
    Priority: exact sex match > 'any'; narrower age band > wider.
    """
    if not ranges:
        return None

    # Prefer exact sex match
    sex_specific = [r for r in ranges if r.sex == sex]
    candidates = sex_specific if sex_specific else ranges

    # Among candidates, prefer range with narrowest age band
    def age_band_width(r: ReferenceRange) -> int:
        if r.age_min_days is None and r.age_max_days is None:
            return 999_999
        if r.age_min_days is None:
            return r.age_max_days or 999_999
        if r.age_max_days is None:
            return 999_999
        return r.age_max_days - r.age_min_days

    return min(candidates, key=age_band_width)


def _flag_description(flag: str) -> str:
    return {
        "N": "Normal",
        "L": "Low — below normal range",
        "H": "High — above normal range",
        "LL": "CRITICAL LOW — notify clinician immediately",
        "HH": "CRITICAL HIGH — notify clinician immediately",
        "?": "Outside reportable range or undetermined",
    }.get(flag, "Unknown")
