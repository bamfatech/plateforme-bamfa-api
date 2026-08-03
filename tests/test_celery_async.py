"""Couverture du chemin Celery réel (non-eager) : dispatch via un broker en
mémoire et exécution par un worker « live » (config/fixtures dans conftest.py).

En dev/tests, CELERY_TASK_ALWAYS_EAGER=True fait exécuter les tâches en
inline, dans le process appelant — ce qui masque tout problème de
sérialisation/dispatch qui n'apparaîtrait qu'avec un vrai broker + worker.
Ce test force `task_always_eager=False` et fait transiter la tâche `ping`
(sans accès BDD, donc thread-safe) par un vrai worker Celery en mémoire.
"""


def test_tache_ping_via_worker_celery_reel(celery_session_worker):
    from apps.common.tasks import ping

    result = ping.delay()

    assert result.get(timeout=10) == "pong"
