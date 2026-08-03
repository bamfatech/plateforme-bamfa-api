import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from rest_framework.test import APIRequestFactory

from apps.accounts.roles import create_roles
from apps.common.permissions import (
    HasAnyRole,
    IsAdministrateur,
    IsAdministrateurOrSecretaire,
    IsAlumni,
)

User = get_user_model()


def _request(user):
    request = APIRequestFactory().get("/")
    request.user = user
    return request


@pytest.mark.django_db
def test_role_present_accorde_l_acces():
    create_roles()
    user = User.objects.create_user(email="a@bamfa.org", password="x")
    user.groups.add(Group.objects.get(name="Administrateur"))
    assert IsAdministrateur().has_permission(_request(user), None) is True


@pytest.mark.django_db
def test_role_absent_refuse_l_acces():
    create_roles()
    user = User.objects.create_user(email="b@bamfa.org", password="x")
    user.groups.add(Group.objects.get(name="Alumni"))
    assert IsAdministrateur().has_permission(_request(user), None) is False


@pytest.mark.django_db
def test_superutilisateur_passe_outre_les_groupes():
    user = User.objects.create_superuser(email="root@bamfa.org", password="x")
    assert IsAdministrateur().has_permission(_request(user), None) is True
    assert IsAlumni().has_permission(_request(user), None) is True


def test_utilisateur_anonyme_refuse():
    assert IsAdministrateur().has_permission(_request(AnonymousUser()), None) is False


@pytest.mark.django_db
def test_plusieurs_roles_acceptes():
    create_roles()
    user = User.objects.create_user(email="c@bamfa.org", password="x")
    user.groups.add(Group.objects.get(name="Secrétaire"))
    assert IsAdministrateurOrSecretaire().has_permission(_request(user), None) is True
    assert IsAdministrateur().has_permission(_request(user), None) is False


def test_has_any_role_sans_roles_declares_refuse_tout():
    class Aucun(HasAnyRole):
        roles = ()

    assert Aucun().has_permission(_request(AnonymousUser()), None) is False
