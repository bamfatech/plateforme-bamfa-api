import pytest

pytest_plugins = ("celery.contrib.pytest",)


# Configuration du worker Celery « live » utilisé par tests/test_celery_async.py
# pour exercer le chemin réel (non-eager) : broker en mémoire, pool "solo"
# (le pool par défaut "prefork" repose sur fork(), indisponible sous Windows).


@pytest.fixture(scope="session")
def celery_config():
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
        "task_always_eager": False,
    }


@pytest.fixture(scope="session")
def celery_worker_pool():
    return "solo"


@pytest.fixture(scope="session")
def celery_worker_parameters():
    return {"perform_ping_check": False}


@pytest.fixture(scope="session")
def celery_includes():
    return ("apps.common.tasks",)
