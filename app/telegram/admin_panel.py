from telebot import types

FIELDS=[
    ("🧠 Chaos","chaos"),
    ("😹 Humor","humor"),
    ("💬 Social","social"),
    ("🌀 Weirdness","weirdness"),
    ("⚡ Proactivity","proactivity"),
    ("🖼️ Images","images"),
    ("🎉 Events","events"),
    ("✨ Emoji","emoji"),
    ("🗣️ Human style","human_imperfection"),
    ("🔥 Roast","roast"),
]
LANGUAGES=[
("🌐 Auto","auto"),("🇲🇦 Darija","ar-MA"),("🇸🇦 Arabic","ar"),("🇬🇧 English","en"),("🇫🇷 French","fr"),("🇪🇸 Spanish","es"),("🇵🇹 Portuguese","pt"),("🇷🇺 Russian","ru"),("🇺🇦 Ukrainian","uk"),("🇹🇷 Turkish","tr"),("🇩🇪 German","de"),("🇮🇹 Italian","it"),("🇳🇱 Dutch","nl"),("🇵🇱 Polish","pl"),("🇷🇴 Romanian","ro"),("🇨🇿 Czech","cs"),("🇸🇰 Slovak","sk"),("🇭🇺 Hungarian","hu"),("🇸🇪 Swedish","sv"),("🇳🇴 Norwegian","no"),("🇩🇰 Danish","da"),("🇫🇮 Finnish","fi"),("🇬🇷 Greek","el"),("🇮🇱 Hebrew","he"),("🇮🇳 Hindi","hi"),("🇵🇰 Urdu","ur"),("🇮🇩 Indonesian","id"),("🇲🇾 Malay","ms"),("🇵🇭 Tagalog","tl"),("🇯🇵 Japanese","ja"),("🇰🇷 Korean","ko"),("🇨🇳 Chinese","zh")]

def panel(p, language="auto"):
    kb=types.InlineKeyboardMarkup(row_width=2)
    for label,key in FIELDS:
        kb.add(types.InlineKeyboardButton(f"{label}: {getattr(p,key)}",callback_data=f"set:{key}:show"))
    kb.add(types.InlineKeyboardButton(f"🌐 Language: {language}",callback_data="language:show"))
    return kb

def adjust_panel(p,key):
    kb=types.InlineKeyboardMarkup(row_width=3)
    kb.add(types.InlineKeyboardButton("−10",callback_data=f"set:{key}:-10"),types.InlineKeyboardButton(f"{getattr(p,key)}",callback_data=f"set:{key}:show"),types.InlineKeyboardButton("+10",callback_data=f"set:{key}:+10"))
    kb.add(types.InlineKeyboardButton("⬅️ Back",callback_data="panel:back"))
    return kb

def language_panel(current="auto"):
    kb=types.InlineKeyboardMarkup(row_width=2)
    for label,key in LANGUAGES:
        mark=" ✓" if key==current else ""
        kb.add(types.InlineKeyboardButton(label+mark,callback_data=f"language:set:{key}"))
    kb.add(types.InlineKeyboardButton("⬅️ Back",callback_data="panel:back"))
    return kb
