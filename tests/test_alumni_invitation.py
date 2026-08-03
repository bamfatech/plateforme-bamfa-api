import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from rest_framework.test import APIClient

from apps.accounts.roles import create_roles
from apps.alumni.models import AlumniProfile
from apps.alumni.services import (
    InvitationAlreadyUsed,
    InvitationExpired,
    InvitationInvalid,
    build_invitation_token,
    claim_invitation,
    resolve_invitation_token,
)

User = get_user_model()
VERIFIER = "/api/v1/alumni/invitation/verifier/"
ACTIVER = "/api/v1/alumni/invitation/activer/"
MOT_DE_PASSE = "un-mot-de-passe-solide-42"


@pytest.fixture
def profil(db):
    create_roles()
    return AlumniProfile.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="awa@example.org",
        promotion=2018,
    )


def test_un_jeton_altere_est_invalide(profil):
    with pytest.raises(InvitationInvalid):
        resolve_invitation_token(build_invitation_token(profil) + "x")


def test_un_jeton_expire_est_detecte(profil, monkeypatch):
    monkeypatch.setattr("apps.alumni.services.INVITATION_MAX_AGE", -1)
    with pytest.raises(InvitationExpired):
        resolve_invitation_token(build_invitation_token(profil))


def test_un_jeton_valide_resout_le_profil(profil):
    assert resolve_invitation_token(build_invitation_token(profil)) == profil


def test_un_jeton_visant_un_profil_inexistant_est_invalide(db):
    jeton = signing.dumps({"profile_id": 999999}, salt="alumni-invitation")
    with pytest.raises(InvitationInvalid):
        resolve_invitation_token(jeton)


def test_le_jeton_devient_inerte_une_fois_le_compte_cree(profil):
    jeton = build_invitation_token(profil)
    claim_invitation(profil, password=MOT_DE_PASSE)

    with pytest.raises(InvitationAlreadyUsed):
        resolve_invitation_token(jeton)


def test_l_activation_cree_le_compte_et_le_role_alumni(profil):
    user, cree = claim_invitation(profil, password=MOT_DE_PASSE)

    profil.refresh_from_db()
    assert cree is True
    assert profil.user == user
    assert user.email == "awa@example.org"
    assert user.check_password(MOT_DE_PASSE) is True
    assert user.is_active is True
    assert list(user.groups.values_list("name", flat=True)) == ["Alumni"]


def test_un_compte_existant_est_rattache_sans_toucher_a_son_mot_de_passe(profil):
    """Le lien d'invitation ne doit jamais permettre de réécrire le mot de
    passe d'un compte déjà en place (un rédacteur, par exemple)."""
    existant = User.objects.create_user(
        email="awa@example.org", password="mot-de-passe-initial"
    )

    user, cree = claim_invitation(profil, password=MOT_DE_PASSE)

    profil.refresh_from_db()
    assert cree is False
    assert user == existant
    assert existant.check_password("mot-de-passe-initial") is True
    assert profil.user == existant


def test_endpoint_verifier_renvoie_l_identite(profil):
    jeton = build_invitation_token(profil)
    response = APIClient().post(VERIFIER, {"token": jeton}, format="json")

    assert response.status_code == 200
    assert response.data == {"first_name": "Awa", "email": "awa@example.org"}


def test_endpoint_verifier_refuse_un_jeton_invalide(profil):
    response = APIClient().post(VERIFIER, {"token": "n-importe-quoi"}, format="json")

    assert response.status_code == 400
    assert "invalide" in str(response.data["error"]["details"]).lower()


def test_endpoint_activer_cree_le_compte(profil):
    jeton = build_invitation_token(profil)
    response = APIClient().post(
        ACTIVER, {"token": jeton, "password": MOT_DE_PASSE}, format="json"
    )

    assert response.status_code == 200
    assert response.data["created"] is True
    profil.refresh_from_db()
    assert profil.user is not None


def test_endpoint_activer_refuse_un_rejeu(profil):
    jeton = build_invitation_token(profil)
    client = APIClient()
    client.post(ACTIVER, {"token": jeton, "password": MOT_DE_PASSE}, format="json")

    response = client.post(
        ACTIVER, {"token": jeton, "password": MOT_DE_PASSE}, format="json"
    )

    assert response.status_code == 400
    assert "déjà" in str(response.data["error"]["details"]).lower()


def test_endpoint_activer_applique_les_validateurs_de_mot_de_passe(profil):
    jeton = build_invitation_token(profil)
    response = APIClient().post(
        ACTIVER, {"token": jeton, "password": "123"}, format="json"
    )

    assert response.status_code == 400
    assert "password" in response.data["error"]["details"]


def test_send_invitation_envoie_un_lien_vers_le_frontend(profil, mailoutbox, settings):
    settings.FRONTEND_BASE_URL = "https://bamfa.example"
    from apps.alumni.services import send_invitation

    send_invitation(profil)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["awa@example.org"]
    assert "https://bamfa.example/alumni/activation?token=" in mailoutbox[0].body
