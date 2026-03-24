"""
tests/patients/factories.py — factory_boy factories for patients.
"""
import datetime

import factory
from factory.django import DjangoModelFactory

from dream_core.patients.models import Patient, PatientContact, PatientIdentifier


class PatientFactory(DjangoModelFactory):
    class Meta:
        model = Patient

    family_name = factory.Faker("last_name")
    given_names = factory.Faker("first_name")
    birth_date = factory.Faker("date_of_birth", minimum_age=1, maximum_age=90)
    gender = factory.Iterator(["male", "female", "other"])
    email = factory.Sequence(lambda n: f"patient{n}@example.com")
    is_active = True


class PatientIdentifierFactory(DjangoModelFactory):
    class Meta:
        model = PatientIdentifier

    patient = factory.SubFactory(PatientFactory)
    system = "https://dream_core.local/cpf"
    value = factory.Sequence(lambda n: f"{n:011d}")
    use = "official"


class PatientContactFactory(DjangoModelFactory):
    class Meta:
        model = PatientContact

    patient = factory.SubFactory(PatientFactory)
    system = "phone"
    value = factory.Faker("phone_number")
    use = "mobile"
    rank = 1
