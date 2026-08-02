from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.accounts.models import Mandate
from apps.accounts.roles import create_roles

User = get_user_model()

DEMO_USERS = [
    {
        "email": "admin@bamfa.org",
        "first_name": "Ada",
        "last_name": "Admin",
        "role": "Administrateur",
        "superuser": True,
        "is_staff": True,
    },
    {
        "email": "redacteur@bamfa.org",
        "first_name": "Rémi",
        "last_name": "Rédacteur",
        "role": "Rédacteur de contenu",
        "superuser": False,
        "is_staff": True,
    },
    {
        "email": "alumni@bamfa.org",
        "first_name": "Awa",
        "last_name": "Alumni",
        "role": "Alumni",
        "superuser": False,
        "is_staff": False,
    },
]

DEMO_PASSWORD = "bamfa1234"


class Command(BaseCommand):
    help = "Peuple un environnement de démonstration (rôles, utilisateurs, mandat). Idempotent."

    def handle(self, *args, **options):
        create_roles()

        for spec in DEMO_USERS:
            user, created = User.objects.get_or_create(
                email=spec["email"],
                defaults={
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "is_staff": spec["is_staff"],
                    "is_superuser": spec["superuser"],
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            user.groups.add(Group.objects.get(name=spec["role"]))

        Mandate.objects.get_or_create(
            label="Mandat 2024-2026",
            defaults={
                "start_date": date(2024, 1, 1),
                "end_date": date(2026, 12, 31),
                "is_current": True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS("Données de démonstration créées / à jour.")
        )
