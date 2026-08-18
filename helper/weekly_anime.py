import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape

import httpx

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database.db import db
from config import LOG_CHANNEL


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("WeeklyAnime")


# ============================================================
# CONFIG
# ============================================================

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
# RESOLVE CHAT ID
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
# VOTE COUNT
# ============================================================

def get_vote_count(anime):

    """
    Calculate total number of votes from AniList's
    scoreDistribution.

    Example:

        10 -> 500 votes
        9  -> 1200 votes
        8  -> 3000 votes

    Total votes = 4700
    """

    stats = anime.get("stats") or {}

    distribution = (
        stats.get("scoreDistribution")
        or []
    )

    total_votes = 0

    for item in distribution:

        try:

            amount = int(
                item.get("amount") or 0
            )

            total_votes += amount

        except Exception:

            continue

    return total_votes


# ============================================================
# FORMAT VOTES
# ============================================================

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
# COVER IMAGE
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


        # ----------------------------------------------------
        # GRAPHQL ERRORS
        # ----------------------------------------------------

        if data.get("errors"):

            logger.error(
                "[WeeklyAnime] AniList GraphQL error: %s",
                data.get("errors")
            )

            return []


        # ----------------------------------------------------
        # MEDIA
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # REMOVE UNRATED
        # ----------------------------------------------------

        anime_list = [

            anime

            for anime in anime_list

            if anime.get("averageScore") is not None

        ]


        # ----------------------------------------------------
        # SORT BY SCORE
        # ----------------------------------------------------

        anime_list.sort(

            key=lambda anime: (

                anime.get("averageScore") or 0

            ),

            reverse=True,
        )


        result = anime_list[:TOP_COUNT]


        # ----------------------------------------------------
        # LOG RESULTS
        # ----------------------------------------------------

        for index, anime in enumerate(
            result,
            start=1
        ):

            logger.info(

                "[WeeklyAnime] #%s %s | Score: %s | Votes: %s",

                index,

                get_anime_title(anime),

                format_score(
                    anime.get("averageScore")
                ),

                get_vote_count(anime),
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
            "[WeeklyAnime] Fetch error: %s",
            e
        )

        return []


# ============================================================
# BUILD ANIME CAPTION
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

        3: "🥉",
    }


    rank = medals.get(

        index,

        f"🏅 #{index}"

    )


    # --------------------------------------------------------
    # ANILIST LINK
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    today = datetime.now(
        IST
    )


    # --------------------------------------------------------
    # CAPTION
    # --------------------------------------------------------

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
# SEND SINGLE ANIME
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
    # BUTTONS
    # --------------------------------------------------------

    buttons = []


    site_url = anime.get(
        "siteUrl"
    )


    if site_url:

        buttons.append(

            InlineKeyboardButton(

                "🎬 AɴɪLɪsᴛ",

                url=site_url

            )

        )


    keyboard = InlineKeyboardMarkup(
        [buttons]
    ) if buttons else None


    # --------------------------------------------------------
    # SEND IMAGE + CAPTION
    # --------------------------------------------------------

    if image_url:

        try:

            await app.send_photo(

                chat_id=chat_id,

                photo=image_url,

                caption=caption,

                parse_mode=ParseMode.HTML,

                reply_markup=keyboard,
            )


            logger.info(

                "[WeeklyAnime] "
                "Sent #%s %s to %s",

                index,

                title,

                chat_id,
            )


            return True


        except Exception as e:

            logger.warning(

                "[WeeklyAnime] "
                "Photo failed for #%s %s: %s",

                index,

                title,

                e,
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

            disable_web_page_preview=False,
        )


        logger.info(

            "[WeeklyAnime] "
            "Text fallback sent #%s to %s",

            index,

            chat_id,
        )


        return True


    except Exception as e:

        logger.error(

            "[WeeklyAnime] "
            "Failed #%s %s to %s: %s",

            index,

            title,

            chat_id,

            e,
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

            f"🥇 <b>Top Anime:</b> "
            f"{escape(get_anime_title(first))}\n"

            f"⭐ <b>Rating:</b> "
            f"{format_score(first.get('averageScore'))}\n"

            f"👥 <b>Votes:</b> "
            f"{format_votes(get_vote_count(first))}\n\n"

            f"✅ <b>Successful:</b> "
            f"{successful}\n"

            f"❌ <b>Failed:</b> "
            f"{failed}\n"

            f"📊 <b>Total Anime:</b> "
            f"{len(anime_list)}"

        )


        await app.send_message(

            chat_id=log_id,

            text=text,

            parse_mode=ParseMode.HTML

        )


    except Exception as e:

        # IMPORTANT:
        # A broken LOG_CHANNEL does not stop the job.

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

        channels = (
            await db.get_all_channels()
        )


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
    # SEND TO CHANNELS
    # --------------------------------------------------------

    successful_channels = 0

    failed_channels = 0


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
        # SEND ALL 16
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


                # Prevent Telegram flood limits.

                await asyncio.sleep(
                    DELAY_BETWEEN_POSTS
                )


            except Exception as e:

                logger.error(

                    "[WeeklyAnime] "
                    "Unexpected error "
                    "#%s in %s: %s",

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


    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    logger.info(

        "[WeeklyAnime] "
        "Completed. "
        "Successful channels: %s | "
        "Failed channels: %s",

        successful_channels,

        failed_channels

    )


    return successful_channels > 0