from django.urls import path
from dream_core.patients.views import (
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

    # Admin
    path("deleted/", DeletedPatientListView.as_view(), name="patient-deleted-list"),
    path("<uuid:pk>/restore/", PatientRestoreView.as_view(), name="patient-restore"),
]
