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
from app.images.meme import caption_meme, meme_mashup
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
    """Telegram handlers for الميرفاوية / lmyrfawya."""

    def __init__(self, bot, runtime):
        self.bot = bot
        self.rt = runtime
        self._bot_username = "الميرفاوية"

        # Per-user reply counters.
        self._user_reply_limits: dict[
            tuple[int, int],
            dict[str, float | int],
        ] = {}

        # Next spontaneous message for each chat.
        self._next_proactive: dict[int, float] = {}

        # Last message used for a random reaction.
        self._last_random_reaction_message: dict[int, int] = {}

        self._register()

    # =========================================================
    # REGISTER
    # =========================================================

    def _register(self):
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
                    "Text API: ❌ GROQ_API_KEY missing or Groq client failed"
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
                "Runtime: groups only + 80% reply chance + random callbacks + random reactions"
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
                log.exception("settings callback failed")

            finally:
                try:
                    self.bot.answer_callback_query(c.id)
                except Exception:
                    pass

        @self.bot.message_handler(
            content_types=["text", "photo", "video"],
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

    # =========================================================
    # ADMIN
    # =========================================================

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

    # =========================================================
    # MEMORY
    # =========================================================

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

    # =========================================================
    # REPLY CONTROLS
    # =========================================================

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

    # =========================================================
    # RANDOM CALLBACK
    # =========================================================

    def _random_callback_context(
        self,
        chat_id: int,
        current_message_id: int,
    ) -> tuple[str, str]:
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

        chosen = random.choice(
            candidates[-25:]
        )

        return (
            "RANDOM OLDER MESSAGE:\n"
            f"{chosen.display_name}: "
            f"{chosen.text[:700]}\n"
            "\n"
            "React to this older message only if it naturally "
            "fits the current conversation.",
            chosen.text[:700],
        )

    # =========================================================
    # RANDOM CHAT REMIX
    # =========================================================

    def _random_remix_context(
        self,
        chat_id: int,
    ) -> str:
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
                    min(
                        4,
                        len(words),
                    ),
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
            "RANDOM CHAT REMIX MATERIAL:\n"
            + "\n".join(pieces)
            + "\n\n"
            "You may combine some of these words or phrases "
            "into one natural message.\n"
            "Do not simply concatenate them.\n"
            "Do not explain where they came from.\n"
            "Do not force the remix."
        )

    def _build_reply_context(
        self,
        m,
        base_context: str,
        text: str,
    ) -> tuple[str, str]:
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
                "Reply target:\n"
                f"{m.reply_to_message.text[:600]}\n"
            )

        mode = "DIRECT_REPLY"

        if random.random() < 0.15:
            callback_context, _ = (
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

        if random.random() < 0.08:
            remix_context = (
                self._random_remix_context(
                    m.chat.id
                )
            )

            if remix_context:
                direct_context += (
                    "\n" + remix_context
                )

                if mode == "DIRECT_REPLY":
                    mode = "CHAT_REMIX"

        return (
            f"{base_context}\n{direct_context}",
            mode,
        )

    # =========================================================
    # RANDOM REACTION
    # =========================================================

    def random_reaction(self, chat_id: int) -> bool:
        """
        Pick a random human message from the chat
        and react to it with a random emoji.

        It does not need to be the latest message
        and it does not need to be directed at the bot.
        """

        recent = self.rt.memory.recent(
            chat_id,
            50,
        )

        candidates = [
            x
            for x in recent
            if (
                x.text
                and not x.is_bot
            )
        ]

        if not candidates:
            return False

        # Avoid the exact same message twice in a row.
        previous_id = self._last_random_reaction_message.get(
            chat_id
        )

        choices = [
            x
            for x in candidates
            if x.message_id != previous_id
        ]

        if not choices:
            choices = candidates

        selected = random.choice(
            choices
        )

        self._last_random_reaction_message[chat_id] = (
            selected.message_id
        )

        reaction_emojis = [
            "👍",
            "❤️",
            "🔥",
            "👀",
            "😹",
            "😮",
            "🤔",
            "👏",
        ]

        emoji = random.choice(
            reaction_emojis
        )

        try:
            if hasattr(
                self.bot,
                "set_message_reaction",
            ):
                from telebot.types import ReactionTypeEmoji

                self.bot.set_message_reaction(
                    chat_id,
                    selected.message_id,
                    [
                        ReactionTypeEmoji(
                            emoji=emoji
                        )
                    ],
                )
                return True

            # Fallback if reaction API isn't available.
            self.bot.send_message(
                chat_id,
                emoji,
                reply_to_message_id=selected.message_id,
                allow_sending_without_reply=True,
            )

            return True

        except Exception:
            log.exception(
                "random reaction failed"
            )
            return False

    # =========================================================
    # NORMAL MESSAGE
    # =========================================================

    def on_message(self, m):
        if not m.from_user:
            return

        # AI interaction is GROUP ONLY.
        # Commands remain separate and continue to work.
        if getattr(
            m.chat,
            "type",
            None,
        ) == "private":
            return

        # Never interact with bots.
        if getattr(
            m.from_user,
            "is_bot",
            False,
        ):
            return

        text = m.text or m.caption or ""

        image_file_id = None
        media_type = None

        # -----------------------------------------------------
        # Photo
        # -----------------------------------------------------

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

        # -----------------------------------------------------
        # Video
        # -----------------------------------------------------

        if getattr(
            m,
            "video",
            None,
        ):
            media_type = "video"

            image_file_id = m.video.file_id

            self.rt.images.add(
                ImageRef(
                    m.chat.id,
                    m.message_id,
                    image_file_id,
                    time.time(),
                    None,
                    m.from_user.id,
                    "video",
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
            False,
        )

        self.rt.memory.add(cm)

        # -----------------------------------------------------
        # Moderation
        # -----------------------------------------------------

        if (
            text
            and settings.enabled_moderation
        ):
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
                    "moderation check failed"
                )

        # Media without caption:
        # stored for future random media use.
        if (
            (m.photo or getattr(m, "video", None))
            and not text
        ):
            return

        if not text:
            return

        if not self.rt.ai.enabled:
            return

        user_id = m.from_user.id

        # -----------------------------------------------------
        # IMPORTANT:
        # All skip decisions happen before Groq.
        # -----------------------------------------------------

        if not self._can_reply_to_user(
            m.chat.id,
            user_id,
        ):
            return

        if not self._reply_chance_passes():
            return

        # NO artificial sleep here.
        # The response starts immediately.

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

        signals = {
            "character_name": "الميرفاوية",
            "english_name": "lmyrfawya",
            "same_language_as_chat": True,
            "emojis_optional": True,
            "cute_but_not_cringe": True,
            "short_and_natural": True,
            "random_callback_possible": True,
            "chat_remix_possible": True,
        }

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
                "AI reply failed"
            )

    # =========================================================
    # CLEAN REPLY
    # =========================================================

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

    # =========================================================
    # PROACTIVE
    # =========================================================

    def proactive(self, chat_id: int):
        """
        Spontaneous message between 6 and 15 hours.

        The runtime/scheduler must call this method periodically.
        """

        if not self.rt.ai.enabled:
            return

        if not getattr(
            settings,
            "enabled_proactive",
            True,
        ):
            return

        recent = self.rt.memory.recent(
            chat_id,
            40,
        )

        if not recent:
            return

        now = time.time()

        # First schedule.
        next_time = self._next_proactive.get(
            chat_id
        )

        if next_time is None:
            minimum = int(
                getattr(
                    settings,
                    "proactive_min_interval",
                    21600,
                )
            )

            maximum = int(
                getattr(
                    settings,
                    "proactive_max_interval",
                    54000,
                )
            )

            if maximum < minimum:
                minimum, maximum = maximum, minimum

            self._next_proactive[chat_id] = (
                now + random.randint(
                    minimum,
                    maximum,
                )
            )

            return

        if now < next_time:
            return

        # Set next random time.
        minimum = int(
            getattr(
                settings,
                "proactive_min_interval",
                21600,
            )
        )

        maximum = int(
            getattr(
                settings,
                "proactive_max_interval",
                54000,
            )
        )

        if maximum < minimum:
            minimum, maximum = maximum, minimum

        self._next_proactive[chat_id] = (
            now + random.randint(
                minimum,
                maximum,
            )
        )

        # Default is 100%.
        chance = max(
            0,
            min(
                100,
                int(
                    getattr(
                        settings,
                        "proactive_chance",
                        100,
                    )
                ),
            ),
        )

        if random.random() * 100 >= chance:
            return

        # Do not interrupt an active chat.
        quiet_seconds = getattr(
            settings,
            "proactive_quiet_seconds",
            600,
        )

        if (
            now - recent[-1].timestamp
            < quiet_seconds
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

        human_messages = [
            x
            for x in recent
            if x.text and not x.is_bot
        ]

        if not human_messages:
            return

        context = self.rt.memory.text(
            chat_id,
            20,
        )

        # Older random callback.
        if (
            len(human_messages) >= 3
            and random.random() < 0.40
        ):
            selected = random.choice(
                human_messages
            )

            context += (
                "\n\nRandom older message:\n"
                f"{selected.display_name}: "
                f"{selected.text[:600]}"
            )

        # Random remix.
        if random.random() < 0.15:
            remix = self._random_remix_context(
                chat_id
            )

            if remix:
                context += (
                    "\n\n" + remix
                )

        lang = detect(
            [
                x.text
                for x in recent
                if x.text
            ]
        )

        p = self.rt.personality(
            chat_id
        )

        try:
            txt = self.rt.ai.generate_text(
                response_prompt(
                    context,
                    lang,
                    p,
                    "PROACTIVE",
                    signals={
                        "spontaneous": True,
                        "character_name": "الميرفاوية",
                        "english_name": "lmyrfawya",
                        "same_language_as_chat": True,
                        "emojis_optional": True,
                        "cute_but_not_cringe": True,
                        "random_callback_allowed": True,
                        "chat_remix_allowed": True,
                    },
                )
            )

            txt = humanize(
                txt,
                p,
                lang.as_dict(),
            )

            txt = self._clean_reply(
                txt
            )

            if not txt:
                return

            self.bot.send_message(
                chat_id,
                txt[:1000],
            )

            self.rt.chaos.cooldowns.record_action(
                chat_id
            )

            self.rt.memory.add(
                ChatMessage(
                    chat_id=chat_id,
                    message_id=int(
                        time.time() * 1000
                    ),
                    user_id=0,
                    display_name=self._bot_username,
                    timestamp=time.time(),
                    text=txt[:1000],
                    reply_to_message_id=None,
                    is_bot=True,
                )
            )

        except Exception:
            log.exception(
                "proactive action failed"
            )

    # =========================================================
    # EXISTING CHAOS / IMAGE ACTIONS
    # =========================================================

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

        reply_id = (
            target_id
            or m.message_id
        )

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

                txt = self._clean_reply(
                    txt
                )

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
            ref = self.rt.images.choose_random_media(
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

                # Video: send it directly.
                if ref.media_type == "video":
                    self.bot.send_video(
                        m.chat.id,
                        raw,
                        reply_to_message_id=reply_id,
                    )

                    self.rt.images.mark_used(
                        ref
                    )

                    return

                # Photo.
                if action == Action.RANDOM_IMAGE:
                    self.bot.send_photo(
                        m.chat.id,
                        BytesIO(raw),
                        reply_to_message_id=reply_id,
                    )

                else:
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
                    "random media action failed"
                )

            return

        if action in {
            Action.IMAGE_MASHUP,
            Action.COLLAGE,
        }:
            a = self.rt.images.choose_photo(
                m.chat.id
            )

            b = self.rt.images.choose_photo(
                m.chat.id,
                avoid_file_id=(
                    a.telegram_file_id
                    if a
                    else None
                ),
            )

            if not a or not b:
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

                if action == Action.IMAGE_MASHUP:
                    out = meme_mashup(
                        raw_a,
                        raw_b,
                    )
                else:
                    out = collage(
                        [
                            raw_a,
                            raw_b,
                        ]
                    )

                self.bot.send_photo(
                    m.chat.id,
                    out,
                    reply_to_message_id=reply_id,
                )

                self.rt.images.mark_used(a)
                self.rt.images.mark_used(b)

            except Exception:
                log.exception(
                    "image mashup failed"
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
                        "🤔",
                        "👏",
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