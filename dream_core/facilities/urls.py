from django.urls import path
from dream_core.facilities.views import (
    CrossFacilityGrantView,
    CrossFacilityRevokeView,
    FacilityDetailView,
    FacilityListCreateView,
    FacilityMemberDetailView,
    FacilityMemberListCreateView,
)

urlpatterns = [
    path("", FacilityListCreateView.as_view(), name="facility-list"),
    path("<uuid:pk>/", FacilityDetailView.as_view(), name="facility-detail"),
    path("<uuid:facility_pk>/members/", FacilityMemberListCreateView.as_view(), name="facility-member-list"),
    path("<uuid:facility_pk>/members/<int:pk>/", FacilityMemberDetailView.as_view(), name="facility-member-detail"),
    path("<uuid:facility_pk>/access/grant/", CrossFacilityGrantView.as_view(), name="facility-access-grant"),
    path("<uuid:facility_pk>/access/revoke/", CrossFacilityRevokeView.as_view(), name="facility-access-revoke"),
]