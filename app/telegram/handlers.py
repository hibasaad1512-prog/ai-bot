
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
    """
    Main Telegram handlers for lmyrfawya.

    - Groups only for AI/chat interaction.
    - Private chats do not receive AI replies.
    - 80% chance to answer normal messages.
    - No per-user reply limit.
    - Same user can receive unlimited replies.
    - Random reactions can happen independently.
    - Random media/meme features remain compatible.
    """

    def __init__(self, bot, runtime):
        self.bot = bot
        self.rt = runtime
        self._bot_username = ""
        self._register()

    # ---------------------------------------------------------
    # REGISTRATION
    # ---------------------------------------------------------

    def _register(self):
        from telebot import types

        @self.bot.message_handler(commands=["start"])
        def start(m):
            # Commands work in private chats.
            if is_group(m.chat.type):
                self.bot.reply_to(
                    m,
                    "هنا الميرفاوية 🐱",
                )
            else:
                self.bot.send_message(
                    m.chat.id,
                    "الميرفاوية هنا 🎀",
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
                "Runtime mode: group AI replies only"
            )

            self.bot.send_message(
                m.chat.id,
                "\n".join(lines),
            )

        # -----------------------------------------------------
        # SETTINGS CALLBACKS
        # -----------------------------------------------------

        @self.bot.callback_query_handler(
            func=lambda c:
                c.data.startswith("panel:")
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
                        "LMYRFAWYA settings",
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
                        "LMYRFAWYA settings",
                        chat_id,
                        c.message.message_id,
                        reply_markup=panel(
                            p,
                            mode,
                        ),
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

                        setattr(
                            p,
                            key,
                            value,
                        )

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

        # -----------------------------------------------------
        # NORMAL GROUP MESSAGES
        # -----------------------------------------------------

        @self.bot.message_handler(
            content_types=["text", "photo"],
            func=is_non_command_message,
        )
        def normal_message(m):
            self.on_message(m)

        # -----------------------------------------------------
        # GAME JOIN
        # -----------------------------------------------------

        @self.bot.message_handler(
            content_types=["text"],
            func=lambda m:
                bool(m.text)
                and m.text.strip().upper() == "JOIN",
        )
        def game_join(m):
            if not is_group(m.chat.type):
                return

            if not self.rt.games.join(
                m.chat.id,
                m.from_user.id,
            ):
                return

            self.bot.reply_to(
                m,
                "joined",
            )

    # ---------------------------------------------------------
    # SETTINGS
    # ---------------------------------------------------------

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
            "LMYRFAWYA settings",
            reply_markup=panel(
                self.rt.personality(m.chat.id),
                self.rt.get_language_mode(m.chat.id),
            ),
        )

    # ---------------------------------------------------------
    # MEMORY
    # ---------------------------------------------------------

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
                display_name=self._bot_username or "الميرفاوية",
                timestamp=time.time(),
                text=text,
                reply_to_message_id=reply_to,
                is_bot=True,
            )
        )

    # ---------------------------------------------------------
    # 80% RESPONSE CHANCE
    # ---------------------------------------------------------

    @staticmethod
    def _reply_chance_passes() -> bool:
        """
        80% chance to continue to AI.

        There is intentionally NO per-user limit.
        A user can receive unlimited replies.
        """

        return random.random() < 0.80

    # ---------------------------------------------------------
    # RANDOM REACTION
    # ---------------------------------------------------------

    def _maybe_random_reaction(
        self,
        m,
    ) -> None:

        # Small independent chance.
        if random.random() > 0.08:
            return

        if not is_group(m.chat.type):
            return

        try:
            emoji = random.choice(
                [
                    "👍",
                    "😂",
                    "❤️",
                    "🔥",
                    "👀",
                    "😹",
                    "😼",
                    "🥺",
                    "🐱",
                ]
            )

            if hasattr(
                self.bot,
                "set_message_reaction",
            ):
                from telebot.types import ReactionTypeEmoji

                self.bot.set_message_reaction(
                    m.chat.id,
                    m.message_id,
                    [
                        ReactionTypeEmoji(
                            emoji=emoji
                        )
                    ],
                )

        except Exception:
            log.exception(
                "random reaction failed"
            )

    # ---------------------------------------------------------
    # MAIN MESSAGE
    # ---------------------------------------------------------

    def on_message(self, m):

        if not m.from_user:
            return

        # -----------------------------------------------------
        # PRIVATE CHAT:
        # AI DOES NOT ANSWER HERE.
        # -----------------------------------------------------

        if not is_group(m.chat.type):
            return

        text = m.text or m.caption or ""

        image_file_id = None
        media_type = None

        # -----------------------------------------------------
        # SAVE PHOTOS TO IMAGE POOL
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
        # STORE MESSAGE
        # -----------------------------------------------------

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

        # -----------------------------------------------------
        # MODERATION
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

                if (
                    mod
                    and mod.action == "delete"
                ):
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

        # -----------------------------------------------------
        # PHOTO WITHOUT TEXT
        # -----------------------------------------------------

        if m.photo and not text:

            # It is already saved to the pool.
            # Do not fake vision understanding.
            self._maybe_random_reaction(m)

            return

        if not text:
            return

        # -----------------------------------------------------
        # RANDOM REACTION IS INDEPENDENT FROM AI RESPONSE
        # -----------------------------------------------------

        self._maybe_random_reaction(m)

        # -----------------------------------------------------
        # AI ENABLED?
        # -----------------------------------------------------

        if not self.rt.ai.enabled:
            return

        # -----------------------------------------------------
        # 80% RESPONSE CHANCE
        # -----------------------------------------------------

        if not self._reply_chance_passes():
            return

        # IMPORTANT:
        #
        # There is NO:
        # _can_reply_to_user()
        #
        # There is NO:
        # _record_user_reply()
        #
        # There is NO limit of 2 replies per user.
        #
        # Same user can receive unlimited replies.

        recent = self.rt.memory.recent(
            m.chat.id,
            16,
        )

        context = self.rt.memory.text(
            m.chat.id,
            12,
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

        # -----------------------------------------------------
        # DIRECT CONTEXT
        # -----------------------------------------------------

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
                "Reply target: "
                f"{m.reply_to_message.text[:600]}\n"
            )

        # -----------------------------------------------------
        # AI GENERATION
        # -----------------------------------------------------

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

            prompt = response_prompt(
                f"{context}\n{direct_context}",
                lang,
                personality,
                "DIRECT_REPLY",
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

            # -------------------------------------------------
            # EMPTY RESPONSE
            # -------------------------------------------------

            if not reply:
                return

            # -------------------------------------------------
            # SEND
            # -------------------------------------------------

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

    # ---------------------------------------------------------
    # CLEAN AI RESPONSE
    # ---------------------------------------------------------

    @staticmethod
    def _clean_reply(
        text: str,
    ) -> str:

        text = (
            text or ""
        ).strip()

        # Remove accidental markdown fences.
        text = re.sub(
            r"^```(?:text)?\s*|\s*```$",
            "",
            text,
            flags=re.I,
        ).strip()

        # Remove surrounding quotes.
        if (
            len(text) >= 2
            and text[0] == '"'
            and text[-1] == '"'
        ):
            text = text[1:-1].strip()

        # Prevent accidental JSON.
        if text.startswith("{") and text.endswith("}"):
            return ""

        return text[:1000]

    # ---------------------------------------------------------
    # PROACTIVE
    # ---------------------------------------------------------

    def proactive(
        self,
        chat_id: int,
    ):

        recent = self.rt.memory.recent(
            chat_id,
            40,
        )

        if (
            not recent
            or not self.rt.ai.enabled
        ):
            return

        p = self.rt.personality(
            chat_id
        )

        now = time.time()

        last = recent[-1].timestamp

        # Do not randomly speak too soon after activity.
        if (
            now - last
            < settings.proactive_quiet_seconds
        ):
            return

        if p.proactivity < 25:
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
            12,
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

            txt = self._clean_reply(
                txt
            )

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

    # ---------------------------------------------------------
    # LEGACY CHAOS / IMAGE ACTIONS
    # ---------------------------------------------------------

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

        # -----------------------------------------------------
        # TEXT ACTIONS
        # -----------------------------------------------------

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
                f"Target: "
                f"{focus.display_name}: "
                f"{focus.text}"
                if focus
                and focus.text
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

        # -----------------------------------------------------
        # IMAGE ACTIONS
        # -----------------------------------------------------

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

        # -----------------------------------------------------
        # MASHUP / COLLAGE
        # -----------------------------------------------------

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

                if action == Action.IMAGE_MASHUP:
                    out = side_by_side(
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
                    "mashup failed"
                )

            return

        # -----------------------------------------------------
        # REACTION ACTION
        # -----------------------------------------------------

        if action == Action.REACTION:

            try:

                emoji = random.choice(
                    [
                        "👍",
                        "😂",
                        "❤️",
                        "🔥",
                        "👀",
                        "😹",
                        "😼",
                        "🥺",
                        "🐱",
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
                    "reaction action failed"
                )

            return

        # -----------------------------------------------------
        # POLL
        # -----------------------------------------------------

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