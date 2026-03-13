"""
tests/patients/test_soft_delete_model.py

Unit tests for the SoftDeleteModel base class behaviour.
These tests verify the core compliance property:
  - delete() is always a soft-delete
  - Records are never physically removed
  - Managers correctly segregate deleted vs active records
  - restore() reverses a soft-delete
"""
import pytest
from django.utils import timezone

from apps.patients.models import Patient
from tests.patients.factories import PatientFactory


pytestmark = pytest.mark.django_db


class TestSoftDeleteModel:
    def test_delete_sets_deleted_at(self) -> None:
        patient = PatientFactory()
        assert patient.deleted_at is None

        patient.delete(reason="Unit test deletion")

        patient.refresh_from_db()
        assert patient.deleted_at is not None

    def test_delete_records_reason(self) -> None:
        patient = PatientFactory()
        reason = "Data correction — duplicate entry removed"
        patient.delete(reason=reason)

        patient.refresh_from_db()
        assert patient.deletion_reason == reason

    def test_delete_does_not_physically_remove_record(self) -> None:
        patient = PatientFactory()
        pk = patient.id

        patient.delete(reason="Must not physically delete")

        # Record still exists via all_objects manager
        assert Patient.all_objects.filter(id=pk).exists()
        # But not via the default manager
        assert not Patient.objects.filter(id=pk).exists()

    def test_is_deleted_property(self) -> None:
        patient = PatientFactory()
        assert patient.is_deleted is False

        patient.delete(reason="Property test")

        patient.refresh_from_db()
        assert patient.is_deleted is True

    def test_default_manager_excludes_deleted(self) -> None:
        active = PatientFactory()
        deleted = PatientFactory()
        deleted.delete(reason="Should be excluded")

        active_ids = list(Patient.objects.values_list("id", flat=True))
        assert active.id in active_ids
        assert deleted.id not in active_ids

    def test_all_objects_manager_includes_deleted(self) -> None:
        active = PatientFactory()
        deleted = PatientFactory()
        deleted.delete(reason="Should be included in all_objects")

        all_ids = list(Patient.all_objects.values_list("id", flat=True))
        assert active.id in all_ids
        assert deleted.id in all_ids

    def test_restore_clears_deleted_at(self) -> None:
        patient = PatientFactory()
        patient.delete(reason="Will be restored")
        assert patient.is_deleted

        patient.restore()

        patient.refresh_from_db()
        assert patient.deleted_at is None
        assert patient.deletion_reason == ""
        assert patient.is_deleted is False

    def test_restore_makes_record_visible_in_default_manager(self) -> None:
        patient = PatientFactory()
        patient.delete(reason="Temp deletion")
        assert not Patient.objects.filter(id=patient.id).exists()

        patient.restore()

        assert Patient.objects.filter(id=patient.id).exists()

    def test_delete_sets_deleted_by_when_provided(self) -> None:
        from tests.accounts.factories import UserFactory
        user = UserFactory()
        patient = PatientFactory()

        patient.delete(deleted_by=user, reason="Deleted by specific user")

        patient.refresh_from_db()
        assert patient.deleted_by_id == user.id

    def test_hard_delete_physically_removes_record(self) -> None:
        """
        hard_delete() is available but should be used sparingly.
        Verify it works as expected for the rare cases where it's needed.
        """
        patient = PatientFactory()
        pk = patient.id

        patient.hard_delete()

        assert not Patient.all_objects.filter(id=pk).exists()

    def test_multiple_soft_deletes_are_idempotent(self) -> None:
        patient = PatientFactory()
        patient.delete(reason="First deletion")
        first_deleted_at = patient.deleted_at

        # Soft-deleting again should update the timestamp
        patient.delete(reason="Second deletion")

        patient.refresh_from_db()
        assert patient.deleted_at is not None
        assert patient.deletion_reason == "Second deletion"
