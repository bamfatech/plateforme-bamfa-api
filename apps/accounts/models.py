from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("adresse e-mail", unique=True)
    first_name = models.CharField("prénom", max_length=150, blank=True)
    last_name = models.CharField("nom", max_length=150, blank=True)
    is_active = models.BooleanField("actif", default=True)
    is_staff = models.BooleanField("équipe", default=False)
    date_joined = models.DateTimeField("date d'inscription", auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"

    def __str__(self):
        return self.email


class Mandate(models.Model):
    label = models.CharField("libellé", max_length=150)
    start_date = models.DateField("date de début")
    end_date = models.DateField("date de fin", null=True, blank=True)
    is_current = models.BooleanField("mandat courant", default=False)

    class Meta:
        verbose_name = "mandat"
        verbose_name_plural = "mandats"
        ordering = ["-start_date"]

    def __str__(self):
        return self.label

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            Mandate.objects.exclude(pk=self.pk).filter(is_current=True).update(
                is_current=False
            )
