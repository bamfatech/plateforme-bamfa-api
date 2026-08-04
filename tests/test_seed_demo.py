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


@pytest.mark.django_db
def test_seed_demo_cree_des_profils_alumni_de_demonstration():
    from apps.alumni.models import AlumniProfile

    call_command("seed_demo")

    assert AlumniProfile.objects.count() >= 3
    assert AlumniProfile.objects.in_directory().exists()


@pytest.mark.django_db
def test_seed_demo_rattache_le_profil_au_compte_alumni_de_demonstration():
    from django.contrib.auth import get_user_model

    from apps.alumni.models import AlumniProfile

    call_command("seed_demo")

    user = get_user_model().objects.get(email="alumni@bamfa.org")
    profil = AlumniProfile.objects.get(email="alumni@bamfa.org")
    assert profil.user == user


@pytest.mark.django_db
def test_seed_demo_reste_idempotente_sur_les_profils_alumni():
    from apps.alumni.models import AlumniProfile

    call_command("seed_demo")
    total = AlumniProfile.objects.count()
    call_command("seed_demo")

    assert AlumniProfile.objects.count() == total
