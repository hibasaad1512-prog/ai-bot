from telebot import types
from app.config import settings
OWNER_ID=8734853156

def is_owner(user_id:int|None)->bool:
    return user_id is not None and int(user_id) in getattr(settings,'groq_admin_ids',frozenset({OWNER_ID}))

def menu()->types.InlineKeyboardMarkup:
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton('🎯 Choose Chat',callback_data='memadmin:chats'),types.InlineKeyboardButton('🧪 Merva Lab',callback_data='mad:open'),types.InlineKeyboardButton('🤖 Automation',callback_data='auto:home'),types.InlineKeyboardButton('🔑 AI Providers',callback_data='memadmin:keys'),types.InlineKeyboardButton('🧠 Memory',callback_data='memadmin:memory'),types.InlineKeyboardButton('💬 Messages',callback_data='memadmin:messages'),types.InlineKeyboardButton('🖼️ Media',callback_data='memadmin:media'),types.InlineKeyboardButton('👤 Users',callback_data='memadmin:users'),types.InlineKeyboardButton('⚙️ Bot Settings',callback_data='memadmin:settings'),types.InlineKeyboardButton('🗄️ Database',callback_data='memadmin:db'),types.InlineKeyboardButton('📊 Status',callback_data='memadmin:status'))
    return kb

def chat_menu(chats,current=None):
    kb=types.InlineKeyboardMarkup(row_width=1)
    if not chats: kb.add(types.InlineKeyboardButton('⚠️ No chats detected yet',callback_data='memadmin:back'))
    for x in chats:
        cid=int(x['chat_id']); title=str(x.get('title') or f'Chat {cid}')[:48]; mark=' ⭐' if current==cid else ''
        kb.add(types.InlineKeyboardButton(f'🎯 {title}{mark}',callback_data=f'memadmin:chat:{cid}'))
    kb.add(types.InlineKeyboardButton('⬅️ Back',callback_data='memadmin:home')); return kb

def memory_menu():
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton('📋 Memories',callback_data='memadmin:listmem'),types.InlineKeyboardButton('🔎 Search',callback_data='memadmin:searchmem'),types.InlineKeyboardButton('➕ Add',callback_data='memadmin:addmem'),types.InlineKeyboardButton('🗑️ Forget',callback_data='memadmin:forgetmem'),types.InlineKeyboardButton('💣 Clear all',callback_data='memadmin:clearmem'),types.InlineKeyboardButton('⬅️ Back',callback_data='memadmin:home')); return kb

def provider_menu(providers):
    kb=types.InlineKeyboardMarkup(row_width=2)
    labels={'groq':'🟢 Groq','gemini':'🔵 Gemini','openai':'⚫ OpenAI','deepseek':'🔴 DeepSeek','openrouter':'🟣 OpenRouter','together':'🟠 Together'}
    for p in providers: kb.add(types.InlineKeyboardButton(labels.get(p,p.title()),callback_data=f'memadmin:provider:{p}'))
    kb.add(types.InlineKeyboardButton('⬅️ Back',callback_data='memadmin:home')); return kb

def provider_actions(provider):
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton('➕ Add key',callback_data=f'memadmin:padd:{provider}'),types.InlineKeyboardButton('📋 Keys',callback_data=f'memadmin:plist:{provider}'))
    kb.add(types.InlineKeyboardButton('🗑️ Delete key',callback_data=f'memadmin:pdelete:{provider}'),types.InlineKeyboardButton('🔄 Test',callback_data=f'memadmin:ptest:{provider}'))
    kb.add(types.InlineKeyboardButton('⬅️ Providers',callback_data='memadmin:keys')); return kb

def key_menu(): return provider_menu(['groq','gemini','openai','deepseek','openrouter','together'])

def simple_back(target='memadmin:home'):
    kb=types.InlineKeyboardMarkup(); kb.add(types.InlineKeyboardButton('⬅️ Back',callback_data=target)); return kb
