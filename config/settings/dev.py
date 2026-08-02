from .base import *  # noqa: F401,F403

CELERY_TASK_ALWAYS_EAGER = True  # exécution inline en dev/tests (pas de worker requis)
