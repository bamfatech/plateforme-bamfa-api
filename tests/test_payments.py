import pytest

from apps.payments.models import Payment
from apps.payments.providers import ManualPaymentProvider, get_payment_provider


@pytest.mark.django_db
def test_transitions_de_statut():
    payment = Payment.objects.create(amount="1000.00", reference="REF-1")
    assert payment.status == Payment.Status.EN_ATTENTE
    payment.mark_confirmed()
    assert payment.status == Payment.Status.CONFIRME
    payment.mark_failed()
    assert payment.status == Payment.Status.ECHOUE


def test_provider_manuel_par_defaut():
    provider = get_payment_provider()
    assert isinstance(provider, ManualPaymentProvider)
    out = provider.create_checkout(Payment(amount="500.00", reference="REF-2"))
    assert out["mode"] == "manuel"
    assert out["checkout_url"] is None
    assert provider.verify_webhook({}) is None
