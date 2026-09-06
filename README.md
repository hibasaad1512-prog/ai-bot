# الميرفاوية — Almirfawya AI Telegram Bot

المشروع هو بوت Telegram اجتماعي بالذكاء الاصطناعي باسم **الميرفاوية**. هدفه أن يتصرف كعضو طبيعي في المجموعة: يفهم السياق، يرد أحيانًا بدل الرد على كل رسالة، يغير طول ونبرة الرد، ويمكنه تنفيذ أحداث اجتماعية/فوضوية عندما تسمح الإعدادات والـ cooldowns.

> الاسم الرسمي في المشروع: **الميرفاوية**. الاسم الداخلي المقترح: `almirfawya`.

## Architecture

```text
Telegram Webhook
      │
      ▼
Message Router / Permissions
      │
      ├── Memory + PostgreSQL
      ├── Moderation / privacy filters
      ├── Social signals
      ▼
Decision / AI Router
      │
      ├── IGNORE
      ├── normal/context reply
      ├── reaction / question / callback
      └── optional chaos/media/game action
      │
      ▼
Unified cooldown + hourly + consecutive-message gate
      │
      ▼
Telegram action execution
```

The bot uses `pyTelegramBotAPI` (TeleBot) and Flask/Gunicorn for the Render Web Service webhook. AI providers are behind a provider router, with Groq as the primary provider.

## Compatibility

- Python: **3.11+**
- Telegram: `pyTelegramBotAPI >=4.29,<5`
- Groq SDK: `groq >=1.7,<2`
- PostgreSQL: recommended for production
- SQLAlchemy 2 + psycopg 3 for database access
- Flask + Gunicorn for Render HTTP service

The Groq SDK currently has a 1.7.0 release, while this repository uses a compatible `<2` range. `python-telegram-bot` is **not** used by this repository. citeturn0search0turn0search1

## Environment

Copy `.env.example` to `.env` locally. Never commit `.env` or real API keys.

Required:

- `TELEGRAM_BOT_TOKEN`
- `GROQ_API_KEY` or `GROQ_API_KEYS` when Groq is the only configured AI provider

Recommended in production:

- `DATABASE_URL` — persistent PostgreSQL connection string
- `WEBHOOK_SECRET`
- `PUBLIC_BASE_URL` (Render can fall back to `RENDER_EXTERNAL_URL`)

Groq keys can be supplied as `GROQ_API_KEYS=key1,key2,key3` or numbered variables such as `GROQ_API_KEY_1`, `GROQ_API_KEY_2`. The application never logs full keys.

## AI / Groq

Groq is used through a provider abstraction. The provider supports multiple keys and automatic rotation for API/rate-limit failures. Stored runtime key state is kept in the database so the active key can survive restarts when PostgreSQL is configured.

The private Groq manager is restricted by `GROQ_ADMIN_IDS`. **Do not use a hard-coded user ID.** Keys shown in administrative UI should be masked, not printed in full.

## Smart randomness

Randomness is not a single `random() < chance` switch. The intended decision flow combines:

- direct mention / reply-to-bot
- group activity
- questions and conversational continuity
- serious/repeated context
- personality values
- recent bot activity
- action-specific cooldowns
- global cooldown
- hourly limits
- maximum consecutive bot messages
- configurable reply probability

Every action must pass the same final gate immediately before execution. This prevents a reaction, chaos event, proactive message, or media action from bypassing normal anti-spam protection.

Important settings:

- `REPLY_CHANCE` — baseline probability for ordinary interventions
- `AI_MIN_SCORE` — minimum social score before an expensive AI decision call
- `MIN_COOLDOWN_SECONDS` / `MAX_COOLDOWN_SECONDS`
- `SOFT_HOURLY_LIMIT` / `HARD_HOURLY_LIMIT`
- `MAX_CONSECUTIVE_BOT_MESSAGES`
- `PROACTIVE_CHANCE`

## Memory and PostgreSQL

The bot keeps bounded recent context rather than sending the entire database to the model. Old message/media storage is pruned. PostgreSQL is the recommended production database because Render's local filesystem is not a durable database location.

Persistent state includes chat settings, memory records, game points, provider state and proactive scheduling state where applicable.

## Proactive behavior

Proactive scheduling is randomized and activity-aware. The next/last proactive timestamps are persisted in `chat_state`, so a restart or Render redeploy does not automatically reset the schedule and cause an immediate burst.

## Telegram permissions

`/settings` is available to Telegram-confirmed group administrators. The bot should not trust a client-provided admin flag. Moderation actions also depend on Telegram permissions granted to the bot.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## Tests / checks

Run before deployment:

```bash
pytest -q
python -m compileall app tests
```

Do not treat a deployment as verified until these commands complete successfully in the target environment.

## Render deployment

This repository is designed as a **Render Web Service**.

1. Create/use a persistent PostgreSQL database.
2. Connect the GitHub repository to a Render Web Service.
3. Build command:

```bash
pip install -r requirements.txt
```

4. Start command should run the Flask application through Gunicorn, as defined by the current `render.yaml`.
5. Add the secrets from `.env.example` in Render Environment Variables.
6. Set `DATABASE_URL` to the Render PostgreSQL connection string.
7. Set a strong `WEBHOOK_SECRET` or let Render generate one through the Blueprint.
8. Deploy and verify `/health`.

The service exposes `/health` for Render health checks and `/telegram/webhook` for Telegram updates.

## Security rules

- Never commit `.env`.
- Never put Telegram/Groq keys in source code.
- Never print API keys in logs or admin responses.
- Keep `GROQ_ADMIN_IDS` explicitly configured.
- Treat structured AI decisions as untrusted input.
- Validate action names, target message IDs, payload length and enabled features before execution.
- Keep Telegram API execution outside the AI provider itself.

## Project cleanup

Generated Python bytecode/cache files are ignored by Git. Local SQLite files are ignored as well. For production persistence, use PostgreSQL rather than relying on Render's ephemeral filesystem.

## Current improvement branch

The `improve/almirfawya-100` branch contains the current hardening pass: safer configuration defaults, current Groq SDK range, thread-safe cooldown primitives, persistent proactive scheduling, a real `.env.example`, Git ignore rules and removal of committed Python cache files.
