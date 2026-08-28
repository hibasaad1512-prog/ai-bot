from app.ai.dialect import detect

def test_moroccan_darija():
    p=detect(["واش خويا شنو هادشي"]); assert p.dialect=="moroccan_darija"

def test_english():
    p=detect(["bro what is this lol"]); assert p.language=="en"
