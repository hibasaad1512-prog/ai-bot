from app.chaos.cooldowns import CooldownStore


def test_try_gate_reserves_once_without_counting_until_send():
    store = CooldownStore()
    assert store.try_gate(123, global_cooldown=60, hourly_limit=30, max_consecutive=2)
    assert store.hourly_count(123) == 0
    assert not store.try_gate(123, global_cooldown=60, hourly_limit=30, max_consecutive=2)


def test_failed_ai_releases_pre_gate_reservation():
    store = CooldownStore()
    assert store.try_gate(123, global_cooldown=60, hourly_limit=30, max_consecutive=2)
    store.release_global(123)
    assert store.try_gate(123, global_cooldown=60, hourly_limit=30, max_consecutive=2)


def test_human_message_resets_consecutive_reply_limit():
    store = CooldownStore()
    store.record_action(123)
    store.record_action(123)
    assert store.consecutive_count(123) == 2
    store.record_human_message(123)
    assert store.consecutive_count(123) == 0
