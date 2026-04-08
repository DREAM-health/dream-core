"""
tests/facilities/test_facility_api.py

Tests for the Facility REST API:
  - CRUD with RBAC (SUPERADMIN creates, ADMIN reads/updates own, etc.)
  - Membership management
  - Cross-facility grant/revoke
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from dream_core.facilities.models import FacilityMembership
from dream_core.testing.factories.facilities import FacilityFactory, FacilityMembershipFactory
from dream_core.testing.factories.accounts import UserFactory
from dream_core.testing.factories.patients import PatientFactory

from django.test import override_settings

pytestmark = pytest.mark.django_db

FACILITIES_URL = "/api/core/v1/facilities/"
LIST_URL = "/api/core/v1/patients/"


def facility_url(pk: object) -> str:
    return f"/api/core/v1/facilities/{pk}/"


def members_url(facility_pk: object) -> str:
    return f"/api/core/v1/facilities/{facility_pk}/members/"


def member_url(facility_pk: object, pk: object) -> str:
    return f"/api/core/v1/facilities/{facility_pk}/members/{pk}/"


def grant_url(facility_pk: object) -> str:
    return f"/api/core/v1/facilities/{facility_pk}/access/grant/"


def revoke_url(facility_pk: object) -> str:
    return f"/api/core/v1/facilities/{facility_pk}/access/revoke/"


# ── Facility CRUD ─────────────────────────────────────────────────────────────

class TestFacilityCRUD:
    def test_superadmin_can_create_facility(self, superadmin_client: APIClient) -> None:
        resp = superadmin_client.post(FACILITIES_URL, {
            "name": "New Clinic", "short_name": "NC", "code": "NC01",
            "facility_type": "center", "timezone": "UTC",
        }, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.json()["code"] == "NC01"

    def test_admin_cannot_create_facility(self, admin_client: APIClient) -> None:
        resp = admin_client.post(FACILITIES_URL, {
            "name": "X", "code": "X01", "facility_type": "center",
        }, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_superadmin_can_list_all_facilities(self, superadmin_client: APIClient) -> None:
        FacilityFactory.create_batch(3)
        resp = superadmin_client.get(FACILITIES_URL)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["count"] >= 3

    def test_admin_sees_only_own_facilities(
        self, admin_client: APIClient, admin_user: object
    ) -> None:
        from guardian.shortcuts import assign_perm

        own = FacilityFactory(code="OWN01")
        FacilityMembershipFactory(user=admin_user, facility=own) # via membership

        other = FacilityFactory(code="OTH01")
        assign_perm("access_facility", admin_user, other) # via guardian grant

        FacilityFactory(code="ANOTH01") # no access

        resp = admin_client.get(FACILITIES_URL)
        codes = [f["code"] for f in resp.json()["results"]]
        assert "DFT01" in codes # default facility, used on admin_user fixture, should always be visible
        assert "OWN01" in codes
        assert "OTH01" in codes
        assert "ANOTH01" not in codes

    def test_superadmin_can_soft_delete_facility(self, superadmin_client: APIClient) -> None:
        f = FacilityFactory()
        resp = superadmin_client.delete(
            facility_url(f.id), {"reason": "Facility permanently closed."}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        f.refresh_from_db()
        assert f.is_deleted is True

    def test_admin_cannot_delete_facility(
        self, admin_client: APIClient, admin_user: object
    ) -> None:
        f = FacilityFactory()
        FacilityMembershipFactory(user=admin_user, facility=f)
        resp = admin_client.delete(facility_url(f.id), format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_code_rejected(self, superadmin_client: APIClient) -> None:
        FacilityFactory(code="DUPE")
        resp = superadmin_client.post(FACILITIES_URL, {
            "name": "Dup", "code": "DUPE", "facility_type": "center",
        }, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_cannot_access(self, anon_client: APIClient) -> None:
        resp = anon_client.get(FACILITIES_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ── Membership management ─────────────────────────────────────────────────────

class TestFacilityMembership:
    def test_superadmin_can_add_member(
        self, superadmin_client: APIClient
    ) -> None:
        facility = FacilityFactory()
        user = UserFactory()
        resp = superadmin_client.post(members_url(facility.id), {
            "user": str(user.id), "is_primary": True,
        }, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert FacilityMembership.objects.filter(user=user, facility=facility).exists()

    def test_own_facility_admin_can_add_member(
        self, admin_client: APIClient, admin_user: object
    ) -> None:
        facility = FacilityFactory()
        FacilityMembershipFactory(user=admin_user, facility=facility)
        new_user = UserFactory()

        resp = admin_client.post(members_url(facility.id), {
            "user": str(new_user.id), "is_primary": False,
        }, format="json")
        assert resp.status_code == status.HTTP_201_CREATED

    def test_admin_cannot_manage_other_facility_members(
        self, admin_client: APIClient, admin_user: object
    ) -> None:
        own = FacilityFactory(code="OADM")
        other = FacilityFactory(code="OADM2")
        FacilityMembershipFactory(user=admin_user, facility=own)
        new_user = UserFactory()

        resp = admin_client.post(members_url(other.id), {
            "user": str(new_user.id), "is_primary": False,
        }, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_membership_rejected(
        self, superadmin_client: APIClient
    ) -> None:
        facility = FacilityFactory()
        user = UserFactory()
        FacilityMembershipFactory(user=user, facility=facility)

        resp = superadmin_client.post(members_url(facility.id), {
            "user": str(user.id), "is_primary": False,
        }, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_superadmin_can_remove_member(
        self, superadmin_client: APIClient
    ) -> None:
        facility = FacilityFactory()
        user = UserFactory()
        m = FacilityMembershipFactory(user=user, facility=facility)

        resp = superadmin_client.delete(member_url(facility.id, m.id))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not FacilityMembership.objects.filter(pk=m.id).exists()

    def test_clinician_cannot_manage_members(
        self, clinician_client: APIClient
    ) -> None:
        facility = FacilityFactory()
        resp = clinician_client.get(members_url(facility.id))
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ── Cross-facility access ─────────────────────────────────────────────────────

class TestCrossFacilityAccess:
    def test_superadmin_can_grant_access(
        self, superadmin_client: APIClient
    ) -> None:
        facility = FacilityFactory()
        user = UserFactory()
        resp = superadmin_client.post(
            grant_url(facility.id), {"user_id": str(user.id)}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK

        from guardian.shortcuts import get_perms
        assert "access_facility" in get_perms(user, facility)

    def test_superadmin_can_revoke_access(
        self, superadmin_client: APIClient
    ) -> None:
        facility = FacilityFactory()
        user = UserFactory()
        from guardian.shortcuts import assign_perm
        assign_perm("access_facility", user, facility)

        resp = superadmin_client.post(
            revoke_url(facility.id), {"user_id": str(user.id)}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK

        from guardian.shortcuts import get_perms
        assert "access_facility" not in get_perms(user, facility)

    def test_admin_cannot_grant_access(
        self, admin_client: APIClient
    ) -> None:
        facility = FacilityFactory()
        user = UserFactory()
        resp = admin_client.post(
            grant_url(facility.id), {"user_id": str(user.id)}, format="json"
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_grant_unknown_user_returns_404(
        self, superadmin_client: APIClient
    ) -> None:
        import uuid
        facility = FacilityFactory()
        resp = superadmin_client.post(
            grant_url(facility.id), {"user_id": str(uuid.uuid4())}, format="json"
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_guardian_grant_visible_in_facility_queryset(self, db: None) -> None:
        """
        A user with a guardian grant on facility B (no membership) should see
        facility B's patients when enforcement is active.
        """
        from guardian.shortcuts import assign_perm
        from dream_core.facilities.mixins import get_all_permitted_facility_ids
        from unittest.mock import MagicMock

        facility_a = FacilityFactory(code="GRN_A")
        facility_b = FacilityFactory(code="GRN_B")
        user = UserFactory()
        FacilityMembershipFactory(user=user, facility=facility_a)
        assign_perm("access_facility", user, facility_b)

        request = MagicMock()
        request.user = user

        with override_settings(FACILITY_ENFORCEMENT_ENABLED=True):
            ids = get_all_permitted_facility_ids(request)

        assert facility_a.pk in ids
        assert facility_b.pk in ids


# ── Patient-facility Scoping ───────────────────────────────────────────────────

class TestPatientFacilityScoping:
    def test_user_sees_only_own_facility_patients(
        self, clinician_client: APIClient, clinician_user: object
    ) -> None:
        facility_a = FacilityFactory(code="SCP_A")
        facility_b = FacilityFactory(code="SCP_B")
        FacilityMembershipFactory(user=clinician_user, facility=facility_a)

        p_a = PatientFactory(facility=facility_a)
        p_b = PatientFactory(facility=facility_b)
        
        resp = clinician_client.get(LIST_URL)
        assert resp.status_code == status.HTTP_200_OK
        ids = [p["id"] for p in resp.json()["results"]]
        assert str(p_a.id) in ids
        assert str(p_b.id) not in ids

    def test_user_with_guardian_grant_sees_cross_facility_patients(
        self, clinician_client: APIClient, clinician_user: object
    ) -> None:
        from guardian.shortcuts import assign_perm

        facility_a = FacilityFactory(code="GR_A")
        facility_b = FacilityFactory(code="GR_B")
        FacilityMembershipFactory(user=clinician_user, facility=facility_a)
        assign_perm("access_facility", clinician_user, facility_b)

        p_a = PatientFactory(facility=facility_a)
        p_b = PatientFactory(facility=facility_b)

        resp = clinician_client.get(LIST_URL).json()
        ids = [p["id"] for p in resp["results"]]
        assert str(p_a.id) in ids
        assert str(p_b.id) in ids

    def test_user_without_membership_sees_no_patients(
        self, roles
    ) -> None:
        from rest_framework_simplejwt.tokens import RefreshToken
        from dream_core.accounts.accounts_utils import RoleType

        PatientFactory()

        # clinician_user has no memberships
        user = UserFactory()
        user.roles.add(roles[RoleType.CLINICIAN])

        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(user).access_token)}"
        )

        resp = client.get(LIST_URL)
        assert resp.json()["count"] == 0

    def test_superadmin_sees_all_patients(self, superadmin_client: APIClient) -> None:
        f1 = FacilityFactory(code="SA_1")
        f2 = FacilityFactory(code="SA_2")
        PatientFactory(facility=f1)
        PatientFactory(facility=f2)

        resp = superadmin_client.get(LIST_URL)
        assert resp.json()["count"] >= 2

    def test_create_patient_injects_facility(
        self, clinician_client: APIClient, clinician_user: object
    ) -> None:
        facility = FacilityFactory(code="INJ_F")
        clinician_user.facility_memberships.update(is_primary=False) # remove primary membership to not conflict
        FacilityMembershipFactory(user=clinician_user, facility=facility, is_primary=True)

        resp = clinician_client.post(LIST_URL, {
            "family_name": "Test",
            "given_names": "Patient",
            "birth_date": "1990-01-01",
            "gender": "male",
        }, format="json")
        assert resp.status_code == status.HTTP_201_CREATED

        from dream_core.patients.models import Patient
        patient = Patient.objects.get(pk=resp.json()["id"])
        assert patient.facility_id == facility.id

    def test_create_patient_without_membership_raises_403(self, roles: dict) -> None:
        from dream_core.testing.factories.accounts import UserFactory
        from dream_core.accounts.accounts_utils import RoleType
        from rest_framework_simplejwt.tokens import RefreshToken

        # clinician_user has no memberships
        clinician_user = UserFactory()
        clinician_user.roles.add(roles[RoleType.CLINICIAN]) 

        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(clinician_user).access_token)}"
        )

        resp = client.post(LIST_URL, {
            "family_name": "Test",
            "given_names": "Fail",
            "birth_date": "1990-01-01",
            "gender": "male",
        }, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_revoking_guardian_grant_removes_access(
        self, clinician_client: APIClient, clinician_user: object
    ) -> None:
        from guardian.shortcuts import assign_perm, remove_perm

        facility_a = FacilityFactory(code="RVK_A")
        facility_b = FacilityFactory(code="RVK_B")
        FacilityMembershipFactory(user=clinician_user, facility=facility_a)
        assign_perm("access_facility", clinician_user, facility_b)

        p_b = PatientFactory(facility=facility_b)

        # Can see before revoke
        resp = clinician_client.get(LIST_URL)
        ids = [p["id"] for p in resp.json()["results"]]
        assert str(p_b.id) in ids

        remove_perm("access_facility", clinician_user, facility_b)

        # Cannot see after revoke — clear request cache by using a fresh client
        from rest_framework_simplejwt.tokens import RefreshToken
        c2 = APIClient()
        c2.credentials(HTTP_AUTHORIZATION=f"Bearer {str(RefreshToken.for_user(clinician_user).access_token)}")
        resp2 = c2.get(LIST_URL)
        ids2 = [p["id"] for p in resp2.json()["results"]]
        assert str(p_b.id) not in ids2
