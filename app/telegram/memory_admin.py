from telebot import types
from app.config import settings
OWNER_ID=8734853156

def is_owner(user_id:int|None)->bool:
    return user_id is not None and int(user_id) in getattr(settings,'groq_admin_ids',frozenset({OWNER_ID}))

def menu()->types.InlineKeyboardMarkup:
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton('🎯 1. Choose Group',callback_data='owner:chats'),
        types.InlineKeyboardButton('🔑 2. AI APIs',callback_data='owner:providers'),
        types.InlineKeyboardButton('⚡ 3. Activity & Media',callback_data='auto:home'),
        types.InlineKeyboardButton('🧪 Merva Lab',callback_data='mad:open'),
        types.InlineKeyboardButton('🧠 Memory',callback_data='memadmin:memory'),
        types.InlineKeyboardButton('💬 Messages',callback_data='memadmin:messages'),
        types.InlineKeyboardButton('🖼️ Media',callback_data='memadmin:media'),
        types.InlineKeyboardButton('👤 Users',callback_data='memadmin:users'),
        types.InlineKeyboardButton('🗑️ Delete Message',callback_data='delmsg:open'),
        types.InlineKeyboardButton('🗄️ Database',callback_data='memadmin:db'),
        types.InlineKeyboardButton('📊 Status',callback_data='memadmin:status'),
    )
    return kb

def chat_menu(chats,current=None):
    kb=types.InlineKeyboardMarkup(row_width=1)
    if not chats: kb.add(types.InlineKeyboardButton('⚠️ No groups detected',callback_data='owner:back'))
    for x in chats:
        cid=int(x['chat_id']); title=str(x.get('title') or 'Unnamed group')[:48]; mark=' ⭐ SELECTED' if current==cid else ''
        kb.add(types.InlineKeyboardButton(f'🎯 {title}{mark}',callback_data=f'owner:chat:{cid}'))
    kb.add(types.InlineKeyboardButton('🔄 Refresh groups',callback_data='owner:chats_refresh'))
    kb.add(types.InlineKeyboardButton('⬅️ Back',callback_data='owner:back'))
    return kb

def memory_menu():
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton('📋 Memories',callback_data='memadmin:listmem'),types.InlineKeyboardButton('🔎 Search',callback_data='memadmin:searchmem'),types.InlineKeyboardButton('➕ Add',callback_data='memadmin:addmem'),types.InlineKeyboardButton('🗑️ Forget',callback_data='memadmin:forgetmem'),types.InlineKeyboardButton('💣 Clear all',callback_data='memadmin:clearmem'),types.InlineKeyboardButton('⬅️ Back',callback_data='owner:back')); return kb

def provider_menu(providers):
    kb=types.InlineKeyboardMarkup(row_width=2)
    labels={'groq':'🟢 Groq','gemini':'🔵 Gemini','openai':'⚫ OpenAI','deepseek':'🔴 DeepSeek','openrouter':'🟣 OpenRouter','together':'🟠 Together'}
    for p in providers: kb.add(types.InlineKeyboardButton(labels.get(p,p.title()),callback_data=f'owner:provider:{p}'))
    kb.add(types.InlineKeyboardButton('⬅️ Back to GOD PANEL',callback_data='owner:back'))
    return kb

def provider_actions(provider):
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton('➕ Add API key',callback_data=f'owner:padd:{provider}'),types.InlineKeyboardButton('📋 Saved keys',callback_data=f'owner:plist:{provider}'))
    kb.add(types.InlineKeyboardButton('🗑️ Delete key',callback_data=f'owner:pdelete:{provider}'),types.InlineKeyboardButton('🧪 Test API',callback_data=f'owner:ptest:{provider}'))
    kb.add(types.InlineKeyboardButton('⬅️ AI APIs',callback_data='owner:providers'))
    return kb

def key_menu(): return provider_menu(['groq','gemini','openai','deepseek','openrouter','together'])
