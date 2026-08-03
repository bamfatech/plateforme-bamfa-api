import django_filters as filters

from .models import AlumniProfile, AlumniRegistration


class AlumniRegistrationFilter(filters.FilterSet):
    statut = filters.CharFilter(field_name="status")

    class Meta:
        model = AlumniRegistration
        fields = ["promotion"]


class PublicDirectoryFilter(filters.FilterSet):
    secteur = filters.CharFilter(field_name="sector")
    pays = filters.CharFilter(field_name="country", lookup_expr="iexact")

    class Meta:
        model = AlumniProfile
        fields = ["promotion"]
