from django.contrib.auth.models import Group

ROLE_GROUPS = [
    "Alumni",
    "Rédacteur de contenu",
    "Secrétaire",
    "Trésorier",
    "Administrateur",
]


def create_roles():
    """Crée les groupes de rôles. Idempotent."""
    for name in ROLE_GROUPS:
        Group.objects.get_or_create(name=name)


def user_has_role(user, name):
    return user.is_authenticated and user.groups.filter(name=name).exists()
