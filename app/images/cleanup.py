from __future__ import annotations
from app.images.pool import ImagePool

def cleanup_pool(pool:ImagePool,chat_ids:list[int])->None:
    for chat_id in chat_ids: pool.cleanup(chat_id)
