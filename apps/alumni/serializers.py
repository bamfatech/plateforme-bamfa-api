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


class AlumniRegistrationCreateSerializer(serializers.ModelSerializer):
    """Soumission publique. Aucun champ d'instruction n'est exposé."""

    # Déclaré explicitement : `PositiveSmallIntegerField.validators` contient un
    # `MaxValueValidator` dont la borne est une fonction (`promotion_max`), pour
    # rester juste au fil des années sans migration. `ModelSerializer` recopierait
    # cette fonction telle quelle dans `IntegerField(max_value=...)`, ce que
    # drf-spectacular ne sait pas introspecter (il attend un entier). Le champ
    # explicite conserve la même borne dynamique, validée à l'exécution, sans
    # exposer de valeur non résolue au générateur de schéma OpenAPI.
    promotion = serializers.IntegerField(
        min_value=PROMOTION_MIN, validators=[MaxValueValidator(promotion_max)]
    )

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
