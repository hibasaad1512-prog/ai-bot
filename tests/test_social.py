import time
from app.models import ChatMessage
from app.chaos.social import analyze
from app.chaos.scoring import Activity, ScoreInput, intervention_score


def msg(i, text, user=1, reply=None, bot=False, age=0):
    return ChatMessage(-100, i, user, f"u{user}", time.time()-age, text, reply, None, None, bot)


def test_direct_address_is_detected():
    s = analyze([msg(1, "yo kyoos", user=2)], bot_username="kyoos")
    assert s.direct_address


def test_serious_context_reduces_score():
    activity = Activity(5, "NORMAL", 0, 0, 0)
    normal = intervention_score(ScoreInput(70,False,False,.2,.2,.4,0,0,False,False,0,30,activity))
    serious = intervention_score(ScoreInput(70,False,False,.2,.2,.4,0,0,False,False,0,30,activity,serious_context=1))
    assert serious < normal
