import asyncio
import logging
import os
import tempfile
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

REQUEST_TIMEOUT = 30

DELAY_BETWEEN_POSTS = 0.7


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
        extraLarge
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

      stats {
        scoreDistribution {
          score
          amount
        }
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
# VOTES
# ============================================================

def get_vote_count(anime):

    stats = anime.get("stats") or {}

    distribution = (
        stats.get("scoreDistribution")
        or []
    )

    total = 0

    for item in distribution:

        try:

            total += int(
                item.get("amount") or 0
            )

        except Exception:

            continue

    return total


def format_votes(votes):

    try:
        votes = int(votes)

    except Exception:
        return "0"


    if votes >= 1_000_000:
        return f"{votes / 1_000_000:.1f}M"

    if votes >= 100_000:
        return f"{votes / 1000:.0f}K"

    if votes >= 10_000:
        return f"{votes / 1000:.1f}K"

    if votes >= 1_000:
        return f"{votes / 1000:.1f}K"

    return f"{votes:,}"


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
        "HIATUS": "Hiatus",
    }

    return status_map.get(
        status,
        status or "Unknown"
    )


# ============================================================
# HIGH QUALITY IMAGE URL
# ============================================================

def get_cover_image(anime):

    cover = anime.get("coverImage") or {}

    # IMPORTANT:
    # extraLarge is higher resolution than large.
    return (
        cover.get("extraLarge")
        or cover.get("large")
        or cover.get("medium")
    )


# ============================================================
# DOWNLOAD HIGH QUALITY IMAGE
# ============================================================

async def download_image(url):

    if not url:
        return None

    try:

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True
        ) as client:

            response = await client.get(url)

            response.raise_for_status()

            content_type = (
                response.headers
                .get("content-type", "")
                .lower()
            )

            if not content_type.startswith("image/"):

                logger.warning(
                    "[WeeklyAnime] "
                    "URL did not return an image: %s",
                    url
                )

                return None


            # ------------------------------------------------
            # Temporary file
            # ------------------------------------------------

            suffix = ".jpg"

            if "png" in content_type:
                suffix = ".png"

            elif "webp" in content_type:
                suffix = ".webp"


            file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=suffix
            )

            file.write(
                response.content
            )

            file.close()


            logger.info(
                "[WeeklyAnime] "
                "Downloaded high-quality image: %.1f KB",
                len(response.content) / 1024
            )


            return file.name


    except Exception as e:

        logger.warning(
            "[WeeklyAnime] "
            "High-quality image download failed: %s",
            e
        )

        return None


# ============================================================
# FETCH TOP 16
# ============================================================

async def fetch_top_anime():

    logger.info(
        "[WeeklyAnime] "
        "Fetching Top %s from AniList...",
        TOP_COUNT
    )

    try:

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT
        ) as client:

            response = await client.post(
                ANILIST_URL,

                json={
                    "query": ANILIST_QUERY
                },

                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

            response.raise_for_status()

            data = response.json()


        if data.get("errors"):

            logger.error(
                "[WeeklyAnime] "
                "AniList error: %s",
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
                "[WeeklyAnime] "
                "AniList returned no anime."
            )

            return []


        anime_list = [
            anime
            for anime in anime_list
            if anime.get("averageScore") is not None
        ]


        anime_list.sort(
            key=lambda anime: (
                anime.get("averageScore") or 0
            ),
            reverse=True
        )


        result = anime_list[:TOP_COUNT]


        for index, anime in enumerate(
            result,
            start=1
        ):

            logger.info(
                "[WeeklyAnime] #%s %s | Rating %s | Votes %s",
                index,
                get_anime_title(anime),
                format_score(
                    anime.get("averageScore")
                ),
                get_vote_count(anime)
            )


        return result


    except httpx.HTTPError as e:

        logger.error(
            "[WeeklyAnime] "
            "AniList HTTP error: %s",
            e
        )

        return []


    except Exception as e:

        logger.exception(
            "[WeeklyAnime] "
            "Fetch error: %s",
            e
        )

        return []


# ============================================================
# BUILD CAPTION
# ============================================================

def build_anime_caption(
    index,
    anime
):

    title = escape(
        get_anime_title(anime)
    )

    score = format_score(
        anime.get("averageScore")
    )

    votes = format_votes(
        get_vote_count(anime)
    )

    episodes = (
        anime.get("episodes")
        or "?"
    )

    status = escape(
        get_status(anime)
    )

    genres = anime.get(
        "genres"
    ) or []

    genres = [
        escape(str(g))
        for g in genres[:4]
    ]

    genre_text = (
        ", ".join(genres)
        if genres
        else "N/A"
    )


    medals = {
        1: "🥇",
        2: "🥈",
        3: "🥉"
    }

    rank = medals.get(
        index,
        f"🏅 #{index}"
    )


    site_url = anime.get(
        "siteUrl"
    )


    if site_url:

        title_line = (
            f'<a href="'
            f'{escape(site_url, quote=True)}'
            f'">'
            f'<b>{title}</b>'
            f'</a>'
        )

    else:

        title_line = (
            f"<b>{title}</b>"
        )


    today = datetime.now(
        IST
    )


    return (
        f"{rank} "
        f"<b>Wᴇᴇᴋʟʏ Tᴏᴘ 𝟷𝟼</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"

        f"🎬 {title_line}\n\n"

        f"⭐ <b>Rᴀᴛɪɴɢ:</b> "
        f"{score}\n"

        f"👥 <b>Vᴏᴛᴇs:</b> "
        f"{votes}\n"

        f"📺 <b>Eᴘɪsᴏᴅᴇs:</b> "
        f"{episodes}\n"

        f"📡 <b>Sᴛᴀᴛᴜs:</b> "
        f"{status}\n"

        f"🏷 <b>Gᴇɴʀᴇs:</b> "
        f"{genre_text}\n\n"

        f"📅 <b>Wᴇᴇᴋ:</b> "
        f"{today.strftime('%d %B %Y')}\n\n"

        f"━━━━━━━━━━━━━━━━━━\n"
        f"✦ <b>Sᴏᴜʀᴄᴇ:</b> AɴɪLɪsᴛ"
    )


# ============================================================
# SEND ONE ANIME
# ============================================================

async def send_single_anime(
    app,
    chat_id,
    index,
    anime
):

    title = get_anime_title(
        anime
    )

    image_url = get_cover_image(
        anime
    )

    caption = build_anime_caption(
        index,
        anime
    )


    # --------------------------------------------------------
    # BUTTON
    # --------------------------------------------------------

    site_url = anime.get(
        "siteUrl"
    )

    keyboard = None

    if site_url:

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🎬 AɴɪLɪsᴛ",
                        url=site_url
                    )
                ]
            ]
        )


    # --------------------------------------------------------
    # DOWNLOAD HIGH QUALITY IMAGE
    # --------------------------------------------------------

    image_file = None


    if image_url:

        image_file = await download_image(
            image_url
        )


    # --------------------------------------------------------
    # SEND LOCAL IMAGE
    # --------------------------------------------------------

    if image_file:

        try:

            await app.send_photo(
                chat_id=chat_id,
                photo=image_file,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )


            logger.info(
                "[WeeklyAnime] "
                "High-quality #%s sent: %s",
                index,
                title
            )


            return True


        except Exception as e:

            logger.warning(
                "[WeeklyAnime] "
                "Local image send failed "
                "#%s %s: %s",
                index,
                title,
                e
            )


        finally:

            try:

                os.remove(
                    image_file
                )

            except Exception:

                pass


    # --------------------------------------------------------
    # REMOTE IMAGE FALLBACK
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
                "[WeeklyAnime] "
                "Remote image fallback sent #%s",
                index
            )


            return True


        except Exception as e:

            logger.warning(
                "[WeeklyAnime] "
                "Remote image failed #%s: %s",
                index,
                e
            )


    # --------------------------------------------------------
    # TEXT FALLBACK
    # --------------------------------------------------------

    try:

        await app.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=False
        )


        return True


    except Exception as e:

        logger.error(
            "[WeeklyAnime] "
            "Everything failed for #%s %s: %s",
            index,
            title,
            e
        )

        return False


# ============================================================
# LOG
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

            f"🥇 <b>Top:</b> "
            f"{escape(get_anime_title(first))}\n"

            f"⭐ <b>Rating:</b> "
            f"{format_score(first.get('averageScore'))}\n"

            f"👥 <b>Votes:</b> "
            f"{format_votes(get_vote_count(first))}\n\n"

            f"✅ <b>Successful:</b> "
            f"{successful}\n"

            f"❌ <b>Failed:</b> "
            f"{failed}\n"

            f"📊 <b>Total:</b> "
            f"{len(anime_list)}"
        )


        await app.send_message(
            chat_id=log_id,
            text=text,
            parse_mode=ParseMode.HTML
        )


    except Exception as e:

        logger.warning(
            "[WeeklyAnime] "
            "Could not send log: %s",
            e
        )


# ============================================================
# MAIN WEEKLY JOB
# ============================================================

async def send_weekly_anime(
    app
):

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


    successful_channels = 0
    failed_channels = 0


    # --------------------------------------------------------
    # CHANNEL LOOP
    # --------------------------------------------------------

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


        sent_count = 0


        # ----------------------------------------------------
        # SEND 16 INDIVIDUAL POSTS
        # ----------------------------------------------------

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
                    sent_count += 1


                await asyncio.sleep(
                    DELAY_BETWEEN_POSTS
                )


            except Exception as e:

                logger.error(
                    "[WeeklyAnime] "
                    "Unexpected error #%s "
                    "in %s: %s",
                    index,
                    chat_id,
                    e
                )


        # ----------------------------------------------------
        # CHANNEL RESULT
        # ----------------------------------------------------

        if sent_count == len(
            anime_list
        ):

            successful_channels += 1

        else:

            failed_channels += 1


        logger.info(
            "[WeeklyAnime] "
            "Channel %s: %s/%s sent",
            chat_id,
            sent_count,
            len(anime_list)
        )


    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    await send_log(
        app=app,
        anime_list=anime_list,
        successful=successful_channels,
        failed=failed_channels
    )


    logger.info(
        "[WeeklyAnime] "
        "Completed. Successful: %s | Failed: %s",
        successful_channels,
        failed_channels
    )


    return successful_channels > 0