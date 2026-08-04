import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_openapi_schema_is_available():
    client = APIClient()
    response = client.get("/api/v1/schema/?format=json")
    assert response.status_code == 200
    assert response.json()["openapi"].startswith("3")


@pytest.mark.django_db
def test_le_schema_expose_les_endpoints_alumni():
    from rest_framework.test import APIClient

    schema = APIClient().get("/api/v1/schema/?format=json").json()
    chemins = schema["paths"]

    for chemin in [
        "/api/v1/alumni/inscriptions/",
        "/api/v1/alumni/annuaire/",
        "/api/v1/alumni/invitation/verifier/",
        "/api/v1/alumni/invitation/activer/",
        "/api/v1/alumni/moi/",
        "/api/v1/alumni/admin/inscriptions/",
        "/api/v1/alumni/admin/profils/",
        "/api/v1/alumni/admin/imports/",
    ]:
        assert chemin in chemins, f"{chemin} absent du schéma"


@pytest.mark.django_db
def test_les_actions_alumni_sont_documentees():
    from rest_framework.test import APIClient

    schema = APIClient().get("/api/v1/schema/?format=json").json()

    for chemin in [
        "/api/v1/alumni/admin/inscriptions/{id}/approuver/",
        "/api/v1/alumni/admin/inscriptions/{id}/rejeter/",
        "/api/v1/alumni/admin/profils/{id}/suspendre/",
        "/api/v1/alumni/admin/profils/{id}/reactiver/",
        "/api/v1/alumni/admin/profils/{id}/archiver/",
        "/api/v1/alumni/admin/profils/{id}/inviter/",
    ]:
        assert chemin in schema["paths"], f"{chemin} absent du schéma"
