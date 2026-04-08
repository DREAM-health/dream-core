"""
dream_core/audit/middlewares/facilities.py

Injects the requesting user's primary facility_id into django-auditlog's
`additional_data` for every audited mutation in the request lifecycle.

This makes AuditEvent.objects.for_facility() functional in Phase 2.

Must be placed AFTER AuditlogMiddleware in MIDDLEWARE so the auditlog
request context is already initialised when we augment it.
"""
from __future__ import annotations

from typing import Any, Callable

from django.http import HttpRequest, HttpResponse


class FacilityAuditMiddleware:
    """
    Augments auditlog's per-request context with the user's primary facility_id.

    auditlog stores `additional_data` at LogEntry creation time by reading
    from the thread-local set up by AuditlogMiddleware. We extend that
    thread-local with facility_id so every subsequent LogEntry in this
    request carries it automatically.

    Implementation note: auditlog exposes `auditlog.context` as a
    thread-local context manager. We push facility_id there so it is
    merged into `additional_data` on every LogEntry.save() call within
    this request.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self._inject_facility(request)
        return self.get_response(request)

    def _inject_facility(self, request: HttpRequest) -> None:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return

        from dream_core.facilities.models import FacilityMembership

        membership = (
            FacilityMembership.objects
            .filter(user=user, is_primary=True)
            .values_list("facility_id", flat=True)
            .first()
        )
        if membership is None:
            membership = (
                FacilityMembership.objects
                .filter(user=user)
                .values_list("facility_id", flat=True)
                .first()
            )

        if membership is not None:
            # auditlog thread-local stores extra data merged into
            # additional_data on every LogEntry write.
            import auditlog.context as _ctx 
            existing: dict[str, Any] = getattr(_ctx._thread_local, "auditlog", {})
            if isinstance(existing, dict):
                existing.setdefault("extra", {})["facility_id"] = str(membership)
                _ctx._thread_local.auditlog = existing

        # TODO: Review options in case of middleware exception.
        # except Exception:
        #     # Never block a request due to audit middleware failure.
        #     pass