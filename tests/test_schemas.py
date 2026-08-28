import pytest
from app.ai.schemas import DecisionPayload

def test_schema_validation():
    d=DecisionPayload.validate({"should_act":True,"action":"REPLY_CONTEXT","confidence":2,"target_message_id":10,"language":"en","dialect":"casual","intensity":"medium"},{10})
    assert d.confidence==1 and d.target_message_id==10

def test_schema_rejects_unknown_action():
    with pytest.raises(ValueError):DecisionPayload.validate({"should_act":True,"action":"NOT_A_REAL_ACTION","confidence":.2,"target_message_id":None,"language":"en","intensity":"low"},set())
