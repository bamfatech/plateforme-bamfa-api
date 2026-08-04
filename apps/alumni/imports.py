import csv
import io
import logging
import re
import unicodedata
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import DatabaseError, transaction

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

logger = logging.getLogger(__name__)

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

# Colonnes du fichier ← champs du modèle : sens inverse de COLUMN_TO_FIELD,
# pour désigner un champ en erreur par son nom de colonne (visible dans le
# fichier de l'administrateur) plutôt que par son nom de champ Django.
FIELD_TO_COLUMN = {champ: colonne for colonne, champ in COLUMN_TO_FIELD.items()}

MESSAGE_EMAIL_INVALIDE = "Adresse e-mail invalide ou absente."
_VALIDATEUR_EMAIL = EmailValidator(message=MESSAGE_EMAIL_INVALIDE)


class ImportFormatError(Exception):
    """Le fichier lui-même est inexploitable : rien n'est écrit."""


class _StrictAbort(Exception):
    """Signal interne : annule la transaction en mode strict."""


def normalize_header(name):
    """Minuscules, espaces retirés, accents supprimés, espaces internes en `_`."""
    texte = unicodedata.normalize("NFKD", (name or "").strip().lower())
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"\s+", "_", texte)


def _nettoyer_valeur_brute(valeur):
    """Assainit une valeur de cellule à la frontière du pipeline.

    L'octet NUL (`\\x00`) est un caractère JSON valide mais que le type
    `jsonb` de PostgreSQL refuse (« unsupported Unicode escape sequence ») :
    laissé passer, il ne casse rien à l'import lui-même, mais fait échouer
    l'écriture de `raw_row` sur `AlumniImportError` — potentiellement bien
    après que les lignes valides ont été committées (voir I4 de la revue
    finale). Il est retiré ici, avant que la valeur n'entre dans le pipeline,
    plutôt que d'être traité comme un cas d'erreur à l'écriture du rapport.
    """
    return (valeur or "").replace("\x00", "").strip()


def parse_csv(uploaded_file):
    """Adaptateur CSV → lignes normalisées `[(numéro_de_ligne, dict), ...]`.

    Renvoie une liste et non un générateur : les en-têtes sont ainsi validés
    **avant** que le cœur d'import n'écrive quoi que ce soit.

    Tout le corps est couvert par le `except csv.Error` du bas : le module
    `csv` peut lever cette exception aussi bien à la détection du séparateur
    (repli géré localement juste en dessous) qu'à la **lecture** d'une ligne
    par `DictReader` (ex. une cellule dépassant la limite de champ du
    module) — un cas qui échappait à la traduction en `ImportFormatError`
    tant que le `try` ne couvrait que le `Sniffer` (voir I3 de la revue
    finale).
    """
    brut = uploaded_file.read()
    texte = brut.decode("utf-8-sig") if isinstance(brut, bytes) else brut

    try:
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
                        normalize_header(cle): _nettoyer_valeur_brute(valeur)
                        for cle, valeur in ligne.items()
                        if cle is not None
                    },
                )
            )
        return lignes
    except csv.Error as exc:
        raise ImportFormatError(
            "Le fichier CSV est illisible (ligne trop longue ou mal formée)."
        ) from exc


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
    if not email:
        raise ValueError(MESSAGE_EMAIL_INVALIDE)
    try:
        _VALIDATEUR_EMAIL(email)
    except ValidationError:
        raise ValueError(MESSAGE_EMAIL_INVALIDE) from None
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


def _message_erreur_validation(exc):
    """Traduit une `ValidationError` de `full_clean()` en message par colonne."""
    if hasattr(exc, "message_dict"):
        parties = [
            f"{FIELD_TO_COLUMN.get(champ, champ)} : {' '.join(messages)}"
            for champ, messages in exc.message_dict.items()
        ]
        return "; ".join(parties)
    return "; ".join(exc.messages)


def _enregistrer(instance):
    """Valide puis enregistre une instance dans une savepoint dédiée à sa ligne.

    `full_clean()` convertit en `ValidationError` — donc en échec de cette
    seule ligne — ce qui serait sinon une erreur base de données (ex. une
    valeur trop longue) susceptible de rendre la transaction englobante
    inutilisable. La savepoint (`transaction.atomic()` imbriqué) isole
    l'écriture de cette ligne : si elle échoue malgré tout côté base de
    données, seule cette savepoint est annulée, pas le lot en cours.
    """
    try:
        with transaction.atomic():
            instance.full_clean()
            instance.save()
    except ValidationError as exc:
        raise ValueError(_message_erreur_validation(exc)) from exc
    except DatabaseError as exc:
        # Le texte brut de Postgres (anglais, fragments de requête SQL, noms
        # de colonnes) ne doit jamais atteindre le rapport lu par
        # l'administrateur — le produit est en français partout. Le détail
        # technique va au journal serveur, pas à la ligne du rapport.
        logger.exception(
            "Échec d'enregistrement en base pour une ligne d'import alumni."
        )
        raise ValueError("Cette ligne n'a pas pu être enregistrée.") from exc


def _appliquer(valeurs, compteurs):
    email = valeurs["email"]
    profil = AlumniProfile.objects.filter(email=email).first()
    if profil is None:
        _enregistrer(AlumniProfile(source=AlumniProfile.Source.IMPORT, **valeurs))
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
    _enregistrer(profil)
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

    Une ligne peut échouer pour deux raisons distinctes, toutes deux traitées
    de la même façon (comptée dans `rows_failed`, consignée dans le rapport,
    et — en mode strict — déclenchant l'abandon) : une valeur invalide
    détectée avant écriture (`_build_values`, `full_clean()`), ou un échec
    survenant malgré tout côté base de données (`DatabaseError`, capturé en
    dernier recours par `_enregistrer`). Dans les deux cas, l'échec d'une
    ligne est isolé par une savepoint dédiée : il ne peut ni corrompre la
    transaction englobante, ni entraîner la perte des lignes déjà traitées.
    """
    compteurs = {"total": 0, "created": 0, "updated": 0, "skipped": 0, "failed": 0}
    lignes_rapport = []
    vues = {}

    def _echec(numero, ligne, exc):
        compteurs["failed"] += 1
        lignes_rapport.append((numero, ligne, str(exc)))
        if strict:
            raise _StrictAbort from exc

    def parcourir():
        for numero, ligne in rows:
            compteurs["total"] += 1
            try:
                valeurs = _build_values(ligne)
            except ValueError as exc:
                _echec(numero, ligne, exc)
                continue

            email = valeurs["email"]
            doublon_de = vues.get(email)
            vues[email] = numero

            try:
                _appliquer(valeurs, compteurs)
            except ValueError as exc:
                _echec(numero, ligne, exc)
                continue

            if doublon_de is not None:
                lignes_rapport.append(
                    (
                        numero,
                        ligne,
                        "Avertissement : doublon dans le fichier — "
                        f"l'occurrence de la ligne {doublon_de} est remplacée.",
                    )
                )

    try:
        try:
            with transaction.atomic():
                parcourir()
        except _StrictAbort:
            # Les écritures sont annulées ; le rapport, lui, est écrit ensuite,
            # hors de la transaction abandonnée, afin que la trace survive.
            compteurs["created"] = 0
            compteurs["updated"] = 0
            compteurs["skipped"] = 0
    finally:
        # Le rapport doit exister même si la boucle se termine de façon
        # imprévue : c'est la trace de la tentative, elle survit à l'échec
        # de la tentative elle-même.
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
        try:
            AlumniImportError.objects.bulk_create(
                [
                    AlumniImportError(
                        import_run=rapport,
                        line_number=numero,
                        raw_row=ligne,
                        message=message,
                    )
                    for numero, ligne, message in lignes_rapport
                ]
            )
        except DatabaseError:
            # Ce `finally` existe pour garantir qu'un rapport est *toujours*
            # créé (§9.3) — il ne doit donc jamais pouvoir lui-même faire
            # échouer la requête. `_nettoyer_valeur_brute` retire déjà les
            # octets NUL à la frontière (I4), mais ce filet couvre toute
            # autre valeur qu'un `jsonb` Postgres refuserait : le rapport et
            # ses compteurs restent la trace qui compte, le contenu brut de
            # la ligne est secondaire.
            logger.exception(
                "Écriture des lignes du rapport d'import %s impossible ; "
                "repli sur des lignes sans contenu brut.",
                rapport.pk,
            )
            AlumniImportError.objects.bulk_create(
                [
                    AlumniImportError(
                        import_run=rapport,
                        line_number=numero,
                        raw_row={},
                        message=message,
                    )
                    for numero, ligne, message in lignes_rapport
                ]
            )
    return rapport
