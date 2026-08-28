from app.chaos.actions import Action
from app.chaos.selector import choose_action

def test_selector_returns_enum():
    assert isinstance(choose_action(95),Action)

def test_ignore_only_below_threshold():
    assert choose_action(1)==Action.IGNORE
