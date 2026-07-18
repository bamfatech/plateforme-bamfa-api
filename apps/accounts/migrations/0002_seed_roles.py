from django.db import migrations

ROLE_GROUPS = [
    "Alumni",
    "Rédacteur de contenu",
    "Secrétaire",
    "Trésorier",
    "Administrateur",
]


def seed_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ROLE_GROUPS:
        Group.objects.get_or_create(name=name)


def unseed_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLE_GROUPS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0001_initial"),
    ]
    operations = [migrations.RunPython(seed_roles, unseed_roles)]
