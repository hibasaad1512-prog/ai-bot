from __future__ import annotations
from io import BytesIO
from PIL import Image,ImageDraw,ImageFont,ImageOps

def caption_meme(raw:bytes,caption:str)->BytesIO:
    im=Image.open(BytesIO(raw)).convert("RGB")
    band=max(80,int(im.height*0.18)); out=ImageOps.fit(im,im.size)
    canvas=Image.new("RGB",(out.width,out.height+band),(0,0,0)); canvas.paste(out,(0,band))
    draw=ImageDraw.Draw(canvas); font=ImageFont.load_default(size=max(18,out.width//28))
    draw.multiline_text((20,12),caption[:250],fill="white",font=font,stroke_width=2,stroke_fill="black",spacing=5)
    b=BytesIO(); b.name="kyoos_meme.jpg"; canvas.save(b,"JPEG",quality=88); b.seek(0); return b
