"""
tests/patients/test_patient_crud.py

Tests for the Patient Registry:
  - List, Create, Retrieve, Update, Soft-delete, Restore
  - FHIR R4 create and retrieve
  - RBAC enforcement on every endpoint
  - Soft-delete requires a reason
  - Hard-deleted records are never physically removed
"""
import datetime

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from dream_core.patients.models import Patient, PatientIdentifier
from tests.patients.factories import (
    PatientContactFactory,
    PatientFactory,
    PatientIdentifierFactory,
)


pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/patients/"


def detail_url(patient_id: object) -> str:
    return f"/api/v1/patients/{patient_id}/"


def fhir_detail_url(patient_id: object) -> str:
    return f"/api/v1/patients/{patient_id}/fhir/"


# ── List ──────────────────────────────────────────────────────────────────────

class TestPatientList:
    def test_authenticated_clinical_user_can_list(self, clinician_client: APIClient) -> None:
        PatientFactory.create_batch(3)
        resp = clinician_client.get(LIST_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["count"] >= 3

    def test_lab_analyst_can_list(self, lab_analyst_client: APIClient) -> None:
        resp = lab_analyst_client.get(LIST_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_unauthenticated_cannot_list(self, anon_client: APIClient) -> None:
        resp = anon_client.get(LIST_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_soft_deleted_patients_not_in_list(self, clinician_client: APIClient) -> None:
        active = PatientFactory()
        deleted = PatientFactory()
        deleted.delete(reason="Test deletion")

        resp = clinician_client.get(LIST_URL)
        ids = [p["id"] for p in resp.json()["results"]]

        assert str(active.id) in ids
        assert str(deleted.id) not in ids

    def test_search_by_family_name(self, clinician_client: APIClient) -> None:
        patient = PatientFactory(family_name="Zzuniquename")
        PatientFactory.create_batch(5)

        resp = clinician_client.get(LIST_URL, {"search": "Zzuniquename"})
        assert resp.status_code == status.HTTP_200_OK
        ids = [p["id"] for p in resp.json()["results"]]
        assert str(patient.id) in ids

    def test_search_by_identifier_value(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        PatientIdentifierFactory(patient=patient, value="99999999999")

        resp = clinician_client.get(LIST_URL, {"search": "99999999999"})
        ids = [p["id"] for p in resp.json()["results"]]
        assert str(patient.id) in ids

    def test_filter_by_gender(self, clinician_client: APIClient) -> None:
        PatientFactory(gender="male")
        PatientFactory(gender="female")

        resp = clinician_client.get(LIST_URL, {"gender": "male"})
        results = resp.json()["results"]
        assert all(p["gender"] == "male" for p in results)


# ── Create ────────────────────────────────────────────────────────────────────

class TestPatientCreate:
    def _payload(self, **overrides: object) -> dict:
        return {
            "family_name": "Silva",
            "given_names": "João Carlos",
            "birth_date": "1985-06-15",
            "gender": "male",
            "email": "joao@test.com",
            **overrides,
        }

    def test_clinician_can_create_patient(self, clinician_client: APIClient) -> None:
        resp = clinician_client.post(LIST_URL, self._payload(), format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data["family_name"] == "Silva"
        assert data["given_names"] == "João Carlos"

    def test_receptionist_can_create_patient(self, db: None, roles: dict) -> None:
        from tests.conftest import _authed_client
        from tests.accounts.factories import UserFactory
        user = UserFactory()
        user.roles.add(roles["RECEPTIONIST"])
        client = _authed_client(user)
        resp = client.post(LIST_URL, self._payload(email="rec@test.com"), format="json")
        assert resp.status_code == status.HTTP_201_CREATED

    def test_lab_analyst_cannot_create_patient(self, lab_analyst_client: APIClient) -> None:
        resp = lab_analyst_client.post(LIST_URL, self._payload(), format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_create_with_identifiers(self, clinician_client: APIClient) -> None:
        payload = self._payload(
            email="id@test.com",
            identifiers=[
                {"use": "official", "system": "https://dream-core.local/cpf", "value": "12345678901"},
            ],
        )
        resp = clinician_client.post(LIST_URL, payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED

        patient_id = resp.json()["id"]
        assert PatientIdentifier.objects.filter(
            patient_id=patient_id, value="12345678901"
        ).exists()

    def test_create_with_contacts(self, clinician_client: APIClient) -> None:
        payload = self._payload(
            email="contacts@test.com",
            contacts=[
                {"system": "phone", "value": "+5511999990000", "use": "mobile", "rank": 1},
            ],
        )
        resp = clinician_client.post(LIST_URL, payload, format="json")
        assert resp.status_code == status.HTTP_201_CREATED

    def test_create_missing_required_fields(self, clinician_client: APIClient) -> None:
        resp = clinician_client.post(LIST_URL, {"email": "incomplete@test.com"}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_patient_gets_uuid_id(self, clinician_client: APIClient) -> None:
        resp = clinician_client.post(LIST_URL, self._payload(email="uuid@test.com"), format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        import uuid
        uuid.UUID(resp.json()["id"])  # raises ValueError if not valid UUID


# ── Retrieve ──────────────────────────────────────────────────────────────────

class TestPatientRetrieve:
    def test_clinician_can_retrieve_patient(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        resp = clinician_client.get(detail_url(patient.id))
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["id"] == str(patient.id)

    def test_retrieve_includes_identifiers_and_contacts(
        self, clinician_client: APIClient
    ) -> None:
        patient = PatientFactory()
        PatientIdentifierFactory(patient=patient, value="55566677788")
        PatientContactFactory(patient=patient)

        resp = clinician_client.get(detail_url(patient.id))
        data = resp.json()
        assert len(data["identifiers"]) >= 1
        assert len(data["contacts"]) >= 1

    def test_retrieve_nonexistent_returns_404(self, clinician_client: APIClient) -> None:
        import uuid
        resp = clinician_client.get(detail_url(uuid.uuid4()))
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_soft_deleted_patient_not_visible_via_standard_endpoint(
        self, clinician_client: APIClient
    ) -> None:
        patient = PatientFactory()
        patient.delete(reason="Test deletion")
        resp = clinician_client.get(detail_url(patient.id))
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ── Update ────────────────────────────────────────────────────────────────────

class TestPatientUpdate:
    def test_patch_updates_field(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        resp = clinician_client.patch(
            detail_url(patient.id),
            {"family_name": "UpdatedName"},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK
        patient.refresh_from_db()
        assert patient.family_name == "UpdatedName"

    def test_put_full_update(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        payload = {
            "family_name": "Pereira",
            "given_names": "Maria",
            "birth_date": "1990-01-01",
            "gender": "female",
            "email": "maria@test.com",
        }
        resp = clinician_client.put(detail_url(patient.id), payload, format="json")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["family_name"] == "Pereira"

    def test_lab_analyst_cannot_update_patient(self, lab_analyst_client: APIClient) -> None:
        patient = PatientFactory()
        resp = lab_analyst_client.patch(
            detail_url(patient.id), {"family_name": "X"}, format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_update_tracks_updated_at(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        original_updated = patient.updated_at

        clinician_client.patch(
            detail_url(patient.id), {"notes": "Updated note"}, format="json"
        )

        patient.refresh_from_db()
        assert patient.updated_at >= original_updated


# ── Soft-delete ───────────────────────────────────────────────────────────────

class TestPatientSoftDelete:
    def test_delete_requires_reason(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        resp = clinician_client.delete(detail_url(patient.id), {}, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_delete_with_short_reason_rejected(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        resp = clinician_client.delete(
            detail_url(patient.id), {"reason": "short"}, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_soft_delete_with_valid_reason(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        resp = clinician_client.delete(
            detail_url(patient.id),
            {"reason": "Patient requested record deactivation."},
            format="json",
        )
        assert resp.status_code == status.HTTP_200_OK

        # Record still exists in DB
        assert Patient.all_objects.filter(id=patient.id).exists()
        # But not via normal manager
        assert not Patient.objects.filter(id=patient.id).exists()

        patient.refresh_from_db()
        assert patient.deleted_at is not None
        assert patient.deletion_reason == "Patient requested record deactivation."

    def test_delete_sets_deletion_timestamp(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        clinician_client.delete(
            detail_url(patient.id),
            {"reason": "Compliance test deletion reason"},
            format="json",
        )
        patient.refresh_from_db()
        assert patient.deleted_at is not None

    def test_lab_analyst_cannot_delete_patient(self, lab_analyst_client: APIClient) -> None:
        patient = PatientFactory()
        resp = lab_analyst_client.delete(
            detail_url(patient.id),
            {"reason": "Analyst should not be able to do this"},
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ── Restore ───────────────────────────────────────────────────────────────────

class TestPatientRestore:
    def test_admin_can_restore_deleted_patient(
        self, admin_client: APIClient
    ) -> None:
        patient = PatientFactory()
        patient.delete(reason="Deleted for restore test")

        resp = admin_client.post(f"/api/v1/patients/{patient.id}/restore/")
        assert resp.status_code == status.HTTP_200_OK

        patient.refresh_from_db()
        assert patient.deleted_at is None
        # Should now be visible via normal manager
        assert Patient.objects.filter(id=patient.id).exists()

    def test_restore_nonexistent_returns_404(self, admin_client: APIClient) -> None:
        import uuid
        resp = admin_client.post(f"/api/v1/patients/{uuid.uuid4()}/restore/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_restore_active_patient_returns_404(self, admin_client: APIClient) -> None:
        # Restoring a non-deleted patient should 404 (only finds deleted ones)
        patient = PatientFactory()
        resp = admin_client.post(f"/api/v1/patients/{patient.id}/restore/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_clinician_cannot_restore_patient(self, clinician_client: APIClient) -> None:
        patient = PatientFactory()
        patient.delete(reason="Deleted for test")
        resp = clinician_client.post(f"/api/v1/patients/{patient.id}/restore/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_deleted_list_visible_to_admin(self, admin_client: APIClient) -> None:
        patient = PatientFactory()
        patient.delete(reason="Test deletion for listing")
        resp = admin_client.get("/api/v1/patients/deleted/")
        assert resp.status_code == status.HTTP_200_OK
        ids = [p["id"] for p in resp.json()]
        assert str(patient.id) in ids

    def test_deleted_list_hidden_from_clinician(self, clinician_client: APIClient) -> None:
        resp = clinician_client.get("/api/v1/patients/deleted/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ── FHIR R4 ───────────────────────────────────────────────────────────────────

class TestFHIRPatient:
    FHIR_CREATE_URL = "/api/v1/patients/fhir/"

    def _fhir_payload(self, **overrides: object) -> dict:
        base: dict = {
            "resourceType": "Patient",
            "active": True,
            "name": [
                {
                    "use": "official",
                    "family": "Ferreira",
                    "given": ["Carlos", "Eduardo"],
                }
            ],
            "gender": "male",
            "birthDate": "1978-03-22",
            "identifier": [
                {
                    "use": "official",
                    "system": "https://dream-core.local/cpf",
                    "value": "98765432100",
                }
            ],
            "telecom": [
                {"system": "phone", "value": "+5511988880000", "use": "mobile", "rank": 1}
            ],
        }
        base.update(overrides)
        return base

    def test_create_from_fhir_resource(self, clinician_client: APIClient) -> None:
        resp = clinician_client.post(
            self.FHIR_CREATE_URL, self._fhir_payload(), format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        # Response should be a FHIR Patient resource
        assert data["resourceType"] == "Patient"
        assert data["name"][0]["family"] == "Ferreira"
        assert data["gender"] == "male"

    def test_fhir_create_validates_resource_type(
        self, clinician_client: APIClient
    ) -> None:
        invalid = {"resourceType": "Observation", "status": "final"}
        resp = clinician_client.post(self.FHIR_CREATE_URL, invalid, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_fhir_create_stores_identifiers(self, clinician_client: APIClient) -> None:
        resp = clinician_client.post(
            self.FHIR_CREATE_URL, self._fhir_payload(), format="json"
        )
        assert resp.status_code == status.HTTP_201_CREATED
        patient_id = resp.json()["id"]
        assert PatientIdentifier.objects.filter(
            patient_id=patient_id, value="98765432100"
        ).exists()

    def test_retrieve_patient_as_fhir(self, clinician_client: APIClient) -> None:
        patient = PatientFactory(family_name="Gomes", given_names="Ana Paula")
        resp = clinician_client.get(fhir_detail_url(patient.id))
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["resourceType"] == "Patient"
        assert data["name"][0]["family"] == "Gomes"
        assert "Ana" in data["name"][0]["given"]

    def test_fhir_response_includes_dream_core_identifier(
        self, clinician_client: APIClient
    ) -> None:
        patient = PatientFactory()
        resp = clinician_client.get(fhir_detail_url(patient.id))
        identifiers = resp.json()["identifier"]
        systems = [i["system"] for i in identifiers]
        assert "https://dream-core.local/patient-id" in systems

    def test_update_patient_via_fhir_put(self, clinician_client: APIClient) -> None:
        patient = PatientFactory(family_name="OldName")
        payload = self._fhir_payload()
        payload["name"][0]["family"] = "UpdatedFHIR"

        resp = clinician_client.put(fhir_detail_url(patient.id), payload, format="json")
        assert resp.status_code == status.HTTP_200_OK

        patient.refresh_from_db()
        assert patient.family_name == "UpdatedFHIR"

    def test_fhir_create_invalid_birth_date(
        self, clinician_client: APIClient
    ) -> None:
        payload = self._fhir_payload()
        payload["birthDate"] = "not-a-date"
        resp = clinician_client.post(self.FHIR_CREATE_URL, payload, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_lab_analyst_can_read_fhir(
        self, lab_analyst_client: APIClient
    ) -> None:
        patient = PatientFactory()
        resp = lab_analyst_client.get(fhir_detail_url(patient.id))
        assert resp.status_code == status.HTTP_200_OK

    def test_lab_analyst_cannot_create_fhir(
        self, lab_analyst_client: APIClient
    ) -> None:
        resp = lab_analyst_client.post(
            self.FHIR_CREATE_URL, self._fhir_payload(), format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
