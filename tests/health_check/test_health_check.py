import pytest
from rest_framework import status
from rest_framework.test import APIClient

@pytest.mark.django_db
class TestHealthCheckEndpoint:
    URL = "/health-check/"

    def test_health_check_unauthenticated(self, anon_client: APIClient) -> None:
        resp = anon_client.get(self.URL)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.status_code != status.HTTP_503_SERVICE_UNAVAILABLE

