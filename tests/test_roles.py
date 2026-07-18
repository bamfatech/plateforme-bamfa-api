import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from apps.accounts.roles import ROLE_GROUPS, create_roles, user_has_role

User = get_user_model()


@pytest.mark.django_db
def test_create_roles_cree_les_groupes_et_est_idempotente():
    create_roles()
    create_roles()  # relance -> pas de doublon
    for name in ROLE_GROUPS:
        assert Group.objects.filter(name=name).count() == 1
    assert Group.objects.filter(name__in=ROLE_GROUPS).count() == len(ROLE_GROUPS)


@pytest.mark.django_db
def test_user_has_role():
    create_roles()
    user = User.objects.create_user(email="a@bamfa.org", password="x")
    user.groups.add(Group.objects.get(name="Administrateur"))
    assert user_has_role(user, "Administrateur") is True
    assert user_has_role(user, "Trésorier") is False
