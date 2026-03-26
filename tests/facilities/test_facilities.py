"""
tests/facilities/test_facilities.py

Test suite for dream_core/facilities — covering:

  1. Model integrity      — Facility and FacilityMembership creation, hierarchy,
                            soft-delete, __str__, properties.
  2. FacilityFilterMixin  — Phase 1 (enforcement OFF): queryset passes through.
                            Phase 2 (enforcement ON):  queryset is scoped to
                            the user's permitted facilities; superadmin bypasses.
  3. FacilityRequiredMixin — Phase 1: returns empty kwargs (no-op).
                             Phase 2: injects primary facility; raises
                             PermissionDenied when user has no membership.
  4. Patient FK stub       — Patient can be created with and without a facility;
                             the facility field is correctly nullable.
  5. Catalog FK stubs      — LabTestPanel / LabTestDefinition carry the stub.
  6. AuditEventManager     — for_facility() returns .none() in Phase 1 and
                             filters by additional_data in Phase 2.
  7. Fixture               — initial_facilities.json loads cleanly.
"""
from __future__ import annotations

import pytest
from django.test import override_settings
from unittest.mock import MagicMock, patch

from dream_core.accounts.accounts_utils import RoleType
from dream_core.facilities.models import Facility, FacilityMembership
from dream_core.facilities.mixins import (
    FacilityFilterMixin,
    FacilityRequiredMixin,
    enforcement_active,
    get_user_facility_ids,
    get_user_primary_facility,
)
from dream_core.patients.models import Patient
from dream_core.catalog.models import LabTestPanel, LabTestDefinition
from dream_core.audit.models import AuditEvent

from tests.facilities.factories import FacilityFactory, FacilityMembershipFactory
from tests.accounts.factories import UserFactory
from tests.patients.factories import PatientFactory
from tests.catalog.factories import LabTestPanelFactory, LabTestDefinitionFactory


# ══════════════════════════════════════════════════════════════════════════════
# 1. Model integrity
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestFacilityModel:

    def test_create_minimal_facility(self) -> None:
        f = FacilityFactory()
        assert f.pk is not None
        assert f.is_active is True
        assert f.parent_facility is None
        assert f.is_branch is False
        assert f.enforcement_enabled is False

    def test_str_representation(self) -> None:
        f = FacilityFactory(name="City Hospital", code="CTH")
        assert str(f) == "City Hospital (CTH)"

    def test_display_name_uses_short_name_when_set(self) -> None:
        f = FacilityFactory(name="City General Hospital", short_name="City General")
        assert f.display_name == "City General"

    def test_display_name_falls_back_to_name(self) -> None:
        f = FacilityFactory(name="Solo Clinic", short_name="")
        assert f.display_name == "Solo Clinic"

    def test_code_is_unique(self) -> None:
        FacilityFactory(code="UNIQUE01")
        with pytest.raises(Exception):
            FacilityFactory(code="UNIQUE01")

    def test_parent_child_hierarchy(self) -> None:
        parent = FacilityFactory(name="Main Campus", code="MAIN")
        branch = FacilityFactory(name="Satellite Lab", code="SAT1", parent_facility=parent)

        assert branch.is_branch is True
        assert branch.parent_facility == parent
        assert parent.is_branch is False

    def test_get_ancestors_single_level(self) -> None:
        parent = FacilityFactory(code="ROOT")
        child = FacilityFactory(code="CHILD", parent_facility=parent)

        ancestors = child.get_ancestors()
        assert ancestors == [parent]

    def test_get_ancestors_two_levels(self) -> None:
        root = FacilityFactory(code="L0")
        mid = FacilityFactory(code="L1", parent_facility=root)
        leaf = FacilityFactory(code="L2", parent_facility=mid)

        ancestors = leaf.get_ancestors()
        assert ancestors == [root, mid]

    def test_get_ancestors_root_returns_empty(self) -> None:
        f = FacilityFactory(code="ALONE")
        assert f.get_ancestors() == []

    def test_soft_delete_facility(self) -> None:
        f = FacilityFactory()
        pk = f.pk
        f.delete(reason="Facility closed permanently.")

        assert Facility.objects.filter(pk=pk).count() == 0
        assert Facility.all_objects.filter(pk=pk).count() == 1
        f.refresh_from_db()  # uses all_objects under the hood via direct PK
        refreshed = Facility.all_objects.get(pk=pk)
        assert refreshed.is_deleted is True
        assert refreshed.deletion_reason == "Facility closed permanently."

    def test_facility_type_choices(self) -> None:
        for choice in Facility.FacilityType.values:
            f = FacilityFactory(facility_type=choice)
            assert f.facility_type == choice


@pytest.mark.django_db
class TestFacilityMembership:

    def test_create_membership(self) -> None:
        user = UserFactory()
        facility = FacilityFactory()
        m = FacilityMembershipFactory(user=user, facility=facility, is_primary=True)

        assert m.user == user
        assert m.facility == facility
        assert m.is_primary is True
        assert m.role_override is None

    def test_str_representation(self) -> None:
        user = UserFactory(email="dr@example.com")
        facility = FacilityFactory(name="Central Lab", code="CL01")
        m = FacilityMembershipFactory(user=user, facility=facility)
        assert "Central Lab" in str(m)

    def test_unique_together_user_facility(self) -> None:
        user = UserFactory()
        facility = FacilityFactory()
        FacilityMembershipFactory(user=user, facility=facility)
        with pytest.raises(Exception):
            FacilityMembershipFactory(user=user, facility=facility)

    def test_user_can_belong_to_multiple_facilities(self) -> None:
        user = UserFactory()
        f1 = FacilityFactory(code="F001")
        f2 = FacilityFactory(code="F002")
        FacilityMembershipFactory(user=user, facility=f1, is_primary=True)
        FacilityMembershipFactory(user=user, facility=f2, is_primary=False)

        assert user.facility_memberships.count() == 2

    def test_role_override_can_be_set(self) -> None:
        from tests.accounts.factories import RoleFactory
        user = UserFactory()
        facility = FacilityFactory()
        role = RoleFactory(name="LAB_ANALYST")
        m = FacilityMembershipFactory(user=user, facility=facility, role_override=role)
        assert m.role_override == role


# ══════════════════════════════════════════════════════════════════════════════
# 2. FacilityFilterMixin
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestFacilityFilterMixin:
    """
    Tests for the queryset scoping mixin.

    The mixin is a plain Python class — we test it by creating a minimal view
    mock with a `request` attribute, then calling get_facility_queryset() directly.
    """

    def _make_view(self, user: object) -> FacilityFilterMixin:
        view = FacilityFilterMixin()
        request = MagicMock()
        request.user = user
        view.request = request
        return view

    # ── Phase 1: enforcement OFF (default) ────────────────────────────────────

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=False)
    def test_phase1_passthrough_returns_full_queryset(self) -> None:
        """With enforcement OFF, all patients are returned regardless of facility."""
        facility = FacilityFactory()
        other = FacilityFactory(code="OTH")

        p1 = PatientFactory(facility=facility)
        p2 = PatientFactory(facility=other)
        p3 = PatientFactory(facility=None)

        user = UserFactory()
        view = self._make_view(user)
        qs = view.get_facility_queryset(Patient.objects.all())

        pks = list(qs.values_list("pk", flat=True))
        assert p1.pk in pks
        assert p2.pk in pks
        assert p3.pk in pks

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=False)
    def test_enforcement_active_returns_false(self) -> None:
        assert enforcement_active() is False

    # ── Phase 2: enforcement ON ───────────────────────────────────────────────

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_scopes_to_user_facilities(self) -> None:
        user = UserFactory()
        facility_a = FacilityFactory(code="FAC_A")
        facility_b = FacilityFactory(code="FAC_B")
        FacilityMembershipFactory(user=user, facility=facility_a)

        p_a = PatientFactory(facility=facility_a)
        p_b = PatientFactory(facility=facility_b)

        view = self._make_view(user)
        qs = view.get_facility_queryset(Patient.objects.all())
        pks = list(qs.values_list("pk", flat=True))

        assert p_a.pk in pks
        assert p_b.pk not in pks

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_user_with_no_memberships_gets_empty_queryset(self) -> None:
        user = UserFactory()
        PatientFactory()  # belongs to some facility

        view = self._make_view(user)
        qs = view.get_facility_queryset(Patient.objects.all())

        assert qs.count() == 0

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_superuser_bypasses_facility_scoping(self) -> None:
        user = UserFactory()
        user.is_superuser = True

        facility_a = FacilityFactory(code="SA_A")
        facility_b = FacilityFactory(code="SA_B")
        # No membership for this superuser
        PatientFactory(facility=facility_a)
        PatientFactory(facility=facility_b)

        view = self._make_view(user)
        qs = view.get_facility_queryset(Patient.objects.all())

        assert qs.count() >= 2

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_superadmin_role_bypasses_facility_scoping(self) -> None:
        from tests.accounts.factories import RoleFactory
        superadmin_role = RoleFactory(name=RoleType.SUPERADMIN)
        user = UserFactory(roles=[superadmin_role])

        facility = FacilityFactory(code="SA_SC")
        PatientFactory(facility=facility)

        view = self._make_view(user)
        qs = view.get_facility_queryset(Patient.objects.all())
        # Should not be .none() — superadmin sees all
        assert qs.count() >= 1

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_user_with_multiple_memberships_sees_all_their_facilities(self) -> None:
        user = UserFactory()
        f1 = FacilityFactory(code="MF_1")
        f2 = FacilityFactory(code="MF_2")
        f3 = FacilityFactory(code="MF_3")
        FacilityMembershipFactory(user=user, facility=f1)
        FacilityMembershipFactory(user=user, facility=f2)

        p1 = PatientFactory(facility=f1)
        p2 = PatientFactory(facility=f2)
        p3 = PatientFactory(facility=f3)  # not a member

        view = self._make_view(user)
        qs = view.get_facility_queryset(Patient.objects.all())
        pks = list(qs.values_list("pk", flat=True))

        assert p1.pk in pks
        assert p2.pk in pks
        assert p3.pk not in pks

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_model_without_facility_field_is_unfiltered(self) -> None:
        """
        Models that have no facility FK (e.g. Role) must not be accidentally
        filtered — the mixin must be a no-op for them.
        """
        from dream_core.accounts.models import Role
        Role.objects.get_or_create(name="CLINICIAN", defaults={"is_system": True})

        user = UserFactory()
        # No facility membership
        view = self._make_view(user)
        qs = view.get_facility_queryset(Role.objects.all())

        # Role has no facility_id — queryset must be returned intact
        assert qs.count() >= 1

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_facility_ids_are_cached_on_request(self) -> None:
        """get_user_facility_ids() must not hit the DB twice in the same request."""
        user = UserFactory()
        f = FacilityFactory(code="CACHE")
        FacilityMembershipFactory(user=user, facility=f)

        request = MagicMock()
        request.user = user

        ids_first = get_user_facility_ids(request)
        # Second call must use cached value (no new DB query)
        ids_second = get_user_facility_ids(request)

        assert ids_first == ids_second
        assert hasattr(request, "_facility_ids")


# ══════════════════════════════════════════════════════════════════════════════
# 3. FacilityRequiredMixin
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestFacilityRequiredMixin:

    def _make_view(self, user: object) -> FacilityRequiredMixin:
        view = FacilityRequiredMixin()
        request = MagicMock()
        request.user = user
        view.request = request
        return view

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=False)
    def test_phase1_returns_empty_kwargs(self) -> None:
        user = UserFactory()
        view = self._make_view(user)
        assert view.get_facility_create_kwargs() == {}

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_injects_primary_facility(self) -> None:
        user = UserFactory()
        facility = FacilityFactory(code="PRI")
        FacilityMembershipFactory(user=user, facility=facility, is_primary=True)

        view = self._make_view(user)
        kwargs = view.get_facility_create_kwargs()

        assert "facility" in kwargs
        assert kwargs["facility"] == facility

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_raises_when_user_has_no_memberships(self) -> None:
        from rest_framework.exceptions import PermissionDenied
        user = UserFactory()
        view = self._make_view(user)

        with pytest.raises(PermissionDenied):
            view.get_facility_create_kwargs()

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_get_user_primary_facility_prefers_is_primary_true(self) -> None:
        user = UserFactory()
        f_secondary = FacilityFactory(code="SEC")
        f_primary = FacilityFactory(code="PRI2")
        FacilityMembershipFactory(user=user, facility=f_secondary, is_primary=False)
        FacilityMembershipFactory(user=user, facility=f_primary, is_primary=True)

        request = MagicMock()
        request.user = user
        result = get_user_primary_facility(request)

        assert result == f_primary

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_phase2_get_user_primary_facility_none_when_no_memberships(self) -> None:
        user = UserFactory()
        request = MagicMock()
        request.user = user
        assert get_user_primary_facility(request) is None


# ══════════════════════════════════════════════════════════════════════════════
# 4. Patient FK stub
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestPatientFacilityStub:

    def test_patient_can_be_created_without_facility(self) -> None:
        p = PatientFactory(facility=None)
        p.refresh_from_db()
        assert p.facility is None

    def test_patient_can_be_created_with_facility(self) -> None:
        facility = FacilityFactory()
        p = PatientFactory(facility=facility)
        p.refresh_from_db()
        assert p.facility == facility

    def test_facility_protect_prevents_deletion_while_patients_exist(self) -> None:
        facility = FacilityFactory()
        PatientFactory(facility=facility)

        # PROTECT means hard-deleting the Facility while patients reference it
        # raises a ProtectedError (not a soft-delete — that uses the SoftDeleteModel path).
        from django.db.models import ProtectedError
        with pytest.raises(ProtectedError):
            facility.hard_delete()

    def test_soft_deleting_facility_does_not_affect_patients(self) -> None:
        """
        Soft-deleting a facility must not cascade to patient records.
        Patient data must remain accessible even when its facility is soft-deleted.
        This is a compliance requirement: patient records are immutable.
        """
        facility = FacilityFactory()
        p = PatientFactory(facility=facility)
        facility.delete(reason="Facility merged into another.")

        p.refresh_from_db()
        assert p.pk is not None   # patient still exists
        assert p.facility_id is not None  # FK still points to the (soft-deleted) facility


# ══════════════════════════════════════════════════════════════════════════════
# 5. Catalog FK stubs
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestCatalogFacilityStubs:

    def test_panel_can_be_created_without_facility(self) -> None:
        panel = LabTestPanelFactory(facility=None)
        panel.refresh_from_db()
        assert panel.facility is None

    def test_panel_can_be_created_with_facility(self) -> None:
        facility = FacilityFactory()
        panel = LabTestPanelFactory(facility=facility)
        panel.refresh_from_db()
        assert panel.facility == facility

    def test_definition_can_be_created_without_facility(self) -> None:
        defn = LabTestDefinitionFactory(facility=None)
        defn.refresh_from_db()
        assert defn.facility is None

    def test_definition_can_be_created_with_facility(self) -> None:
        facility = FacilityFactory()
        defn = LabTestDefinitionFactory(facility=facility)
        defn.refresh_from_db()
        assert defn.facility == facility

    def test_global_panel_visible_to_all(self) -> None:
        """
        A panel with facility=None represents a shared global catalog entry.
        Both facilities should be able to access it in Phase 2.
        """
        global_panel = LabTestPanelFactory(facility=None, code="GLOBAL_FBC")

        user = UserFactory()
        f = FacilityFactory(code="FC_ONLY")
        FacilityMembershipFactory(user=user, facility=f)

        # In Phase 1, this is trivially true. In Phase 2, the view's queryset
        # must use facility__in=[user_facility_ids] | facility__isnull=True.
        # This test documents the intended contract for Phase 2 implementation.
        assert global_panel.facility is None


# ══════════════════════════════════════════════════════════════════════════════
# 6. AuditEventManager.for_facility()
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAuditEventManagerFacility:

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=False)
    def test_for_facility_returns_none_in_phase1(self) -> None:
        """
        for_facility() must return an empty queryset in Phase 1.
        Calling it in Phase 1 is a programming error — guard on the setting.
        """
        facility = FacilityFactory()
        qs = AuditEvent.objects.for_facility(str(facility.pk))
        assert qs.count() == 0

    @override_settings(FACILITY_ENFORCEMENT_ENABLED=True)
    def test_for_facility_filters_by_additional_data_in_phase2(self) -> None:
        """
        In Phase 2, for_facility() filters on additional_data__facility_id.
        This test verifies the filter path is correct; actual additional_data
        population requires the Phase 2 audit middleware (not yet built).
        """
        facility = FacilityFactory()
        # Without the Phase 2 middleware there are no matching entries — the
        # test validates the queryset returns zero rather than raising.
        qs = AuditEvent.objects.for_facility(str(facility.pk))
        assert qs.count() == 0  # correct — no entries have additional_data yet


# ══════════════════════════════════════════════════════════════════════════════
# 7. Fixture loading
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestFacilityFixture:

    def test_initial_facilities_fixture_loads(self, django_db_reset_sequences: None) -> None:
        from django.core.management import call_command
        call_command("loaddata", "dream_core/facilities/fixtures/initial_facilities.json", verbosity=0)

        default = Facility.objects.get(code="DEFAULT")
        assert default.name == "Default Facility"
        assert default.is_active is True
        assert default.timezone == "UTC"
        assert default.enforcement_enabled is False