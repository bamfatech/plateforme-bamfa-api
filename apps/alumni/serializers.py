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
