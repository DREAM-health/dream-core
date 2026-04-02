"""
dream_core/testing/factories/facilities.py — factory_boy factories for the test facilities.
"""
import factory
from factory.django import DjangoModelFactory

from dream_core.facilities.models import Facility, FacilityMembership


class FacilityFactory(DjangoModelFactory):
    class Meta:
        model = Facility

    name = factory.Sequence(lambda n: f"Test Facility {n}")
    short_name = factory.Sequence(lambda n: f"TF{n}")
    code = factory.Sequence(lambda n: f"TF{n:03d}")
    facility_type = Facility.FacilityType.CENTER
    is_active = True
    timezone = "UTC"


class FacilityMembershipFactory(DjangoModelFactory):
    class Meta:
        model = FacilityMembership

    user = factory.SubFactory("dream_core.testing.factories.accounts.UserFactory")
    facility = factory.SubFactory(FacilityFactory)
    is_primary = True