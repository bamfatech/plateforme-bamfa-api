from rest_framework.permissions import BasePermission

from apps.accounts.roles import user_has_role


class HasAnyRole(BasePermission):
    """Accorde l'accès aux super-utilisateurs et aux membres de l'un des groupes listés.

    Le passe-droit super-utilisateur est volontaire : l'administrateur de
    démonstration est superutilisateur, et le frontend traite déjà
    `is_superuser` comme équivalent au rôle « Administrateur ».
    """

    roles: tuple[str, ...] = ()

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return any(user_has_role(user, role) for role in self.roles)


class IsAdministrateur(HasAnyRole):
    roles = ("Administrateur",)


class IsAdministrateurOrSecretaire(HasAnyRole):
    roles = ("Administrateur", "Secrétaire")


class IsAlumni(HasAnyRole):
    roles = ("Alumni",)
