from celery import shared_task


@shared_task
def ping():
    """Tâche de vérification du câblage Celery."""
    return "pong"
