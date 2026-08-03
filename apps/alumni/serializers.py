from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import MaxValueValidator
from rest_framework import serializers

from .models import (
    PROMOTION_MIN,
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


class AlumniRegistrationCreateSerializer(serializers.ModelSerializer):
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
        email = normalize_email(value)
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


class AdminProfileSerializer(serializers.ModelSerializer):
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
            "status_display",
            "sector_display",
            "completeness",
        ]
