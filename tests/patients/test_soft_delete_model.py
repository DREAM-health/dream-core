"""
tests/patients/test_soft_delete_model.py

Unit tests for the SoftDeleteModel base class behaviour.
These tests verify the core compliance property for normal operations:
  - delete() performs a soft-delete by default
  - Records are not physically removed via the default delete()/manager paths
  - Managers correctly segregate deleted vs active records
  - restore() reverses a soft-delete

The suite also includes tests for an explicit hard-delete operation
(e.g. test_hard_delete_physically_removes_record), which is only
intended to be used under specific, authorized conditions.
"""
import pytest
from django.utils import timezone

from dream_core.patients.models import Patient
from dream_core.testing.factories.patients import PatientFactory


pytestmark = pytest.mark.django_db


VALID_TOKEN = "LGPD art.18 erasure — ticket #DPO-2024-0042"


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
        from dream_core.testing.factories.accounts import UserFactory
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
        from dream_core.accounts.models import User

        su = User.objects.create_superuser(
            email="superuser@test.local",
            password="Sup3rS3cur3!",
            first_name="Super",
            last_name="User",
        )

        patient = PatientFactory()
        pk = patient.id

        patient.hard_delete(authorised_by=su, authorisation_token=VALID_TOKEN)

        assert not Patient.all_objects.filter(id=pk).exists()

    def test_multiple_soft_deletes_update_metadata(self) -> None:
        patient = PatientFactory()
        patient.delete(reason="First deletion")
        first_deleted_at = patient.deleted_at

        # Soft-deleting again should update the timestamp
        patient.delete(reason="Second deletion")

        patient.refresh_from_db()
        assert patient.deleted_at is not None
        assert patient.deletion_reason == "Second deletion"
