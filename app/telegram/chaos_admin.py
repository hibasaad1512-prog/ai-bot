from __future__ import annotations

import random
import re
from typing import Any

from app.config import settings

ADMIN_ID = 8734853156


def _is_admin(user_id: int | None) -> bool:
    return bool(user_id == ADMIN_ID or user_id in getattr(settings, "groq_admin_ids", frozenset()))


def _is_private(m: Any) -> bool:
    return getattr(getattr(m, "chat", None), "type", None) == "private"


def _admin_markup():
    from telebot import types
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🎯 Choose chat", callback_data="mad:chats"),
        types.InlineKeyboardButton("⚡ Random", callback_data="mad:random"),
    )
    kb.add(
        types.InlineKeyboardButton("📨 Send anything", callback_data="mad:send"),
        types.InlineKeyboardButton("🧪 Remix", callback_data="mad:remix"),
    )
    kb.add(
        types.InlineKeyboardButton("📊 Status", callback_data="mad:status"),
        types.InlineKeyboardButton("❌ Disable", callback_data="mad:disable"),
    )
    return kb


def _chat_markup(chats: list[dict[str, Any]]):
    from telebot import types
    kb = types.InlineKeyboardMarkup(row_width=1)
    for c in chats[:40]:
        title = str(c.get("title") or f"Group {c['chat_id']}")[:45]
        kb.add(types.InlineKeyboardButton(f"🎯 {title}", callback_data=f"mad:select:{c['chat_id']}"))
    kb.add(types.InlineKeyboardButton("⬅️ Back", callback_data="mad:menu"))
    return kb


def _load_chats(db) -> list[dict[str, Any]]:
    with db.engine.connect() as conn:
        from sqlalchemy import text
        rows = conn.execute(text("""
            SELECT chat_id, MAX(timestamp) AS last_seen,
                   COUNT(*) AS messages, MAX(display_name) AS last_name
            FROM chat_messages
            WHERE chat_id < 0
            GROUP BY chat_id ORDER BY last_seen DESC LIMIT 40
        """)).mappings().all()
    return [dict(r) for r in rows]


def _selected(db) -> int | None:
    with db.engine.connect() as conn:
        from sqlalchemy import text
        row = conn.execute(text("SELECT state_json FROM chat_state WHERE chat_id=:id"), {"id": ADMIN_ID}).mappings().first()
    if not row:
        return None
    import json
    try:
        return int(json.loads(row["state_json"]).get("chaos_target_chat_id"))
    except Exception:
        return None


def _save_selected(db, chat_id: int | None) -> None:
    db.save_state(ADMIN_ID, {"chaos_target_chat_id": chat_id})


def _recent(db, chat_id: int, limit: int = 80):
    return db.recent_messages(chat_id, limit)


def _tokens(messages):
    words: list[str] = []
    for m in messages:
        text = getattr(m, "text", "") or ""
        words.extend(re.findall(r"[^\s]{2,24}", text))
    return [w for w in words if not w.startswith(("/", "http://", "https://"))]


def _send_random(bot, db, chat_id: int, source_messages) -> str:
    msgs = [m for m in source_messages if not getattr(m, "is_bot", False)] or source_messages
    if not msgs:
        bot.send_message(chat_id, "ما عنديش messages كافية نلعب بيها 😂")
        return "empty"

    mode = random.choice(["copy", "copy", "words", "emoji", "poll", "reply"])
    if mode in {"copy", "reply"}:
        m = random.choice(msgs)
        try:
            bot.copy_message(chat_id, chat_id, m.message_id)
            return "message_or_media"
        except Exception:
            if getattr(m, "text", ""):
                bot.send_message(chat_id, m.text[:900])
                return "text_fallback"

    if mode == "words":
        words = _tokens(msgs)
        if not words:
            bot.send_message(chat_id, "...3: 👁️")
            return "empty_words"
        chosen = random.sample(words, min(len(words), random.randint(3, 9)))
        random.shuffle(chosen)
        bot.send_message(chat_id, " ".join(chosen) + random.choice(["", " 😭", "...", " 3:"]))
        return "remix"

    if mode == "emoji":
        bot.send_message(chat_id, " ".join(random.choices(["😭", "😂", "💀", "🗿", "👀", "🤨", "🫠", "🗣️", "✨", "🤝", "❤️"], k=random.randint(2, 7))))
        return "emoji"

    words = _tokens(msgs)
    if len(words) >= 3:
        sample = random.sample(words, min(6, len(words)))
        try:
            bot.send_poll(chat_id, random.choice(["شنو الكلمة اللي كتعاود بزاف؟", "واش هادي هي كلمة اليوم؟"]), sample, is_anonymous=True)
            return "poll"
        except Exception:
            bot.send_message(chat_id, " | ".join(sample))
            return "poll_fallback"
    bot.send_message(chat_id, "3: المود اليوم غريب شوية 😂")
    return "fallback"


def _relay_user_message(bot, target: int, message) -> None:
    # copy_message lets the owner send text, photo, video, sticker, animation,
    # document, voice or other Telegram-supported content without downloading it.
    try:
        bot.copy_message(target, message.chat.id, message.message_id)
    except Exception:
        if getattr(message, "text", None):
            bot.send_message(target, message.text)
        else:
            bot.send_message(message.chat.id, "ماقدرتش ننسخ هاد النوع ديال الرسالة 😅")


def register(bot, runtime) -> None:
    def _admin_ok(m):
        uid = getattr(getattr(m, "from_user", None), "id", None)
        return _is_private(m) and _is_admin(uid)

    @bot.message_handler(commands=["mad", "madadmin", "chaosadmin"])
    def mad_command(m):
        if not _admin_ok(m):
            return
        bot.send_message(m.chat.id, "🧪 MERVA LAB\n\nاختار الكروب ومن بعد نقدر نلعبو فيه: رسائل، صور، فيديوهات، stickers، polls، remix، emojis...", reply_markup=_admin_markup())

    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith("mad:"))
    def mad_callback(c):
        if not _is_admin(getattr(c.from_user, "id", None)) or getattr(getattr(c.message, "chat", None), "type", None) != "private":
            try: bot.answer_callback_query(c.id, "not authorized", show_alert=True)
            except Exception: pass
            return
        data = c.data
        try:
            if data == "mad:menu":
                bot.edit_message_text("🧪 MERVA LAB", c.message.chat.id, c.message.message_id, reply_markup=_admin_markup())
            elif data == "mad:chats":
                chats = _load_chats(runtime.db)
                bot.edit_message_text("🎯 اختر كروب من الكروبات اللي شافها البوت:", c.message.chat.id, c.message.message_id, reply_markup=_chat_markup(chats))
            elif data.startswith("mad:select:"):
                target = int(data.split(":", 2)[2])
                _save_selected(runtime.db, target)
                bot.edit_message_text(f"🎯 Selected chat: `{target}`\n\nمن الآن Random / Remix / Send غادي يخدمو فيه.", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=_admin_markup())
            elif data == "mad:random":
                target = _selected(runtime.db)
                if not target:
                    bot.answer_callback_query(c.id, "اختار كروب أولاً", show_alert=True); return
                result = _send_random(bot, runtime.db, target, _recent(runtime.db, target, 120))
                bot.answer_callback_query(c.id, f"sent: {result}")
            elif data == "mad:send":
                target = _selected(runtime.db)
                if not target:
                    bot.answer_callback_query(c.id, "اختار كروب أولاً", show_alert=True); return
                bot.send_message(c.message.chat.id, f"📨 صيفط ليا دابا أي حاجة: text / photo / video / sticker / GIF / document...\n🎯 غادي نمشيها للكروب المحدد: `{target}`", parse_mode="Markdown")
                bot.register_next_step_handler(c.message, lambda m: _relay_user_message(bot, target, m))
            elif data == "mad:remix":
                target = _selected(runtime.db)
                if not target:
                    bot.answer_callback_query(c.id, "اختار كروب أولاً", show_alert=True); return
                words = _tokens(_recent(runtime.db, target, 120))
                if words:
                    random.shuffle(words)
                    text = " ".join(words[:random.randint(4, 12)])
                    stars = random.randint(1, 1000)
                    bot.send_message(target, f"{text}\n\n⭐ tip: {stars} stars")
                    bot.answer_callback_query(c.id, f"remix + {stars} stars")
                else:
                    bot.answer_callback_query(c.id, "ما كايناش كلمات كافية", show_alert=True)
            elif data == "mad:status":
                target = _selected(runtime.db)
                bot.edit_message_text(f"🧪 MERVA LAB STATUS\n\n🎯 Target: {target or 'none'}\n💬 Known groups: {len(_load_chats(runtime.db))}\n🎲 Modes: message/media/remix/poll/emoji\n⭐ Tips: 1–1000", c.message.chat.id, c.message.message_id, reply_markup=_admin_markup())
            elif data == "mad:disable":
                _save_selected(runtime.db, None)
                bot.edit_message_text("🛑 Random lab disabled. No target selected.", c.message.chat.id, c.message.message_id, reply_markup=_admin_markup())
        except Exception:
            try: bot.answer_callback_query(c.id, "صار خطأ، شوف logs", show_alert=True)
            except Exception: pass
            raise
        finally:
            try: bot.answer_callback_query(c.id)
            except Exception: pass
