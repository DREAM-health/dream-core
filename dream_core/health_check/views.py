import logging
from django.http import JsonResponse
from django.db import connections
from django.db.utils import OperationalError
from django.core.cache import cache


logger = logging.getLogger(__name__)


def health_check_view(request):
    """
    Comprehensive infrastructure health check.
    Returns 200 if all critical systems are up.
    Returns 503 if any critical system is down.
    """
    health_status = {
        "status": "healthy",
        "components": {
            "postgresql": "unhealthy",
        }
    }
    http_status = 200

    try:
        db_conn = connections['default']
        db_conn.cursor() # forces Django to ensure the connection is alive
        health_status["components"]["postgresql"] = "healthy"
    except OperationalError as e:
        logger.critical(f"Health Check Failed: Database unreachable - {e}")
        health_status["status"] = "unhealthy"
        http_status = 503

    return JsonResponse(health_status, status=http_status)