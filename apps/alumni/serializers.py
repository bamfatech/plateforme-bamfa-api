from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import MaxValueValidator
from rest_framework import serializers

from .models import (
    PROMOTION_MIN,
    AlumniImport,
    AlumniImportError,
    AlumniProfile,
    AlumniRegistration,
    normalize_email,
    promotion_max,
)

DOUBLON_MESSAGE = "Une demande est déjà enregistrée pour cette adresse e-mail."


def promotion_serializer_field():
    """Champ `promotion` explicite, partagé par tous les sérialiseurs alumni.

    `ModelSerializer` recopierait `MaxValueValidator.limit_value` — ici la
    fonction `promotion_max` — dans `max_value`, que drf-spectacular lit sans
    l'appeler : la génération du schéma OpenAPI planterait. En déclarant le
    champ, `max_value` reste None et la borne reste portée par le validateur,
    qui résout le callable à l'appel.
    """
    return serializers.IntegerField(
        min_value=PROMOTION_MIN, validators=[MaxValueValidator(promotion_max)]
    )


class NormalizedEmailMixin:
    """Normalise l'e-mail (minuscules, espaces retirés) une seule fois,
    réutilisée par tous les sérialiseurs qui acceptent `email` en écriture.

    Le modèle normalise déjà à l'écriture (`AlumniFieldsMixin.save()` et
    `clean()`), mais un sérialiseur qui laisse passer une casse différente
    jusque-là expose l'`UniqueValidator` (ou toute vérification applicative
    de doublon) à une valeur non normalisée — c'est exactement ce qui
    laissait passer un `PATCH` d'e-mail à la casse différente jusqu'à la
    contrainte d'unicité en base (voir I5 de la revue finale).
    """

    def validate_email(self, value):
        return normalize_email(value)


class AlumniRegistrationCreateSerializer(
    NormalizedEmailMixin, serializers.ModelSerializer
):
    """Soumission publique. Aucun champ d'instruction n'est exposé."""

    promotion = promotion_serializer_field()

    class Meta:
        model = AlumniRegistration
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "promotion",
            "country",
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
            "directory_consent",
        ]
        read_only_fields = ["id"]

    def validate_email(self, value):
        """Message unique pour « déjà membre » et « demande en cours ».

        Ne pas distinguer les deux cas évite d'énumérer les membres.
        """
        email = super().validate_email(value)
        deja_membre = AlumniProfile.objects.filter(email=email).exists()
        deja_demande = AlumniRegistration.objects.filter(
            email=email, status=AlumniRegistration.Status.EN_ATTENTE
        ).exists()
        if deja_membre or deja_demande:
            raise serializers.ValidationError(DOUBLON_MESSAGE)
        return email


class InvitationVerifySerializer(serializers.Serializer):
    token = serializers.CharField()


class InvitationActivateSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class AlumniRegistrationAdminSerializer(serializers.ModelSerializer):
    """Lecture d'une demande dans le back-office."""

    reviewed_by_email = serializers.EmailField(
        source="reviewed_by.email", read_only=True, default=None
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    sector_display = serializers.CharField(source="get_sector_display", read_only=True)

    class Meta:
        model = AlumniRegistration
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "promotion",
            "country",
            "phone",
            "city",
            "university",
            "mcf_program",
            "sector",
            "sector_display",
            "current_position",
            "organization",
            "bio",
            "linkedin_url",
            "birth_date",
            "gender",
            "directory_consent",
            "status",
            "status_display",
            "submitted_at",
            "reviewed_at",
            "reviewed_by_email",
            "rejection_reason",
            "profile",
        ]
        read_only_fields = fields


class RejectSerializer(serializers.Serializer):
    motif = serializers.CharField(required=False, allow_blank=True, default="")


class AdminProfileSerializer(NormalizedEmailMixin, serializers.ModelSerializer):
    """Niveau administration : tous les champs, e-mail et téléphone inclus."""

    # `promotion` est modifiable ici : le helper partagé est obligatoire, sans
    # quoi la génération du schéma OpenAPI plante (voir Contraintes globales).
    promotion = promotion_serializer_field()
    completeness = serializers.IntegerField(read_only=True)
    has_account = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    sector_display = serializers.CharField(source="get_sector_display", read_only=True)
    user_email = serializers.EmailField(
        source="user.email", read_only=True, default=None
    )

    def validate_email(self, value):
        """`ModelSerializer` attacherait normalement un `UniqueValidator` sur
        `email` (le modèle porte `unique=True`) — mais ce validateur agit
        avant la normalisation faite ici (voir `NormalizedEmailMixin`),
        directement sur la valeur brute envoyée par le client : deux e-mails
        identiques à la casse près le franchissent tous les deux sans être
        détectés, et c'est la contrainte d'unicité en base qui tranchait
        ensuite avec une `IntegrityError` non traduite. Le contrôle
        d'unicité est donc fait ici, sur la valeur déjà normalisée, avec le
        validateur par défaut désactivé (`extra_kwargs` ci-dessous).
        """
        email = super().validate_email(value)
        collision = AlumniProfile.objects.filter(email=email)
        if self.instance is not None:
            collision = collision.exclude(pk=self.instance.pk)
        if collision.exists():
            raise serializers.ValidationError(
                "Cette adresse e-mail est déjà utilisée par un autre profil."
            )
        return email

    class Meta:
        model = AlumniProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "promotion",
            "country",
            "phone",
            "city",
            "university",
            "mcf_program",
            "sector",
            "sector_display",
            "current_position",
            "organization",
            "bio",
            "linkedin_url",
            "birth_date",
            "gender",
            "directory_consent",
            "status",
            "status_display",
            "source",
            "mandate",
            "completeness",
            "has_account",
            "user_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "status_display",
            "source",
            "sector_display",
            "completeness",
            "has_account",
            "user_email",
            "created_at",
            "updated_at",
        ]
        # Le `UniqueValidator` que `ModelSerializer` attacherait ici agirait
        # avant la normalisation de `validate_email` ci-dessus : désactivé,
        # au profit du contrôle explicite fait sur la valeur normalisée.
        extra_kwargs = {"email": {"validators": []}}


class PublicDirectorySerializer(serializers.ModelSerializer):
    """Niveau public : ni e-mail, ni téléphone, ni champs enrichis."""

    sector_display = serializers.CharField(source="get_sector_display", read_only=True)

    class Meta:
        model = AlumniProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "promotion",
            "sector",
            "sector_display",
            "country",
            "current_position",
            "organization",
        ]
        read_only_fields = fields


class MemberDirectorySerializer(PublicDirectorySerializer):
    """Niveau connecté : ajoute ville, biographie et LinkedIn. Toujours pas
    d'e-mail ni de téléphone — ceux-là ne sortent jamais du back-office."""

    class Meta(PublicDirectorySerializer.Meta):
        fields = PublicDirectorySerializer.Meta.fields + [
            "city",
            "bio",
            "linkedin_url",
        ]
        read_only_fields = fields


class SelfProfileSerializer(serializers.ModelSerializer):
    """Profil vu et édité par son titulaire.

    `email`, `promotion`, `status` et `source` restent réservés à
    l'administration : ce sont des données d'instruction, pas des préférences.
    """

    completeness = serializers.IntegerField(read_only=True)
    sector_display = serializers.CharField(source="get_sector_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = AlumniProfile
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "promotion",
            "country",
            "phone",
            "city",
            "university",
            "mcf_program",
            "sector",
            "sector_display",
            "current_position",
            "organization",
            "bio",
            "linkedin_url",
            "birth_date",
            "gender",
            "directory_consent",
            "status",
            "status_display",
            "completeness",
        ]
        read_only_fields = [
            "id",
            "email",
            "promotion",
            "status",
        ]


class AlumniImportErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlumniImportError
        fields = ["id", "line_number", "raw_row", "message"]
        read_only_fields = fields


class AlumniImportSerializer(serializers.ModelSerializer):
    """Rapport d'import, avec ses lignes en erreur et avertissements."""

    errors = AlumniImportErrorSerializer(many=True, read_only=True)
    uploaded_by_email = serializers.EmailField(
        source="uploaded_by.email", read_only=True, default=None
    )

    class Meta:
        model = AlumniImport
        fields = [
            "id",
            "filename",
            "strict",
            "created_at",
            "uploaded_by_email",
            "rows_total",
            "rows_created",
            "rows_updated",
            "rows_skipped",
            "rows_failed",
            "errors",
        ]
        read_only_fields = fields


class AlumniImportCreateSerializer(serializers.Serializer):
    fichier = serializers.FileField()
    strict = serializers.BooleanField(default=False)
