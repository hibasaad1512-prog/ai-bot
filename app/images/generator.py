from __future__ import annotations
from app.ai.base import AIProvider

def generate(provider:AIProvider,prompt:str)->bytes|None:
    return provider.generate_image(prompt)
