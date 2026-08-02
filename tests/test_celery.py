def test_tache_ping_en_mode_eager():
    from apps.common.tasks import ping

    result = ping.delay()
    assert result.get(timeout=5) == "pong"
