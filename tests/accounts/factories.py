"""
tests/accounts/factories.py — factory_boy factories for accounts.
"""
import factory
from factory.django import DjangoModelFactory

from dream_core.accounts.models import Role, User


class RoleFactory(DjangoModelFactory):
    class Meta:
        model = Role
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"ROLE_{n}")
    description = factory.Faker("sentence")
    is_system = False


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True  # suppress deprecation warning

    email = factory.Sequence(lambda n: f"user{n}@dream_core.test")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    password = factory.PostGenerationMethodCall("set_password", "TestPass123!")
    is_active = True
    must_change_password = False

    @factory.post_generation  # type: ignore[misc]
    def roles(self, create: bool, extracted: list[Role] | None, **kwargs: object) -> None:
        if not create or not extracted:
            return
        self.roles.set(extracted)
