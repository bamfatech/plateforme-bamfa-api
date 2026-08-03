import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from apps.accounts.roles import create_roles
from apps.alumni.models import AlumniProfile, AlumniRegistration

User = get_user_model()
LISTE = "/api/v1/alumni/admin/inscriptions/"


def _client(role=None):
    create_roles()
    client = APIClient()
    if role is None:
        return client
    user = User.objects.create_user(email=f"{role.lower()}@bamfa.org", password="x")
    user.groups.add(Group.objects.get(name=role))
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def demande(db):
    return AlumniRegistration.objects.create(
        first_name="Awa",
        last_name="Doe",
        email="awa@example.org",
        promotion=2018,
        directory_consent=True,
        city="Cotonou",
        sector="numerique",
    )


@pytest.mark.django_db
def test_l_approbation_cree_un_profil_actif_sans_compte(demande, mailoutbox):
    client = _client("Administrateur")

    response = client.post(f"{LISTE}{demande.pk}/approuver/")

    assert response.status_code == 200
    profil = AlumniProfile.objects.get()
    assert profil.status == AlumniProfile.Status.ACTIF
    assert profil.source == AlumniProfile.Source.INSCRIPTION
    assert profil.user is None
    assert profil.email == "awa@example.org"
    assert profil.city == "Cotonou"
    assert profil.directory_consent is True


@pytest.mark.django_db
def test_l_approbation_trace_l_instruction_et_lie_le_profil(demande):
    client = _client("Administrateur")

    client.post(f"{LISTE}{demande.pk}/approuver/")

    demande.refresh_from_db()
    assert demande.status == AlumniRegistration.Status.APPROUVEE
    assert demande.reviewed_at is not None
    assert demande.reviewed_by.email == "administrateur@bamfa.org"
    assert demande.profile == AlumniProfile.objects.get()


@pytest.mark.django_db
def test_l_approbation_envoie_le_lien_d_invitation(demande, mailoutbox):
    _client("Administrateur").post(f"{LISTE}{demande.pk}/approuver/")

    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["awa@example.org"]
    assert "/alumni/activation?token=" in mailoutbox[0].body


@pytest.mark.django_db
def test_le_rejet_conserve_le_motif_et_ne_cree_rien(demande, mailoutbox):
    client = _client("Administrateur")

    response = client.post(
        f"{LISTE}{demande.pk}/rejeter/",
        {"motif": "Promotion non rattachée à BAMFA."},
        format="json",
    )

    assert response.status_code == 200
    demande.refresh_from_db()
    assert demande.status == AlumniRegistration.Status.REJETEE
    assert demande.rejection_reason == "Promotion non rattachée à BAMFA."
    assert demande.reviewed_by is not None
    assert demande.reviewed_at is not None
    assert AlumniProfile.objects.count() == 0
    assert User.objects.filter(email="awa@example.org").count() == 0


@pytest.mark.django_db
def test_le_rejet_notifie_le_demandeur_avec_le_motif(demande, mailoutbox):
    _client("Administrateur").post(
        f"{LISTE}{demande.pk}/rejeter/", {"motif": "Dossier incomplet."}, format="json"
    )

    assert len(mailoutbox) == 1
    assert "Dossier incomplet." in mailoutbox[0].body


@pytest.mark.django_db
def test_le_rejet_sans_motif_est_accepte(demande, mailoutbox):
    response = _client("Administrateur").post(f"{LISTE}{demande.pk}/rejeter/")

    assert response.status_code == 200
    demande.refresh_from_db()
    assert demande.rejection_reason == ""


@pytest.mark.django_db
def test_une_demande_deja_instruite_ne_peut_pas_etre_reinstruite(demande):
    client = _client("Administrateur")
    client.post(f"{LISTE}{demande.pk}/approuver/")

    response = client.post(f"{LISTE}{demande.pk}/approuver/")

    assert response.status_code == 400
    assert AlumniProfile.objects.count() == 1


@pytest.mark.django_db
def test_la_secretaire_lit_la_file_mais_ne_peut_pas_approuver(demande):
    client = _client("Secrétaire")

    assert client.get(LISTE).status_code == 200
    assert client.post(f"{LISTE}{demande.pk}/approuver/").status_code == 403
    assert client.post(f"{LISTE}{demande.pk}/rejeter/").status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["Alumni", "Rédacteur de contenu", "Trésorier"])
def test_les_autres_roles_n_ont_aucun_acces(demande, role):
    client = _client(role)

    assert client.get(LISTE).status_code == 403
    assert client.post(f"{LISTE}{demande.pk}/approuver/").status_code == 403


@pytest.mark.django_db
def test_un_anonyme_est_refuse(demande):
    client = _client()

    assert client.get(LISTE).status_code in (401, 403)
    assert client.post(f"{LISTE}{demande.pk}/approuver/").status_code in (401, 403)


@pytest.mark.django_db
def test_la_file_est_filtrable_par_statut(demande):
    AlumniRegistration.objects.create(
        first_name="Kofi",
        last_name="Mensah",
        email="kofi@example.org",
        promotion=2019,
        status=AlumniRegistration.Status.REJETEE,
    )
    client = _client("Administrateur")

    response = client.get(LISTE, {"statut": "en_attente"})

    assert response.data["count"] == 1
    assert response.data["results"][0]["email"] == "awa@example.org"
