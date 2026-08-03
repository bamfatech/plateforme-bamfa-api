import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.accounts.roles import create_roles
from apps.alumni.models import AlumniProfile

User = get_user_model()
URL = "/api/v1/alumni/annuaire/"

CHAMPS_PRIVES = ("email", "phone")
CHAMPS_ENRICHIS = ("city", "bio", "linkedin_url")


def _profil(**kwargs):
    valeurs = {
        "first_name": "Awa",
        "last_name": "Doe",
        "email": "awa@example.org",
        "promotion": 2018,
        "directory_consent": True,
        "phone": "+229 90 00 00 00",
        "city": "Cotonou",
        "bio": "Développeuse.",
        "linkedin_url": "https://linkedin.com/in/awa",
        "sector": "numerique",
        "country": "Bénin",
        "organization": "BAMFA",
        "current_position": "Développeuse",
    }
    valeurs.update(kwargs)
    return AlumniProfile.objects.create(**valeurs)


def _client_avec_role(role):
    create_roles()
    user = User.objects.create_user(email=f"{role.lower()}@bamfa.org", password="x")
    user.groups.add(Group.objects.get(name=role))
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_l_annuaire_public_masque_email_et_telephone():
    _profil()

    entree = APIClient().get(URL).data["results"][0]

    for champ in CHAMPS_PRIVES:
        assert champ not in entree


@pytest.mark.django_db
def test_l_annuaire_public_n_expose_pas_les_champs_enrichis():
    _profil()

    entree = APIClient().get(URL).data["results"][0]

    for champ in CHAMPS_ENRICHIS:
        assert champ not in entree


@pytest.mark.django_db
def test_l_annuaire_public_expose_les_champs_de_presentation():
    _profil()

    entree = APIClient().get(URL).data["results"][0]

    assert entree["first_name"] == "Awa"
    assert entree["last_name"] == "Doe"
    assert entree["promotion"] == 2018
    assert entree["sector_display"] == "Technologies et numérique"
    assert entree["country"] == "Bénin"
    assert entree["organization"] == "BAMFA"
    assert entree["current_position"] == "Développeuse"


@pytest.mark.django_db
def test_un_alumni_connecte_voit_les_champs_enrichis_mais_pas_les_prives():
    _profil()
    client = _client_avec_role("Alumni")

    entree = client.get(URL).data["results"][0]

    for champ in CHAMPS_ENRICHIS:
        assert champ in entree
    for champ in CHAMPS_PRIVES:
        assert champ not in entree


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["Rédacteur de contenu", "Trésorier"])
def test_un_role_non_habilite_reste_au_niveau_public(role):
    _profil()
    client = _client_avec_role(role)

    entree = client.get(URL).data["results"][0]

    assert "city" not in entree


@pytest.mark.django_db
def test_l_annuaire_exclut_les_profils_sans_consentement():
    _profil(email="visible@example.org")
    _profil(email="cache@example.org", directory_consent=False)

    response = APIClient().get(URL)

    assert response.data["count"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize(
    "statut", [AlumniProfile.Status.SUSPENDU, AlumniProfile.Status.ARCHIVE]
)
def test_l_annuaire_exclut_les_profils_non_actifs(statut):
    _profil(email="hors@example.org", status=statut)

    assert APIClient().get(URL).data["count"] == 0


@pytest.mark.django_db
def test_le_detail_applique_les_memes_regles_de_champs():
    profil = _profil()

    entree = APIClient().get(f"{URL}{profil.pk}/").data

    assert entree["first_name"] == "Awa"
    for champ in CHAMPS_PRIVES + CHAMPS_ENRICHIS:
        assert champ not in entree


@pytest.mark.django_db
def test_le_detail_d_un_profil_hors_annuaire_est_introuvable():
    profil = _profil(directory_consent=False)

    assert APIClient().get(f"{URL}{profil.pk}/").status_code == 404


@pytest.mark.django_db
def test_filtrage_par_promotion_secteur_et_pays():
    _profil(email="a@example.org", promotion=2018, sector="numerique", country="Bénin")
    _profil(email="b@example.org", promotion=2020, sector="sante", country="Togo")
    client = APIClient()

    assert client.get(URL, {"promotion": 2018}).data["count"] == 1
    assert client.get(URL, {"secteur": "sante"}).data["count"] == 1
    assert client.get(URL, {"pays": "togo"}).data["count"] == 1


@pytest.mark.django_db
def test_recherche_sur_nom_organisation_et_poste():
    _profil(email="a@example.org", last_name="Mensah", organization="ONG Espoir")
    _profil(email="b@example.org", last_name="Doe", organization="BAMFA")
    client = APIClient()

    assert client.get(URL, {"search": "Mensah"}).data["count"] == 1
    assert client.get(URL, {"search": "Espoir"}).data["count"] == 1


@pytest.mark.django_db
def test_l_annuaire_est_pagine():
    for index in range(25):
        _profil(email=f"alumni{index}@example.org", last_name=f"Nom{index:02d}")

    response = APIClient().get(URL)

    assert response.data["count"] == 25
    assert len(response.data["results"]) == 20
    assert response.data["next"] is not None
