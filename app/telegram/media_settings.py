from __future__ import annotations

from telebot import types

from app.telegram.memory_admin import is_owner


def _root(db) -> dict:
    return db.get_json('chat_settings', 'chat_id', 0, {})


def _save_root(db, state: dict) -> None:
    db.save_chat_settings(0, state)


def _defaults(db) -> dict:
    root = _root(db)
    d = dict(root.get('media_defaults') or {})
    d.setdefault('auto_media_enabled', True)
    d.setdefault('auto_media_interval_min', 120)
    d.setdefault('auto_media_interval_max', 300)
    d.setdefault('active_media_enabled', True)
    d.setdefault('auto_media_delete_after_send', False)
    d.setdefault('media_requests_enabled', True)
    root['media_defaults'] = d
    _save_root(db, root)
    return d


def _state(db, chat_id: int) -> dict:
    return db.get_json('chat_state', 'chat_id', int(chat_id), {})


def _save(db, chat_id: int, **changes) -> dict:
    s = _state(db, chat_id)
    s.update(changes)
    db.save_state(int(chat_id), s)
    return s


def _chats(db):
    root = _root(db)
    known = {}
    memberships = root.get('bot_memberships', {})
    for x in root.get('known_chats', []):
        try:
            cid = int(x.get('chat_id'))
        except Exception:
            continue
        if cid >= 0 or (str(cid) in memberships and not memberships[str(cid)]):
            continue
        known[cid] = x
    for cid in db.list_chat_ids():
        try:
            cid = int(cid)
        except Exception:
            continue
        if cid >= 0 or (str(cid) in memberships and not memberships[str(cid)]):
            continue
        known.setdefault(cid, {'chat_id': cid, 'title': None})
    return list(known.values())


def _fmt(s: dict, title: str = 'GROUP') -> str:
    lo = int(s.get('auto_media_interval_min', 120))
    hi = int(s.get('auto_media_interval_max', 300))
    return (
        f'🎬 MEDIA SETTINGS — {title}\n\n'
        f'🖼 Automatic media: {"ON 🟢" if s.get("auto_media_enabled") else "OFF 🔴"}\n'
        f'⚡ Active pulse: {"ON 🟢" if s.get("active_media_enabled") else "OFF 🔴"}\n'
        f'⏱ Interval: {lo}–{hi} minutes\n'
        f'🗑 Delete after send: {"ON 🟢" if s.get("auto_media_delete_after_send") else "OFF 🔴"}\n'
        f'📩 Explicit media requests: {"ON 🟢" if s.get("media_requests_enabled", True) else "OFF 🔴"}\n'
    )


def _keyboard(chat_id: int, back='mediaadmin:home'):
    s = _state(runtime_db := _keyboard.db, chat_id) if False else None
    # This function is replaced by _make_keyboard below; kept intentionally tiny.
    return types.InlineKeyboardMarkup()


def _make_keyboard(db, chat_id: int, back='mediaadmin:home'):
    s = _state(db, chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f'🖼 Auto: {"ON" if s.get("auto_media_enabled", True) else "OFF"}', callback_data=f'mediaadmin:toggle:{chat_id}'),
        types.InlineKeyboardButton(f'⚡ Pulse: {"ON" if s.get("active_media_enabled", True) else "OFF"}', callback_data=f'mediaadmin:pulse:{chat_id}'),
    )
    kb.add(
        types.InlineKeyboardButton('⏱ Interval', callback_data=f'mediaadmin:interval:{chat_id}'),
        types.InlineKeyboardButton(f'🗑 Delete: {"ON" if s.get("auto_media_delete_after_send", False) else "OFF"}', callback_data=f'mediaadmin:delete:{chat_id}'),
    )
    kb.add(types.InlineKeyboardButton(f'📩 Requests: {"ON" if s.get("media_requests_enabled", True) else "OFF"}', callback_data=f'mediaadmin:requests:{chat_id}'))
    kb.add(types.InlineKeyboardButton('⬅️ Back', callback_data=back))
    return kb


def register(bot, runtime):
    db = runtime.db

    def allowed(c):
        return is_owner(getattr(c.from_user, 'id', None))

    def show(c, chat_id=None, global_mode=False):
        if global_mode:
            s = _defaults(db)
            text = _fmt(s, 'GLOBAL DEFAULTS') + '\nThese defaults are used when a group has no custom media settings.'
            kb = types.InlineKeyboardMarkup(row_width=2)
            kb.add(types.InlineKeyboardButton(f'🖼 Auto: {"ON" if s.get("auto_media_enabled") else "OFF"}', callback_data='mediaadmin:global_toggle'))
            kb.add(types.InlineKeyboardButton(f'⚡ Pulse: {"ON" if s.get("active_media_enabled") else "OFF"}', callback_data='mediaadmin:global_pulse'))
            kb.add(types.InlineKeyboardButton('⏱ Interval', callback_data='mediaadmin:global_interval'))
            kb.add(types.InlineKeyboardButton(f'🗑 Delete: {"ON" if s.get("auto_media_delete_after_send") else "OFF"}', callback_data='mediaadmin:global_delete'))
            kb.add(types.InlineKeyboardButton(f'📩 Requests: {"ON" if s.get("media_requests_enabled", True) else "OFF"}', callback_data='mediaadmin:global_requests'))
            kb.add(types.InlineKeyboardButton('⬅️ Media Settings', callback_data='mediaadmin:home'))
            bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=kb)
            return
        cid = int(chat_id)
        s = _state(db, cid)
        s.setdefault('auto_media_enabled', True)
        s.setdefault('active_media_enabled', True)
        s.setdefault('auto_media_interval_min', 120)
        s.setdefault('auto_media_interval_max', 300)
        s.setdefault('auto_media_delete_after_send', False)
        s.setdefault('media_requests_enabled', True)
        db.save_state(cid, s)
        title = next((str(x.get('title') or '') for x in _chats(db) if int(x['chat_id']) == cid), str(cid))
        bot.edit_message_text(_fmt(s, title[:50]), c.message.chat.id, c.message.message_id, reply_markup=_make_keyboard(db, cid, 'mediaadmin:groups'))

    @bot.callback_query_handler(func=lambda c: bool(c.data) and c.data.startswith('mediaadmin:'))
    def callbacks(c):
        if not allowed(c):
            bot.answer_callback_query(c.id, 'Owner only', show_alert=True)
            return
        try:
            d = c.data
            if d == 'mediaadmin:home':
                kb = types.InlineKeyboardMarkup(row_width=1)
                kb.add(types.InlineKeyboardButton('🌐 Global defaults (all groups)', callback_data='mediaadmin:global'))
                kb.add(types.InlineKeyboardButton('🎯 Settings for one group', callback_data='mediaadmin:groups'))
                kb.add(types.InlineKeyboardButton('⬅️ GOD PANEL', callback_data='owner:back'))
                bot.edit_message_text('🎬 MEDIA CONTROL\n\nChoose global defaults or configure one specific group.', c.message.chat.id, c.message.message_id, reply_markup=kb)
                return
            if d == 'mediaadmin:global':
                show(c, global_mode=True); return
            if d == 'mediaadmin:groups':
                chats = _chats(db)
                kb = types.InlineKeyboardMarkup(row_width=1)
                for x in chats:
                    cid = int(x['chat_id']); title = str(x.get('title') or f'Group {cid}')[:50]
                    kb.add(types.InlineKeyboardButton(f'🎯 {title}', callback_data=f'mediaadmin:group:{cid}'))
                kb.add(types.InlineKeyboardButton('🌐 Global defaults', callback_data='mediaadmin:global'))
                kb.add(types.InlineKeyboardButton('⬅️ Media Settings', callback_data='mediaadmin:home'))
                bot.edit_message_text('🎯 SELECT GROUP\n\nChoose exactly one group to edit its media settings.', c.message.chat.id, c.message.message_id, reply_markup=kb); return
            if d.startswith('mediaadmin:group:'):
                show(c, int(d.split(':')[-1])); return
            if d.startswith('mediaadmin:global_'):
                action = d.split('_', 1)[1]
                s = _defaults(db)
                key = {'toggle':'auto_media_enabled','pulse':'active_media_enabled','delete':'auto_media_delete_after_send','requests':'media_requests_enabled'}.get(action)
                if key:
                    s[key] = not bool(s.get(key)); root = _root(db); root['media_defaults'] = s; _save_root(db, root)
                    show(c, global_mode=True)
                elif action == 'interval':
                    bot.answer_callback_query(c.id, 'اكتب: /adminmedia 120 300 في الخاص', show_alert=True)
                return
            if d.startswith('mediaadmin:'):
                parts = d.split(':'); action = parts[1]; cid = int(parts[2]); s = _state(db, cid)
                if action == 'toggle': _save(db, cid, auto_media_enabled=not bool(s.get('auto_media_enabled', True)))
                elif action == 'pulse': _save(db, cid, active_media_enabled=not bool(s.get('active_media_enabled', True)))
                elif action == 'delete': _save(db, cid, auto_media_delete_after_send=not bool(s.get('auto_media_delete_after_send', False)))
                elif action == 'requests': _save(db, cid, media_requests_enabled=not bool(s.get('media_requests_enabled', True)))
                elif action == 'interval':
                    bot.answer_callback_query(c.id, 'اكتب في الخاص: /adminmedia GROUP_ID 120 300', show_alert=True); return
                s = _state(db, cid)
                title = next((str(x.get('title') or '') for x in _chats(db) if int(x['chat_id']) == cid), str(cid))
                bot.edit_message_text(_fmt(s, title[:50]), c.message.chat.id, c.message.message_id, reply_markup=_make_keyboard(db, cid, 'mediaadmin:groups'))
                bot.answer_callback_query(c.id); return
            bot.answer_callback_query(c.id)
        except Exception:
            bot.answer_callback_query(c.id, 'Media settings error', show_alert=True)

    @bot.message_handler(commands=['adminmedia'])
    def adminmedia_command(m):
        if not is_owner(getattr(m.from_user, 'id', None)) or getattr(m.chat, 'type', '') != 'private':
            return
        args = (getattr(m, 'text', '') or '').split()[1:]
        if len(args) == 3:
            try:
                cid = int(args[0]); lo = max(1, min(10080, int(args[1]))); hi = max(lo, min(10080, int(args[2])))
                _save(db, cid, auto_media_interval_min=lo, auto_media_interval_max=hi, auto_media_next_at=0)
                bot.send_message(m.chat.id, f'✅ Group {cid}: interval set to {lo}–{hi} minutes.')
                return
            except Exception:
                bot.send_message(m.chat.id, '❌ Usage: /adminmedia GROUP_ID 120 300'); return
        if len(args) == 2:
            try:
                lo = max(1, min(10080, int(args[0]))); hi = max(lo, min(10080, int(args[1])))
                d = _defaults(db); d['auto_media_interval_min'] = lo; d['auto_media_interval_max'] = hi
                root = _root(db); root['media_defaults'] = d; _save_root(db, root)
                bot.send_message(m.chat.id, f'✅ Global default interval: {lo}–{hi} minutes.'); return
            except Exception: pass
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton('🌐 Global defaults', callback_data='mediaadmin:global'))
        kb.add(types.InlineKeyboardButton('🎯 One specific group', callback_data='mediaadmin:groups'))
        bot.send_message(m.chat.id, '🎬 MEDIA CONTROL\n\n/adminmedia 120 300 → global interval\n/adminmedia GROUP_ID 120 300 → one group interval', reply_markup=kb)
