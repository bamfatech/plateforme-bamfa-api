from abc import ABC, abstractmethod

from django.conf import settings
from django.utils.module_loading import import_string


class PaymentProvider(ABC):
    """Interface d'un fournisseur de paiement (agrégateur).

    Impl. manuelle aujourd'hui ; FedaPay/Kkiapay branchables plus tard
    en fournissant une autre implémentation (réglage PAYMENT_PROVIDER).
    """

    name = "base"

    @abstractmethod
    def create_checkout(self, payment):
        """Initie un paiement ; retourne un dict décrivant l'étape suivante."""

    @abstractmethod
    def verify_webhook(self, payload):
        """Valide un webhook entrant ; retourne le statut ou None."""


class ManualPaymentProvider(PaymentProvider):
    """Aucun agrégateur branché : le paiement reste 'en_attente' jusqu'à
    confirmation manuelle par un trésorier / administrateur."""

    name = "manual"

    def create_checkout(self, payment):
        return {"mode": "manuel", "reference": payment.reference, "checkout_url": None}

    def verify_webhook(self, payload):
        return None


def get_payment_provider():
    dotted = getattr(
        settings,
        "PAYMENT_PROVIDER",
        "apps.payments.providers.ManualPaymentProvider",
    )
    return import_string(dotted)()
