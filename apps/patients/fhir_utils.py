"""
apps/patients/fhir_utils.py

Bidirectional conversion between Patient Django model instances
and HL7 FHIR R4 Patient resources using the fhir.resources library.

Why a separate utility module (not in the serializer)?
- The FHIR resource model is a Pydantic v2 model, completely separate from
  DRF serializers. Keeping conversion logic here makes it reusable by
  both the REST API and any future HL7 messaging layer (v2/v3).
- fhir.resources uses strict Pydantic v2 validation, which acts as a second
  schema validation layer on top of Django's model validation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fhir.resources.patient import Patient as FHIRPatient  # type: ignore[import-untyped]
from fhir.resources.humanname import HumanName  # type: ignore[import-untyped]
from fhir.resources.identifier import Identifier  # type: ignore[import-untyped]
from fhir.resources.contactpoint import ContactPoint  # type: ignore[import-untyped]
from fhir.resources.address import Address  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from apps.patients.models import Patient


# ── Django → FHIR ─────────────────────────────────────────────────────────────

def patient_to_fhir(patient: "Patient") -> FHIRPatient:
    """
    Convert a Patient Django instance to a FHIR R4 Patient resource.

    The FHIR resource is NOT persisted — it is used for API responses and
    outbound HL7 messaging.
    """
    # Identifiers
    identifiers: list[dict[str, Any]] = [
        {
            "use": ident.use,
            "system": ident.system,
            "value": ident.value,
        }
        for ident in patient.identifiers.all()
    ]
    # Always add the internal dream-core ID as an identifier
    identifiers.insert(0, {
        "use": "official",
        "system": "https://dream-core.local/patient-id",
        "value": str(patient.id),
    })

    # HumanName
    name: list[dict[str, Any]] = [
        {
            "use": "official",
            "family": patient.family_name,
            "given": patient.given_names.split(),
        }
    ]

    # Telecom
    telecom: list[dict[str, Any]] = [
        {
            "system": c.system,
            "value": c.value,
            "use": c.use,
            "rank": c.rank,
        }
        for c in patient.contacts.filter(is_active=True)
    ]
    if patient.email:
        telecom.append({"system": "email", "value": patient.email, "use": "home"})

    # Address
    addresses: list[dict[str, Any]] = []
    if patient.address:
        addresses.append(patient.address)

    resource_dict: dict[str, Any] = {
        "resourceType": "Patient",
        "id": str(patient.id),
        "active": patient.is_active,
        "identifier": identifiers,
        "name": name,
        "gender": patient.gender,
        "birthDate": patient.birth_date.isoformat() if patient.birth_date else None,
        "telecom": telecom if telecom else None,
        "address": addresses if addresses else None,
    }

    if patient.deceased_date:
        resource_dict["deceasedDateTime"] = patient.deceased_date.isoformat()

    # Remove None values — FHIR validation rejects null for optional fields
    resource_dict = {k: v for k, v in resource_dict.items() if v is not None}

    return FHIRPatient.model_validate(resource_dict)


def fhir_to_patient_data(fhir_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Parse and validate a FHIR R4 Patient resource dict, then return
    a flat dict suitable for Patient model creation/update.

    Raises pydantic.ValidationError if the FHIR resource is invalid.
    """
    # Validate against FHIR schema first
    fhir_patient = FHIRPatient.model_validate(fhir_dict)

    # Extract name (use the first 'official' or just first name)
    family_name = ""
    given_names = ""
    if fhir_patient.name:
        name_obj: HumanName = next(
            (n for n in fhir_patient.name if n.use == "official"),
            fhir_patient.name[0],
        )
        family_name = name_obj.family or ""
        given_names = " ".join(name_obj.given or [])

    # Extract email from telecom
    email = ""
    if fhir_patient.telecom:
        for tp in fhir_patient.telecom:
            if tp.system == "email" and tp.value:
                email = tp.value
                break

    # Extract address
    address: dict[str, Any] = {}
    if fhir_patient.address:
        addr: Address = fhir_patient.address[0]
        address = addr.model_dump(exclude_none=True)

    data: dict[str, Any] = {
        "family_name": family_name,
        "given_names": given_names,
        "gender": fhir_patient.gender or "unknown",
        "birth_date": fhir_patient.birthDate,  # already a date
        "email": email,
        "address": address,
        "is_active": fhir_patient.active if fhir_patient.active is not None else True,
    }

    # Identifiers (excluding our internal one)
    identifiers: list[dict[str, Any]] = []
    if fhir_patient.identifier:
        for ident in fhir_patient.identifier:
            if ident.system != "https://dream-core.local/patient-id":
                identifiers.append({
                    "use": ident.use or "official",
                    "system": str(ident.system),
                    "value": ident.value,
                })
    data["identifiers"] = identifiers

    # Contacts (non-email telecom)
    contacts: list[dict[str, Any]] = []
    if fhir_patient.telecom:
        for i, tp in enumerate(fhir_patient.telecom):
            if tp.system != "email":
                contacts.append({
                    "system": tp.system or "phone",
                    "value": tp.value or "",
                    "use": tp.use or "home",
                    "rank": tp.rank or (i + 1),
                })
    data["contacts"] = contacts

    return data
