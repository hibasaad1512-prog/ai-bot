from types import SimpleNamespace

from app.telegram.routing import is_non_command_message


def msg(text=None, caption=None, chat_type="private"):
    return SimpleNamespace(
        text=text,
        caption=caption,
        from_user=SimpleNamespace(id=1, first_name="u", username="u", is_bot=False),
        chat=SimpleNamespace(id=123, type=chat_type),
        photo=[],
    )


def test_non_command_is_ai_message():
    assert is_non_command_message(msg("hello")) is True
    assert is_non_command_message(msg("what is chaos?")) is True


def test_required_commands_bypass_ai_handler():
    assert is_non_command_message(msg("/start")) is False
    assert is_non_command_message(msg("/settings")) is False
    assert is_non_command_message(msg("/testai")) is False
    assert is_non_command_message(msg("/start@kyoos_bot")) is False


def test_photo_with_caption_is_ai_message():
    m = msg(caption="look at this")
    m.photo = [SimpleNamespace(file_id="photo")]
    assert is_non_command_message(m) is True


def test_photo_without_caption_stays_non_text_path():
    m = msg()
    m.photo = [SimpleNamespace(file_id="photo")]
    assert is_non_command_message(m) is True
