from __future__ import annotations

import logging
import random
import re
import time
from io import BytesIO

from app.ai.dialect import detect
from app.ai.humanizer import humanize
from app.ai.prompts import response_prompt
from app.chaos.actions import Action
from app.config import settings
from app.images.collage import collage, side_by_side
from app.images.meme import caption_meme
from app.images.pool import ImageRef
from app.models import ChatMessage
from app.telegram.admin_panel import adjust_panel, language_panel, panel
from app.telegram.routing import is_non_command_message
from app.telegram.permissions import (
    can_use_settings,
    can_use_settings_callback,
    can_use_testai,
    is_group,
)

log = logging.getLogger(__name__)


class TelegramHandlers:
    """Telegram handlers for الميرفاوية.

    Normal behavior:
    - 80% configurable reply chance
    - random human-like delay
    - per-user reply limit
    - occasional random callbacks to older messages
    - occasional remix of words/phrases from the conversation
    """

    def __init__(self, bot, runtime):
        self.bot = bot
        self.rt = runtime
        self._bot_username = "الميرفاوية"

        self._user_reply_limits: dict[
            tuple[int, int],
            dict[str, float | int],
        ] = {}

        self._register()

    def _register(self):
        from telebot import types

        @self.bot.message_handler(commands=["start"])
        def start(m):
            if is_group(m.chat.type):
                self.bot.reply_to(m, "أنا هنا")
            else:
                self.bot.send_message(
                    m.chat.id,
                    "الميرفاوية هنا",
                )

        @self.bot.message_handler(commands=["settings"])
        def settings_cmd(m):
            self.admin_command(m)

        @self.bot.message_handler(commands=["testai"])
        def testai(m):
            if not can_use_testai(self.bot, m):
                return

            lines = [
                "LMYRFAWYA AI TEST",
                f"Provider: Groq {'✅' if self.rt.ai.enabled else '❌'}",
            ]

            if not self.rt.ai.enabled:
                lines.append(
                    "Text API: ❌ GROQ_API_KEY missing or Groq client failed to initialize"
                )
            else:
                try:
                    text = self.rt.ai.generate_text(
                        "Reply with exactly: ping"
                    )

                    lines.append(
                        f"Text API: {'✅' if text.strip() else '❌'}"
                    )

                    if text.strip() and text.strip().lower() != "ping":
                        lines.append(
                            f"Reply: {text[:120]}"
                        )

                except Exception as exc:
                    log.exception("/testai failed")
                    lines.append(
                        f"Text API: ❌ {type(exc).__name__}: {str(exc)[:160]}"
                    )

            lines.append(
                "Runtime: 80% reply chance + delay + random callbacks"
            )

            self.bot.send_message(
                m.chat.id,
                "\n".join(lines),
            )

        @self.bot.callback_query_handler(
            func=lambda c: c.data.startswith("panel:")
            or c.data.startswith("set:")
            or c.data.startswith("language:")
        )
        def callbacks(c):
            if not can_use_settings_callback(self.bot, c):
                self.bot.answer_callback_query(
                    c.id,
                    "group admins only",
                    show_alert=True,
                )
                return

            chat_id = c.message.chat.id
            p = self.rt.personality(chat_id)
            data = c.data

            try:
                if data == "panel:back":
                    self.bot.edit_message_text(
                        "الميرفاوية settings",
                        chat_id,
                        c.message.message_id,
                        reply_markup=panel(
                            p,
                            self.rt.get_language_mode(chat_id),
                        ),
                    )

                elif data == "language:show":
                    self.bot.edit_message_reply_markup(
                        chat_id,
                        c.message.message_id,
                        reply_markup=language_panel(
                            self.rt.get_language_mode(chat_id)
                        ),
                    )

                elif data.startswith("language:set:"):
                    mode = data.split(":", 2)[2]

                    self.rt.save_language_mode(
                        chat_id,
                        mode,
                    )

                    self.bot.edit_message_text(
                        "الميرفاوية settings",
                        chat_id,
                        c.message.message_id,
                        reply_markup=panel(p, mode),
                    )

                elif data.startswith("set:"):
                    _, key, delta = data.split(":")

                    if delta == "show":
                        self.bot.edit_message_reply_markup(
                            chat_id,
                            c.message.message_id,
                            reply_markup=adjust_panel(
                                p,
                                key,
                            ),
                        )
                    else:
                        value = max(
                            0,
                            min(
                                100,
                                getattr(p, key) + int(delta),
                            ),
                        )

                        setattr(p, key, value)
                        self.rt.save_personality(
                            chat_id,
                            p,
                        )

                        self.bot.edit_message_reply_markup(
                            chat_id,
                            c.message.message_id,
                            reply_markup=adjust_panel(
                                p,
                                key,
                            ),
                        )

            except Exception:
                log.exception(
                    "settings callback failed"
                )

            finally:
                try:
                    self.bot.answer_callback_query(c.id)
                except Exception:
                    pass

        @self.bot.message_handler(
            content_types=["text", "photo"],
            func=is_non_command_message,
        )
        def normal_message(m):
            self.on_message(m)

        @self.bot.message_handler(
            content_types=["text"],
            func=lambda m: bool(m.text)
            and m.text.strip().upper() == "JOIN",
        )
        def game_join(m):
            if not self.rt.games.join(
                m.chat.id,
                m.from_user.id,
            ):
                return

            self.bot.reply_to(
                m,
                "joined",
            )

    def admin_command(self, m):
        if not can_use_settings(self.bot, m):
            if getattr(m.chat, "type", None) == "private":
                self.bot.send_message(
                    m.chat.id,
                    "⚙️ /settings is available inside groups for admins",
                )
            return

        self.bot.send_message(
            m.chat.id,
            "الميرفاوية settings",
            reply_markup=panel(
                self.rt.personality(m.chat.id),
                self.rt.get_language_mode(m.chat.id),
            ),
        )

    def _remember_bot_reply(
        self,
        m,
        text: str,
        reply_to: int | None = None,
    ) -> None:
        self.rt.memory.add(
            ChatMessage(
                chat_id=m.chat.id,
                message_id=int(time.time() * 1000),
                user_id=0,
                display_name=self._bot_username,
                timestamp=time.time(),
                text=text,
                reply_to_message_id=reply_to,
                is_bot=True,
            )
        )

    def _can_reply_to_user(
        self,
        chat_id: int,
        user_id: int,
    ) -> bool:
        key = (chat_id, user_id)
        now = time.time()

        state = self._user_reply_limits.get(key)

        if not state:
            return True

        reset_at = float(
            state.get("reset_at", 0)
        )

        if now >= reset_at:
            self._user_reply_limits.pop(
                key,
                None,
            )
            return True

        count = int(
            state.get("count", 0)
        )

        limit = getattr(
            settings,
            "same_user_limit",
            2,
        )

        return count < limit

    def _record_user_reply(
        self,
        chat_id: int,
        user_id: int,
    ) -> None:
        key = (chat_id, user_id)
        now = time.time()

        limit = getattr(
            settings,
            "same_user_limit",
            2,
        )

        cooldown = getattr(
            settings,
            "same_user_cooldown",
            180,
        )

        state = self._user_reply_limits.get(key)

        if not state:
            state = {
                "count": 0,
                "reset_at": now + cooldown,
            }

        state["count"] = (
            int(state.get("count", 0)) + 1
        )

        if int(state["count"]) >= limit:
            state["reset_at"] = (
                now + cooldown
            )

        self._user_reply_limits[key] = state

    def _reply_chance_passes(self) -> bool:
        chance = getattr(
            settings,
            "reply_chance",
            80,
        )

        chance = max(
            0,
            min(
                100,
                int(chance),
            ),
        )

        return random.random() * 100 < chance

    def _random_reply_delay(self) -> float:
        minimum = float(
            getattr(
                settings,
                "reply_delay_min",
                1.5,
            )
        )

        maximum = float(
            getattr(
                settings,
                "reply_delay_max",
                4.0,
            )
        )

        if maximum < minimum:
            minimum, maximum = maximum, minimum

        return random.uniform(
            minimum,
            maximum,
        )

    def _random_callback_enabled(self) -> bool:
        """Small chance of responding to an older message."""

        return random.random() < 0.15

    def _random_remix_enabled(self) -> bool:
        """Small chance of creating a conversational remix."""

        return random.random() < 0.08

    def _random_callback_context(
        self,
        chat_id: int,
        current_message_id: int,
    ) -> tuple[str, str]:
        """Pick an older human message for an occasional callback."""

        recent = self.rt.memory.recent(
            chat_id,
            40,
        )

        candidates = [
            x
            for x in recent
            if (
                x.text
                and not x.is_bot
                and x.message_id != current_message_id
            )
        ]

        if not candidates:
            return "", ""

        # Prefer messages that are not extremely old.
        candidates = candidates[-25:]

        chosen = random.choice(candidates)

        return (
            f"Random older message selected for a callback:\n"
            f"{chosen.display_name}: {chosen.text[:700]}\n",
            chosen.text[:700],
        )

    def _random_remix_context(
        self,
        chat_id: int,
    ) -> str:
        """Collect random words/phrases from different messages.

        The AI decides whether they can be combined naturally.
        It must not blindly concatenate them.
        """

        recent = self.rt.memory.recent(
            chat_id,
            40,
        )

        candidates = [
            x
            for x in recent
            if (
                x.text
                and not x.is_bot
                and len(x.text.strip()) >= 2
            )
        ]

        if len(candidates) < 3:
            return ""

        chosen_messages = random.sample(
            candidates,
            min(
                4,
                len(candidates),
            ),
        )

        pieces: list[str] = []

        for message in chosen_messages:
            words = re.findall(
                r"\S+",
                message.text.strip(),
            )

            if not words:
                continue

            if len(words) <= 4:
                piece = " ".join(words)
            else:
                count = random.randint(
                    1,
                    min(4, len(words)),
                )

                start = random.randint(
                    0,
                    len(words) - count,
                )

                piece = " ".join(
                    words[start:start + count]
                )

            pieces.append(
                f"{message.display_name}: {piece}"
            )

        if not pieces:
            return ""

        return (
            "Random words/phrases from different "
            "parts of the conversation:\n"
            + "\n".join(pieces)
            + "\n\n"
            "Use these only if they can be turned into "
            "a natural, contextually relevant message. "
            "Do not simply concatenate them."
        )

    def _build_reply_context(
        self,
        m,
        base_context: str,
        text: str,
    ) -> tuple[str, str]:
        """Build normal, callback, or remix context."""

        direct_context = (
            f"Latest user message: "
            f"{m.from_user.first_name or m.from_user.username or 'user'}: "
            f"{text[:1000]}\n"
        )

        if (
            m.reply_to_message
            and m.reply_to_message.text
        ):
            direct_context += (
                f"Reply target: "
                f"{m.reply_to_message.text[:600]}\n"
            )

        mode = "DIRECT_REPLY"

        # Sometimes callback to an older message.
        if self._random_callback_enabled():
            callback_context, target = (
                self._random_callback_context(
                    m.chat.id,
                    m.message_id,
                )
            )

            if callback_context:
                direct_context += (
                    "\n" + callback_context
                )
                mode = "RANDOM_CALLBACK"

        # Sometimes remix words/phrases from the chat.
        if self._random_remix_enabled():
            remix_context = (
                self._random_remix_context(
                    m.chat.id,
                )
            )

            if remix_context:
                direct_context += (
                    "\n" + remix_context
                )

                # If both happen, the model decides how to
                # naturally combine them.
                if mode == "DIRECT_REPLY":
                    mode = "CHAT_REMIX"

        return (
            f"{base_context}\n{direct_context}",
            mode,
        )

    def on_message(self, m):
        if not m.from_user:
            return

        text = m.text or m.caption or ""

        image_file_id = None
        media_type = None

        if m.photo:
            media_type = "photo"
            image_file_id = m.photo[-1].file_id

            self.rt.images.add(
                ImageRef(
                    m.chat.id,
                    m.message_id,
                    image_file_id,
                    time.time(),
                    None,
                    m.from_user.id,
                    "photo",
                )
            )

        cm = ChatMessage(
            m.chat.id,
            m.message_id,
            m.from_user.id,
            m.from_user.first_name
            or m.from_user.username
            or "user",
            m.date or time.time(),
            text,
            (
                m.reply_to_message.message_id
                if m.reply_to_message
                else None
            ),
            media_type,
            image_file_id,
            bool(
                getattr(
                    m.from_user,
                    "is_bot",
                    False,
                )
            ),
        )

        self.rt.memory.add(cm)

        # Never reply to another bot.
        if getattr(
            m.from_user,
            "is_bot",
            False,
        ):
            return

        if text and settings.enabled_moderation:
            try:
                mod = self.rt.moderation.detect(
                    text,
                    [
                        x.text
                        for x in self.rt.memory.recent(
                            m.chat.id,
                            12,
                        )
                        if x.text
                    ],
                )

                if mod and mod.action == "delete":
                    try:
                        self.bot.delete_message(
                            m.chat.id,
                            m.message_id,
                        )
                    except Exception:
                        pass

                    return

            except Exception:
                log.exception(
                    "moderation check failed; continuing to AI"
                )

        if m.photo and not text:
            return

        if not text:
            return

        if not self.rt.ai.enabled:
            self.bot.send_message(
                m.chat.id,
                "⚠️ AI is not configured right now",
            )
            return

        user_id = m.from_user.id

        # Per-user limit.
        if not self._can_reply_to_user(
            m.chat.id,
            user_id,
        ):
            log.info(
                "Reply skipped: user %s reached limit in chat %s",
                user_id,
                m.chat.id,
            )
            return

        # 80% chance.
        if not self._reply_chance_passes():
            log.info(
                "Reply skipped by reply chance: chat=%s user=%s",
                m.chat.id,
                user_id,
            )
            return

        # Human-like delay.
        delay = self._random_reply_delay()

        try:
            time.sleep(delay)
        except Exception:
            pass

        recent = self.rt.memory.recent(
            m.chat.id,
            40,
        )

        base_context = self.rt.memory.text(
            m.chat.id,
            20,
        )

        lang = detect(
            [
                x.text
                for x in recent
                if x.text
            ]
        )

        personality = self.rt.personality(
            m.chat.id
        )

        signals = None

        try:
            state = self.rt.db.get_json(
                "chat_settings",
                "chat_id",
                m.chat.id,
                {},
            )

            state["language"] = lang.as_dict()

            self.rt.db.save_chat_settings(
                m.chat.id,
                state,
            )

            prompt_context, mode = (
                self._build_reply_context(
                    m,
                    base_context,
                    text,
                )
            )

            prompt = response_prompt(
                prompt_context,
                lang,
                personality,
                mode,
                target=text,
                signals=signals,
            )

            reply = self.rt.ai.generate_text(
                prompt
            )

            reply = humanize(
                reply,
                personality,
                lang.as_dict(),
            )

            reply = self._clean_reply(
                reply
            )

            # Empty AI response does not consume the user's slot.
            if not reply:
                return

            reply_to_id = (
                m.message_id
                if is_group(m.chat.type)
                else None
            )

            self.bot.send_message(
                m.chat.id,
                reply[:1000],
                reply_to_message_id=reply_to_id,
                allow_sending_without_reply=True,
            )

            # Count only successful responses.
            self._record_user_reply(
                m.chat.id,
                user_id,
            )

            self._remember_bot_reply(
                m,
                reply[:1000],
                reply_to_id,
            )

            self.rt.chaos.cooldowns.record_action(
                m.chat.id
            )

        except Exception:
            log.exception(
                "direct AI reply failed"
            )

    @staticmethod
    def _clean_reply(text: str) -> str:
        text = (text or "").strip()

        text = re.sub(
            r"^```(?:text)?\s*|\s*```$",
            "",
            text,
            flags=re.I,
        ).strip()

        text = text.strip('"').strip()

        return text[:1000]

    def proactive(self, chat_id: int):
        recent = self.rt.memory.recent(
            chat_id,
            40,
        )

        if not recent or not self.rt.ai.enabled:
            return

        p = self.rt.personality(
            chat_id
        )

        now = time.time()
        last = recent[-1].timestamp

        if (
            now - last
            < settings.proactive_quiet_seconds
            or p.proactivity < 25
        ):
            return

        if self.rt.chaos.cooldowns.active(
            f"chat:{chat_id}"
        ):
            return

        if (
            self.rt.chaos.cooldowns.hourly_count(
                chat_id
            )
            >= settings.soft_hourly_limit
        ):
            return

        context = self.rt.memory.text(
            chat_id,
            20,
        )

        lang = detect(
            [
                x.text
                for x in recent
                if x.text
            ]
        )

        try:
            txt = self.rt.ai.generate_text(
                response_prompt(
                    context,
                    lang,
                    p,
                    "PROACTIVE",
                )
            )

            txt = humanize(
                txt,
                p,
                lang.as_dict(),
            )

            txt = self._clean_reply(txt)

            if txt:
                self.bot.send_message(
                    chat_id,
                    txt[:1000],
                )

                self.rt.chaos.cooldowns.record_action(
                    chat_id
                )

        except Exception:
            log.exception(
                "proactive action failed"
            )

    def execute(
        self,
        m,
        action,
        context,
        lang,
        target_id,
        signals=None,
    ):
        p = self.rt.personality(
            m.chat.id
        )

        reply_id = target_id or m.message_id

        if action in {
            Action.REPLY_CONTEXT,
            Action.JOIN_CONVERSATION,
            Action.CHAOS_TEXT,
            Action.QUOTE_REMIX,
            Action.RANDOM_QUESTION,
            Action.MINI_CHALLENGE,
            Action.RANDOM_TEMPLATE,
            Action.FAKE_ANNOUNCEMENT,
        }:
            focus = next(
                (
                    x
                    for x in reversed(
                        self.rt.memory.recent(
                            m.chat.id,
                            40,
                        )
                    )
                    if x.message_id == target_id
                ),
                None,
            )

            focus_text = (
                f"Target: {focus.display_name}: {focus.text}"
                if focus and focus.text
                else ""
            )

            try:
                txt = self.rt.ai.generate_text(
                    response_prompt(
                        context,
                        lang,
                        p,
                        action.value,
                        target=focus_text,
                        signals=signals,
                    )
                )

                txt = humanize(
                    txt,
                    p,
                    lang.as_dict(),
                )

                txt = self._clean_reply(txt)

                if txt:
                    self.bot.send_message(
                        m.chat.id,
                        txt[:1000],
                        reply_to_message_id=reply_id,
                        allow_sending_without_reply=True,
                    )

            except Exception:
                log.exception(
                    "text action failed"
                )

            return

        if action in {
            Action.RANDOM_IMAGE,
            Action.IMAGE_CAPTION,
            Action.CONTEXT_MEME,
        }:
            ref = self.rt.images.choose(
                m.chat.id
            )

            if not ref:
                return

            try:
                info = self.bot.get_file(
                    ref.telegram_file_id
                )

                raw = self.bot.download_file(
                    info.file_path
                )

                caption = self.rt.ai.generate_text(
                    response_prompt(
                        context,
                        lang,
                        p,
                        action.value,
                    )
                )

                caption = humanize(
                    caption,
                    p,
                    lang.as_dict(),
                )

                caption = self._clean_reply(
                    caption
                )

                if action == Action.CONTEXT_MEME:
                    out = caption_meme(
                        raw,
                        caption,
                    )

                    self.bot.send_photo(
                        m.chat.id,
                        out,
                        caption=None,
                        reply_to_message_id=reply_id,
                    )
                else:
                    self.bot.send_photo(
                        m.chat.id,
                        BytesIO(raw),
                        caption=caption[:1024],
                        reply_to_message_id=reply_id,
                    )

                self.rt.images.mark_used(
                    ref
                )

            except Exception:
                log.exception(
                    "image action failed"
                )

            return

        if action in {
            Action.IMAGE_MASHUP,
            Action.COLLAGE,
        }:
            a = self.rt.images.choose(
                m.chat.id
            )

            b = self.rt.images.choose(
                m.chat.id
            )

            if (
                not a
                or not b
                or a.message_id == b.message_id
            ):
                return

            try:
                raw_a = self.bot.download_file(
                    self.bot.get_file(
                        a.telegram_file_id
                    ).file_path
                )

                raw_b = self.bot.download_file(
                    self.bot.get_file(
                        b.telegram_file_id
                    ).file_path
                )

                out = (
                    side_by_side(
                        raw_a,
                        raw_b,
                    )
                    if action == Action.IMAGE_MASHUP
                    else collage(
                        [
                            raw_a,
                            raw_b,
                        ]
                    )
                )

                self.bot.send_photo(
                    m.chat.id,
                    out,
                    reply_to_message_id=reply_id,
                )

            except Exception:
                log.exception(
                    "mashup failed"
                )

            return

        if action == Action.REACTION:
            try:
                emoji = random.choice(
                    [
                        "👍",
                        "😹",
                        "❤️",
                        "🔥",
                        "👀",
                    ]
                )

                if hasattr(
                    self.bot,
                    "set_message_reaction",
                ):
                    from telebot.types import ReactionTypeEmoji

                    self.bot.set_message_reaction(
                        m.chat.id,
                        reply_id,
                        [
                            ReactionTypeEmoji(
                                emoji=emoji
                            )
                        ],
                    )
                else:
                    self.bot.reply_to(
                        m,
                        emoji,
                    )

            except Exception:
                log.exception(
                    "reaction failed"
                )

            return

        if action == Action.POLL:
            try:
                question = self.rt.ai.generate_text(
                    response_prompt(
                        context,
                        lang,
                        p,
                        "POLL",
                    )
                ) or "which one"

                self.bot.send_poll(
                    m.chat.id,
                    question[:300],
                    [
                        "yes",
                        "no",
                        "idk",
                    ],
                    is_anonymous=True,
                )

            except Exception:
                log.exception(
                    "poll failed"
                )

            return
