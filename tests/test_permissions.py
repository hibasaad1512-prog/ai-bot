from types import SimpleNamespace
from app.telegram.permissions import can_use_settings, can_use_testai

class DummyBot:
    def __init__(self, status="member"):
        self.status=status
    def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status=self.status)

def msg(chat_type, user_id, chat_id=-1001):
    return SimpleNamespace(chat=SimpleNamespace(type=chat_type,id=chat_id), from_user=SimpleNamespace(id=user_id))

def test_settings_rejects_private():
    assert not can_use_settings(DummyBot("administrator"), msg("private", 123))

def test_settings_accepts_group_admin():
    assert can_use_settings(DummyBot("administrator"), msg("supergroup", 123))

def test_settings_rejects_group_member():
    assert not can_use_settings(DummyBot("member"), msg("group", 123))

def test_testai_works_in_private_for_global_admin(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_IDS", "123")
    # config is loaded at import time; use the already configured set if present in test env.
    from app.config import settings
    object.__setattr__(settings, "admin_user_ids", frozenset({123}))
    assert can_use_testai(DummyBot("member"), msg("private", 123))


def test_settings_isolated_per_chat_admin():
    assert can_use_settings(DummyBot("administrator"), msg("group", 42, -1001))
    assert not can_use_settings(DummyBot("member"), msg("group", 42, -1002))

def test_testai_rejects_private_non_global_admin(monkeypatch):
    from app.config import settings
    object.__setattr__(settings, "admin_user_ids", frozenset({999}))
    assert not can_use_testai(DummyBot("member"), msg("private", 123))

def test_settings_requires_telegram_admin_status():
    assert not can_use_settings(DummyBot("member"), msg("supergroup", 123, -2002))
