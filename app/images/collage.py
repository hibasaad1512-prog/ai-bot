from __future__ import annotations
from io import BytesIO
from PIL import Image,ImageOps,ImageDraw

def _open(raw:bytes)->Image.Image:
    return Image.open(BytesIO(raw)).convert("RGB")

def side_by_side(a:bytes,b:bytes)->BytesIO:
    im1,im2=_open(a),_open(b); h=max(im1.height,im2.height); w=im1.width*h//im1.height+im2.width*h//im2.height
    out=Image.new("RGB",(w,h)); out.paste(ImageOps.contain(im1,(w//2,h)),(0,0)); out.paste(ImageOps.contain(im2,(w-w//2,h)),(w//2,0)); return _save(out)

def collage(images:list[bytes],cols:int=2)->BytesIO:
    ims=[_open(x) for x in images[:4]]; size=700; cell=size//cols; rows=(len(ims)+cols-1)//cols
    out=Image.new("RGB",(size,rows*cell),(25,25,25))
    for i,im in enumerate(ims):out.paste(ImageOps.fit(im,(cell,cell)),((i%cols)*cell,(i//cols)*cell))
    return _save(out)

def _save(im:Image.Image)->BytesIO:
    b=BytesIO(); b.name="kyoos_mashup.jpg"; im.save(b,"JPEG",quality=88,optimize=True); b.seek(0); return b
