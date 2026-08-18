import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape

import httpx

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.db import db
from config import LOG_CHANNEL


logger = logging.getLogger("WeeklyAnime")

ANILIST_URL = "https://graphql.anilist.co"
TOP_COUNT = 16

IST = ZoneInfo("Asia/Kolkata")


# ============================================================
# ANILIST
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
# TITLE
# ============================================================

def get_anime_title(anime):

    title = anime.get("title") or {}

    return (
        title.get("english")
        or title.get("romaji")
        or title.get("native")
        or "Unknown Anime"
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
# IMAGE
# ============================================================

def get_cover_image(anime):

    cover = anime.get("coverImage") or {}

    return (
        cover.get("large")
        or cover.get("medium")
    )


# ============================================================
# FETCH TOP 16
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


        if data.get("errors"):

            logger.error(
                "[WeeklyAnime] AniList API error: %s",
                data.get("errors")
            )

            return []


        anime_list = (
            data
            .get("data", {})
            .get("Page", {})
            .get("media", [])
        )


        if not anime_list:

            logger.warning(
                "[WeeklyAnime] No anime returned."
            )

            return []


        # Only anime with a rating
        anime_list = [
            anime
            for anime in anime_list
            if anime.get("averageScore") is not None
        ]


        # Highest rated first
        anime_list.sort(
            key=lambda anime: (
                anime.get("averageScore") or 0
            ),
            reverse=True
        )


        return anime_list[:TOP_COUNT]


    except httpx.HTTPError as e:

        logger.error(
            "[WeeklyAnime] HTTP error: %s",
            e
        )

        return []


    except Exception as e:

        logger.exception(
            "[WeeklyAnime] Fetch error: %s",
            e
        )

        return []


# ============================================================
# BUILD SINGLE ANIME CAPTION
# ============================================================

def build_anime_caption(index, anime):

    title = escape(
        get_anime_title(anime)
    )

    score = format_score(
        anime.get("averageScore")
    )

    episodes = anime.get("episodes") or "?"

    status = escape(
        get_status(anime)
    )

    genres = anime.get("genres") or []

    genres = [
        escape(str(genre))
        for genre in genres[:4]
    ]

    genre_text = (
        ", ".join(genres)
        if genres
        else "N/A"
    )


    # --------------------------------------------------------
    # RANK
    # --------------------------------------------------------

    medals = {
        1: "🥇",
        2: "🥈",
        3: "🥉"
    }

    rank = medals.get(
        index,
        f"🏅 #{index}"
    )


    # --------------------------------------------------------
    # TITLE LINK
    # --------------------------------------------------------

    site_url = anime.get("siteUrl")

    if site_url:

        title_line = (
            f'<a href="{escape(site_url, quote=True)}">'
            f'<b>{title}</b>'
            f'</a>'
        )

    else:

        title_line = f"<b>{title}</b>"


    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    today = datetime.now(IST)

    return (
        f"{rank} <b>Wᴇᴇᴋʟʏ Tᴏᴘ 𝟷𝟼</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"

        f"🎬 {title_line}\n\n"

        f"⭐ <b>Rᴀᴛɪɴɢ:</b> {score}\n"
        f"📺 <b>Eᴘɪsᴏᴅᴇs:</b> {episodes}\n"
        f"📡 <b>Sᴛᴀᴛᴜs:</b> {status}\n"
        f"🏷 <b>Gᴇɴʀᴇs:</b> {genre_text}\n\n"

        f"📅 <b>Wᴇᴇᴋ:</b> "
        f"{today.strftime('%d %B %Y')}\n\n"

        f"━━━━━━━━━━━━━━━━━━\n"
        f"✦ <b>Sᴏᴜʀᴄᴇ:</b> AɴɪLɪsᴛ"
    )


# ============================================================
# SEND ONE ANIME
# ============================================================

async def send_single_anime(
    app: Client,
    chat_id,
    index,
    anime
):

    title = get_anime_title(anime)

    image_url = get_cover_image(anime)

    caption = build_anime_caption(
        index,
        anime
    )


    # --------------------------------------------------------
    # BUTTON
    # --------------------------------------------------------

    buttons = []

    site_url = anime.get("siteUrl")

    if site_url:

        buttons.append(
            InlineKeyboardButton(
                "🎬 Wᴀᴛᴄʜ / Mᴏʀᴇ Iɴғᴏ",
                url=site_url
            )
        )


    buttons.append(
        InlineKeyboardButton(
            f"🏆 #{index} Tᴏᴘ 𝟷𝟼",
            callback_data=f"weekly_rank_{index}"
        )
    )


    keyboard = InlineKeyboardMarkup(
        [buttons]
    )


    # --------------------------------------------------------
    # SEND POSTER
    # --------------------------------------------------------

    if image_url:

        try:

            await app.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )

            logger.info(
                "[WeeklyAnime] Sent #%s %s to %s",
                index,
                title,
                chat_id
            )

            return True


        except Exception as e:

            logger.warning(
                "[WeeklyAnime] "
                "Poster failed for #%s (%s): %s",
                index,
                title,
                e
            )


    # --------------------------------------------------------
    # FALLBACK TEXT MESSAGE
    # --------------------------------------------------------

    try:

        await app.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=False
        )

        logger.info(
            "[WeeklyAnime] Sent text fallback #%s to %s",
            index,
            chat_id
        )

        return True


    except Exception as e:

        logger.error(
            "[WeeklyAnime] "
            "Failed #%s (%s) to %s: %s",
            index,
            title,
            chat_id,
            e
        )

        return False


# ============================================================
# SEND LOG
# ============================================================

async def send_log(
    app,
    anime_list,
    successful,
    failed
):

    if not LOG_CHANNEL:
        return


    try:

        log_id = resolve_chat_id(
            LOG_CHANNEL
        )


        first = anime_list[0]

        text = (
            "<b>📊 WEEKLY TOP 16 LOG</b>\n\n"

            f"🏆 Anime: "
            f"<b>{escape(get_anime_title(first))}</b>\n"

            f"⭐ Rating: "
            f"<b>{format_score(first.get('averageScore'))}</b>\n\n"

            f"✅ Successful: <b>{successful}</b>\n"
            f"❌ Failed: <b>{failed}</b>\n"
            f"📊 Total: <b>{len(anime_list)}</b>"
        )


        await app.send_message(
            chat_id=log_id,
            text=text,
            parse_mode=ParseMode.HTML
        )


    except Exception as e:

        # IMPORTANT:
        # A bad LOG_CHANNEL must NEVER stop the job.

        logger.warning(
            "[WeeklyAnime] "
            "Could not send log: %s",
            e
        )


# ============================================================
# MAIN FUNCTION
# ============================================================

async def send_weekly_anime(app: Client):

    logger.info(
        "[WeeklyAnime] "
        "Starting Weekly Top %s...",
        TOP_COUNT
    )


    # --------------------------------------------------------
    # FETCH
    # --------------------------------------------------------

    anime_list = await fetch_top_anime()


    if not anime_list:

        logger.warning(
            "[WeeklyAnime] "
            "No anime found."
        )

        return False


    # --------------------------------------------------------
    # CHANNELS
    # --------------------------------------------------------

    try:

        channels = await db.get_all_channels()

    except Exception as e:

        logger.exception(
            "[WeeklyAnime] "
            "Database error: %s",
            e
        )

        return False


    if not channels:

        logger.warning(
            "[WeeklyAnime] "
            "No target channels configured."
        )

        return False


    # --------------------------------------------------------
    # SEND
    # --------------------------------------------------------

    successful = 0
    failed = 0


    for channel in channels:

        chat_id = resolve_chat_id(
            channel
        )


        logger.info(
            "[WeeklyAnime] "
            "Sending Top %s to %s",
            len(anime_list),
            chat_id
        )


        channel_success = 0


        for index, anime in enumerate(
            anime_list,
            start=1
        ):

            try:

                result = await send_single_anime(
                    app=app,
                    chat_id=chat_id,
                    index=index,
                    anime=anime
                )


                if result:

                    channel_success += 1


                # Small delay so Telegram isn't hit
                # with 16 requests at exactly the same time.
                await __import__("asyncio").sleep(0.5)


            except Exception as e:

                logger.error(
                    "[WeeklyAnime] "
                    "Unexpected error #%s in %s: %s",
                    index,
                    chat_id,
                    e
                )


        if channel_success == len(anime_list):

            successful += 1

        else:

            failed += 1


        logger.info(
            "[WeeklyAnime] "
            "Channel %s: %s/%s sent",
            chat_id,
            channel_success,
            len(anime_list)
        )


    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    await send_log(
        app=app,
        anime_list=anime_list,
        successful=successful,
        failed=failed
    )


    logger.info(
        "[WeeklyAnime] "
        "Completed. Channels successful: %s | failed: %s",
        successful,
        failed
    )


    return successful > 0