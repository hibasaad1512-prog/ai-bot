# Storage

`smart_archive.py` stores only lightweight Telegram metadata and file IDs. Binary media must not be persisted in Neon on the free tier; use Telegram file IDs and temporary files when processing media.