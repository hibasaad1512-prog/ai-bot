from __future__ import annotations
import base64, json, logging
from typing import Any
from .base import AIProvider
from .schemas import DECISION_SCHEMA
from app.config import settings
log=logging.getLogger(__name__)

class GeminiProvider(AIProvider):
    def __init__(self, api_key: str|None=None, model: str|None=None):
        self.api_key=(api_key if api_key is not None else settings.gemini_api_key).strip()
        self.model=(model or settings.text_model).strip()
        self.client=None
        if self.api_key:
            try:
                from google import genai
                self.client=genai.Client(api_key=self.api_key)
            except Exception: log.exception('Gemini init failed')
    @property
    def enabled(self)->bool: return self.client is not None and bool(self.model)
    def _call(self,prompt:str,system:str|None=None,structured:bool=False):
        if not self.client: raise RuntimeError('Gemini is not configured')
        from google.genai import types
        config=types.GenerateContentConfig(system_instruction=system or '',temperature=0.65,max_output_tokens=500)
        if structured:
            config.response_mime_type='application/json'; config.response_schema=DECISION_SCHEMA
        return self.client.models.generate_content(model=self.model,contents=prompt,config=config)
    def generate_text(self,prompt,system=None)->str: return (getattr(self._call(prompt,system),'text','') or '').strip()
    def generate_structured(self,prompt,schema,system=None)->dict[str,Any]: return json.loads((getattr(self._call(prompt,system,True),'text','') or '{}').strip())
    def analyze_image(self,image_bytes:bytes,prompt:str)->str:
        if not self.client: raise RuntimeError('Gemini is not configured')
        from google.genai import types
        r=self.client.models.generate_content(model=self.model,contents=[prompt,types.Part.from_bytes(data=image_bytes,mime_type='image/jpeg')],config=types.GenerateContentConfig(max_output_tokens=400,temperature=0.2))
        return (getattr(r,'text','') or '').strip()
    def generate_image(self,prompt:str)->bytes|None:
        if not self.client:return None
        try:
            r=self.client.models.generate_content(model=settings.image_model,contents=prompt,config={'response_modalities':['IMAGE']})
            for part in getattr(r,'parts',[]) or []:
                if getattr(part,'inline_data',None): return part.inline_data.data if isinstance(part.inline_data.data,(bytes,bytearray)) else base64.b64decode(part.inline_data.data)
        except Exception: log.exception('Gemini image generation failed')
        return None
