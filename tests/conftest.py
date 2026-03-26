"""
tests/conftest.py

Shared pytest fixtures for the entire dream-core test suite.
"""
import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from dream_core.accounts.models import Role, User
from dream_core.accounts.accounts_utils import RoleType

# ── Roles fixture (creates the core system roles once per session) ─────────────

@pytest.fixture
def roles(db: None) -> dict[str, Role]:
    """Create the standard system roles."""
    role_names = [
        RoleType.SUPERADMIN, RoleType.ADMIN, RoleType.CLINICIAN,
        RoleType.LAB_MANAGER, RoleType.LAB_ANALYST, RoleType.RECEPTIONIST, RoleType.AUDITOR,
    ]
    return {
        name: Role.objects.get_or_create(name=name, defaults={"is_system": True})[0]
        for name in role_names
    }


# ── User fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def superadmin_user(db: None, roles: dict[str, Role]) -> User:
    user = User.objects.create_user(
        email="superadmin@dream_core.test",
        password="Sup3rS3cur3!",
        first_name="Super",
        last_name="Admin",
        must_change_password=False,
    )
    user.roles.add(roles[RoleType.SUPERADMIN])
    return user


@pytest.fixture
def admin_user(db: None, roles: dict[str, Role]) -> User:
    user = User.objects.create_user(
        email="admin@dream_core.test",
        password="Adm1nP4ss!",
        first_name="Facility",
        last_name="Admin",
        must_change_password=False,
    )
    user.roles.add(roles[RoleType.ADMIN])
    return user


@pytest.fixture
def lab_manager_user(db: None, roles: dict[str, Role]) -> User:
    user = User.objects.create_user(
        email="lab.manager@dream_core.test",
        password="L4bM4n4g3r!",
        first_name="Lab",
        last_name="Manager",
        must_change_password=False,
    )
    user.roles.add(roles[RoleType.LAB_MANAGER])
    return user


@pytest.fixture
def lab_analyst_user(db: None, roles: dict[str, Role]) -> User:
    user = User.objects.create_user(
        email="analyst@dream_core.test",
        password="An4lyst!Pass",
        first_name="Lab",
        last_name="Analyst",
        must_change_password=False,
    )
    user.roles.add(roles[RoleType.LAB_ANALYST])
    return user


@pytest.fixture
def clinician_user(db: None, roles: dict[str, Role]) -> User:
    user = User.objects.create_user(
        email="doctor@dream_core.test",
        password="D0ct0rP4ss!",
        first_name="Jane",
        last_name="Doctor",
        must_change_password=False,
    )
    user.roles.add(roles[RoleType.CLINICIAN])
    return user


@pytest.fixture
def auditor_user(db: None, roles: dict[str, Role]) -> User:
    user = User.objects.create_user(
        email="auditor@dream_core.test",
        password="Aud1t0rP4ss!",
        first_name="Audit",
        last_name="User",
        must_change_password=False,
    )
    user.roles.add(roles[RoleType.AUDITOR])
    return user


# ── API client fixtures ───────────────────────────────────────────────────────

def _authed_client(user: User) -> APIClient:
    """Return an API client authenticated as the given user."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


@pytest.fixture
def anon_client() -> APIClient:
    return APIClient()


@pytest.fixture
def superadmin_client(superadmin_user: User) -> APIClient:
    return _authed_client(superadmin_user)


@pytest.fixture
def admin_client(admin_user: User) -> APIClient:
    return _authed_client(admin_user)


@pytest.fixture
def lab_manager_client(lab_manager_user: User) -> APIClient:
    return _authed_client(lab_manager_user)


@pytest.fixture
def lab_analyst_client(lab_analyst_user: User) -> APIClient:
    return _authed_client(lab_analyst_user)


@pytest.fixture
def clinician_client(clinician_user: User) -> APIClient:
    return _authed_client(clinician_user)


@pytest.fixture
def auditor_client(auditor_user: User) -> APIClient:
    return _authed_client(auditor_user)
