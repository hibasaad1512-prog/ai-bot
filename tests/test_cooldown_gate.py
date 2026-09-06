from app.chaos.cooldowns import CooldownStore


def test_claim_is_atomic_for_global_and_action_limits():
    store = CooldownStore()
    assert store.claim(
        1,
        "REPLY_CONTEXT",
        action_cooldown=60,
        global_cooldown=60,
        hourly_limit=20,
        max_consecutive=2,
    )
    assert not store.claim(
        1,
        "REACTION",
        action_cooldown=60,
        global_cooldown=60,
        hourly_limit=20,
        max_consecutive=2,
    )


def test_hourly_limit_blocks_new_actions():
    store = CooldownStore()
    assert store.claim(
        2,
        "A",
        action_cooldown=0,
        global_cooldown=0,
        hourly_limit=1,
        max_consecutive=10,
    )
    assert not store.claim(
        2,
        "B",
        action_cooldown=0,
        global_cooldown=0,
        hourly_limit=1,
        max_consecutive=10,
    )


def test_human_message_resets_consecutive_guard():
    store = CooldownStore()
    assert store.claim(
        3,
        "A",
        action_cooldown=0,
        global_cooldown=0,
        hourly_limit=20,
        max_consecutive=1,
    )
    store.record_human_message(3)
    assert store.claim(
        3,
        "B",
        action_cooldown=0,
        global_cooldown=0,
        hourly_limit=20,
        max_consecutive=1,
    )
