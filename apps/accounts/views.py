"""
apps/accounts/views.py
"""
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Role, User
from apps.accounts.permissions import IsAdmin, IsSuperAdmin
from apps.accounts.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserDetailSerializer,
    UserListSerializer,
)


# ── Auth views ────────────────────────────────────────────────────────────────

@extend_schema(tags=["auth"])
class LoginView(APIView):
    """Authenticate and receive JWT access + refresh tokens."""

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user: User = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "roles": [r.name for r in user.roles.all()],
                    "must_change_password": user.must_change_password,
                },
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["auth"])
class LogoutView(APIView):
    """Blacklist the refresh token (invalidates the session)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            refresh_token: str = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except Exception:
            return Response({"detail": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=["auth"])
class ChangePasswordView(APIView):
    """Change the authenticated user's password."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user: User = request.user  # type: ignore[assignment]
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.password_changed_at = timezone.now()
        user.save(update_fields=["password", "must_change_password", "password_changed_at"])
        return Response({"detail": "Password changed successfully."})


# ── User views ────────────────────────────────────────────────────────────────

@extend_schema(tags=["accounts"])
@extend_schema_view(
    get=extend_schema(summary="Get current user profile"),
)
class MeView(generics.RetrieveUpdateAPIView[User]):
    """Read or update the currently authenticated user's profile."""

    permission_classes = [IsAuthenticated]
    serializer_class = UserDetailSerializer

    def get_object(self) -> User:
        return self.request.user  # type: ignore[return-value]


@extend_schema(tags=["accounts"])
@extend_schema_view(
    get=extend_schema(summary="List users"),
    post=extend_schema(summary="Create user"),
)
class UserListCreateView(generics.ListCreateAPIView[User]):
    """List all users or create a new one. Admin only."""

    permission_classes = [IsAuthenticated, IsAdmin]
    filterset_fields = ["is_active", "department"]
    search_fields = ["email", "password",  "first_name", "last_name", "professional_id"]
    ordering_fields = ["last_name", "created_at"]

    def get_queryset(self) -> Any:
        return User.objects.prefetch_related("roles").all()

    def get_serializer_class(self) -> Any:
        if self.request.method == "POST":
            return UserCreateSerializer
        return UserListSerializer


@extend_schema(tags=["accounts"])
@extend_schema_view(
    get=extend_schema(summary="Get user detail"),
    put=extend_schema(summary="Update user"),
    patch=extend_schema(summary="Partial update user"),
    delete=extend_schema(summary="Deactivate user"),
)
class UserDetailView(generics.RetrieveUpdateDestroyAPIView[User]):
    """Get, update, or deactivate a user. Admin only."""

    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = UserDetailSerializer

    def get_queryset(self) -> Any:
        return User.objects.prefetch_related("roles").all()

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Deactivate instead of deleting — users are never hard-deleted."""
        user: User = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(
            {"detail": "User deactivated."},
            status=status.HTTP_200_OK,
        )


# ── Role views ────────────────────────────────────────────────────────────────

@extend_schema(tags=["accounts"])
class RoleListCreateView(generics.ListCreateAPIView[Role]):
    """List or create roles. SuperAdmin only."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = Role.objects.prefetch_related("permissions").all()
    serializer_class = RoleSerializer


@extend_schema(tags=["accounts"])
class RoleDetailView(generics.RetrieveUpdateDestroyAPIView[Role]):
    """Get, update, or delete a role. SuperAdmin only."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]
    queryset = Role.objects.all()
    serializer_class = RoleSerializer

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        role: Role = self.get_object()
        if role.is_system:
            return Response(
                {"detail": "System roles cannot be deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )
        role.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
