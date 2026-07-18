import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_openapi_schema_is_available():
    client = APIClient()
    response = client.get("/api/v1/schema/?format=json")
    assert response.status_code == 200
    assert response.json()["openapi"].startswith("3")
