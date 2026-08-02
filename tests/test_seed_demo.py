import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.accounts.models import Mandate


@pytest.mark.django_db
def test_seed_demo_cree_les_donnees_et_est_idempotent():
    call_command("seed_demo")
    User = get_user_model()

    admin = User.objects.get(email="admin@bamfa.org")
    assert admin.is_superuser
    assert admin.groups.filter(name="Administrateur").exists()
    assert User.objects.filter(email="redacteur@bamfa.org").exists()
    assert not User.objects.get(email="alumni@bamfa.org").is_staff
    assert Mandate.objects.filter(is_current=True).count() == 1

    # Idempotent : un second passage ne duplique rien.
    call_command("seed_demo")
    assert User.objects.filter(email="admin@bamfa.org").count() == 1
    assert Mandate.objects.filter(label="Mandat 2024-2026").count() == 1
