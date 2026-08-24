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

    if not text:
        return ""

    return str(text).translate(
        SMALL_CAPS
    )


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = str(text).strip()

    text = " ".join(
        text.split()
    )

    return html.escape(
        text,
        quote=False
    )


# ============================================================
# SUMMARY
# ============================================================

def prepare_summary(summary):

    if not summary:

        return (
            "ᴛʜᴇ ᴏғғɪᴄɪᴀʟ ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛ "
            "ᴄᴏɴғɪʀᴍs ɴᴇᴡ ɪɴғᴏʀᴍᴀᴛɪᴏɴ "
            "ᴀʙᴏᴜᴛ ᴛʜᴇ ᴀɴɪᴍᴇ."
        )

    summary = " ".join(
        str(summary).split()
    )

    if len(summary) > 320:

        summary = (
            summary[:320]
            .rsplit(" ", 1)[0]
            + "..."
        )

    summary = small_caps(
        summary
    )

    return clean_text(
        summary
    )


# ============================================================
# CHAT ID
# ============================================================

def resolve_chat_id(channel):

    if isinstance(channel, str):

        if channel.lstrip("-").isdigit():

            return int(channel)

        return channel

    return int(channel)


# ============================================================
# CREATE CAPTION
# ============================================================

def create_caption(item):

    title = getattr(
        item,
        "title",
        None
    )

    if not title:

        title = "Anime News"

    title = small_caps(
        str(title).strip()
    )

    title = clean_text(
        title
    )

    summary = getattr(
        item,
        "summary",
        None
    )

    summary = prepare_summary(
        summary
    )

    caption = (
        "╭━━━━━「 ɪɴꜰᴏ 」━━━━━╮\n"
        "\n"
        "🔥 ɴᴇᴡ ᴀɴɪᴍᴇ ᴀɴɴᴏᴜɴᴄᴇᴅ!\n"
        "\n"
        f"「 {title} 」\n"
        "\n"
        f"<blockquote>{summary}</blockquote>\n"
        "\n"
        "╰━━━━━━━━━━━━━━╯\n"
        "\n"
        f'⚡ <a href="{UPDATE_LINK}">Sᴛᴀʏ Uᴘᴅᴀᴛᴇᴅ</a>'
    )

    return caption


# ============================================================
# BROADCAST NEWS
# ============================================================

async def broadcast_news(app: Client):

    logger = logging.getLogger(
        "Broadcaster"
    )

    logger.info(
        "[Broadcaster] Starting news broadcast cycle..."
    )

    # --------------------------------------------------------
    # FETCH
    # --------------------------------------------------------

    try:

        news_items = await fetch_latest_news()

    except Exception as e:

        logger.exception(
            "[Broadcaster] Failed to fetch latest news: %s",
            e
        )

        return

    if not news_items:

        logger.info(
            "[Broadcaster] No news items."
        )

        return

    # --------------------------------------------------------
    # CHANNELS
    # --------------------------------------------------------

    try:

        target_channels = (
            await db.get_all_channels()
        )

    except Exception as e:

        logger.exception(
            "[Broadcaster] Failed to get channels: %s",
            e
        )

        return

    if not target_channels:

        logger.info(
            "[Broadcaster] No target channels configured."
        )

        return

    # --------------------------------------------------------
    # NEWS LOOP
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
                "[Broadcaster] Missing news link: %s",
                title
            )

            continue

        # ----------------------------------------------------
        # DUPLICATE CHECK
        # ----------------------------------------------------

        try:

            if await db.is_posted(
                link
            ):

                logger.info(
                    "[Broadcaster] Already posted: %s",
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
        # MARK AS POSTED
        # ----------------------------------------------------

        try:

            await db.mark_posted(
                link
            )

        except Exception as e:

            logger.exception(
                "[Broadcaster] Could not mark news: %s",
                e
            )

            continue

        # ----------------------------------------------------
        # CAPTION
        # ----------------------------------------------------

        caption = create_caption(
            item
        )

        # ----------------------------------------------------
        # IMAGE
        # ----------------------------------------------------

        image_url = getattr(
            item,
            "image_url",
            None
        )

        # ----------------------------------------------------
        # SEND TO CHANNELS
        # ----------------------------------------------------

        for channel in target_channels:

            chat_id = resolve_chat_id(
                channel
            )

            try:

                if image_url:

                    await app.send_photo(
                        chat_id=chat_id,
                        photo=image_url,
                        caption=caption,
                        parse_mode=ParseMode.HTML
                    )

                    logger.info(
                        "[Broadcaster] Sent image to %s: %s",
                        chat_id,
                        title
                    )

                else:

                    await app.send_message(
                        chat_id=chat_id,
                        text=caption,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )

                    logger.info(
                        "[Broadcaster] Sent text to %s: %s",
                        chat_id,
                        title
                    )

            except Exception as e:

                logger.error(
                    "[Broadcaster] Failed to send to %s: %s",
                    channel,
                    e
                )

                # --------------------------------------------
                # ADMIN ERROR
                # --------------------------------------------

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
        # LOG CHANNEL
        # ----------------------------------------------------

        if LOG_CHANNEL:

            try:

                log_id = resolve_chat_id(
                    LOG_CHANNEL
                )

                log_caption = (
                    "<b>[NEWS LOG]</b>\n\n"
                    + caption
                )

                if image_url:

                    await app.send_photo(
                        chat_id=log_id,
                        photo=image_url,
                        caption=log_caption,
                        parse_mode=ParseMode.HTML
                    )

                else:

                    await app.send_message(
                        chat_id=log_id,
                        text=log_caption,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )

            except Exception as e:

                logger.error(
                    "[Broadcaster] Log channel error: %s",
                    e
                )

        # ----------------------------------------------------
        # DELAY
        # ----------------------------------------------------

        await asyncio.sleep(
            3
        )

    logger.info(
        "[Broadcaster] Broadcast cycle completed."
    )