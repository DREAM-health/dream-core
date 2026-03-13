from django.urls import path
from apps.catalog.views import (
    ResultInterpretationView,
    TestDefinitionDetailView,
    TestDefinitionListCreateView,
    TestPanelDetailView,
    TestPanelListCreateView,
    UnitDetailView,
    UnitListCreateView,
)

urlpatterns = [
    # Units
    path("units/", UnitListCreateView.as_view(), name="catalog-unit-list"),
    path("units/<uuid:pk>/", UnitDetailView.as_view(), name="catalog-unit-detail"),

    # Panels
    path("panels/", TestPanelListCreateView.as_view(), name="catalog-panel-list"),
    path("panels/<uuid:pk>/", TestPanelDetailView.as_view(), name="catalog-panel-detail"),

    # Test definitions
    path("tests/", TestDefinitionListCreateView.as_view(), name="catalog-test-list"),
    path("tests/interpret/", ResultInterpretationView.as_view(), name="catalog-test-interpret"),
    path("tests/<uuid:pk>/", TestDefinitionDetailView.as_view(), name="catalog-test-detail"),
]
