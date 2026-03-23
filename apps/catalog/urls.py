from django.urls import path
from apps.catalog.views import (
    ResultInterpretationView,
    LabTestDefinitionDetailView,
    LabTestDefinitionListCreateView,
    LabTestPanelDetailView,
    LabTestPanelListCreateView,
    UnitDetailView,
    UnitListCreateView,
)

urlpatterns = [
    # Units
    path("units/", UnitListCreateView.as_view(), name="catalog-unit-list"),
    path("units/<uuid:pk>/", UnitDetailView.as_view(), name="catalog-unit-detail"),

    # Panels
    path("panels/", LabTestPanelListCreateView.as_view(), name="catalog-panel-list"),
    path("panels/<uuid:pk>/", LabTestPanelDetailView.as_view(), name="catalog-panel-detail"),

    # LabTest definitions
    path("labtests/", LabTestDefinitionListCreateView.as_view(), name="catalog-labtest-list"),
    path("labtests/interpret/", ResultInterpretationView.as_view(), name="catalog-labtest-interpret"),
    path("labtests/<uuid:pk>/", LabTestDefinitionDetailView.as_view(), name="catalog-labtest-detail"),
]
