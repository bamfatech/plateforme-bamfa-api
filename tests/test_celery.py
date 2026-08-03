def test_tache_ping_en_mode_eager():
    from apps.common.tasks import ping

    result = ping.delay()
    assert result.get(timeout=5) == "pong"


def test_tache_envoi_email_asynchrone(mailoutbox):
    from apps.common.tasks import send_templated_email_task

    result = send_templated_email_task.delay(
        "Bienvenue", "exemple", {"nom": "Awa"}, "awa@example.org"
    )
    result.get(timeout=5)

    assert len(mailoutbox) == 1
    assert mailoutbox[0].subject == "Bienvenue"
