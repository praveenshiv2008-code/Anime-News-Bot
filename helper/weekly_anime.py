import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape

import httpx

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from database.db import db
from config import LOG_CHANNEL


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("WeeklyAnime")


# ============================================================
# CONFIGURATION
# ============================================================

ANILIST_URL = "https://graphql.anilist.co"

TOP_COUNT = 16

IST = ZoneInfo("Asia/Kolkata")

# Telegram media captions have a 1024 character limit.
# We keep the text messages below the normal Telegram
# message limit as well.
MAX_MEDIA_CAPTION = 1024
MAX_TEXT_MESSAGE = 4096


# ============================================================
# ANILIST QUERY
# ============================================================

ANILIST_QUERY = """
query {
  Page(page: 1, perPage: 50) {
    media(
      type: ANIME
      status: RELEASING
      sort: SCORE_DESC
      isAdult: false
    ) {
      id

      title {
        romaji
        english
        native
      }

      coverImage {
        large
        medium
      }

      averageScore
      episodes
      status
      genres

      season
      seasonYear

      siteUrl

      nextAiringEpisode {
        episode
        airingAt
      }
    }
  }
}
"""


# ============================================================
# CHAT ID
# ============================================================

def resolve_chat_id(channel):
    """
    Convert numeric Telegram channel IDs to int.

    Examples:

        "-1001234567890" -> -1001234567890
        -1001234567890   -> -1001234567890
        "@mychannel"     -> "@mychannel"
    """

    try:

        if isinstance(channel, int):
            return channel

        if isinstance(channel, str):

            channel = channel.strip()

            if channel.lstrip("-").isdigit():
                return int(channel)

            return channel

        return channel

    except Exception:

        return channel


# ============================================================
# ANIME TITLE
# ============================================================

def get_anime_title(anime):
    """
    Get the best available AniList title.
    """

    title = anime.get("title") or {}

    return (
        title.get("english")
        or title.get("romaji")
        or title.get("native")
        or "Unknown Anime"
    )


# ============================================================
# STATUS
# ============================================================

def get_status(anime):

    status = anime.get("status")

    status_map = {
        "RELEASING": "Airing",
        "FINISHED": "Finished",
        "NOT_YET_RELEASED": "Not Yet Released",
        "CANCELLED": "Cancelled",
        "HIATUS": "Hiatus"
    }

    return status_map.get(
        status,
        status or "Unknown"
    )


# ============================================================
# SCORE
# ============================================================

def format_score(score):

    if score is None:
        return "N/A"

    try:
        return f"{float(score) / 10:.1f}/10"

    except Exception:
        return "N/A"


# ============================================================
# IMAGE
# ============================================================

def get_cover_image(anime):

    cover = anime.get("coverImage") or {}

    return (
        cover.get("large")
        or cover.get("medium")
    )


# ============================================================
# FETCH TOP ANIME
# ============================================================

async def fetch_top_anime():

    logger.info(
        "[WeeklyAnime] Fetching Top %s anime from AniList...",
        TOP_COUNT
    )

    try:

        async with httpx.AsyncClient(
            timeout=30
        ) as client:

            response = await client.post(
                ANILIST_URL,
                json={
                    "query": ANILIST_QUERY
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )

            response.raise_for_status()

            data = response.json()


        # ----------------------------------------------------
        # API ERRORS
        # ----------------------------------------------------

        if data.get("errors"):

            logger.error(
                "[WeeklyAnime] AniList API error: %s",
                data.get("errors")
            )

            return []


        # ----------------------------------------------------
        # GET MEDIA
        # ----------------------------------------------------

        media = (
            data
            .get("data", {})
            .get("Page", {})
            .get("media", [])
        )


        if not media:

            logger.warning(
                "[WeeklyAnime] AniList returned no anime."
            )

            return []


        # ----------------------------------------------------
        # ONLY ANIME WITH RATINGS
        # ----------------------------------------------------

        media = [
            anime
            for anime in media
            if anime.get("averageScore") is not None
        ]


        # ----------------------------------------------------
        # SORT BY SCORE
        # ----------------------------------------------------

        media.sort(
            key=lambda anime: (
                anime.get("averageScore") or 0
            ),
            reverse=True
        )


        # ----------------------------------------------------
        # TOP 16
        # ----------------------------------------------------

        result = media[:TOP_COUNT]


        logger.info(
            "[WeeklyAnime] Found %s anime.",
            len(result)
        )


        return result


    except httpx.HTTPError as e:

        logger.error(
            "[WeeklyAnime] AniList HTTP error: %s",
            e
        )

        return []


    except Exception as e:

        logger.exception(
            "[WeeklyAnime] Failed to fetch anime: %s",
            e
        )

        return []


# ============================================================
# BUILD ONE ANIME ENTRY
# ============================================================

def build_anime_entry(index, anime):

    title = escape(
        get_anime_title(anime)
    )

    score = escape(
        format_score(
            anime.get("averageScore")
        )
    )

    episodes = anime.get("episodes")

    if episodes is None:
        episodes = "?"

    status = escape(
        get_status(anime)
    )

    genres = anime.get("genres") or []

    genres = [
        escape(str(g))
        for g in genres[:3]
    ]

    genre_text = (
        ", ".join(genres)
        if genres
        else "N/A"
    )

    site_url = anime.get("siteUrl")

    # --------------------------------------------------------
    # MEDALS
    # --------------------------------------------------------

    medals = {
        1: "🥇",
        2: "🥈",
        3: "🥉"
    }

    position = medals.get(
        index,
        f"#{index}"
    )


    # --------------------------------------------------------
    # TITLE LINK
    # --------------------------------------------------------

    if site_url:

        title_text = (
            f'<a href="{escape(site_url, quote=True)}">'
            f'<b>{title}</b>'
            f'</a>'
        )

    else:

        title_text = f"<b>{title}</b>"


    # --------------------------------------------------------
    # ENTRY
    # --------------------------------------------------------

    return (
        f"{position} {title_text}\n"
        f"   ⭐ <b>Rating:</b> {score}\n"
        f"   🎬 <b>Episodes:</b> {episodes}\n"
        f"   📡 <b>Status:</b> {status}\n"
        f"   🏷 <b>Genres:</b> {genre_text}\n"
    )


# ============================================================
# BUILD HEADER
# ============================================================

def build_header():

    today = datetime.now(
        IST
    )

    return (
        "<blockquote>"
        "<b>🏆 WEEKLY TOP 16 ANIME</b>"
        "</blockquote>\n\n"
        f"<b>📅 Updated:</b> "
        f"{today.strftime('%d %B %Y')}\n\n"
    )


# ============================================================
# BUILD FOOTER
# ============================================================

def build_footer():

    return (
        "\n"
        "<blockquote>"
        "✦ Updated every Sunday\n"
        "✦ Source: AniList"
        "</blockquote>"
    )


# ============================================================
# BUILD TOP 16 TEXT
# ============================================================

def build_caption(anime_list):

    header = build_header()

    entries = []

    for index, anime in enumerate(
        anime_list,
        start=1
    ):

        entries.append(
            build_anime_entry(
                index,
                anime
            )
        )

    footer = build_footer()

    text = (
        header
        + "\n".join(entries)
        + footer
    )

    return text


# ============================================================
# SPLIT LONG TELEGRAM TEXT
# ============================================================

def split_text(text, max_length=MAX_TEXT_MESSAGE):

    if len(text) <= max_length:
        return [text]


    parts = []

    current = ""

    for line in text.split("\n"):

        # ----------------------------------------------------
        # Normal line
        # ----------------------------------------------------

        if len(current) + len(line) + 1 <= max_length:

            current += (
                line
                + "\n"
            )

            continue


        # ----------------------------------------------------
        # Save current part
        # ----------------------------------------------------

        if current.strip():

            parts.append(
                current.rstrip()
            )


        # ----------------------------------------------------
        # Handle a single very long line
        # ----------------------------------------------------

        if len(line) > max_length:

            start = 0

            while start < len(line):

                end = start + max_length

                parts.append(
                    line[start:end]
                )

                start = end

            current = ""

        else:

            current = line + "\n"


    if current.strip():

        parts.append(
            current.rstrip()
        )


    return parts


# ============================================================
# SEND ONE CHANNEL
# ============================================================

async def send_to_channel(
    app: Client,
    chat_id,
    anime_list,
    full_text
):

    # --------------------------------------------------------
    # SEND POSTER SEPARATELY
    #
    # This avoids MEDIA_CAPTION_TOO_LONG.
    # --------------------------------------------------------

    first_anime = anime_list[0]

    image_url = get_cover_image(
        first_anime
    )


    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✦ AniList",
                    url="https://anilist.co"
                )
            ]
        ]
    )


    try:

        # ----------------------------------------------------
        # POSTER
        # ----------------------------------------------------

        if image_url:

            try:

                await app.send_photo(
                    chat_id=chat_id,
                    photo=image_url
                )

                logger.info(
                    "[WeeklyAnime] Poster sent to %s",
                    chat_id
                )

            except Exception as e:

                logger.warning(
                    "[WeeklyAnime] "
                    "Could not send poster to %s: %s",
                    chat_id,
                    e
                )


        # ----------------------------------------------------
        # TEXT
        #
        # Sent separately, so it can be up to 4096 chars.
        # ----------------------------------------------------

        parts = split_text(
            full_text,
            MAX_TEXT_MESSAGE
        )


        for index, part in enumerate(parts):

            try:

                await app.send_message(
                    chat_id=chat_id,
                    text=part,
                    parse_mode=ParseMode.HTML,

                    # Only show the button on the final message.
                    reply_markup=(
                        keyboard
                        if index == len(parts) - 1
                        else None
                    ),

                    disable_web_page_preview=True
                )

            except Exception as e:

                logger.error(
                    "[WeeklyAnime] "
                    "Failed sending part %s/%s to %s: %s",
                    index + 1,
                    len(parts),
                    chat_id,
                    e
                )

                return False


        return True


    except Exception as e:

        logger.exception(
            "[WeeklyAnime] "
            "Failed sending weekly post to %s: %s",
            chat_id,
            e
        )

        return False


# ============================================================
# LOG MESSAGE
# ============================================================

async def send_log(
    app: Client,
    anime_list,
    sent_count,
    failed_count
):

    if not LOG_CHANNEL:

        return


    try:

        log_id = resolve_chat_id(
            LOG_CHANNEL
        )


        # ----------------------------------------------------
        # If LOG_CHANNEL is accidentally invalid,
        # don't break the weekly job.
        # ----------------------------------------------------

        log_text = (
            "<b>📊 WEEKLY ANIME LOG</b>\n\n"

            f"🏆 <b>Top:</b> {len(anime_list)}\n"

            f"✅ <b>Successful:</b> "
            f"{sent_count}\n"

            f"❌ <b>Failed:</b> "
            f"{failed_count}\n\n"

            f"🥇 <b>Top Anime:</b> "
            f"{escape(get_anime_title(anime_list[0]))}\n"

            f"⭐ <b>Rating:</b> "
            f"{format_score(anime_list[0].get('averageScore'))}"
        )


        await app.send_message(
            chat_id=log_id,
            text=log_text,
            parse_mode=ParseMode.HTML
        )


    except Exception as e:

        # ----------------------------------------------------
        # IMPORTANT:
        # LOG FAILURE MUST NOT STOP THE JOB.
        # ----------------------------------------------------

        logger.warning(
            "[WeeklyAnime] "
            "Could not send log: %s",
            e
        )


# ============================================================
# MAIN WEEKLY FUNCTION
# ============================================================

async def send_weekly_anime(
    app: Client
):

    logger.info(
        "[WeeklyAnime] "
        "Starting weekly Top %s job...",
        TOP_COUNT
    )


    # --------------------------------------------------------
    # FETCH
    # --------------------------------------------------------

    anime_list = await fetch_top_anime()


    if not anime_list:

        logger.warning(
            "[WeeklyAnime] "
            "No anime available. Job cancelled."
        )

        return False


    # --------------------------------------------------------
    # BUILD TEXT
    # --------------------------------------------------------

    full_text = build_caption(
        anime_list
    )


    logger.info(
        "[WeeklyAnime] "
        "Generated text length: %s characters",
        len(full_text)
    )


    # --------------------------------------------------------
    # GET CHANNELS
    # --------------------------------------------------------

    try:

        target_channels = (
            await db.get_all_channels()
        )

    except Exception as e:

        logger.exception(
            "[WeeklyAnime] "
            "Could not get target channels: %s",
            e
        )

        return False


    if not target_channels:

        logger.warning(
            "[WeeklyAnime] "
            "No target channels configured."
        )

        return False


    # --------------------------------------------------------
    # SEND TO CHANNELS
    # --------------------------------------------------------

    sent_count = 0

    failed_count = 0


    for channel in target_channels:

        chat_id = resolve_chat_id(
            channel
        )


        logger.info(
            "[WeeklyAnime] "
            "Sending Top %s to %s...",
            TOP_COUNT,
            chat_id
        )


        success = await send_to_channel(
            app=app,
            chat_id=chat_id,
            anime_list=anime_list,
            full_text=full_text
        )


        if success:

            sent_count += 1

        else:

            failed_count += 1


        # ----------------------------------------------------
        # IMPORTANT:
        # Continue to next channel even when this one fails.
        # ----------------------------------------------------


    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    await send_log(
        app=app,
        anime_list=anime_list,
        sent_count=sent_count,
        failed_count=failed_count
    )


    # --------------------------------------------------------
    # FINAL LOG
    # --------------------------------------------------------

    logger.info(
        "[WeeklyAnime] "
        "Weekly job completed. "
        "Sent: %s | Failed: %s",
        sent_count,
        failed_count
    )


    return sent_count > 0