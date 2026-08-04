import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.accounts.roles import create_roles
from apps.alumni.models import AlumniProfile

User = get_user_model()
LISTE = "/api/v1/alumni/admin/profils/"


def _client(role=None):
    create_roles()
    client = APIClient()
    if role is None:
        return client
    user = User.objects.create_user(email=f"{role.lower()}@bamfa.org", password="x")
    user.groups.add(Group.objects.get(name=role))
    client.force_authenticate(user=user)
    return client


def _profil(**kwargs):
    valeurs = {
        "first_name": "Awa",
        "last_name": "Doe",
        "email": "awa@example.org",
        "promotion": 2018,
        "phone": "+229 90 00 00 00",
    }
    valeurs.update(kwargs)
    return AlumniProfile.objects.create(**valeurs)


@pytest.mark.django_db
def test_l_administration_voit_email_telephone_et_completude():
    _profil()

    entree = _client("Administrateur").get(LISTE).data["results"][0]

    assert entree["email"] == "awa@example.org"
    assert entree["phone"] == "+229 90 00 00 00"
    assert "completeness" in entree
    assert entree["has_account"] is False


@pytest.mark.django_db
def test_l_administration_voit_les_profils_sans_consentement_et_non_actifs():
    _profil(email="a@example.org", directory_consent=False)
    _profil(email="b@example.org", status=AlumniProfile.Status.SUSPENDU)
    _profil(email="c@example.org", status=AlumniProfile.Status.ARCHIVE)

    assert _client("Administrateur").get(LISTE).data["count"] == 3


@pytest.mark.django_db
def test_la_secretaire_lit_mais_ne_modifie_pas():
    profil = _profil()
    client = _client("Secrétaire")

    assert client.get(LISTE).status_code == 200
    assert (
        client.patch(f"{LISTE}{profil.pk}/", {"city": "Cotonou"}, format="json").status_code
        == 403
    )
    assert client.post(f"{LISTE}{profil.pk}/suspendre/").status_code == 403
    assert client.post(f"{LISTE}{profil.pk}/reactiver/").status_code == 403
    assert client.post(f"{LISTE}{profil.pk}/archiver/").status_code == 403
    assert client.post(f"{LISTE}{profil.pk}/inviter/").status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["Alumni", "Rédacteur de contenu", "Trésorier"])
def test_les_autres_roles_n_ont_aucun_acces(role):
    profil = _profil()
    client = _client(role)

    assert client.get(LISTE).status_code == 403
    assert client.post(f"{LISTE}{profil.pk}/suspendre/").status_code == 403


@pytest.mark.django_db
def test_un_anonyme_est_refuse():
    profil = _profil()
    client = _client()

    assert client.get(LISTE).status_code in (401, 403)
    assert client.post(f"{LISTE}{profil.pk}/suspendre/").status_code in (401, 403)
    assert client.post(f"{LISTE}{profil.pk}/reactiver/").status_code in (401, 403)
    assert client.post(f"{LISTE}{profil.pk}/archiver/").status_code in (401, 403)
    assert client.post(f"{LISTE}{profil.pk}/inviter/").status_code in (401, 403)


@pytest.mark.django_db
def test_patch_modifie_un_profil():
    profil = _profil()

    response = _client("Administrateur").patch(
        f"{LISTE}{profil.pk}/",
        {"city": "Cotonou", "sector": "numerique", "directory_consent": True},
        format="json",
    )

    assert response.status_code == 200
    profil.refresh_from_db()
    assert profil.city == "Cotonou"
    assert profil.sector == "numerique"
    assert profil.directory_consent is True


@pytest.mark.django_db
def test_patch_ne_peut_pas_changer_le_statut():
    profil = _profil()

    _client("Administrateur").patch(
        f"{LISTE}{profil.pk}/", {"status": "suspendu"}, format="json"
    )

    profil.refresh_from_db()
    assert profil.status == AlumniProfile.Status.ACTIF


@pytest.mark.django_db
def test_la_suspension_desactive_le_compte():
    profil = _profil()
    user = User.objects.create_user(email="awa@example.org", password="x")
    profil.user = user
    profil.save()

    response = _client("Administrateur").post(f"{LISTE}{profil.pk}/suspendre/")

    assert response.status_code == 200
    profil.refresh_from_db()
    user.refresh_from_db()
    assert profil.status == AlumniProfile.Status.SUSPENDU
    assert user.is_active is False


@pytest.mark.django_db
def test_la_suspension_bloque_l_authentification_par_jeton():
    """SimpleJWT refuse un utilisateur inactif : la suspension prend effet à la
    requête suivante, sans mise en liste noire des jetons.

    Le contrôle passe par un vrai jeton dans le cookie (et non
    `force_authenticate`, qui court-circuite l'authentification et ne
    prouverait rien) et par `/auth/me/`, livré en S1 — la vue est donc
    indépendante des tâches suivantes.
    """
    from django.conf import settings
    from rest_framework_simplejwt.tokens import RefreshToken

    create_roles()
    user = User.objects.create_user(email="awa@example.org", password="x")
    user.groups.add(Group.objects.get(name="Alumni"))
    profil = _profil(user=user)

    client = APIClient()
    client.cookies[settings.AUTH_COOKIE] = str(RefreshToken.for_user(user).access_token)
    assert client.get("/api/v1/auth/me/").status_code == 200

    _client("Administrateur").post(f"{LISTE}{profil.pk}/suspendre/")

    assert client.get("/api/v1/auth/me/").status_code == 401


@pytest.mark.django_db
def test_la_reactivation_reactive_le_compte():
    user = User.objects.create_user(email="awa@example.org", password="x")
    user.is_active = False
    user.save()
    profil = _profil(user=user, status=AlumniProfile.Status.SUSPENDU)

    _client("Administrateur").post(f"{LISTE}{profil.pk}/reactiver/")

    profil.refresh_from_db()
    user.refresh_from_db()
    assert profil.status == AlumniProfile.Status.ACTIF
    assert user.is_active is True


@pytest.mark.django_db
def test_la_reactivation_depuis_archive_reactive_le_compte():
    """Le diagramme d'états autorise `archive -> actif` : à vérifier
    séparément de la réactivation depuis `suspendu`."""
    user = User.objects.create_user(email="awa@example.org", password="x")
    user.is_active = False
    user.save()
    profil = _profil(user=user, status=AlumniProfile.Status.ARCHIVE)

    _client("Administrateur").post(f"{LISTE}{profil.pk}/reactiver/")

    profil.refresh_from_db()
    user.refresh_from_db()
    assert profil.status == AlumniProfile.Status.ACTIF
    assert user.is_active is True


@pytest.mark.django_db
def test_l_archivage_masque_le_profil_et_conserve_les_donnees():
    user = User.objects.create_user(email="awa@example.org", password="x")
    profil = _profil(directory_consent=True, user=user)

    _client("Administrateur").post(f"{LISTE}{profil.pk}/archiver/")

    profil.refresh_from_db()
    user.refresh_from_db()
    assert profil.status == AlumniProfile.Status.ARCHIVE
    assert profil.email == "awa@example.org"
    assert user.is_active is False
    assert AlumniProfile.objects.in_directory().count() == 0


@pytest.mark.django_db
def test_l_action_inviter_envoie_le_lien(mailoutbox):
    profil = _profil()

    response = _client("Administrateur").post(f"{LISTE}{profil.pk}/inviter/")

    assert response.status_code == 200
    assert len(mailoutbox) == 1
    assert "/alumni/activation?token=" in mailoutbox[0].body


@pytest.mark.django_db
def test_inviter_un_profil_qui_a_deja_un_compte_est_refuse(mailoutbox):
    user = User.objects.create_user(email="awa@example.org", password="x")
    profil = _profil(user=user)

    response = _client("Administrateur").post(f"{LISTE}{profil.pk}/inviter/")

    assert response.status_code == 400
    assert len(mailoutbox) == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "statut", [AlumniProfile.Status.SUSPENDU, AlumniProfile.Status.ARCHIVE]
)
def test_inviter_un_profil_suspendu_ou_archive_est_refuse(statut, mailoutbox):
    """C1 : ni le bouton front ni l'API ne doivent laisser inviter un profil
    qui n'est plus actif — sans quoi il pourrait activer un compte et se
    connecter malgré la suspension ou l'archivage."""
    profil = _profil(status=statut)

    response = _client("Administrateur").post(f"{LISTE}{profil.pk}/inviter/")

    assert response.status_code == 400
    assert len(mailoutbox) == 0
    assert User.objects.filter(email=profil.email).count() == 0


@pytest.mark.django_db
def test_filtre_a_un_compte():
    user = User.objects.create_user(email="avec@example.org", password="x")
    _profil(email="avec@example.org", user=user)
    _profil(email="sans@example.org")
    client = _client("Administrateur")

    assert client.get(LISTE, {"a_un_compte": "true"}).data["count"] == 1
    assert (
        client.get(LISTE, {"a_un_compte": "true"}).data["results"][0]["email"]
        == "avec@example.org"
    )
    assert client.get(LISTE, {"a_un_compte": "false"}).data["count"] == 1
    assert (
        client.get(LISTE, {"a_un_compte": "false"}).data["results"][0]["email"]
        == "sans@example.org"
    )


@pytest.mark.django_db
def test_filtres_statut_consentement_promotion_et_recherche_email():
    _profil(
        email="a@example.org",
        promotion=2018,
        directory_consent=True,
        sector="numerique",
        country="Bénin",
    )
    _profil(
        email="b@example.org",
        promotion=2020,
        status=AlumniProfile.Status.SUSPENDU,
        sector="sante",
        country="France",
    )
    client = _client("Administrateur")

    assert client.get(LISTE, {"statut": "suspendu"}).data["count"] == 1
    assert client.get(LISTE, {"consentement": "true"}).data["count"] == 1
    assert client.get(LISTE, {"promotion": 2020}).data["count"] == 1
    assert client.get(LISTE, {"search": "b@example.org"}).data["count"] == 1
    assert client.get(LISTE, {"secteur": "numerique"}).data["count"] == 1
    assert (
        client.get(LISTE, {"secteur": "numerique"}).data["results"][0]["email"]
        == "a@example.org"
    )
    # `pays` est en `iexact` : une casse différente doit tout de même matcher.
    assert client.get(LISTE, {"pays": "FRANCE"}).data["count"] == 1
    assert (
        client.get(LISTE, {"pays": "FRANCE"}).data["results"][0]["email"]
        == "b@example.org"
    )
