# Lmyrfawya AI

lmyrfawya (kyoos) is a Telegram bot designed to feel like a casual, social, slightly chaotic member. `/start`, `/settings` and `/testai` are local commands; every other non-command text message is sent directly to Groq for a reply.

## Core behavior

Kyoos replies to every normal text message by default. There is no local AI-eligibility gate on ordinary messages, so a valid user message is never silently discarded just because a score was low. The local command handlers always run first for `/start`, `/settings` and `/testai`.

The action system is modular and includes `IGNORE`, contextual replies, conversation joins, reactions, old-message callbacks, quote remixes, random member interaction, random images, image captions, local image mashups/collages, context memes, image generation, polls, chaos events, mini challenges and companion-bot routing hooks.

## Architecture

```text
Telegram webhook
      |
      v
 ContextStore -> Activity/Moderation -> Local Chaos Scoring
      |                                  |
      |                            likely ignore?
      |                                  |
      +---------------------------- no -> Groq Decision
                                             |
                                   schema/action validation
                                             |
                                  cooldown/rate-limit gate
                                             |
                                        Action Registry
                                             |
                               Telegram / Pillow / Games
```

AI is provider-agnostic through `AIProvider`; Groq is the active implementation.


### Per-group admin permissions
`/settings` is never gated by a global admin list. In every group/supergroup, KYOOS checks Telegram live with `getChatMember` and only allows users whose status is `administrator` or `creator` to open or interact with the settings panel. Settings and language are stored by `chat_id`, so each group has its own configuration.

For Telegram to reliably report another member's admin status, KYOOS should have appropriate group administration/member visibility (normally the bot is added as an admin when moderation/admin verification is required). The bot never trusts a client-provided "admin" flag.

## Environment

Copy `.env.example` to `.env` locally. Never commit `.env`.

Required:

- `TELEGRAM_BOT_TOKEN`
- `GROQ_API_KEY`

Production persistence:

- `DATABASE_URL` — optional. Leave empty for local SQLite on the Render instance; use PostgreSQL later when persistent storage is needed.
- `REDIS_URL` — optional. KYOOS does not require Redis to run.

Render/webhook:

- `PUBLIC_BASE_URL`
- `WEBHOOK_SECRET`
- `PORT` is supplied by Render; local default is 10000.

Optional model settings:

- `GROQ_TEXT_MODEL` (default `openai/gpt-oss-120b`)
- `COMPANION_BOT_TOKENS`

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

For local webhook testing, expose the HTTP service with a tunnel and set `PUBLIC_BASE_URL` to the public HTTPS URL.

## Render deployment

This repository is prepared as a Render **Web Service** using Gunicorn and an HTTP health endpoint. Render supports Python web services with a build command such as `pip install -r requirements.txt`, a configurable start command, and HTTP health checks; `render.yaml` declares the health check at `/health`. citeturn992296search0turn992296search1turn992296search5

Recommended production setup:

1. Push the repository to GitHub.
2. Create a Render Web Service from that repository.
3. Use the included `render.yaml`.
4. Add the environment variables from `.env.example`.
5. Leave `DATABASE_URL` and `REDIS_URL` empty for the simple free setup.
6. `PUBLIC_BASE_URL` can also be left empty on Render because the app auto-uses `RENDER_EXTERNAL_URL`.
7. Add the Kyoos bot to the target groups with the required Telegram permissions.

The application configures the Telegram webhook automatically when `PUBLIC_BASE_URL` is present. It also continues to boot if webhook registration temporarily fails.

## Telegram configuration

Kyoos needs to receive enough group messages to build context. Telegram Privacy Mode can limit which group messages a bot receives. For natural group observation, configure BotFather privacy settings and group permissions appropriately. The exact messages Telegram delivers depend on privacy mode and the bot's role/permissions.

For moderation features, grant only the group permissions you actually enable. Deleting messages and restricting/kicking users require elevated group permissions.

## `/start` and admin controls

Regular members mainly use `/start`. Kyoos then observes and acts automatically.

Admins can use `/settings` only inside groups/supergroups where Telegram confirms they are administrators. Every inline settings button and language change is re-checked against the current group admin status. `/testai` is available in private chats without a global admin ID, and is restricted to confirmed group admins inside groups.

Personality values are stored per chat:

- chaos
- humor
- social
- weirdness
- images
- events
- roast
- emoji
- human_imperfection
- proactivity

## AI behavior

Groq structured decisions are treated as untrusted input. The application validates:

- action enum
- confidence range
- target message ID
- feature enablement
- cooldown state
- hourly/burst limits

Groq cannot call Telegram APIs directly.

Groq is used for text and structured decision generation. The current Groq provider build does not expose image generation or vision, so those capabilities stay disabled rather than failing silently. citeturn992296search2turn992296search3turn992296search4

## Memory and privacy

Chat context is bounded (default 40 messages) and TTL-based. Uploaded image references are also bounded and temporary in the in-memory pool. Kyoos does not intentionally build a permanent archive of every message or image.

Persistent database state is limited to chat settings, game points and chat state. PostgreSQL is recommended in production.

## Moderation

Moderation is separate from personality. The included baseline detector handles basic duplicate spam, link-spam patterns and oversized messages. It does not give Groq moderation authority. Telegram enforcement remains subject to bot permissions.

## Games

The game engine uses virtual points only. There is no real-money gambling. Supported building blocks include emoji/guess/challenge-style events, participant joining and point awarding.

## Image engine

`Pillow` is used for local operations whenever possible:

- side-by-side mashup
- collage
- meme captioning

Groq is reserved for semantic captioning/vision or actual generation when needed.

## Testing

Run:

```bash
pytest -q
python -m compileall app tests
```

The test suite covers chaos scoring, selector behavior, cooldowns, dialect detection, structured decision validation, image pool/collage, game points and required deployment files.

## Troubleshooting

### Groq disabled
Check `GROQ_API_KEY`, provider availability and the configured model names. Kyoos will keep running without Groq; it will simply avoid AI-driven interventions or use local fallbacks.

### No proactive behavior
Proactive messages are disabled by default to save free-plan quota. Normal user messages still go directly to Groq.

### No group messages arrive
Check Telegram Privacy Mode, bot membership and permissions. A bot cannot react to messages Telegram does not deliver to it.

### Database errors
Check `DATABASE_URL` and credentials. Local SQLite is intentionally a simple free-mode fallback; its state is not guaranteed across Render redeploys/restarts. Use PostgreSQL later if permanent persistence is required.

## Production limitations / paid or external services

Kyoos itself is deployable as a Render Web Service, but some capabilities inherently depend on external services:

- Groq text/vision/image generation requires a working Groq API configuration and whatever quota/billing/availability applies to that account.
- PostgreSQL persistence is recommended for production; use a persistent database service.
- Redis is optional but recommended for multi-instance or stronger shared ephemeral state.
- Telegram group moderation depends on the bot having the required Telegram admin permissions.
- Companion bots require separately configured bot tokens and must comply with Telegram's platform limits/rules.

The core bot remains functional when Groq image generation is unavailable.

## Smart Social Behavior
Kyoos uses a local social-signal layer before Groq: activity level, direct address, reply-to-bot, questions, humor/laughter cues, serious-context cues, repetition, continuity, old-message callback opportunities, and recent bot behavior. Weak messages can stop before an AI call, while directly addressed messages receive a higher response priority. Humanization remains probabilistic so replies do not all look identical.

### Smart behavior environment variables
- `AI_MIN_SCORE`: local score required before spending a Groq decision call (default `34`).
- `CALLBACK_MIN_AGE_SECONDS`: minimum age for considering older messages as callback material (default `300`).
- `PROACTIVE_QUIET_SECONDS`: minimum quiet period before proactive behavior is considered (default `600`).

These can stay at their defaults on Render. Lowering `AI_MIN_SCORE` makes Kyoos more talkative and increases Groq usage; increasing it makes Kyoos quieter and cheaper.
