from apps.common.tasks import send_templated_email_task


def acknowledge_registration(registration):
    """Accusé de réception au demandeur."""
    send_templated_email_task.delay(
        "Votre demande d'inscription à BAMFA",
        "alumni_demande_recue",
        {"prenom": registration.first_name},
        registration.email,
    )
