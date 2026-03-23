"""
apps/audit/views.py

Read-only API over AuditEvent (proxy over django-auditlog's LogEntry).

Endpoints:
  GET /api/v1/audit/logs/                  — list all log entries (paginated)
  GET /api/v1/audit/logs/{id}/             — retrieve single entry
  GET /api/v1/audit/logs/object/{ct}/{pk}/ — all logs for a specific object

Access: AUDITOR, ADMIN, SUPERADMIN only (read-only, no mutations).

django-auditlog stores:
  - actor       (user who made the change)
  - action      (0=create, 1=update, 2=delete, 3=access)
  - content_type + object_pk (what was changed)
  - object_repr (string representation at time of change)
  - changes     (JSON: field -> [old, new])
  - timestamp
  - remote_addr (IP address)

Migration from raw LogEntry to AuditEvent:
  The only change from the previous implementation is that we now import
  AuditEvent instead of LogEntry. The database query is identical — the proxy
  shares the underlying table. The benefit is that view code can now use the
  manager helpers (for_object, for_actor, etc.) and the computed properties
  (action_display, resource_label, actor_display) without duplicating logic.
"""

from typing import Any

from django.contrib.contenttypes.models import ContentType
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from apps.accounts.permissions import IsAuditor
from apps.audit.models import AuditEvent


# ── Serializer ────────────────────────────────────────────────────────────────

class AuditEventSerializer(serializers.Serializer[AuditEvent]):
    id = serializers.IntegerField(read_only=True)
    timestamp = serializers.DateTimeField(read_only=True)

    actor_id = serializers.SerializerMethodField()
    actor_email = serializers.SerializerMethodField()

    action = serializers.IntegerField(read_only=True)
    action_display = serializers.SerializerMethodField()

    content_type = serializers.SerializerMethodField()
    object_pk = serializers.CharField(read_only=True)
    object_repr = serializers.CharField(read_only=True)

    changes = serializers.JSONField(read_only=True)
    changed_fields = serializers.SerializerMethodField()
    remote_addr = serializers.IPAddressField(read_only=True, allow_null=True)
    additional_data = serializers.JSONField(read_only=True, allow_null=True)

    def get_actor_id(self, obj: AuditEvent) -> str | None:
        return str(obj.actor_id) if obj.actor_id else None

    def get_actor_email(self, obj: AuditEvent) -> str | None:
        return obj.actor_display if obj.actor_id else None

    def get_action_display(self, obj: AuditEvent) -> str:
        return obj.action_display

    def get_content_type(self, obj: AuditEvent) -> str:
        return obj.resource_label
    
    def get_changed_fields(self, obj: AuditEvent) -> list[str]:
        return obj.changed_fields


# ── Pagination ────────────────────────────────────────────────────────────────

class AuditLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


# ── Views ─────────────────────────────────────────────────────────────────────

@extend_schema(tags=["audit"])
class AuditLogListView(APIView):
    """
    GET /api/v1/audit/logs/

    List audit log entries with filtering.

    Query params:
      actor_id   — UUID of the user who performed the action
      action     — 0=CREATE, 1=UPDATE, 2=DELETE, 3=ACCESS
      app_label  — Django app label (e.g. "patients")
      model      — model name, case-insensitive (e.g. "patient")
      object_pk  — PK of the specific object
      date_from  — ISO 8601 datetime (inclusive lower bound)
      date_to    — ISO 8601 datetime (inclusive upper bound)
    """

    permission_classes = [IsAuthenticated, IsAuditor]

    @extend_schema(
        summary="List audit log entries",
        parameters=[
            OpenApiParameter("actor_id", str, description="Filter by user UUID"),
            OpenApiParameter("action", int, description="0=create,1=update,2=delete,3=access"),
            OpenApiParameter("app_label", str),
            OpenApiParameter("model", str),
            OpenApiParameter("object_pk", str),
            OpenApiParameter("date_from", str, description="ISO 8601 datetime"),
            OpenApiParameter("date_to", str, description="ISO 8601 datetime"),
        ],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        qs = (
            AuditEvent.objects
            .select_related("actor", "content_type")
            .order_by("-timestamp")
        )

        # Filtering
        if actor_id := request.query_params.get("actor_id"):
            qs = qs.filter(actor_id=actor_id)

        if action := request.query_params.get("action"):
            qs = qs.filter(action=action)

        if app_label := request.query_params.get("app_label"):
            qs = qs.filter(content_type__app_label=app_label)

        if model := request.query_params.get("model"):
            qs = qs.filter(content_type__model=model.lower())

        if object_pk := request.query_params.get("object_pk"):
            qs = qs.filter(object_pk=object_pk)

        if date_from := request.query_params.get("date_from"):
            qs = qs.filter(timestamp__gte=date_from)

        if date_to := request.query_params.get("date_to"):
            qs = qs.filter(timestamp__lte=date_to)

        paginator = AuditLogPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AuditEventSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


@extend_schema(tags=["audit"])
class AuditLogDetailView(APIView):
    """GET /api/v1/audit/logs/{id}/ — retrieve a single audit event."""

    permission_classes = [IsAuthenticated, IsAuditor]

    @extend_schema(summary="Retrieve audit audit event")
    def get(self, request: Request, pk: int, *args: Any, **kwargs: Any) -> Response:
        from django.http import Http404
        try:
            entry = AuditEvent.objects.select_related("actor", "content_type").get(pk=pk)
        except AuditEvent.DoesNotExist:
            raise Http404
        return Response(AuditEventSerializer(entry).data)


@extend_schema(tags=["audit"])
class ObjectAuditLogView(APIView):
    """
    GET /api/v1/audit/logs/object/{app_label}/{model}/{object_pk}/

    All audit log entries for a specific object instance.
    Useful for a "history" tab in the UI.
    """

    permission_classes = [IsAuthenticated, IsAuditor]

    @extend_schema(summary="Audit history for a specific object")
    def get(
        self,
        request: Request,
        app_label: str,
        model: str,
        object_pk: str,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        from django.http import Http404
        try:
            ct = ContentType.objects.get(app_label=app_label, model=model.lower())
        except ContentType.DoesNotExist:
            raise Http404

        entries = (
            AuditEvent.objects
            .filter(content_type=ct, object_pk=object_pk)
            .select_related("actor")
            .order_by("-timestamp")
        )
        serializer = AuditEventSerializer(entries, many=True)
        return Response(serializer.data)
