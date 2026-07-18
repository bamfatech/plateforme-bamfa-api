import datetime

import pytest

from apps.accounts.models import Mandate


@pytest.mark.django_db
def test_un_seul_mandat_courant():
    m1 = Mandate.objects.create(
        label="Mandat 2022-2024", start_date=datetime.date(2022, 1, 1), is_current=True
    )
    m2 = Mandate.objects.create(
        label="Mandat 2024-2026", start_date=datetime.date(2024, 1, 1), is_current=True
    )
    m1.refresh_from_db()
    assert m2.is_current is True
    assert m1.is_current is False


@pytest.mark.django_db
def test_str_mandate():
    m = Mandate.objects.create(label="Mandat 2024-2026", start_date=datetime.date(2024, 1, 1))
    assert str(m) == "Mandat 2024-2026"
