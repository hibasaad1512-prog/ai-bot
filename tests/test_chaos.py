import time
from app.chaos.scoring import Activity,ScoreInput,intervention_score

def test_very_active_reduces_score():
    base=dict(personality_chaos=70,mentioned=False,reply_to_bot=False,funny_context=.5,useful_context=.2,continuity=.3,image_opportunity=.2,event_opportunity=.1,action_recently_used=False,cooldown_active=False,hourly_count=0,hard_limit=30)
    quiet=intervention_score(ScoreInput(**base,activity=Activity(0,"QUIET",11,0,0)))
    active=intervention_score(ScoreInput(**base,activity=Activity(100,"VERY_ACTIVE",0,2,2)))
    assert quiet>active

def test_cooldown_zeroes_score():
    x=ScoreInput(70,True,True,.9,.5,.5,.5,.5,False,True,0,30,Activity(1,"NORMAL",0,0,0))
    assert intervention_score(x)==0
