from django.db import models


class Payment(models.Model):
    class Status(models.TextChoices):
        EN_ATTENTE = "en_attente", "En attente"
        CONFIRME = "confirme", "Confirmé"
        ECHOUE = "echoue", "Échoué"
        REMBOURSE = "rembourse", "Remboursé"

    amount = models.DecimalField("montant", max_digits=12, decimal_places=2)
    currency = models.CharField("devise", max_length=3, default="XOF")
    status = models.CharField(
        "statut", max_length=12, choices=Status.choices, default=Status.EN_ATTENTE
    )
    provider = models.CharField("fournisseur", max_length=50, default="manual")
    provider_reference = models.CharField(
        "référence fournisseur", max_length=255, blank=True
    )
    reference = models.CharField("référence interne", max_length=64, unique=True)
    metadata = models.JSONField("métadonnées", default=dict, blank=True)
    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)

    class Meta:
        verbose_name = "paiement"
        verbose_name_plural = "paiements"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} — {self.amount} {self.currency} ({self.status})"

    def mark_confirmed(self):
        self.status = self.Status.CONFIRME

    def mark_failed(self):
        self.status = self.Status.ECHOUE
