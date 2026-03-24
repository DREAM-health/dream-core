"""
tests/accounts/test_rbac.py

Tests for RBAC — verifying that role boundaries are enforced across endpoints.
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from dream_core.accounts.models import User
from tests.accounts.factories import RoleFactory, UserFactory

from rest_framework.request import Request

pytestmark = pytest.mark.django_db


class TestUserManagement:
    LIST_URL = "/api/v1/accounts/users/"

    def test_admin_can_list_users(self, admin_client: APIClient) -> None:
        resp = admin_client.get(self.LIST_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_lab_analyst_cannot_list_users(self, lab_analyst_client: APIClient) -> None:
        resp = lab_analyst_client.get(self.LIST_URL)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_clinician_cannot_list_users(self, clinician_client: APIClient) -> None:
        resp = clinician_client.get(self.LIST_URL)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_list_users(self, anon_client: APIClient) -> None:
        resp = anon_client.get(self.LIST_URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_can_create_user(self, admin_client: APIClient) -> None:
        resp = admin_client.post(self.LIST_URL, {
            "email": "new@test.com",
            "password": "NewUser123!@",
            "first_name": "New",
            "last_name": "User",
            "professional_id": "test-xxxx",
            "department": "Test 1127"
        })
        assert resp.status_code == status.HTTP_201_CREATED

    def test_lab_manager_cannot_create_user(self, lab_manager_client: APIClient) -> None:
        resp = lab_manager_client.post(self.LIST_URL, {
            "email": "new2@test.com",
            "password": "NewUser123!",
            "first_name": "New",
            "last_name": "User",
        })
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_deactivate_user_does_not_delete(
        self, admin_client: APIClient, admin_user: User
    ) -> None:
        target = UserFactory()
        url = f"/api/v1/accounts/users/{target.id}/"

        resp = admin_client.delete(url)

        assert resp.status_code == status.HTTP_200_OK
        target.refresh_from_db()
        assert target.is_active is False
        # Must still exist in DB
        assert User.objects.filter(id=target.id).exists()


class TestRoleManagement:
    LIST_URL = "/api/v1/accounts/roles/"

    def test_superadmin_can_manage_roles(self, superadmin_client: APIClient) -> None:
        resp = superadmin_client.get(self.LIST_URL)
        assert resp.status_code == status.HTTP_200_OK

    def test_admin_cannot_manage_roles(self, admin_client: APIClient) -> None:
        resp = admin_client.get(self.LIST_URL)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_superadmin_can_create_role(self, superadmin_client: APIClient) -> None:
        resp = superadmin_client.post(self.LIST_URL, {
            "name": "CUSTOM_ROLE",
            "description": "A custom role",
        })
        assert resp.status_code == status.HTTP_201_CREATED

    def test_cannot_delete_system_role(
        self, superadmin_client: APIClient, roles: dict
    ) -> None:
        url = f"/api/v1/accounts/roles/{roles['ADMIN'].id}/"
        resp = superadmin_client.delete(url)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_can_delete_non_system_role(self, superadmin_client: APIClient) -> None:
        role = RoleFactory(is_system=False)
        url = f"/api/v1/accounts/roles/{role.id}/"
        resp = superadmin_client.delete(url)
        assert resp.status_code == status.HTTP_204_NO_CONTENT


class TestUserRoleAssignment:
    def test_user_has_role_method_works(self, db: None, roles: dict) -> None:
        user = UserFactory()
        user.roles.add(roles["LAB_ANALYST"])
        assert user.has_role("LAB_ANALYST") is True
        assert user.has_role("LAB_MANAGER") is False

    def test_superuser_bypasses_role_check(self, db: None) -> None:
        from dream_core.accounts.permissions import HasRole
        from unittest.mock import MagicMock

        request = MagicMock(spec=Request)
        request.user = UserFactory(is_superuser=True)
        view = MagicMock()

        perm = HasRole("ANY_ROLE")()
        assert perm.has_permission(request, view) is True

    def test_multiple_roles_aggregate_permissions(self, db: None, roles: dict) -> None:
        user = UserFactory()
        user.roles.add(roles["LAB_ANALYST"])
        user.roles.add(roles["CLINICIAN"])
        assert user.has_role("LAB_ANALYST") is True
        assert user.has_role("CLINICIAN") is True
        assert user.has_role("ADMIN") is False
