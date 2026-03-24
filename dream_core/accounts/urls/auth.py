from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from dream_core.accounts.views import ChangePasswordView, LoginView, LogoutView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
]
