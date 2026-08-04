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
    """Rejeu séquentiel : à la deuxième requête, le profil porte déjà un
    compte en base, donc c'est `resolve_invitation_token` qui détecte le
    rejeu (avant même d'appeler `claim_invitation`). Voir
    `test_claim_invitation_rejoue_sur_le_meme_profil_leve_deja_active` et
    `test_endpoint_activer_traduit_le_rejeu_detecte_par_claim_invitation`
    pour le garde-fou de `claim_invitation` lui-même."""
    jeton = build_invitation_token(profil)
    client = APIClient()
    client.post(ACTIVER, {"token": jeton, "password": MOT_DE_PASSE}, format="json")

    response = client.post(
        ACTIVER, {"token": jeton, "password": MOT_DE_PASSE}, format="json"
    )

    assert response.status_code == 400
    assert "déjà" in str(response.data["error"]["details"]).lower()
    assert User.objects.filter(email=profil.email).count() == 1


def test_endpoint_activer_traduit_le_rejeu_detecte_par_claim_invitation(
    profil, monkeypatch
):
    """Simule la fenêtre de course où deux requêtes concurrentes franchissent
    toutes deux `resolve_invitation_token` avant qu'aucune n'ait acquis le
    compte : c'est alors `claim_invitation` qui détecte le rejeu. Sans
    traduction de son exception dans la vue, ce cas remonterait en 500 au
    lieu d'un 400 propre — exactement le bogue relevé en revue."""
    jeton = build_invitation_token(profil)
    profile_id = profil.pk
    monkeypatch.setattr(
        "apps.alumni.services.resolve_invitation_token",
        lambda token: AlumniProfile.objects.get(pk=profile_id),
    )

    client = APIClient()
    client.post(ACTIVER, {"token": jeton, "password": MOT_DE_PASSE}, format="json")

    response = client.post(
        ACTIVER, {"token": jeton, "password": MOT_DE_PASSE}, format="json"
    )

    assert response.status_code == 400
    assert "déjà" in str(response.data["error"]["details"]).lower()
    assert User.objects.filter(email=profil.email).count() == 1


def test_claim_invitation_rejoue_sur_le_meme_profil_leve_deja_active(profil):
    """Garde-fou propre à `claim_invitation`, indépendant de
    `resolve_invitation_token` : un deuxième appel sur le même profil déjà
    rattaché doit lever `InvitationAlreadyUsed`, pas créer un second compte."""
    claim_invitation(profil, password=MOT_DE_PASSE)

    with pytest.raises(InvitationAlreadyUsed):
        claim_invitation(profil, password=MOT_DE_PASSE)


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


# --- C1 : un profil suspendu ou archivé ne doit ni activer ni se connecter ---


@pytest.mark.django_db
@pytest.mark.parametrize(
    "statut", [AlumniProfile.Status.SUSPENDU, AlumniProfile.Status.ARCHIVE]
)
def test_resolve_invitation_token_refuse_un_profil_non_actif(statut):
    create_roles()
    profil = AlumniProfile.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="awa@example.org",
        promotion=2018,
        status=statut,
    )
    jeton = build_invitation_token(profil)

    with pytest.raises(InvitationInvalid) as exc:
        resolve_invitation_token(jeton)

    # Même message qu'un jeton altéré : ne doit pas révéler qu'une personne a
    # été suspendue ou archivée (§12.3, non-énumération).
    assert str(exc.value) == "Ce lien d'invitation est invalide."


@pytest.mark.django_db
@pytest.mark.parametrize(
    "statut", [AlumniProfile.Status.SUSPENDU, AlumniProfile.Status.ARCHIVE]
)
def test_claim_invitation_refuse_un_profil_non_actif(statut):
    """C'est `claim_invitation`, pas seulement `resolve_invitation_token`, qui
    doit refuser : le statut peut changer entre les deux appels."""
    profil = AlumniProfile.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="awa@example.org",
        promotion=2018,
        status=statut,
    )

    with pytest.raises(InvitationInvalid):
        claim_invitation(profil, password=MOT_DE_PASSE)

    assert User.objects.count() == 0
    profil.refresh_from_db()
    assert profil.user_id is None


@pytest.mark.django_db
@pytest.mark.parametrize("statut", ["suspendu", "archive"])
def test_endpoint_verifier_refuse_un_profil_suspendu_ou_archive(statut, mailoutbox):
    create_roles()
    profil = AlumniProfile.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="awa@example.org",
        promotion=2018,
        status=statut,
    )
    jeton = build_invitation_token(profil)

    response = APIClient().post(VERIFIER, {"token": jeton}, format="json")

    assert response.status_code == 400
    assert response.data["error"]["details"]["token"] == [
        "Ce lien d'invitation est invalide."
    ]
    assert User.objects.count() == 0
    assert len(mailoutbox) == 0


@pytest.mark.django_db
@pytest.mark.parametrize("statut", ["suspendu", "archive"])
def test_endpoint_activer_refuse_un_profil_suspendu_ou_archive(statut, mailoutbox):
    create_roles()
    profil = AlumniProfile.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="awa@example.org",
        promotion=2018,
        status=statut,
    )
    jeton = build_invitation_token(profil)

    response = APIClient().post(
        ACTIVER, {"token": jeton, "password": MOT_DE_PASSE}, format="json"
    )

    assert response.status_code == 400
    assert response.data["error"]["details"]["token"] == [
        "Ce lien d'invitation est invalide."
    ]
    assert User.objects.count() == 0
    profil.refresh_from_db()
    assert profil.user_id is None
    assert len(mailoutbox) == 0


# --- I6 : un compte déjà rattaché à un autre profil ne peut pas être repris ---


@pytest.mark.django_db
def test_claim_invitation_refuse_un_compte_deja_rattache_a_un_autre_profil():
    """L'administrateur modifie l'e-mail du profil A (l'e-mail du compte ne
    suit pas, §PATCH admin) ; un profil B importé porte ensuite l'ancienne
    adresse. Sans le contrôle, `profile.save()` sur B lèverait un
    `IntegrityError` sur la contrainte d'unicité de `user_id`."""
    profil_a = AlumniProfile.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="ancien@example.org",
        promotion=2018,
    )
    compte, _ = claim_invitation(profil_a, password=MOT_DE_PASSE)
    profil_a.email = "nouveau@example.org"
    profil_a.save(update_fields=["email"])

    profil_b = AlumniProfile.objects.create(
        first_name="Kofi",
        last_name="Mensah",
        email="ancien@example.org",
        promotion=2019,
    )

    with pytest.raises(InvitationInvalid):
        claim_invitation(profil_b, password=MOT_DE_PASSE)

    profil_b.refresh_from_db()
    assert profil_b.user_id is None
    profil_a.refresh_from_db()
    assert profil_a.user_id == compte.pk


@pytest.mark.django_db
def test_endpoint_activer_traduit_le_compte_deja_rattache_en_400():
    profil_a = AlumniProfile.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="ancien@example.org",
        promotion=2018,
    )
    claim_invitation(profil_a, password=MOT_DE_PASSE)
    profil_a.email = "nouveau@example.org"
    profil_a.save(update_fields=["email"])

    profil_b = AlumniProfile.objects.create(
        first_name="Kofi",
        last_name="Mensah",
        email="ancien@example.org",
        promotion=2019,
    )
    jeton = build_invitation_token(profil_b)

    response = APIClient().post(
        ACTIVER, {"token": jeton, "password": MOT_DE_PASSE}, format="json"
    )

    assert response.status_code == 400
    assert User.objects.filter(email="ancien@example.org").count() == 1
