from django.core.management.base import BaseCommand

from apps.accounts.roles import ROLE_GROUPS, create_roles


class Command(BaseCommand):
    help = "Crée les groupes de rôles BAMFA (idempotent)."

    def handle(self, *args, **options):
        create_roles()
        self.stdout.write(self.style.SUCCESS(f"Rôles seedés : {', '.join(ROLE_GROUPS)}"))
