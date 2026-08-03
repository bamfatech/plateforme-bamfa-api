import pytest
from django.db import IntegrityError, transaction

from apps.alumni.models import (
    DEFAULT_COUNTRY,
    AlumniProfile,
    AlumniRegistration,
    normalize_email,
)


def _profil(**kwargs):
    valeurs = {
        "first_name": "Awa",
        "last_name": "Doe",
        "email": "awa@example.org",
        "promotion": 2018,
    }
    valeurs.update(kwargs)
    return AlumniProfile.objects.create(**valeurs)


def _demande(**kwargs):
    valeurs = {
        "first_name": "Kofi",
        "last_name": "Mensah",
        "email": "kofi@example.org",
        "promotion": 2019,
    }
    valeurs.update(kwargs)
    return AlumniRegistration.objects.create(**valeurs)


def test_normalize_email_met_en_minuscules_et_retire_les_espaces():
    assert normalize_email("  Awa.DOE@Example.ORG ") == "awa.doe@example.org"
    assert normalize_email(None) == ""


@pytest.mark.django_db
def test_le_profil_normalise_son_email_a_l_enregistrement():
    profil = _profil(email="  AWA@Example.ORG ")
    profil.refresh_from_db()
    assert profil.email == "awa@example.org"


@pytest.mark.django_db
def test_la_demande_normalise_son_email_a_l_enregistrement():
    demande = _demande(email="KOFI@Example.ORG")
    demande.refresh_from_db()
    assert demande.email == "kofi@example.org"


@pytest.mark.django_db
def test_le_pays_par_defaut_est_le_benin():
    assert _profil().country == DEFAULT_COUNTRY


@pytest.mark.django_db
def test_un_pays_vide_retombe_sur_la_valeur_par_defaut():
    profil = _profil(country="   ")
    profil.refresh_from_db()
    assert profil.country == DEFAULT_COUNTRY


@pytest.mark.django_db
def test_deux_demandes_en_attente_pour_le_meme_email_sont_refusees():
    _demande()
    with pytest.raises(IntegrityError), transaction.atomic():
        _demande()


@pytest.mark.django_db
def test_une_nouvelle_demande_est_possible_apres_un_rejet():
    demande = _demande()
    demande.status = AlumniRegistration.Status.REJETEE
    demande.save()
    assert _demande().pk is not None


@pytest.mark.django_db
def test_completude_nulle_quand_aucun_champ_optionnel_n_est_rempli():
    assert _profil().completeness == 0


@pytest.mark.django_db
def test_completude_totale_quand_tous_les_champs_optionnels_sont_remplis():
    profil = _profil(
        phone="+229 90 00 00 00",
        city="Cotonou",
        university="UAC",
        mcf_program="Scholars",
        sector="numerique",
        current_position="Développeuse",
        organization="BAMFA",
        bio="Courte bio.",
        linkedin_url="https://linkedin.com/in/awa",
        birth_date="1995-04-12",
        gender="femme",
    )
    assert profil.completeness == 100


@pytest.mark.django_db
def test_l_annuaire_ne_retient_que_les_profils_actifs_et_consentants():
    visible = _profil(email="visible@example.org", directory_consent=True)
    _profil(email="sans-consentement@example.org", directory_consent=False)
    _profil(
        email="suspendu@example.org",
        directory_consent=True,
        status=AlumniProfile.Status.SUSPENDU,
    )
    _profil(
        email="archive@example.org",
        directory_consent=True,
        status=AlumniProfile.Status.ARCHIVE,
    )

    assert list(AlumniProfile.objects.in_directory()) == [visible]


@pytest.mark.django_db
def test_un_profil_existe_sans_compte():
    assert _profil().user is None
