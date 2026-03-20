"""
tests/accounts/test_auth.py

Tests for authentication endpoints:
  - Login (success, wrong password, locked account)
  - Token refresh
  - Logout (blacklist)
  - Change password
"""
import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from tests.accounts.factories import UserFactory


pytestmark = pytest.mark.django_db


class TestLogin:
    URL = "/api/v1/auth/login/"

    def test_sample(self) -> None:
        assert True == True

    def test_login_success_returns_tokens(self, anon_client: APIClient) -> None:
        user = UserFactory(email="login@test.com")
        user.set_password("GoodPass123!")
        user.save()

        resp = anon_client.post(self.URL, {"email": "login@test.com", "password": "GoodPass123!"})

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert "access" in data
        assert "refresh" in data
        assert data["user"]["email"] == "login@test.com"

    def test_login_wrong_password_returns_401(self, anon_client: APIClient) -> None:
        UserFactory(email="wrong@test.com")

        resp = anon_client.post(self.URL, {"email": "wrong@test.com", "password": "WrongPass!"})

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_nonexistent_user_returns_401(self, anon_client: APIClient) -> None:
        resp = anon_client.post(self.URL, {"email": "ghost@test.com", "password": "AnyPass!"})

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_inactive_user_returns_401(self, anon_client: APIClient) -> None:
        user = UserFactory(email="inactive@test.com", is_active=False)
        user.set_password("Pass123!")
        user.save()

        resp = anon_client.post(self.URL, {"email": "inactive@test.com", "password": "Pass123!"})

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_increments_failed_attempts(self, anon_client: APIClient) -> None:
        UserFactory(email="fail@test.com")

        anon_client.post(self.URL, {"email": "fail@test.com", "password": "Wrong!"})
        anon_client.post(self.URL, {"email": "fail@test.com", "password": "Wrong!"})

        user = User.objects.get(email="fail@test.com")
        assert user.failed_login_attempts == 2

    def test_login_locked_account_returns_401(self, anon_client: APIClient) -> None:
        user = UserFactory(email="locked@test.com")
        user.set_password("Pass123!")
        user.locked_until = timezone.now() + timezone.timedelta(minutes=10)
        user.save()

        resp = anon_client.post(self.URL, {"email": "locked@test.com", "password": "Pass123!"})

        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert "locked" in resp.json().get("detail", "").lower()

    def test_login_resets_failed_attempts_on_success(self, anon_client: APIClient) -> None:
        user = UserFactory(email="reset@test.com")
        user.set_password("GoodPass123!")
        user.failed_login_attempts = 3
        user.save()

        anon_client.post(self.URL, {"email": "reset@test.com", "password": "GoodPass123!"})

        user.refresh_from_db()
        assert user.failed_login_attempts == 0

    def test_login_missing_fields_returns_400(self, anon_client: APIClient) -> None:
        resp = anon_client.post(self.URL, {"email": "only@test.com"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_login_response_includes_roles(
        self, anon_client: APIClient, roles: dict
    ) -> None:
        user = UserFactory(email="roletest@test.com")
        user.set_password("Pass123!")
        user.roles.add(roles["LAB_ANALYST"])
        user.save()

        resp = anon_client.post(
            self.URL, {"email": "roletest@test.com", "password": "Pass123!"}
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "LAB_ANALYST" in resp.json()["user"]["roles"]


class TestLogout:
    LOGIN_URL = "/api/v1/auth/login/"
    LOGOUT_URL = "/api/v1/auth/logout/"

    def _login(self, client: APIClient, email: str, password: str) -> dict:
        resp = client.post(self.LOGIN_URL, {"email": email, "password": password})
        return resp.json()

    def test_logout_blacklists_refresh_token(self, anon_client: APIClient) -> None:
        user = UserFactory(email="logout@test.com")
        user.set_password("Pass123!")
        user.save()

        tokens = self._login(anon_client, "logout@test.com", "Pass123!")
        anon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        resp = anon_client.post(self.LOGOUT_URL, {"refresh": tokens["refresh"]})
        assert resp.status_code == status.HTTP_200_OK

        # Using the blacklisted refresh token should now fail
        refresh_resp = anon_client.post(
            "/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]}
        )
        assert refresh_resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_unauthenticated_returns_401(self, anon_client: APIClient) -> None:
        resp = anon_client.post(self.LOGOUT_URL, {"refresh": "fake-token"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestChangePassword:
    URL = "/api/v1/auth/change-password/"

    def test_change_password_success(self, admin_client: APIClient, admin_user: User) -> None:
        resp = admin_client.post(self.URL, {
            "current_password": "Adm1nP4ss!",
            "new_password": "NewStr0ngP4ss!",
            "confirm_password": "NewStr0ngP4ss!",
        })
        assert resp.status_code == status.HTTP_200_OK

        admin_user.refresh_from_db()
        assert admin_user.check_password("NewStr0ngP4ss!")
        assert admin_user.must_change_password is False

    def test_change_password_wrong_current(self, admin_client: APIClient) -> None:
        resp = admin_client.post(self.URL, {
            "current_password": "WrongCurrent!",
            "new_password": "NewStr0ng!",
            "confirm_password": "NewStr0ng!",
        })
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_mismatch(self, admin_client: APIClient) -> None:
        resp = admin_client.post(self.URL, {
            "current_password": "Adm1nP4ss!",
            "new_password": "NewPass123!",
            "confirm_password": "DifferentPass123!",
        })
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_unauthenticated(self, anon_client: APIClient) -> None:
        resp = anon_client.post(self.URL, {
            "current_password": "any",
            "new_password": "any",
            "confirm_password": "any",
        })
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


class TestMeEndpoint:
    URL = "/api/v1/accounts/me/"

    def test_me_returns_current_user(
        self, admin_client: APIClient, admin_user: User
    ) -> None:
        resp = admin_client.get(self.URL)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()["email"] == admin_user.email

    def test_me_unauthenticated(self, anon_client: APIClient) -> None:
        resp = anon_client.get(self.URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_me_patch_updates_profile(
        self, admin_client: APIClient, admin_user: User
    ) -> None:
        resp = admin_client.patch(self.URL, {"department": "Haematology Lab"})
        assert resp.status_code == status.HTTP_200_OK
        admin_user.refresh_from_db()
        assert admin_user.department == "Haematology Lab"
