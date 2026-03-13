"""
apps/accounts/serializers.py
"""
from typing import Any

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.models import Role, User


# ── Role ──────────────────────────────────────────────────────────────────────

class RoleSerializer(serializers.ModelSerializer[Role]):
    class Meta:
        model = Role
        fields = ["id", "name", "description", "is_system", "created_at"]
        read_only_fields = ["id", "created_at"]


# ── User ──────────────────────────────────────────────────────────────────────

class UserListSerializer(serializers.ModelSerializer[User]):
    """Compact representation for list endpoints."""

    full_name = serializers.CharField(read_only=True)
    roles = RoleSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "first_name", "last_name",
            "department", "roles", "is_active", "created_at",
        ]
        read_only_fields = fields


class UserDetailSerializer(serializers.ModelSerializer[User]):
    """Full representation including compliance fields."""

    full_name = serializers.CharField(read_only=True)
    roles = RoleSerializer(many=True, read_only=True)
    role_ids = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(),
        many=True,
        write_only=True,
        source="roles",
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "first_name", "last_name",
            "professional_id", "department", "phone",
            "roles", "role_ids",
            "is_active", "must_change_password",
            "last_login", "last_login_ip",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "last_login", "last_login_ip", "created_at", "updated_at",
        ]

    def update(self, instance: User, validated_data: dict[str, Any]) -> User:
        roles: list[Role] | None = validated_data.pop("roles", None)
        user = super().update(instance, validated_data)
        if roles is not None:
            user.roles.set(roles)
        return user


class UserCreateSerializer(serializers.ModelSerializer[User]):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    role_ids = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(),
        many=True,
        write_only=True,
        source="roles",
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "email", "password", "first_name", "last_name",
            "professional_id", "department", "phone", "role_ids",
        ]

    def create(self, validated_data: dict[str, Any]) -> User:
        roles: list[Role] = validated_data.pop("roles", [])
        password: str = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if roles:
            user.roles.set(roles)
        return user


class ChangePasswordSerializer(serializers.Serializer[User]):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def validate_current_password(self, value: str) -> str:
        user: User = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value


# ── Auth ──────────────────────────────────────────────────────────────────────

class LoginSerializer(serializers.Serializer[User]):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        email: str = attrs["email"]
        password: str = attrs["password"]

        user = User.objects.filter(email=email).first()

        if user and user.is_locked:
            raise AuthenticationFailed(
                f"Account locked. Try again after {user.locked_until}."
            )

        authenticated = authenticate(
            request=self.context.get("request"),
            username=email,
            password=password,
        )

        if not authenticated:
            if user:
                user.record_failed_login()
            raise AuthenticationFailed("Invalid credentials.")

        assert isinstance(authenticated, User)

        if not authenticated.is_active:
            raise AuthenticationFailed("Account is deactivated.")

        authenticated.record_successful_login(
            ip=self.context["request"].META.get("REMOTE_ADDR")
            if self.context.get("request")
            else None
        )
        attrs["user"] = authenticated
        return attrs
