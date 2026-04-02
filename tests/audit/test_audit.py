"""
tests/audit/test_audit.py

Tests for the Audit Log API:
  - Only auditors/admins can read the audit log
  - Filtering by actor, action, model, date
  - Object history endpoint
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from dream_core.testing.factories.patients import PatientFactory


pytestmark = pytest.mark.django_db

AUDIT_URL = "/api/core/v1/audit/logs/"


class TestAuditLogAccess:
    def test_auditor_can_read_audit_log(self, auditor_client: APIClient) -> None:
        resp = auditor_client.get(AUDIT_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_admin_can_read_audit_log(self, admin_client: APIClient) -> None:
        resp = admin_client.get(AUDIT_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_superadmin_can_read_audit_log(self, superadmin_client: APIClient) -> None:
        resp = superadmin_client.get(AUDIT_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_lab_analyst_cannot_read_audit_log(
        self, lab_analyst_client: APIClient
    ) -> None:
        resp = lab_analyst_client.get(AUDIT_URL)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_clinician_cannot_read_audit_log(
        self, clinician_client: APIClient
    ) -> None:
        resp = clinician_client.get(AUDIT_URL)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_read_audit_log(
        self, anon_client: APIClient
    ) -> None:
        resp = anon_client.get(AUDIT_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestAuditLogFiltering:
    def test_filter_by_model(self, auditor_client: APIClient) -> None:
        resp = auditor_client.get(AUDIT_URL, {"model": "patient"})
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        for entry in data["results"]:
            assert "patient" in entry["content_type"].lower()

    def test_filter_by_action(self, auditor_client: APIClient) -> None:
        resp = auditor_client.get(AUDIT_URL, {"action": 0})  # 0 = CREATE
        assert resp.status_code == status.HTTP_200_OK
        for entry in resp.json()["results"]:
            assert entry["action"] == 0

    def test_filter_by_app_label(self, auditor_client: APIClient) -> None:
        resp = auditor_client.get(AUDIT_URL, {"app_label": "patients"})
        assert resp.status_code == status.HTTP_200_OK
        for entry in resp.json()["results"]:
            assert entry["content_type"].startswith("patients.")

    def test_audit_log_is_paginated(self, auditor_client: APIClient) -> None:
        resp = auditor_client.get(AUDIT_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert "count" in resp.json()
        assert "results" in resp.json()


class TestObjectAuditHistory:
    def test_object_history_url_with_invalid_model_returns_404(
        self, auditor_client: APIClient
    ) -> None:
        import uuid
        resp = auditor_client.get(
            f"/api/core/v1/audit/logs/object/nonexistent/model/{uuid.uuid4()}/"
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_object_history_returns_list(
        self, auditor_client: APIClient
    ) -> None:
        patient = PatientFactory()
        resp = auditor_client.get(
            f"/api/core/v1/audit/logs/object/patients/patient/{patient.id}/"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert isinstance(resp.json(), list)


class TestAuditLogEntryDetail:
    def test_retrieve_nonexistent_entry_returns_404(
        self, auditor_client: APIClient
    ) -> None:
        resp = auditor_client.get(f"{AUDIT_URL}999999999/")
        assert resp.status_code == status.HTTP_404_NOT_FOUND
