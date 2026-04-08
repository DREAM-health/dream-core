"""
dream_core/facilities/serializers.py
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers

from dream_core.accounts.serializers import UserListSerializer
from dream_core.facilities.models import Facility, FacilityMembership


# ── Facility ──────────────────────────────────────────────────────────────────

class FacilityListSerializer(serializers.ModelSerializer[Facility]):
    class Meta:
        model = Facility
        fields = [
            "id", "name", "short_name", "code", "facility_type",
            "parent_facility", "is_active", "timezone", "created_at",
        ]
        read_only_fields = fields


class FacilityDetailSerializer(serializers.ModelSerializer[Facility]):
    parent_facility_name = serializers.CharField(
        source="parent_facility.name", read_only=True, default=None
    )

    class Meta:
        model = Facility
        fields = [
            "id", "name", "short_name", "code", "facility_type",
            "parent_facility", "parent_facility_name",
            "address", "phone", "email", "website",
            "tax_id", "oid", "fhir_organization_id",
            "is_active", "timezone",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class FacilityWriteSerializer(serializers.ModelSerializer[Facility]):
    class Meta:
        model = Facility
        fields = [
            "name", "short_name", "code", "facility_type",
            "parent_facility",
            "address", "phone", "email", "website",
            "tax_id", "oid", "fhir_organization_id",
            "is_active", "timezone",
        ]

    def validate_code(self, value: str) -> str:
        qs = Facility.objects.filter(code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A facility with this code already exists.")
        return value


# ── FacilityMembership ────────────────────────────────────────────────────────

class FacilityMembershipSerializer(serializers.ModelSerializer[FacilityMembership]):
    user_detail = UserListSerializer(source="user", read_only=True)
    role_override_name = serializers.CharField(
        source="role_override.name", read_only=True, default=None
    )

    class Meta:
        model = FacilityMembership
        fields = [
            "id", "user", "user_detail",
            "facility", "is_primary",
            "role_override", "role_override_name",
        ]
        read_only_fields = ["id", "facility"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        facility = self.context.get("facility")
        user = attrs.get("user")
        if facility and user:
            qs = FacilityMembership.objects.filter(facility=facility, user=user)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "This user is already a member of this facility."
                )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> FacilityMembership:
        facility = self.context["facility"]
        return FacilityMembership.objects.create(facility=facility, **validated_data)


# ── Cross-facility access ─────────────────────────────────────────────────────

class CrossFacilityGrantSerializer(serializers.Serializer[Any]):
    """Body for granting/revoking cross-facility access."""
    # TODO: Add using also id_patient & id_dream
    user_id = serializers.UUIDField(help_text="UUID of the user to grant/revoke access for.")