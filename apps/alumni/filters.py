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


class AdminProfileFilter(filters.FilterSet):
    statut = filters.CharFilter(field_name="status")
    secteur = filters.CharFilter(field_name="sector")
    pays = filters.CharFilter(field_name="country", lookup_expr="iexact")
    consentement = filters.BooleanFilter(field_name="directory_consent")
    # `exclude=True` : a_un_compte=true écarte les profils sans compte, et
    # a_un_compte=false écarte ceux qui en ont un.
    a_un_compte = filters.BooleanFilter(
        field_name="user", lookup_expr="isnull", exclude=True
    )

    class Meta:
        model = AlumniProfile
        fields = ["promotion"]
