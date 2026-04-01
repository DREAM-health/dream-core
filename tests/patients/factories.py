"""
tests/patients/factories.py — factory_boy factories for patients.
"""
import datetime

import factory
from factory.django import DjangoModelFactory

from dream_core.patients.models import DataConsent, Patient, PatientContact, PatientIdentifier


class PatientFactory(DjangoModelFactory):
    class Meta:
        model = Patient

    family_name = factory.Faker("last_name")
    given_names = factory.Faker("first_name")
    birth_date = factory.Faker("date_of_birth", minimum_age=1, maximum_age=90)
    gender = factory.Iterator(["male", "female", "other"])
    email = factory.Sequence(lambda n: f"patient{n}@example.com")
    id_patient = factory.Sequence(lambda n: f"PAT-{n:06d}")
    id_dream = factory.Sequence(lambda n: f"DRM-{n:06d}")
    caregiver_name = ""
    caregiver_contact = ""
    is_pregnant = None
    is_breastfeeding = None
    is_active = True
    facility = None  # Phase 1 default: no facility required


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


class DataConsentFactory(DjangoModelFactory):
    class Meta:
        model = DataConsent
 
    patient = factory.SubFactory(PatientFactory)
    scope = DataConsent.ConsentScope.FULL
    version = "v1.0"
    consented_at = factory.Faker("date_time_this_year", tzinfo=datetime.timezone.utc)
    is_active = True
    collection_method = "paper"