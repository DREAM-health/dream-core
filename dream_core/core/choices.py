# dream_core/core/choices.py

from django.db import models


class FHIRGender(models.TextChoices):
    """
    Administrative gender — HL7 FHIR R4 vocabulary.
    https://hl7.org/fhir/valueset-administrative-gender.html

    Use this anywhere a FHIR-aligned gender field is needed.
    Do NOT conflate with biological sex (used for reference ranges —
    see ReferenceRange.GenderChoices in dream_core/catalog/models.py).
    """
    MALE    = "male",    "Male"
    FEMALE  = "female",  "Female"
    OTHER   = "other",   "Other"
    UNKNOWN = "unknown", "Unknown"
