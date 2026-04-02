"""
dream_core/catalog/serializers.py
"""
from typing import Any
from decimal import Decimal

from rest_framework import serializers

from dream_core.catalog.models import ReferenceRange, LabTestDefinition, LabTestPanel, MeasurementUnit


# ── Unit ──────────────────────────────────────────────────────────────────────

class UnitSerializer(serializers.ModelSerializer[MeasurementUnit]):
    class Meta:
        model = MeasurementUnit
        fields = ["id", "name", "symbol", "ucum_code", "description", "created_at"]
        read_only_fields = ["id", "created_at"]


# ── ReferenceRange ────────────────────────────────────────────────────────────

class ReferenceRangeSerializer(serializers.ModelSerializer[ReferenceRange]):
    class Meta:
        model = ReferenceRange
        fields = [
            "id", "gender", "age_min_days", "age_max_days", "label",
            "low_normal", "high_normal",
            "low_critical", "high_critical",
            "low_reportable", "high_reportable",
            "notes", "is_active",
        ]
        read_only_fields = ["id"]


class ReferenceRangeWriteSerializer(serializers.ModelSerializer[ReferenceRange]):
    """Used for nested write within TestDefinition."""

    class Meta:
        model = ReferenceRange
        fields = [
            "id", "gender", "age_min_days", "age_max_days", "label",
            "low_normal", "high_normal",
            "low_critical", "high_critical",
            "low_reportable", "high_reportable",
            "notes", "is_active",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        low = attrs.get("low_normal")
        high = attrs.get("high_normal")
        if low is not None and high is not None and low >= high:
            raise serializers.ValidationError(
                {"low_normal": "low_normal must be less than high_normal."}
            )
        low_crit = attrs.get("low_critical")
        high_crit = attrs.get("high_critical")
        if low_crit is not None and low is not None and low_crit >= low:
            raise serializers.ValidationError(
                {"low_critical": "low_critical must be less than low_normal."}
            )
        if high_crit is not None and high is not None and high_crit <= high:
            raise serializers.ValidationError(
                {"high_critical": "high_critical must be greater than high_normal."}
            )
        return attrs


# ── TestDefinition ────────────────────────────────────────────────────────────

class LabTestDefinitionListSerializer(serializers.ModelSerializer[LabTestDefinition]):
    unit_symbol = serializers.CharField(source="unit.symbol", read_only=True, default=None)

    class Meta:
        model = LabTestDefinition
        fields = [
            "id", "code", "name", "abbreviation", "loinc_code",
            "result_type", "unit_symbol",
            "turnaround_hours", "is_active",
        ]
        read_only_fields = fields


class LabTestDefinitionDetailSerializer(serializers.ModelSerializer[LabTestDefinition]):
    unit = UnitSerializer(read_only=True)
    reference_ranges = ReferenceRangeSerializer(many=True, read_only=True)

    class Meta:
        model = LabTestDefinition
        fields = [
            "id", "code", "name", "full_name", "abbreviation",
            "description", "loinc_code", "snomed_code", "minimum_volume_ml",
            "result_type", "unit", "decimal_places",
            "turnaround_hours", "method", "instrument",
            "requires_validation", "reportable", "is_active", "sort_order",
            "price", "allowed_values",
            "panels",
            "reference_ranges",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class LabTestDefinitionWriteSerializer(serializers.ModelSerializer[LabTestDefinition]):
    reference_ranges = ReferenceRangeWriteSerializer(many=True, required=False)

    class Meta:
        model = LabTestDefinition
        fields = [
            "code", "name", "full_name", "abbreviation",
            "description", "loinc_code", "snomed_code",
            "result_type", "unit", "decimal_places", "minimum_volume_ml",
            "turnaround_hours", "method", "instrument",
            "price", "allowed_values",
            "requires_validation", "reportable", "is_active", "sort_order",
            "panels", "reference_ranges",
        ]

    def validate_allowed_values(self, value: list[Any]) -> list[Any]:
        if not isinstance(value, list):
            raise serializers.ValidationError("allowed_values must be a list.")
        for item in value:
            if not isinstance(item, str):
                raise serializers.ValidationError("Each allowed value must be a string.")
        return value

    def _sync_reference_ranges(
        self,
        test: LabTestDefinition,
        ranges_data: list[dict[str, Any]],
    ) -> None:
        """Replace reference ranges on update."""
        test.reference_ranges.all().delete()
        for rr_data in ranges_data:
            ReferenceRange.objects.create(test=test, **rr_data)

    def create(self, validated_data: dict[str, Any]) -> LabTestDefinition:
        ranges_data: list[dict[str, Any]] = validated_data.pop("reference_ranges", [])
        test = LabTestDefinition.objects.create(**validated_data)
        self._sync_reference_ranges(test, ranges_data)
        return test

    def update(self, instance: LabTestDefinition, validated_data: dict[str, Any]) -> LabTestDefinition:
        ranges_data: list[dict[str, Any]] | None = validated_data.pop("reference_ranges", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if ranges_data is not None:
            self._sync_reference_ranges(instance, ranges_data)
        return instance


# ── LabTestPanel ─────────────────────────────────────────────────────────────────

class LabTestPanelListSerializer(serializers.ModelSerializer[LabTestPanel]):
    test_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = LabTestPanel
        fields = [
            "id",
            "category",
            "name",
            "code",
            "description",
            "loinc_code",
            "is_active",
            "price",
            "test_count",
        ]
        read_only_fields = fields


class LabTestPanelDetailSerializer(serializers.ModelSerializer[LabTestPanel]):
    tests = LabTestDefinitionListSerializer(many=True, read_only=True)

    class Meta:
        model = LabTestPanel
        fields = [
            "id",
            "category",
            "name",
            "code",
            "description",
            "loinc_code",
            "is_active",
            "price",
            "tests",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class LabTestPanelWriteSerializer(serializers.ModelSerializer[LabTestPanel]):
    class Meta:
        model = LabTestPanel
        fields = [
            "category",
            "name",
            "code",
            "description",
            "loinc_code",
            "is_active",
            "price",
        ]


# ── Result interpretation helper ──────────────────────────────────────────────

class ResultInterpretationSerializer(serializers.Serializer[Any]):
    """
    Given a test code, a numeric value, patient age in days, and gender,
    return the appropriate reference range interpretation flag.
    """
    test_code = serializers.CharField()
    value = serializers.DecimalField(max_digits=16, decimal_places=6)
    patient_age_days = serializers.IntegerField(required=False, allow_null=True, default=None)
    patient_gender = serializers.ChoiceField(
        choices=["male", "female", "any"],
        required=False,
        default="any",
    )
