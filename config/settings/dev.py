from .base import *  # noqa: F401,F403

# Exécution des tâches Celery :
# - par défaut True : inline sur l'hôte / en tests (aucun worker requis) ;
# - False en conteneur (docker-compose) pour un worker asynchrone réel.
CELERY_TASK_ALWAYS_EAGER = env.bool(  # noqa: F405
    "CELERY_TASK_ALWAYS_EAGER", default=True
)
