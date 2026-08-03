import io

import pytest

from apps.alumni.imports import ImportFormatError, import_alumni, parse_csv
from apps.alumni.models import AlumniProfile

EN_TETE = "email,nom,prenom,promotion"


def _fichier(contenu, encodage="utf-8"):
    return io.BytesIO(contenu.encode(encodage))


def _importer(contenu, **kwargs):
    return import_alumni(
        parse_csv(_fichier(contenu)), uploaded_by=None, filename="test.csv", **kwargs
    )


def test_les_en_tetes_sont_normalises():
    from apps.alumni.imports import normalize_header

    assert normalize_header("  Prénom ") == "prenom"
    assert normalize_header("Programme MCF") == "programme_mcf"
    assert normalize_header("E-MAIL") == "e-mail"


def test_une_colonne_requise_absente_leve_une_erreur_de_format():
    with pytest.raises(ImportFormatError) as exc:
        parse_csv(_fichier("email,nom\nawa@example.org,Doe\n"))

    assert "prenom" in str(exc.value)
    assert "promotion" in str(exc.value)


def test_un_fichier_vide_leve_une_erreur_de_format():
    with pytest.raises(ImportFormatError):
        parse_csv(_fichier(""))


def test_le_separateur_point_virgule_est_accepte():
    lignes = parse_csv(
        _fichier("email;nom;prenom;promotion\nawa@example.org;Doe;Awa;2018\n")
    )

    assert lignes[0][1]["email"] == "awa@example.org"


def test_le_bom_utf8_est_tolere():
    lignes = parse_csv(
        _fichier(f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n", encodage="utf-8-sig")
    )

    assert lignes[0][1]["email"] == "awa@example.org"


def test_les_colonnes_inconnues_sont_ignorees():
    lignes = parse_csv(
        _fichier(f"{EN_TETE},lubie\nawa@example.org,Doe,Awa,2018,xyz\n")
    )

    assert "lubie" in lignes[0][1]  # conservée dans la ligne brute
    assert lignes[0][0] == 2  # la numérotation démarre à la 2e ligne du fichier


@pytest.mark.django_db
def test_un_import_cree_les_profils_valides_directement():
    rapport = _importer(f"{EN_TETE}\nAWA@Example.org,Doe,Awa,2018\n")

    profil = AlumniProfile.objects.get()
    assert profil.email == "awa@example.org"
    assert profil.status == AlumniProfile.Status.ACTIF
    assert profil.source == AlumniProfile.Source.IMPORT
    assert profil.user is None
    assert rapport.rows_total == 1
    assert rapport.rows_created == 1


@pytest.mark.django_db
def test_les_profils_importes_ne_consentent_pas_par_defaut():
    _importer(f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n")

    assert AlumniProfile.objects.get().directory_consent is False
    assert AlumniProfile.objects.in_directory().count() == 0


@pytest.mark.django_db
def test_la_colonne_consentement_est_prise_en_compte():
    _importer(
        f"{EN_TETE},consentement_annuaire\nawa@example.org,Doe,Awa,2018,oui\n"
    )

    assert AlumniProfile.objects.get().directory_consent is True


@pytest.mark.django_db
def test_deux_passes_du_meme_fichier_ne_creent_rien_la_seconde_fois():
    contenu = f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n"

    premier = _importer(contenu)
    second = _importer(contenu)

    assert premier.rows_created == 1
    assert second.rows_created == 0
    assert second.rows_skipped == 1
    assert AlumniProfile.objects.count() == 1


@pytest.mark.django_db
def test_une_seconde_passe_met_a_jour_les_champs_modifies():
    _importer(f"{EN_TETE}\nawa@example.org,Doe,Awa,2018\n")

    rapport = _importer(
        f"{EN_TETE},ville\nawa@example.org,Doe,Awa,2018,Cotonou\n"
    )

    assert rapport.rows_updated == 1
    assert AlumniProfile.objects.get().city == "Cotonou"


@pytest.mark.django_db
def test_une_colonne_vide_n_ecrase_jamais_une_valeur_existante():
    _importer(f"{EN_TETE},ville\nawa@example.org,Doe,Awa,2018,Cotonou\n")

    _importer(f"{EN_TETE},ville\nawa@example.org,Doe,Awa,2018,\n")

    assert AlumniProfile.objects.get().city == "Cotonou"


@pytest.mark.django_db
def test_une_ligne_invalide_est_consignee_sans_bloquer_les_valides():
    rapport = _importer(
        f"{EN_TETE}\n"
        "awa@example.org,Doe,Awa,2018\n"
        "pas-un-email,Mensah,Kofi,2019\n"
        "kofi@example.org,Mensah,Kofi,2019\n"
    )

    assert rapport.rows_total == 3
    assert rapport.rows_created == 2
    assert rapport.rows_failed == 1
    erreur = rapport.errors.get()
    assert erreur.line_number == 3
    assert "e-mail" in erreur.message.lower()
    assert erreur.raw_row["nom"] == "Mensah"
    assert AlumniProfile.objects.count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ligne,fragment",
    [
        ("awa@example.org,Doe,,2018", "prénom"),
        ("awa@example.org,,Awa,2018", "nom"),
        ("awa@example.org,Doe,Awa,mille", "promotion"),
        ("awa@example.org,Doe,Awa,1990", "bornes"),
    ],
)
def test_les_lignes_invalides_portent_un_message_explicite(ligne, fragment):
    rapport = _importer(f"{EN_TETE}\n{ligne}\n")

    assert rapport.rows_failed == 1
    assert fragment in rapport.errors.get().message.lower()


@pytest.mark.django_db
def test_un_secteur_inconnu_est_refuse():
    rapport = _importer(
        f"{EN_TETE},secteur\nawa@example.org,Doe,Awa,2018,astrologie\n"
    )

    assert rapport.rows_failed == 1
    assert "secteur" in rapport.errors.get().message.lower()


@pytest.mark.django_db
def test_un_genre_inconnu_est_refuse():
    rapport = _importer(
        f"{EN_TETE},genre\nawa@example.org,Doe,Awa,2018,extraterrestre\n"
    )

    assert rapport.rows_failed == 1
    assert "genre" in rapport.errors.get().message.lower()


@pytest.mark.django_db
def test_une_date_de_naissance_mal_formee_est_refusee():
    rapport = _importer(
        f"{EN_TETE},date_naissance\nawa@example.org,Doe,Awa,2018,12/04/1995\n"
    )

    assert rapport.rows_failed == 1
    assert "naissance" in rapport.errors.get().message.lower()


@pytest.mark.django_db
def test_un_doublon_dans_le_fichier_garde_la_derniere_occurrence():
    rapport = _importer(
        f"{EN_TETE},ville\n"
        "awa@example.org,Doe,Awa,2018,Cotonou\n"
        "awa@example.org,Doe,Awa,2018,Porto-Novo\n"
    )

    assert AlumniProfile.objects.count() == 1
    assert AlumniProfile.objects.get().city == "Porto-Novo"
    assert rapport.errors.filter(line_number=3).exists()
    assert "avertissement" in rapport.errors.get(line_number=3).message.lower()


@pytest.mark.django_db
def test_les_compteurs_couvrent_toujours_le_total_lu():
    rapport = _importer(
        f"{EN_TETE}\n"
        "awa@example.org,Doe,Awa,2018\n"
        "pas-un-email,Mensah,Kofi,2019\n"
    )

    somme = (
        rapport.rows_created
        + rapport.rows_updated
        + rapport.rows_skipped
        + rapport.rows_failed
    )
    assert somme == rapport.rows_total


@pytest.mark.django_db
def test_le_mode_strict_annule_tout_au_premier_echec():
    rapport = _importer(
        f"{EN_TETE}\n"
        "awa@example.org,Doe,Awa,2018\n"
        "pas-un-email,Mensah,Kofi,2019\n"
        "kofi@example.org,Mensah,Kofi,2019\n",
        strict=True,
    )

    assert AlumniProfile.objects.count() == 0
    assert rapport.rows_created == 0
    assert rapport.rows_updated == 0
    assert rapport.rows_failed == 1
    assert rapport.strict is True


@pytest.mark.django_db
def test_le_rapport_survit_a_l_annulation_du_mode_strict():
    from apps.alumni.models import AlumniImport

    _importer(f"{EN_TETE}\npas-un-email,Doe,Awa,2018\n", strict=True)

    assert AlumniImport.objects.count() == 1
    assert AlumniImport.objects.get().errors.count() == 1


@pytest.mark.django_db
def test_une_valeur_trop_longue_echoue_seule_sans_bloquer_les_lignes_valides():
    from apps.alumni.models import AlumniImport

    ville_trop_longue = "A" * 300
    rapport = _importer(
        f"{EN_TETE},ville\n"
        "awa@example.org,Doe,Awa,2018,Cotonou\n"
        f"trop-long@example.org,Mensah,Kofi,2019,{ville_trop_longue}\n"
        "kofi@example.org,Toure,Aya,2020,Porto-Novo\n"
    )

    assert rapport.rows_total == 3
    assert rapport.rows_created == 2
    assert rapport.rows_failed == 1
    assert AlumniProfile.objects.count() == 2
    assert AlumniProfile.objects.filter(email="awa@example.org").exists()
    assert AlumniProfile.objects.filter(email="kofi@example.org").exists()
    erreur = rapport.errors.get()
    assert erreur.line_number == 3
    assert "ville" in erreur.message.lower()
    assert AlumniImport.objects.filter(pk=rapport.pk).exists()


@pytest.mark.django_db
def test_le_mode_strict_annule_tout_meme_pour_une_erreur_de_base_de_donnees():
    from apps.alumni.models import AlumniImport

    ville_trop_longue = "A" * 300
    rapport = _importer(
        f"{EN_TETE},ville\n"
        "awa@example.org,Doe,Awa,2018,Cotonou\n"
        f"trop-long@example.org,Mensah,Kofi,2019,{ville_trop_longue}\n"
        "kofi@example.org,Toure,Aya,2020,Porto-Novo\n",
        strict=True,
    )

    assert AlumniProfile.objects.count() == 0
    assert rapport.rows_created == 0
    assert rapport.rows_updated == 0
    assert rapport.rows_failed == 1
    assert AlumniImport.objects.filter(pk=rapport.pk).exists()


@pytest.mark.django_db
def test_en_mode_strict_rows_total_ne_couvre_que_les_lignes_lues_avant_l_abandon():
    rapport = _importer(
        f"{EN_TETE}\n"
        "awa@example.org,Doe,Awa,2018\n"
        "pas-un-email,Mensah,Kofi,2019\n"
        "kofi@example.org,Mensah,Kofi,2019\n"
        "aya@example.org,Toure,Aya,2020\n",
        strict=True,
    )

    # La ligne fautive est la 2e ligne de données ; deux lignes valides la
    # suivent dans le fichier mais ne sont jamais lues : l'abandon survient
    # avant. rows_total (2) doit rester strictement inférieur au nombre de
    # lignes de données du fichier (4), preuve qu'il compte les lignes
    # *lues*, pas le fichier entier.
    assert rapport.rows_total == 2
    assert rapport.rows_failed == 1
    assert rapport.rows_created == 0
    assert rapport.rows_updated == 0
    assert rapport.rows_skipped == 0
    assert AlumniProfile.objects.count() == 0


@pytest.mark.django_db
def test_un_rapport_est_cree_meme_quand_le_fichier_ne_contient_aucune_ligne():
    rapport = _importer(f"{EN_TETE}\n")

    assert rapport.rows_total == 0
    assert rapport.pk is not None
