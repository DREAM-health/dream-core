from django.urls import path
from dream_core.patients.views import (
    DataConsentListCreateView,
    DataConsentRevokeView,
    DeletedPatientListView,
    FHIRPatientCreateView,
    FHIRPatientDetailView,
    PatientDetailView,
    PatientListCreateView,
    PatientRestoreView,
)

urlpatterns = [
    # Standard REST
    path("", PatientListCreateView.as_view(), name="patient-list"),
    path("<uuid:pk>/", PatientDetailView.as_view(), name="patient-detail"),

    # FHIR R4
    path("fhir/", FHIRPatientCreateView.as_view(), name="patient-fhir-create"),
    path("<uuid:pk>/fhir/", FHIRPatientDetailView.as_view(), name="patient-fhir-detail"),

    # DataConsent
    path("<uuid:pk>/consents/", DataConsentListCreateView.as_view(), name="patient-consent-list"),
    path("consents/<uuid:consent_id>/revoke/", DataConsentRevokeView.as_view(), name="patient-consent-revoke"),

    # Admin
    path("deleted/", DeletedPatientListView.as_view(), name="patient-deleted-list"),
    path("<uuid:pk>/restore/", PatientRestoreView.as_view(), name="patient-restore"),
]
