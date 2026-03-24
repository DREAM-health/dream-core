from django.urls import path
from dream_core.audit.views import AuditLogDetailView, AuditLogListView, ObjectAuditLogView

urlpatterns = [
    path("logs/", AuditLogListView.as_view(), name="audit-log-list"),
    path("logs/<int:pk>/", AuditLogDetailView.as_view(), name="audit-log-detail"),
    path(
        "logs/object/<str:app_label>/<str:model>/<str:object_pk>/",
        ObjectAuditLogView.as_view(),
        name="audit-log-object",
    ),
]
