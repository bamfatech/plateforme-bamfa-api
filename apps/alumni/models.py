from datetime import date

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

DEFAULT_COUNTRY = "Bénin"
PROMOTION_MIN = 2010


def promotion_max():
    """Borne haute de la promotion. Fonction (et non constante) pour rester
    juste au fil des années sans nouvelle migration de validateur."""
    return date.today().year + 1


def normalize_email(value):
    """Minuscules + espaces retirés.

    `UserManager.normalize_email` de Django ne met en minuscules que le
    domaine : cette normalisation-ci porte sur l'adresse entière, ce qui rend
    les contraintes d'unicité effectivement insensibles à la casse.
    """
    return (value or "").strip().lower()


class Sector(models.TextChoices):
    AGRICULTURE = "agriculture", "Agriculture et agro-industrie"
    SANTE = "sante", "Santé"
    EDUCATION = "education", "Éducation et formation"
    NUMERIQUE = "numerique", "Technologies et numérique"
    FINANCE = "finance", "Finance et assurance"
    ENTREPRENEURIAT = "entrepreneuriat", "Entrepreneuriat et PME"
    ENERGIE = "energie", "Énergie et environnement"
    INDUSTRIE = "industrie", "Industrie et BTP"
    COMMERCE = "commerce", "Commerce et distribution"
    TRANSPORT = "transport", "Transport et logistique"
    PUBLIC = "public", "Administration publique"
    ONG = "ong", "Société civile et ONG"
    CULTURE = "culture", "Arts, culture et médias"
    RECHERCHE = "recherche", "Recherche"
    AUTRE = "autre", "Autre"


class Gender(models.TextChoices):
    FEMME = "femme", "Femme"
    HOMME = "homme", "Homme"
    AUTRE = "autre", "Autre"
    NON_PRECISE = "non_precise", "Non précisé"


class AlumniFieldsMixin(models.Model):
    """Champs de personne partagés par la demande et le profil."""

    first_name = models.CharField("prénom", max_length=150)
    last_name = models.CharField("nom", max_length=150)
    email = models.EmailField("adresse e-mail")
    promotion = models.PositiveSmallIntegerField(
        "promotion",
        validators=[MinValueValidator(PROMOTION_MIN), MaxValueValidator(promotion_max)],
    )
    country = models.CharField("pays", max_length=100, default=DEFAULT_COUNTRY)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    city = models.CharField("ville", max_length=100, blank=True)
    university = models.CharField("université", max_length=200, blank=True)
    mcf_program = models.CharField("programme MCF", max_length=200, blank=True)
    sector = models.CharField(
        "secteur d'activité", max_length=50, choices=Sector.choices, blank=True
    )
    current_position = models.CharField("poste actuel", max_length=200, blank=True)
    organization = models.CharField("organisation", max_length=200, blank=True)
    bio = models.TextField("biographie", blank=True)
    linkedin_url = models.URLField("profil LinkedIn", blank=True)
    birth_date = models.DateField("date de naissance", null=True, blank=True)
    gender = models.CharField("genre", max_length=20, choices=Gender.choices, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        self.country = (self.country or "").strip() or DEFAULT_COUNTRY
        super().save(*args, **kwargs)


class AlumniProfileQuerySet(models.QuerySet):
    def in_directory(self):
        """Point d'entrée unique de tous les annuaires non-administratifs.

        La règle de visibilité est écrite ici et nulle part ailleurs : aucune
        vue ne peut oublier un filtre.
        """
        return self.filter(
            status=AlumniProfile.Status.ACTIF, directory_consent=True
        )


class AlumniProfile(AlumniFieldsMixin):
    """Un membre reconnu par BAMFA. Peut exister sans compte de connexion."""

    class Status(models.TextChoices):
        ACTIF = "actif", "Actif"
        SUSPENDU = "suspendu", "Suspendu"
        ARCHIVE = "archive", "Archivé"

    class Source(models.TextChoices):
        INSCRIPTION = "inscription", "Inscription en ligne"
        IMPORT = "import", "Import"

    OPTIONAL_FIELDS = (
        "phone",
        "city",
        "university",
        "mcf_program",
        "sector",
        "current_position",
        "organization",
        "bio",
        "linkedin_url",
        "birth_date",
        "gender",
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name="compte",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alumni_profile",
    )
    email = models.EmailField("adresse e-mail", unique=True)
    directory_consent = models.BooleanField(
        "publication dans l'annuaire", default=False
    )
    status = models.CharField(
        "statut", max_length=10, choices=Status.choices, default=Status.ACTIF
    )
    mandate = models.ForeignKey(
        "accounts.Mandate",
        verbose_name="mandat",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alumni_profiles",
    )
    source = models.CharField(
        "origine", max_length=15, choices=Source.choices, default=Source.INSCRIPTION
    )
    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    objects = AlumniProfileQuerySet.as_manager()

    class Meta:
        verbose_name = "profil alumni"
        verbose_name_plural = "profils alumni"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def completeness(self):
        """Pourcentage de champs optionnels renseignés.

        Les champs obligatoires sont exclus : toujours remplis, ils tireraient
        l'indicateur vers le haut sans rien dire de la richesse du profil.
        """
        rempli = sum(1 for champ in self.OPTIONAL_FIELDS if getattr(self, champ))
        return round(rempli * 100 / len(self.OPTIONAL_FIELDS))

    @property
    def has_account(self):
        return self.user_id is not None


class AlumniRegistration(AlumniFieldsMixin):
    """Une candidature soumise depuis le site public."""

    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        APPROUVEE = "approuvee", "Approuvée"
        REJETEE = "rejetee", "Rejetée"

    directory_consent = models.BooleanField(
        "publication dans l'annuaire", default=False
    )
    status = models.CharField(
        "statut", max_length=12, choices=Status.choices, default=Status.EN_ATTENTE
    )
    submitted_at = models.DateTimeField("soumise le", auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="instruite par",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alumni_reviews",
    )
    reviewed_at = models.DateTimeField("instruite le", null=True, blank=True)
    rejection_reason = models.TextField("motif du rejet", blank=True)
    profile = models.ForeignKey(
        AlumniProfile,
        verbose_name="profil créé",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registrations",
    )

    class Meta:
        verbose_name = "demande d'inscription alumni"
        verbose_name_plural = "demandes d'inscription alumni"
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["email"],
                condition=Q(status="en_attente"),
                name="unique_demande_en_attente_par_email",
            )
        ]

    def __str__(self):
        return f"{self.email} ({self.get_status_display()})"


class AlumniImport(models.Model):
    """Rapport d'un import. Créé même quand rien n'a été importé."""

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="importé par",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alumni_imports",
    )
    filename = models.CharField("nom du fichier", max_length=255, blank=True)
    strict = models.BooleanField("mode strict", default=False)
    created_at = models.DateTimeField("importé le", auto_now_add=True)
    rows_total = models.PositiveIntegerField("lignes lues", default=0)
    rows_created = models.PositiveIntegerField("profils créés", default=0)
    rows_updated = models.PositiveIntegerField("profils mis à jour", default=0)
    rows_skipped = models.PositiveIntegerField("lignes sans changement", default=0)
    rows_failed = models.PositiveIntegerField("lignes en erreur", default=0)

    class Meta:
        verbose_name = "import alumni"
        verbose_name_plural = "imports alumni"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.filename or 'import'} — {self.rows_total} ligne(s)"


class AlumniImportError(models.Model):
    """Une ligne du rapport d'import : erreur bloquante ou avertissement."""

    import_run = models.ForeignKey(
        AlumniImport,
        verbose_name="import",
        on_delete=models.CASCADE,
        related_name="errors",
    )
    line_number = models.PositiveIntegerField("ligne")
    raw_row = models.JSONField("ligne brute", default=dict)
    message = models.TextField("message")

    class Meta:
        verbose_name = "ligne en erreur"
        verbose_name_plural = "lignes en erreur"
        ordering = ["line_number"]

    def __str__(self):
        return f"ligne {self.line_number} : {self.message}"
