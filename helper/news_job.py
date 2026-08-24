import asyncio
import logging
import html

from pyrogram import Client
from pyrogram.enums import ParseMode

from helper.fetcher import fetch_latest_news
from database.db import db
from config import *


# ============================================================
# SETTINGS
# ============================================================

UPDATE_LINK = "https://t.me/Anicore_Animes"


# ============================================================
# SMALL CAPS
# ============================================================

SMALL_CAPS = str.maketrans(
    "abcdefghijklmnopqrstuvwxyz",
    "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ"
)


def small_caps(text):
    """
    Convert normal English letters to Unicode small caps.
    """
    if not text:
        return ""

    return str(text).translate(SMALL_CAPS)


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(text):
    """
    Clean and safely prepare RSS/news text for Telegram HTML.
    """

    if not text:
        return ""

    text = str(text).strip()

    # Escape HTML characters so article text cannot break
    # Telegram's HTML formatting.
    text = html.escape(text, quote=False)

    return text


# ============================================================
# SHORT SUMMARY
# ============================================================

def prepare_summary(summary):
    """
    Keep the news description short and clean.
    """

    if not summary:
        return (
            "ᴛʜᴇ ᴏғғɪᴄɪᴀʟ ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛ ᴄᴏɴғɪʀᴍs "
            "ɴᴇᴡ ɪɴғᴏʀᴍᴀᴛɪᴏɴ ᴀʙᴏᴜᴛ ᴛʜᴇ ᴀɴɪᴍᴇ."
        )

    # Remove excessive spaces/newlines.
    summary = " ".join(str(summary).split())

    # Keep captions reasonably sized.
    if len(summary) > 320:
        summary = summary[:320].rsplit(" ", 1)[0] + "..."

    return small_caps(summary)


# ============================================================
# CHANNEL ID
# ============================================================

def resolve_chat_id(channel):
    """
    Convert numeric channel IDs to int.
    Keep @username as string.
    """

    if isinstance(channel, str):

        if channel.lstrip("-").isdigit():
            return int(channel)

        return channel

    return int(channel)


# ============================================================
# NEWS CAPTION
# ============================================================

def create_caption(item):
    """
    Creates the exact requested format.

    Example:

    ╭━━━━━「 ɪɴꜰᴏ 」━━━━━╮

    🔥 ɴᴇᴡ ᴀɴɪᴍᴇ ᴀɴɴᴏᴜɴᴄᴇᴅ!

    「 ᴀɴɪᴍᴇ ᴛɪᴛʟᴇ 」

    <blockquote>
    ᴛʜᴇ ᴏғғɪᴄɪᴀʟ...
    </blockquote>

    📅 ʀᴇʟᴇᴀsᴇ: ᴛʙᴀ
    🎬 sᴛᴜᴅɪᴏ: ᴛʙᴀ

    ╰━━━━━━━━━━━━━━╯

    ⚡ Sᴛᴀʏ Uᴘᴅᴀᴛᴇᴅ
    """

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = getattr(item, "title", None)

    if not title:
        title = "Anime News"

    title = str(title).strip()

    title = small_caps(title)

    title = html.escape(
        title,
        quote=False
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = getattr(item, "summary", None)

    summary = prepare_summary(summary)

    summary = clean_text(summary)

    # --------------------------------------------------------
    # FINAL CAPTION
    # --------------------------------------------------------

    caption = (
        "╭━━━━━「 ɪɴꜰᴏ 」━━━━━╮\n"
        "\n"
        "🔥 ɴᴇᴡ ᴀɴɪᴍᴇ ᴀɴɴᴏᴜɴᴄᴇᴅ!\n"
        "\n"
        f"「 {title} 」\n"
        "\n"
        f"<blockquote>{summary}</blockquote>\n"
        "\n"
        "📅 ʀᴇʟᴇᴀsᴇ: ᴛʙᴀ\n"
        "🎬 sᴛᴜᴅɪᴏ: ᴛʙᴀ\n"
        "\n"
        "╰━━━━━━━━━━━━━━╯\n"
        "\n"
        f'⚡ <a href="{UPDATE_LINK}">Sᴛᴀʏ Uᴘᴅᴀᴛᴇᴅ</a>'
    )

    return caption


# ============================================================
# NEWS BROADCAST
# ============================================================

async def broadcast_news(app: Client):

    logger = logging.getLogger("Broadcaster")

    logger.info(
        "[Broadcaster] Starting news broadcast cycle..."
    )

    # --------------------------------------------------------
    # FETCH NEWS
    # --------------------------------------------------------

    try:

        news_items = await fetch_latest_news()

    except Exception as e:

        logger.exception(
            "[Broadcaster] Failed to fetch news: %s",
            e
        )

        return

    if not news_items:

        logger.info(
            "[Broadcaster] No news items to broadcast."
        )

        return

    # --------------------------------------------------------
    # GET CHANNELS
    # --------------------------------------------------------

    try:

        target_channels = await db.get_all_channels()

    except Exception as e:

        logger.exception(
            "[Broadcaster] Failed to get target channels: %s",
            e
        )

        return

    if not target_channels:

        logger.info(
            "[Broadcaster] No target channels configured. Skipping."
        )

        return

    # --------------------------------------------------------
    # PROCESS NEWS
    # --------------------------------------------------------

    for item in reversed(news_items):

        title = getattr(
            item,
            "title",
            "Unknown News"
        )

        link = getattr(
            item,
            "link",
            None
        )

        if not link:

            logger.warning(
                "[Broadcaster] News item has no link: %s",
                title
            )

            continue

        # ----------------------------------------------------
        # DUPLICATE CHECK
        # ----------------------------------------------------

        try:

            if await db.is_posted(link):

                logger.info(
                    "[Broadcaster] Already posted, skipping: '%s'",
                    title
                )

                continue

        except Exception as e:

            logger.exception(
                "[Broadcaster] Database check failed: %s",
                e
            )

            continue

        # ----------------------------------------------------
        # LOCK NEWS
        # ----------------------------------------------------

        try:

            await db.mark_posted(link)

            logger.info(
                "[Broadcaster] 🔒 Locked for posting: '%s'",
                title
            )

        except Exception as e:

            logger.exception(
                "[Broadcaster] Failed to mark news as posted: %s",
                e
            )

            continue

        # ----------------------------------------------------
        # CREATE CAPTION
        # ----------------------------------------------------

        caption = create_caption(item)

        # ----------------------------------------------------
        # IMAGE
        # ----------------------------------------------------

        image_url = getattr(
            item,
            "image_url",
            None
        )

        # ----------------------------------------------------
        # SEND TO ALL CHANNELS
        # ----------------------------------------------------

        for channel in target_channels:

            chat_id = resolve_chat_id(channel)

            try:

                # ============================================
                # WITH IMAGE
                # ============================================

                if image_url:

                    await app.send_photo(
                        chat_id=chat_id,
                        photo=image_url,
                        caption=caption,
                        parse_mode=ParseMode.HTML
                    )

                    logger.info(
                        "[Broadcaster] ✅ Sent image news to %s: '%s'",
                        chat_id,
                        title
                    )

                # ============================================
                # WITHOUT IMAGE
                # ============================================

                else:

                    await app.send_message(
                        chat_id=chat_id,
                        text=caption,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )

                    logger.info(
                        "[Broadcaster] ✅ Sent text news to %s: '%s'",
                        chat_id,
                        title
                    )

            except Exception as e:

                logger.error(
                    "[Broadcaster] ❌ Failed to send to %s: %s",
                    channel,
                    e
                )

                # ------------------------------------------------
                # ADMIN ERROR MESSAGE
                # ------------------------------------------------

                try:

                    if ADMIN_IDS:

                        error_text = (
                            "⚠️ <b>News Broadcast Error</b>\n\n"
                            f"<b>Channel:</b> "
                            f"<code>{html.escape(str(channel))}</code>\n"
                            f"<b>News:</b> "
                            f"<code>{html.escape(str(title))}</code>\n"
                            f"<b>Error:</b> "
                            f"<code>{html.escape(str(e))}</code>"
                        )

                        await app.send_message(
                            ADMIN_IDS[0],
                            error_text,
                            parse_mode=ParseMode.HTML
                        )

                except Exception:
                    pass

        # ----------------------------------------------------
        # DUMP / LOG CHANNEL
        # ----------------------------------------------------

        if LOG_CHANNEL:

            try:

                log_id = resolve_chat_id(
                    LOG_CHANNEL
                )

                dump_caption = (
                    "<b>[NEWS LOG]</b>\n\n"
                    f"{caption}"
                )

                if image_url:

                    await app.send_photo(
                        chat_id=log_id,
                        photo=image_url,
                        caption=dump_caption,
                        parse_mode=ParseMode.HTML
                    )

                else:

                    await app.send_message(
                        chat_id=log_id,
                        text=dump_caption,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )

                logger.info(
                    "[Broadcaster] ✅ News logged."
                )

            except Exception as e:

                logger.error(
                    "[Broadcaster] ❌ Failed to log news: %s",
                    e
                )

        # ----------------------------------------------------
        # DELAY BETWEEN POSTS
        # ----------------------------------------------------

        await asyncio.sleep(3)

    logger.info(
        "[Broadcaster] News broadcast cycle completed."
    )