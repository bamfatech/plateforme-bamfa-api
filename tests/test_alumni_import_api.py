import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.roles import create_roles
from apps.alumni.models import AlumniImport, AlumniProfile

User = get_user_model()
URL = "/api/v1/alumni/admin/imports/"
EN_TETE = "email,nom,prenom,promotion"


def _client(role=None):
    create_roles()
    client = APIClient()
    if role is None:
        return client
    user = User.objects.create_user(email=f"{role.lower()}@bamfa.org", password="x")
    user.groups.add(Group.objects.get(name=role))
    client.force_authenticate(user=user)
    return client


def _fichier(contenu, nom="alumni.csv"):
    return SimpleUploadedFile(nom, contenu.encode("utf-8"), content_type="text/csv")


@pytest.mark.django_db
def test_un_administrateur_importe_un_fichier():
    response = _client("Administrateur").post(
        URL,
        {"fichier": _fichier(f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n")},
        format="multipart",
    )

    assert response.status_code == 201
    assert response.data["rows_created"] == 1
    assert response.data["filename"] == "alumni.csv"
    assert AlumniProfile.objects.count() == 1


@pytest.mark.django_db
def test_la_secretaire_peut_importer():
    response = _client("Secrétaire").post(
        URL,
        {"fichier": _fichier(f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n")},
        format="multipart",
    )

    assert response.status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["Alumni", "Rédacteur de contenu", "Trésorier"])
def test_les_autres_roles_ne_peuvent_pas_importer(role):
    response = _client(role).post(
        URL,
        {"fichier": _fichier(f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n")},
        format="multipart",
    )

    assert response.status_code == 403
    assert AlumniProfile.objects.count() == 0


@pytest.mark.django_db
def test_un_anonyme_ne_peut_pas_importer():
    response = _client().post(
        URL,
        {"fichier": _fichier(f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n")},
        format="multipart",
    )

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_l_import_trace_son_auteur():
    _client("Administrateur").post(
        URL,
        {"fichier": _fichier(f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n")},
        format="multipart",
    )

    assert AlumniImport.objects.get().uploaded_by.email == "administrateur@bamfa.org"


@pytest.mark.django_db
def test_une_colonne_requise_absente_renvoie_400_sans_rien_ecrire():
    response = _client("Administrateur").post(
        URL, {"fichier": _fichier("email,nom\nawa@example.org,Doe\n")}, format="multipart"
    )

    assert response.status_code == 400
    assert "fichier" in response.data["error"]["details"]
    assert AlumniProfile.objects.count() == 0
    assert AlumniImport.objects.count() == 0


@pytest.mark.django_db
def test_le_fichier_est_obligatoire():
    response = _client("Administrateur").post(URL, {}, format="multipart")

    assert response.status_code == 400
    assert "fichier" in response.data["error"]["details"]


@pytest.mark.django_db
def test_le_rapport_expose_les_lignes_en_erreur():
    response = _client("Administrateur").post(
        URL,
        {
            "fichier": _fichier(
                f"{EN_TETE}\n"
                "awa@example.org,Doe,Awa,2018\n"
                "pas-un-email,Mensah,Kofi,2019\n"
            )
        },
        format="multipart",
    )

    assert response.data["rows_created"] == 1
    assert response.data["rows_failed"] == 1
    assert len(response.data["errors"]) == 1
    assert response.data["errors"][0]["line_number"] == 3
    assert response.data["errors"][0]["raw_row"]["nom"] == "Mensah"


@pytest.mark.django_db
def test_le_mode_strict_est_transmis():
    response = _client("Administrateur").post(
        URL,
        {
            "fichier": _fichier(
                f"{EN_TETE}\n"
                "awa@example.org,Doe,Awa,2018\n"
                "pas-un-email,Mensah,Kofi,2019\n"
            ),
            "strict": "true",
        },
        format="multipart",
    )

    assert response.data["strict"] is True
    assert response.data["rows_created"] == 0
    assert AlumniProfile.objects.count() == 0


@pytest.mark.django_db
def test_l_historique_liste_les_rapports_du_plus_recent_au_plus_ancien():
    client = _client("Administrateur")
    client.post(
        URL,
        {"fichier": _fichier(f"{EN_TETE}\na@example.org,Doe,Awa,2018\n", "premier.csv")},
        format="multipart",
    )
    client.post(
        URL,
        {"fichier": _fichier(f"{EN_TETE}\nb@example.org,Doe,Awa,2018\n", "second.csv")},
        format="multipart",
    )

    response = client.get(URL)

    assert response.data["count"] == 2
    assert response.data["results"][0]["filename"] == "second.csv"


@pytest.mark.django_db
def test_le_detail_d_un_rapport_est_consultable():
    client = _client("Administrateur")
    creation = client.post(
        URL,
        {"fichier": _fichier(f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n")},
        format="multipart",
    )

    response = client.get(f"{URL}{creation.data['id']}/")

    assert response.status_code == 200
    assert response.data["rows_total"] == 1
