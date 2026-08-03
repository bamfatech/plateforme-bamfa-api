import django_filters as filters

from .models import AlumniRegistration


class AlumniRegistrationFilter(filters.FilterSet):
    statut = filters.CharFilter(field_name="status")

    class Meta:
        model = AlumniRegistration
        fields = ["promotion"]
