from django.db import models
from django.utils import timezone


class PublishableMixin(models.Model):
    class Status(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        PUBLIE = "publie", "Publié"
        DEPUBLIE = "depublie", "Dépublié"

    status = models.CharField(
        "statut", max_length=10, choices=Status.choices, default=Status.BROUILLON
    )
    published_at = models.DateTimeField("date de publication", null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_published(self):
        return self.status == self.Status.PUBLIE

    def publish(self):
        self.status = self.Status.PUBLIE
        self.published_at = timezone.now()

    def unpublish(self):
        self.status = self.Status.DEPUBLIE
