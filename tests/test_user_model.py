import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_create_user_avec_email():
    user = User.objects.create_user(email="Alice@Bamfa.org", password="motdepasse123")
    assert user.email == "Alice@bamfa.org"  # domaine normalisé
    assert user.check_password("motdepasse123")
    assert user.is_staff is False
    assert user.is_superuser is False


@pytest.mark.django_db
def test_create_user_sans_email_leve_erreur():
    with pytest.raises(ValueError):
        User.objects.create_user(email="", password="x")


@pytest.mark.django_db
def test_create_superuser():
    admin = User.objects.create_superuser(email="admin@bamfa.org", password="x")
    assert admin.is_staff is True
    assert admin.is_superuser is True


@pytest.mark.django_db
def test_username_field_est_email():
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []
