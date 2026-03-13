"""
apps/patients/serializers.py

Two serializer families:
1. Standard DRF serializers for internal CRUD operations.
2. FHIRPatientSerializer – accepts and returns a FHIR R4 Patient JSON document.
"""
from typing import Any

from rest_framework import serializers

from apps.patients.fhir_utils import fhir_to_patient_data, patient_to_fhir
from apps.patients.models import Patient, PatientContact, PatientIdentifier


# ── Sub-resource serializers ──────────────────────────────────────────────────

class PatientIdentifierSerializer(serializers.ModelSerializer[PatientIdentifier]):
    class Meta:
        model = PatientIdentifier
        fields = ["id", "use", "system", "value"]


class PatientContactSerializer(serializers.ModelSerializer[PatientContact]):
    class Meta:
        model = PatientContact
        fields = ["id", "system", "value", "use", "rank", "is_active"]


# ── Patient list (compact) ────────────────────────────────────────────────────

class PatientListSerializer(serializers.ModelSerializer[Patient]):
    full_name = serializers.CharField(read_only=True)
    identifiers = PatientIdentifierSerializer(many=True, read_only=True)

    class Meta:
        model = Patient
        fields = [
            "id", "full_name", "family_name", "given_names",
            "birth_date", "gender", "email", "is_active",
            "identifiers", "created_at",
        ]
        read_only_fields = fields


# ── Patient detail (standard DRF) ────────────────────────────────────────────

class PatientDetailSerializer(serializers.ModelSerializer[Patient]):
    full_name = serializers.CharField(read_only=True)
    identifiers = PatientIdentifierSerializer(many=True, read_only=True)
    contacts = PatientContactSerializer(many=True, read_only=True)

    class Meta:
        model = Patient
        fields = [
            "id", "full_name", "family_name", "given_names",
            "birth_date", "gender", "email",
            "blood_type", "allergies_notes", "notes",
            "address", "is_active",
            "identifiers", "contacts",
            "created_at", "updated_at", "deleted_at",
        ]
        read_only_fields = ["id", "full_name", "created_at", "updated_at", "deleted_at"]


class PatientWriteSerializer(serializers.ModelSerializer[Patient]):
    """Used for CREATE and UPDATE via the standard REST path."""

    identifiers = PatientIdentifierSerializer(many=True, required=False)
    contacts = PatientContactSerializer(many=True, required=False)

    class Meta:
        model = Patient
        fields = [
            "family_name", "given_names", "birth_date", "gender",
            "email", "blood_type", "allergies_notes", "notes",
            "address", "identifiers", "contacts",
        ]

    def _upsert_identifiers(self, patient: Patient, identifiers: list[dict[str, Any]]) -> None:
        existing_ids = {(i.system, i.value) for i in patient.identifiers.all()}
        for ident in identifiers:
            key = (ident["system"], ident["value"])
            if key not in existing_ids:
                PatientIdentifier.objects.create(patient=patient, **ident)

    def _upsert_contacts(self, patient: Patient, contacts: list[dict[str, Any]]) -> None:
        # Replace contacts on update
        patient.contacts.all().delete()
        for contact in contacts:
            PatientContact.objects.create(patient=patient, **contact)

    def create(self, validated_data: dict[str, Any]) -> Patient:
        identifiers: list[dict[str, Any]] = validated_data.pop("identifiers", [])
        contacts: list[dict[str, Any]] = validated_data.pop("contacts", [])
        patient = Patient.objects.create(**validated_data)
        self._upsert_identifiers(patient, identifiers)
        self._upsert_contacts(patient, contacts)
        return patient

    def update(self, instance: Patient, validated_data: dict[str, Any]) -> Patient:
        identifiers: list[dict[str, Any]] = validated_data.pop("identifiers", [])
        contacts: list[dict[str, Any]] = validated_data.pop("contacts", [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if identifiers:
            self._upsert_identifiers(instance, identifiers)
        if contacts:
            self._upsert_contacts(instance, contacts)
        return instance


# ── FHIR serializer ───────────────────────────────────────────────────────────

class FHIRPatientSerializer(serializers.Serializer[Patient]):
    """
    Accepts a raw FHIR R4 Patient JSON document.
    On read, returns the full FHIR Patient resource.

    This serializer uses fhir.resources (Pydantic v2) for validation —
    a second validation layer on top of Django model validation.
    """

    # Accept any dict that represents a FHIR Patient resource
    def to_internal_value(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate FHIR document and convert to model-ready dict."""
        try:
            return fhir_to_patient_data(data)
        except Exception as exc:
            raise serializers.ValidationError(
                {"fhir": f"Invalid FHIR R4 Patient resource: {exc}"}
            ) from exc

    def to_representation(self, instance: Patient) -> dict[str, Any]:
        """Convert Django Patient to FHIR R4 Patient JSON."""
        fhir_patient = patient_to_fhir(instance)
        return fhir_patient.model_dump(exclude_none=True)

    def create(self, validated_data: dict[str, Any]) -> Patient:
        identifiers: list[dict[str, Any]] = validated_data.pop("identifiers", [])
        contacts: list[dict[str, Any]] = validated_data.pop("contacts", [])
        patient = Patient.objects.create(**validated_data)
        for ident in identifiers:
            PatientIdentifier.objects.get_or_create(
                patient=patient,
                system=ident["system"],
                value=ident["value"],
                defaults={"use": ident.get("use", "official")},
            )
        for contact in contacts:
            PatientContact.objects.create(patient=patient, **contact)
        return patient

    def update(self, instance: Patient, validated_data: dict[str, Any]) -> Patient:
        identifiers: list[dict[str, Any]] = validated_data.pop("identifiers", [])
        contacts: list[dict[str, Any]] = validated_data.pop("contacts", [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        for ident in identifiers:
            PatientIdentifier.objects.get_or_create(
                patient=instance,
                system=ident["system"],
                value=ident["value"],
                defaults={"use": ident.get("use", "official")},
            )
        if contacts:
            instance.contacts.all().delete()
            for contact in contacts:
                PatientContact.objects.create(patient=instance, **contact)
        return instance


# ── Soft-delete serializer ────────────────────────────────────────────────────

class PatientSoftDeleteSerializer(serializers.Serializer[Patient]):
    reason = serializers.CharField(
        required=True,
        min_length=10,
        help_text="Mandatory reason for deactivating this patient record.",
    )
