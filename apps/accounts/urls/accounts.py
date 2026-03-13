from django.urls import path
from apps.accounts.views import (
    MeView,
    RoleDetailView,
    RoleListCreateView,
    UserDetailView,
    UserListCreateView,
)

urlpatterns = [
    path("me/", MeView.as_view(), name="accounts-me"),
    path("users/", UserListCreateView.as_view(), name="accounts-user-list"),
    path("users/<uuid:pk>/", UserDetailView.as_view(), name="accounts-user-detail"),
    path("roles/", RoleListCreateView.as_view(), name="accounts-role-list"),
    path("roles/<uuid:pk>/", RoleDetailView.as_view(), name="accounts-role-detail"),
]
