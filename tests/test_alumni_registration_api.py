import pytest
from rest_framework.test import APIClient

from apps.alumni.models import AlumniProfile, AlumniRegistration, normalize_email, promotion_max
from apps.alumni.serializers import DOUBLON_MESSAGE, AlumniRegistrationCreateSerializer

URL = "/api/v1/alumni/inscriptions/"

CHARGE = {
    "first_name": "Awa",
    "last_name": "Doe",
    "email": "Awa.DOE@Example.org",
    "promotion": 2018,
    "country": "Bénin",
    "directory_consent": True,
}


@pytest.mark.django_db
def test_une_soumission_valide_cree_une_demande_en_attente():
    response = APIClient().post(URL, CHARGE, format="json")

    assert response.status_code == 201
    demande = AlumniRegistration.objects.get()
    assert demande.status == AlumniRegistration.Status.EN_ATTENTE
    assert demande.email == "awa.doe@example.org"
    assert demande.directory_consent is True


@pytest.mark.django_db
def test_la_soumission_ne_cree_ni_compte_ni_profil():
    APIClient().post(URL, CHARGE, format="json")

    assert AlumniProfile.objects.count() == 0


@pytest.mark.django_db
def test_un_accuse_de_reception_est_envoye(mailoutbox):
    APIClient().post(URL, CHARGE, format="json")

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["awa.doe@example.org"]
    assert "Awa" in mailoutbox[0].body


@pytest.mark.django_db
@pytest.mark.parametrize(
    "champ", ["first_name", "last_name", "email", "promotion"]
)
def test_les_champs_obligatoires_sont_exiges(champ):
    charge = {k: v for k, v in CHARGE.items() if k != champ}
    response = APIClient().post(URL, charge, format="json")

    assert response.status_code == 400
    assert champ in response.data["error"]["details"]


@pytest.mark.django_db
def test_une_promotion_hors_bornes_est_refusee():
    response = APIClient().post(URL, {**CHARGE, "promotion": 1990}, format="json")

    assert response.status_code == 400
    assert "promotion" in response.data["error"]["details"]


@pytest.mark.django_db
def test_une_promotion_superieure_a_la_borne_haute_est_refusee():
    response = APIClient().post(
        URL, {**CHARGE, "promotion": promotion_max() + 1}, format="json"
    )

    assert response.status_code == 400
    assert "promotion" in response.data["error"]["details"]


@pytest.mark.django_db
def test_une_seconde_demande_en_attente_est_refusee_par_un_message_neutre():
    client = APIClient()
    client.post(URL, CHARGE, format="json")
    response = client.post(URL, CHARGE, format="json")

    assert response.status_code == 400
    assert response.data["error"]["details"]["email"] == [
        "Une demande est déjà enregistrée pour cette adresse e-mail."
    ]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "statut",
    [
        AlumniProfile.Status.ACTIF,
        AlumniProfile.Status.SUSPENDU,
        AlumniProfile.Status.ARCHIVE,
    ],
)
def test_un_profil_existant_bloque_la_demande_par_le_meme_message(statut):
    AlumniProfile.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="awa.doe@example.org",
        promotion=2018,
        status=statut,
    )

    response = APIClient().post(URL, CHARGE, format="json")

    assert response.status_code == 400
    assert response.data["error"]["details"]["email"] == [
        "Une demande est déjà enregistrée pour cette adresse e-mail."
    ]


@pytest.mark.django_db
def test_une_nouvelle_demande_est_acceptee_apres_un_rejet():
    client = APIClient()
    client.post(URL, CHARGE, format="json")
    demande = AlumniRegistration.objects.get()
    demande.status = AlumniRegistration.Status.REJETEE
    demande.save()

    assert client.post(URL, CHARGE, format="json").status_code == 201


@pytest.mark.django_db
def test_le_statut_n_est_pas_pilotable_par_le_client():
    APIClient().post(
        URL, {**CHARGE, "status": "approuvee"}, format="json"
    )

    assert (
        AlumniRegistration.objects.get().status
        == AlumniRegistration.Status.EN_ATTENTE
    )


@pytest.mark.django_db
def test_un_doublon_concurrent_est_refuse_par_le_meme_message_neutre(
    monkeypatch, mailoutbox
):
    """Deux soumissions quasi simultanées (double clic, retry sur timeout)
    peuvent toutes deux franchir la vérification applicative de
    `validate_email` avant qu'aucune n'ait été enregistrée. On neutralise
    cette vérification pour de bon (et pas seulement le temps d'une requête)
    afin de forcer la contrainte d'unicité en base à faire foi pour la
    seconde soumission : le message renvoyé doit rester identique au cas
    séquentiel, pour ne rien révéler de la concurrence.
    """
    monkeypatch.setattr(
        AlumniRegistrationCreateSerializer,
        "validate_email",
        lambda self, value: normalize_email(value),
    )
    client = APIClient()
    premiere = client.post(URL, CHARGE, format="json")
    assert premiere.status_code == 201

    response = client.post(URL, CHARGE, format="json")

    assert response.status_code == 400
    assert response.data["error"]["details"]["email"] == [DOUBLON_MESSAGE]
    assert AlumniRegistration.objects.count() == 1
    assert len(mailoutbox) == 1
