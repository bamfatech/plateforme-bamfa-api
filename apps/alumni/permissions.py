from apps.common.permissions import HasAnyRole


class CanReviewRegistrations(HasAnyRole):
    """Approuver ou rejeter une demande : acte de gouvernance."""

    roles = ("Administrateur",)


class CanManageDirectory(HasAnyRole):
    """Éditer, suspendre, réactiver, archiver, (ré)inviter."""

    roles = ("Administrateur",)


class CanReadAdminDirectory(HasAnyRole):
    """Consulter la base complète, e-mails et profils sans consentement inclus."""

    roles = ("Administrateur", "Secrétaire")


class CanImportAlumni(HasAnyRole):
    """Alimenter la base par import de fichier."""

    roles = ("Administrateur", "Secrétaire")
