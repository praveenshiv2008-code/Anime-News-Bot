import asyncio
import logging
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from helper.fetcher import fetch_latest_news
from database.db import db
from config import *


async def broadcast_news(app: Client):
    logger = logging.getLogger("Broadcaster")
    logger.info("[Broadcaster] Starting news broadcast cycle...")

    news_items = await fetch_latest_news()

    if not news_items:
        logger.info("[Broadcaster] No news items to broadcast.")
        return

    target_channels = await db.get_all_channels()
    if not target_channels:
        logger.info("[Broadcaster] No target channels configured. Skipping.")
        return

    def get_markup(url: str) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Rᴇᴀᴅ ɪᴛ ғᴜʟʟʏ...", url=url)
        ]])

    def resolve_chat_id(channel):
        if isinstance(channel, str):
            return int(channel) if channel.lstrip('-').isdigit() else channel
        return int(channel)

    for item in reversed(news_items):

        # ✅ Check first — skip if already posted
        if await db.is_posted(item.link):
            logger.info(f"[Broadcaster] Already posted, skipping: '{item.title}'")
            continue

        # ✅ Lock immediately before sending to prevent double posting
        await db.mark_posted(item.link)
        logger.info(f"[Broadcaster] 🔒 Locked for posting: '{item.title}'")

        try:
            caption = (
    f"<blockquote><b>{item.title}</b></blockquote>\n\n"
    f"<blockquote><b>{item.summary}</b></blockquote>\n\n"
    f'<a href="https://t.me/Anicore_Animes">Anicore Animes</a>'
)
            markup = get_markup(item.link)

            for channel in target_channels:
                chat_id = resolve_chat_id(channel)
                try:
                    if item.image_url:
                        # 🥇 or 🥈 — AniList poster or RSS image
                        await app.send_photo(
                            chat_id=chat_id,
                            photo=item.image_url,
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=markup
                        )
                        logger.info(f"[Broadcaster] ✅ Sent with image to {chat_id}: '{item.title}'")
                    else:
                        # 🥉 — No image at all, text only
                        await app.send_message(
                            chat_id=chat_id,
                            text=caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=markup,
                            disable_web_page_preview=False
                        )
                        logger.info(f"[Broadcaster] ✅ Sent text-only to {chat_id}: '{item.title}'")

                except Exception as e:
                    error_text = (
                        f"⚠️ <b>Routing Error!</b>\n"
                        f"Cannot send to channel: <code>{channel}</code>\n"
                        f"Reason: <code>{e}</code>"
                    )
                    logger.error(f"[Broadcaster] ❌ Failed to send to {channel}: {e}")
                    try:
                        await app.send_message(
                            ADMIN_IDS[0],
                            error_text,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass

            # --- Log to dump channel ---
            if LOG_CHANNEL:
                try:
                    log_id = resolve_chat_id(LOG_CHANNEL)
                    dump_caption = (
                        f"<b>[NEWS LOG]</b>\n"
                        f"Target Chat(s): <code>{', '.join(str(c) for c in target_channels)}</code>\n\n"
                        f"{caption}"
                    )
                    if item.image_url:
                        await app.send_photo(
                            chat_id=log_id,
                            photo=item.image_url,
                            caption=dump_caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=markup
                        )
                    else:
                        await app.send_message(
                            chat_id=log_id,
                            text=dump_caption,
                            parse_mode=ParseMode.HTML,
                            reply_markup=markup,
                            disable_web_page_preview=False
                        )
                except Exception as log_e:
                    logger.error(f"[Broadcaster] ❌ Failed to log to dump channel: {log_e}")

            await asyncio.sleep(3)

        except Exception as e:
            logger.error(f"[Broadcaster] 💥 Critical error processing '{item.title}': {e}")
