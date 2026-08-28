from app.chaos.cooldowns import CooldownStore

def test_cooldown():
    c=CooldownStore(); c.set('x',60); assert c.active('x')

def test_hourly_count():
    c=CooldownStore(); c.record_action(1); assert c.hourly_count(1)==1
