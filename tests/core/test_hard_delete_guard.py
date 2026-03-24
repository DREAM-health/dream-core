"""
tests/core/test_hard_delete_guard.py

Test suite for apps.core.hard_delete.HardDeleteGuard.

Coverage targets (all must be >= 90%):
  - HardDeleteGuard.hard_delete() happy path
  - All three failure branches in _validate_hard_delete_authorisation
  - Superuser bypass of permission check
  - CanHardDelete DRF permission class (has_permission + has_object_permission)
  - Audit log entry is written on successful hard delete
  - hard_delete() is NOT available on plain SoftDeleteModel (regression guard)
"""
import pytest
from unittest.mock import MagicMock, patch

from dream_core.accounts.models import User, Role
from dream_core.core.hard_delete import (
    CanHardDelete,
    HardDeleteGuard,
    HardDeleteNotAuthorised,
    MIN_TOKEN_LENGTH,
)
from dream_core.patients.models import Patient
from tests.accounts.factories import UserFactory
from tests.patients.factories import PatientFactory


pytestmark = pytest.mark.django_db


VALID_TOKEN = "LGPD art.18 erasure — ticket #DPO-2024-0042"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def authorised_user(db: None) -> User:
    """A user with the patients.hard_delete_patient permission."""
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    user = UserFactory()
    ct = ContentType.objects.get_for_model(Patient)
    perm, _ = Permission.objects.get_or_create(
        codename="hard_delete_patient",
        content_type=ct,
        defaults={"name": "Can hard delete Patient"},
    )
    user.user_permissions.add(perm)
    # Refresh to clear permission cache
    return User.objects.get(pk=user.pk)


@pytest.fixture
def unauthorised_user(db: None) -> User:
    """A regular user with no special permissions."""
    return UserFactory()


@pytest.fixture
def superuser(db: None) -> User:
    """A Django superuser."""
    return User.objects.create_superuser(
        email="superuser@test.local",
        password="Sup3rS3cur3!",
        first_name="Super",
        last_name="User",
    )


@pytest.fixture
def patient(db: None) -> Patient:
    return PatientFactory()


# ── hard_delete() — happy path ─────────────────────────────────────────────

class TestHardDeleteHappyPath:
    def test_authorised_user_can_hard_delete(
        self, patient: Patient, authorised_user: User
    ) -> None:
        pk = patient.pk
        patient.hard_delete(
            authorised_by=authorised_user,
            authorisation_token=VALID_TOKEN,
        )
        assert not Patient.all_objects.filter(pk=pk).exists()

    def test_superuser_can_hard_delete_without_explicit_permission(
        self, patient: Patient, superuser: User
    ) -> None:
        """Superusers bypass the permission check (consistent with Django convention)."""
        pk = patient.pk
        patient.hard_delete(
            authorised_by=superuser,
            authorisation_token=VALID_TOKEN,
        )
        assert not Patient.all_objects.filter(pk=pk).exists()

    def test_hard_delete_returns_standard_django_delete_tuple(
        self, patient: Patient, authorised_user: User
    ) -> None:
        result = patient.hard_delete(
            authorised_by=authorised_user,
            authorisation_token=VALID_TOKEN,
        )
        # Django delete() returns (count, {model_label: count})
        count, breakdown = result
        assert count >= 1

    def test_hard_delete_token_exactly_min_length_is_accepted(
        self, patient: Patient, authorised_user: User
    ) -> None:
        token = "x" * MIN_TOKEN_LENGTH
        patient.hard_delete(authorised_by=authorised_user, authorisation_token=token)
        assert not Patient.all_objects.filter(pk=patient.pk).exists()


# ── hard_delete() — failure branches ──────────────────────────────────────────

class TestHardDeleteFailures:
    def test_raises_when_no_user_provided(self, patient: Patient) -> None:
        with pytest.raises(HardDeleteNotAuthorised, match="authorised_by user"):
            patient.hard_delete(authorisation_token=VALID_TOKEN)

    def test_raises_when_user_is_none(self, patient: Patient) -> None:
        with pytest.raises(HardDeleteNotAuthorised, match="authorised_by user"):
            patient.hard_delete(authorised_by=None, authorisation_token=VALID_TOKEN)

    def test_raises_when_token_is_empty(
        self, patient: Patient, authorised_user: User
    ) -> None:
        with pytest.raises(HardDeleteNotAuthorised, match="authorisation_token"):
            patient.hard_delete(authorised_by=authorised_user, authorisation_token="")

    def test_raises_when_token_is_too_short(
        self, patient: Patient, authorised_user: User
    ) -> None:
        short_token = "x" * (MIN_TOKEN_LENGTH - 1)
        with pytest.raises(HardDeleteNotAuthorised, match="authorisation_token"):
            patient.hard_delete(
                authorised_by=authorised_user, authorisation_token=short_token
            )

    def test_raises_when_token_is_only_whitespace(
        self, patient: Patient, authorised_user: User
    ) -> None:
        # A string of spaces that is long enough in raw length but empty after strip.
        whitespace_token = " " * MIN_TOKEN_LENGTH
        with pytest.raises(HardDeleteNotAuthorised, match="authorisation_token"):
            patient.hard_delete(
                authorised_by=authorised_user, authorisation_token=whitespace_token
            )

    def test_raises_when_user_lacks_permission(
        self, patient: Patient, unauthorised_user: User
    ) -> None:
        with pytest.raises(HardDeleteNotAuthorised, match="does not have permission"):
            patient.hard_delete(
                authorised_by=unauthorised_user,
                authorisation_token=VALID_TOKEN,
            )

    def test_raises_when_user_is_unauthenticated_mock(self, patient: Patient) -> None:
        """Covers the is_authenticated=False branch."""
        fake_user = MagicMock()
        fake_user.is_authenticated = False
        fake_user.is_superuser = False
        with pytest.raises(HardDeleteNotAuthorised, match="does not have permission"):
            patient.hard_delete(
                authorised_by=fake_user,
                authorisation_token=VALID_TOKEN,
            )

    def test_record_is_not_deleted_after_failed_attempt(
        self, patient: Patient, unauthorised_user: User
    ) -> None:
        pk = patient.pk
        with pytest.raises(HardDeleteNotAuthorised):
            patient.hard_delete(
                authorised_by=unauthorised_user,
                authorisation_token=VALID_TOKEN,
            )
        # Record must still exist
        assert Patient.all_objects.filter(pk=pk).exists()


# ── Audit log ─────────────────────────────────────────────────────────────────

class TestHardDeleteAuditLog:
    def test_python_logger_is_called_on_success(
        self, patient: Patient, authorised_user: User
    ) -> None:
        with patch("dream_core.core.hard_delete.logger") as mock_logger:
            patient.hard_delete(
                authorised_by=authorised_user,
                authorisation_token=VALID_TOKEN,
            )
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        # First positional arg is the format string
        assert "HARD_DELETE" in call_args[0][0]

    def test_logger_includes_token_in_extra(
        self, patient: Patient, authorised_user: User
    ) -> None:
        with patch("dream_core.core.hard_delete.logger") as mock_logger:
            patient.hard_delete(
                authorised_by=authorised_user,
                authorisation_token=VALID_TOKEN,
            )
        extra = mock_logger.warning.call_args[1].get("extra", {})
        assert extra.get("authorisation_token") == VALID_TOKEN

    def test_auditlog_entry_created_on_success(
        self, patient: Patient, authorised_user: User
    ) -> None:
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        pk_str = str(patient.pk)
        ct = ContentType.objects.get_for_model(Patient)

        patient.hard_delete(
            authorised_by=authorised_user,
            authorisation_token=VALID_TOKEN,
        )

        # The log entry should exist even after the record is gone
        entry = LogEntry.objects.filter(
            content_type=ct,
            object_pk=pk_str,
            action=LogEntry.Action.DELETE,
        ).order_by("-timestamp").first()

        assert entry is not None
        assert entry.additional_data is not None
        assert entry.additional_data.get("hard_delete") is True
        assert entry.additional_data.get("authorisation_token") == VALID_TOKEN

    def test_logger_is_not_called_when_authorisation_fails(
        self, patient: Patient, unauthorised_user: User
    ) -> None:
        with patch("dream_core.core.hard_delete.logger") as mock_logger:
            with pytest.raises(HardDeleteNotAuthorised):
                patient.hard_delete(
                    authorised_by=unauthorised_user,
                    authorisation_token=VALID_TOKEN,
                )
        mock_logger.warning.assert_not_called()


# ── CanHardDelete DRF permission ──────────────────────────────────────────────

class TestCanHardDeletePermission:
    """
    Unit tests for the CanHardDelete DRF permission class.
    Uses mock Request and View objects to avoid HTTP overhead.
    """

    def _make_request(self, user: User) -> MagicMock:
        request = MagicMock()
        request.user = user
        return request

    def _make_view(self, model_class: type) -> MagicMock:
        view = MagicMock()
        view.queryset = model_class.all_objects.all()
        return view

    def test_authorised_user_passes(
        self, authorised_user: User
    ) -> None:
        perm = CanHardDelete()
        request = self._make_request(authorised_user)
        view = self._make_view(Patient)
        assert perm.has_permission(request, view) is True

    def test_superuser_passes(self, superuser: User) -> None:
        perm = CanHardDelete()
        request = self._make_request(superuser)
        view = self._make_view(Patient)
        assert perm.has_permission(request, view) is True

    def test_unauthorised_user_fails(self, unauthorised_user: User) -> None:
        perm = CanHardDelete()
        request = self._make_request(unauthorised_user)
        view = self._make_view(Patient)
        assert perm.has_permission(request, view) is False

    def test_unauthenticated_request_fails(self) -> None:
        perm = CanHardDelete()
        request = MagicMock()
        request.user = MagicMock()
        request.user.is_authenticated = False
        view = self._make_view(Patient)
        assert perm.has_permission(request, view) is False

    def test_view_with_no_queryset_fails_gracefully(
        self, authorised_user: User
    ) -> None:
        """If the view has no queryset, deny rather than raise."""
        perm = CanHardDelete()
        request = self._make_request(authorised_user)
        view = MagicMock(spec=[])  # no queryset or get_queryset attribute
        assert perm.has_permission(request, view) is False

    def test_has_object_permission_delegates_to_has_permission(
        self, authorised_user: User
    ) -> None:
        perm = CanHardDelete()
        request = self._make_request(authorised_user)
        view = self._make_view(Patient)
        patient = PatientFactory()
        assert perm.has_object_permission(request, view, patient) is True


# ── Regression: plain SoftDeleteModel has no hard_delete ─────────────────────

class TestNoHardDeleteOnPlainSoftDeleteModel:
    """
    Ensure that a model using SoftDeleteModel (without HardDeleteGuard)
    does not have a hard_delete() method at all.

    This is a regression test.  The old SoftDeleteModel had a bare
    hard_delete() with no guard.  After the refactor, hard_delete() only
    exists when HardDeleteGuard is in the MRO.
    """

    def test_soft_delete_model_has_no_hard_delete(self) -> None:
        from dream_core.core.models import SoftDeleteModel
        assert not hasattr(SoftDeleteModel, "hard_delete"), (
            "SoftDeleteModel must NOT define hard_delete(). "
            "Use HardDeleteGuard mixin to opt in."
        )

    def test_patient_has_hard_delete_because_of_guard(self) -> None:
        assert hasattr(Patient, "hard_delete"), (
            "Patient should have hard_delete() via HardDeleteGuard mixin."
        )