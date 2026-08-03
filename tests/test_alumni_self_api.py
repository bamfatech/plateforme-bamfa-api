import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.accounts.roles import create_roles
from apps.alumni.models import AlumniProfile

User = get_user_model()
URL = "/api/v1/alumni/moi/"


@pytest.fixture
def alumni(db):
    create_roles()
    user = User.objects.create_user(email="awa@example.org", password="x")
    user.groups.add(Group.objects.get(name="Alumni"))
    profil = AlumniProfile.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="awa@example.org",
        promotion=2018,
        user=user,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client, profil


@pytest.mark.django_db
def test_un_alumni_lit_son_profil(alumni):
    client, _profil = alumni

    response = client.get(URL)

    assert response.status_code == 200
    assert response.data["email"] == "awa@example.org"
    assert response.data["completeness"] == 0


@pytest.mark.django_db
def test_un_alumni_modifie_ses_coordonnees_et_son_consentement(alumni):
    client, profil = alumni

    response = client.patch(
        URL,
        {
            "city": "Cotonou",
            "bio": "Développeuse.",
            "sector": "numerique",
            "directory_consent": True,
        },
        format="json",
    )

    assert response.status_code == 200
    profil.refresh_from_db()
    assert profil.city == "Cotonou"
    assert profil.bio == "Développeuse."
    assert profil.directory_consent is True


@pytest.mark.django_db
def test_la_completude_progresse_avec_les_champs_remplis(alumni):
    client, _profil = alumni

    response = client.patch(URL, {"city": "Cotonou"}, format="json")

    assert response.data["completeness"] > 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "champ,valeur",
    [("email", "autre@example.org"), ("promotion", 2000), ("status", "suspendu")],
)
def test_les_champs_reserves_a_l_administration_ne_sont_pas_modifiables(
    alumni, champ, valeur
):
    client, profil = alumni
    avant = getattr(profil, champ)

    client.patch(URL, {champ: valeur}, format="json")

    profil.refresh_from_db()
    assert getattr(profil, champ) == avant


@pytest.mark.django_db
def test_un_compte_sans_profil_alumni_recoit_404(db):
    user = User.objects.create_user(email="redacteur@bamfa.org", password="x")
    client = APIClient()
    client.force_authenticate(user=user)

    assert client.get(URL).status_code == 404


@pytest.mark.django_db
def test_un_anonyme_est_refuse(db):
    assert APIClient().get(URL).status_code in (401, 403)


@pytest.mark.django_db
def test_le_profil_d_autrui_est_inatteignable(alumni):
    """L'endpoint n'expose aucun identifiant : le périmètre est porté par le
    queryset, filtré sur `user=request.user`."""
    client, profil = alumni
    autre = AlumniProfile.objects.create(
        first_name="Kofi",
        last_name="Mensah",
        email="kofi@example.org",
        promotion=2019,
    )

    response = client.get(URL)

    assert response.data["id"] == profil.pk
    assert response.data["id"] != autre.pk
