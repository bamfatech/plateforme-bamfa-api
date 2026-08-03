import csv
import io
import re
import unicodedata
from datetime import date

from django.db import transaction

from .models import (
    PROMOTION_MIN,
    AlumniImport,
    AlumniImportError,
    AlumniProfile,
    Gender,
    Sector,
    normalize_email,
    promotion_max,
)

REQUIRED_COLUMNS = ("email", "nom", "prenom", "promotion")

# Colonnes du fichier → champs du modèle.
COLUMN_TO_FIELD = {
    "email": "email",
    "nom": "last_name",
    "prenom": "first_name",
    "promotion": "promotion",
    "pays": "country",
    "telephone": "phone",
    "ville": "city",
    "universite": "university",
    "programme_mcf": "mcf_program",
    "secteur": "sector",
    "poste": "current_position",
    "organisation": "organization",
    "bio": "bio",
    "linkedin": "linkedin_url",
    "date_naissance": "birth_date",
    "genre": "gender",
    "consentement_annuaire": "directory_consent",
}

VALEURS_VRAIES = {"1", "true", "vrai", "oui", "yes", "x"}


class ImportFormatError(Exception):
    """Le fichier lui-même est inexploitable : rien n'est écrit."""


class _StrictAbort(Exception):
    """Signal interne : annule la transaction en mode strict."""


def normalize_header(name):
    """Minuscules, espaces retirés, accents supprimés, espaces internes en `_`."""
    texte = unicodedata.normalize("NFKD", (name or "").strip().lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"\s+", "_", texte)


def parse_csv(uploaded_file):
    """Adaptateur CSV → lignes normalisées `[(numéro_de_ligne, dict), ...]`.

    Renvoie une liste et non un générateur : les en-têtes sont ainsi validés
    **avant** que le cœur d'import n'écrive quoi que ce soit.
    """
    brut = uploaded_file.read()
    texte = brut.decode("utf-8-sig") if isinstance(brut, bytes) else brut

    try:
        delimiteur = csv.Sniffer().sniff(texte[:4096], delimiters=",;").delimiter
    except csv.Error:
        delimiteur = ","

    lecteur = csv.DictReader(io.StringIO(texte), delimiter=delimiteur)
    if not lecteur.fieldnames:
        raise ImportFormatError("Le fichier est vide ou n'a pas d'en-tête.")

    en_tetes = [normalize_header(nom) for nom in lecteur.fieldnames]
    manquantes = [col for col in REQUIRED_COLUMNS if col not in en_tetes]
    if manquantes:
        raise ImportFormatError(
            "Colonnes requises absentes : " + ", ".join(manquantes) + "."
        )

    lignes = []
    for numero, ligne in enumerate(lecteur, start=2):
        lignes.append(
            (
                numero,
                {
                    normalize_header(cle): (valeur or "").strip()
                    for cle, valeur in ligne.items()
                    if cle is not None
                },
            )
        )
    return lignes


def _valeur_optionnelle(champ, brut):
    """Convertit et valide une valeur optionnelle. Lève `ValueError` si invalide."""
    if champ == "directory_consent":
        return brut.lower() in VALEURS_VRAIES
    if champ == "birth_date":
        try:
            return date.fromisoformat(brut)
        except ValueError:
            raise ValueError(
                "Date de naissance invalide (format AAAA-MM-JJ attendu)."
            ) from None
    if champ == "sector" and brut not in Sector.values:
        raise ValueError(f"Secteur inconnu : « {brut} ».")
    if champ == "gender" and brut not in Gender.values:
        raise ValueError(f"Genre inconnu : « {brut} ».")
    return brut


def _build_values(row):
    """Traduit une ligne normalisée en champs de modèle.

    Les colonnes vides sont **omises** du résultat : c'est ce qui garantit
    qu'une mise à jour n'écrase jamais une valeur existante par du vide.
    """
    email = normalize_email(row.get("email"))
    if not email or "@" not in email:
        raise ValueError("Adresse e-mail invalide ou absente.")
    if not row.get("nom"):
        raise ValueError("Le nom est obligatoire.")
    if not row.get("prenom"):
        raise ValueError("Le prénom est obligatoire.")

    try:
        promotion = int(row.get("promotion", ""))
    except ValueError:
        raise ValueError("Promotion invalide (une année est attendue).") from None
    if not PROMOTION_MIN <= promotion <= promotion_max():
        raise ValueError(
            f"Promotion hors bornes ({PROMOTION_MIN}–{promotion_max()})."
        )

    valeurs = {
        "email": email,
        "last_name": row["nom"],
        "first_name": row["prenom"],
        "promotion": promotion,
    }
    for colonne, champ in COLUMN_TO_FIELD.items():
        if colonne in REQUIRED_COLUMNS:
            continue
        brut = row.get(colonne, "")
        if brut == "":
            continue
        valeurs[champ] = _valeur_optionnelle(champ, brut)
    return valeurs


def _appliquer(valeurs, compteurs):
    email = valeurs["email"]
    profil = AlumniProfile.objects.filter(email=email).first()
    if profil is None:
        AlumniProfile.objects.create(
            source=AlumniProfile.Source.IMPORT, **valeurs
        )
        compteurs["created"] += 1
        return

    modifies = [
        champ
        for champ, valeur in valeurs.items()
        if getattr(profil, champ) != valeur
    ]
    if not modifies:
        compteurs["skipped"] += 1
        return
    for champ in modifies:
        setattr(profil, champ, valeurs[champ])
    profil.save()
    compteurs["updated"] += 1


def import_alumni(rows, *, uploaded_by, strict=False, filename=""):
    """Applique un lot de lignes déjà normalisées.

    Ne sait rien de CSV : `rows` est un itérable de `(numéro, dict)`. C'est ce
    découplage qui permettra à une future API Transition d'alimenter la même
    fonction sans la modifier.

    Contrat des compteurs du rapport, selon le mode :

    - **Mode par défaut** (`strict=False`) : chaque ligne lue se retrouve
      dans exactement un compteur, donc
      `rows_created + rows_updated + rows_skipped + rows_failed == rows_total`.
    - **Mode strict** (`strict=True`) : au premier échec, la transaction est
      annulée — `rows_created`, `rows_updated` et `rows_skipped` retombent
      donc à zéro (les écritures, y compris celles des lignes valides
      précédant l'échec, sont annulées). `rows_total` et `rows_failed`, eux,
      ne sont *pas* remis à zéro : ils enregistrent ce qui a été lu jusqu'à
      l'abandon inclus, pas le fichier entier — les lignes situées après la
      ligne fautive ne sont jamais lues. L'égalité ci-dessus ne tient donc
      plus en mode strict.
    """
    compteurs = {"total": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}
    lignes_rapport = []
    vues = {}

    def parcourir():
        for numero, ligne in rows:
            compteurs["total"] += 1
            try:
                valeurs = _build_values(ligne)
            except ValueError as exc:
                compteurs["failed"] += 1
                lignes_rapport.append((numero, ligne, str(exc)))
                if strict:
                    raise _StrictAbort from exc
                continue

            email = valeurs["email"]
            if email in vues:
                lignes_rapport.append(
                    (
                        numero,
                        ligne,
                        "Avertissement : doublon dans le fichier — "
                        f"l'occurrence de la ligne {vues[email]} est remplacée.",
                    )
                )
            vues[email] = numero
            _appliquer(valeurs, compteurs)

    try:
        with transaction.atomic():
            parcourir()
    except _StrictAbort:
        # Les écritures sont annulées ; le rapport, lui, est écrit ensuite,
        # hors de la transaction abandonnée, afin que la trace survive.
        compteurs["created"] = 0
        compteurs["updated"] = 0
        compteurs["skipped"] = 0

    rapport = AlumniImport.objects.create(
        uploaded_by=uploaded_by,
        filename=filename,
        strict=strict,
        rows_total=compteurs["total"],
        rows_created=compteurs["created"],
        rows_updated=compteurs["updated"],
        rows_skipped=compteurs["skipped"],
        rows_failed=compteurs["failed"],
    )
    AlumniImportError.objects.bulk_create(
        [
            AlumniImportError(
                import_run=rapport, line_number=numero, raw_row=ligne, message=message
            )
            for numero, ligne, message in lignes_rapport
        ]
    )
    return rapport
