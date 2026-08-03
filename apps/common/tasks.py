from celery import shared_task


@shared_task
def ping():
    """Tâche de vérification du câblage Celery."""
    return "pong"


@shared_task
def send_templated_email_task(subject, template_name, context, to, from_email=None):
    """Envoi d'un email transactionnel en tâche asynchrone (délégué au worker Celery)."""
    from apps.common.emails import send_templated_email

    return send_templated_email(
        subject=subject,
        template_name=template_name,
        context=context,
        to=to,
        from_email=from_email,
    )
