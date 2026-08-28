from app.images.collage import collage
from app.images.pool import ImagePool,ImageRef
from io import BytesIO
from PIL import Image

def raw(color):
    b=BytesIO(); Image.new('RGB',(50,50),color).save(b,'PNG'); return b.getvalue()

def test_collage():
    out=collage([raw('red'),raw('blue')]); assert out.getbuffer().nbytes>0

def test_pool_marks_used():
    p=ImagePool(ttl=100,max_per_chat=2); r=ImageRef(1,1,'f',__import__('time').time(),None,2,'photo'); p.add(r); assert p.choose(1)==r; p.mark_used(r); assert r.used_at is not None
