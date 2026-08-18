import asyncio
import logging
import random
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import httpx
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import *
from helper.news_job import broadcast_news
from helper.weekly_anime import send_weekly_anime, fetch_top_anime


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("AnimeBot")


# ============================================================
# TIMEZONE
# ============================================================

IST = ZoneInfo("Asia/Kolkata")

ANILIST_URL = "https://graphql.anilist.co"

ANILIST_TIMEOUT = 30


# ============================================================
# ADMIN IDS
# ============================================================

ADMIN_IDS = set()

for value in (
    globals().get("OWNER_ID"),
    globals().get("ADMIN_ID"),
):

    if value is not None:

        try:
            ADMIN_IDS.add(int(value))

        except Exception:
            pass


# ============================================================
# ANILIST REQUEST
# ============================================================

async def anilist_request(query, variables=None):

    try:

        async with httpx.AsyncClient(
            timeout=ANILIST_TIMEOUT
        ) as http:

            response = await http.post(

                ANILIST_URL,

                json={
                    "query": query,
                    "variables": variables or {}
                },

                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Anime-News-Bot"
                }
            )

            response.raise_for_status()

            result = response.json()


        if result.get("errors"):

            logger.warning(
                "AniList error: %s",
                result["errors"]
            )

            return None


        return result.get("data")


    except Exception as e:

        logger.error(
            "AniList request failed: %s",
            e
        )

        return None


# ============================================================
# FORMAT HELPERS
# ============================================================

def anime_title(anime):

    title = anime.get("title") or {}

    return (
        title.get("english")
        or title.get("romaji")
        or title.get("native")
        or "Unknown Anime"
    )


def native_title(anime):

    title = anime.get("title") or {}

    return (
        title.get("native")
        or title.get("romaji")
        or "N/A"
    )


def cover_image(anime):

    image = anime.get("coverImage") or {}

    return (
        image.get("extraLarge")
        or image.get("large")
        or image.get("medium")
    )


def rating(anime):

    score = anime.get("averageScore")

    if not score:
        return "N/A"

    return f"{score / 10:.1f}/10"


def vote_count(anime):

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
            pass


    if total >= 1_000_000:

        return f"{total / 1_000_000:.1f}M"

    if total >= 1_000:

        return f"{total / 1_000:.1f}K"

    return str(total)


def popularity(anime):

    value = anime.get("popularity")

    if not value:
        return "N/A"

    if value >= 1_000_000:

        return f"{value / 1_000_000:.1f}M"

    if value >= 1_000:

        return f"{value / 1_000:.1f}K"

    return str(value)


def favourites(anime):

    value = anime.get("favourites")

    if not value:
        return "N/A"

    if value >= 1_000_000:

        return f"{value / 1_000_000:.1f}M"

    if value >= 1_000:

        return f"{value / 1_000:.1f}K"

    return str(value)


def status_text(anime):

    status = anime.get("status")

    if not status:
        return "N/A"

    return str(status).replace(
        "_",
        " "
    ).title()


def format_date(date):

    if not date:
        return "N/A"

    year = date.get("year")
    month = date.get("month")
    day = date.get("day")

    if not year:
        return "N/A"

    if month and day:

        return (
            f"{day:02d}/"
            f"{month:02d}/"
            f"{year}"
        )

    if month:

        return (
            f"{month:02d}/"
            f"{year}"
        )

    return str(year)


def format_season(anime):

    season = anime.get("season")
    year = anime.get("seasonYear")

    if not season and not year:

        return "N/A"

    if season and year:

        return (
            f"{str(season).title()} "
            f"{year}"
        )

    return str(year or season)


def format_genres(anime):

    genres = anime.get("genres") or []

    if not genres:
        return "N/A"

    return " • ".join(
        escape(str(x))
        for x in genres[:8]
    )


def format_studios(anime):

    studios = (
        anime
        .get("studios", {})
        .get("nodes", [])
    )

    names = []

    for studio in studios[:6]:

        name = studio.get("name")

        if name:
            names.append(
                escape(name)
            )

    return (
        ", ".join(names)
        if names
        else "N/A"
    )


def format_source(anime):

    source = anime.get("source")

    if not source:
        return "N/A"

    return str(
        source
    ).replace(
        "_",
        " "
    ).title()


def format_airing(anime):

    next_episode = anime.get(
        "nextAiringEpisode"
    )

    if not next_episode:

        return None

    episode = next_episode.get(
        "episode"
    )

    timestamp = next_episode.get(
        "airingAt"
    )

    if not timestamp:

        return (
            f"Episode {episode}"
            if episode
            else None
        )

    try:

        dt = datetime.fromtimestamp(
            int(timestamp),
            tz=IST
        )

        return {
            "episode": episode,
            "datetime": dt
        }

    except Exception:

        return None


def trailer_url(anime):

    trailer = anime.get(
        "trailer"
    )

    if not trailer:
        return None

    site = trailer.get("site")
    trailer_id = trailer.get("id")

    if site == "youtube" and trailer_id:

        return (
            "https://www.youtube.com/watch?v="
            f"{trailer_id}"
        )

    if site == "dailymotion" and trailer_id:

        return (
            "https://www.dailymotion.com/video/"
            f"{trailer_id}"
        )

    return None


# ============================================================
# ANILIST DETAILS QUERY
# ============================================================

DETAIL_QUERY = """
query ($search: String!) {

    Media(
        search: $search
        type: ANIME
    ) {

        id

        title {
            romaji
            english
            native
        }

        description(
            asHtml: false
        )

        coverImage {
            extraLarge
            large
            medium
        }

        bannerImage

        averageScore
        meanScore
        popularity
        favourites

        episodes
        duration

        status
        format
        source

        genres

        season
        seasonYear

        startDate {
            year
            month
            day
        }

        endDate {
            year
            month
            day
        }

        siteUrl

        trailer {
            id
            site
            thumbnail
        }

        studios {
            nodes {
                name
            }
        }

        nextAiringEpisode {
            episode
            airingAt
        }

        relations {

            edges {

                relationType

                node {

                    id

                    type

                    format

                    title {
                        romaji
                        english
                        native
                    }

                    status

                    startDate {
                        year
                        month
                        day
                    }

                    season

                    seasonYear

                    siteUrl

                    coverImage {
                        extraLarge
                        large
                        medium
                    }
                }
            }
        }

        stats {

            scoreDistribution {
                score
                amount
            }
        }
    }
}
"""


# ============================================================
# SEARCH ANIME
# ============================================================

async def search_anime(name):

    data = await anilist_request(
        DETAIL_QUERY,
        {
            "search": name
        }
    )

    if not data:
        return None

    return data.get("Media")


# ============================================================
# FIND NEXT SEASON / SEQUEL
# ============================================================

def find_next_season(anime):

    relations = (
        anime
        .get("relations", {})
        .get("edges", [])
    )

    candidates = []

    for edge in relations:

        relation_type = edge.get(
            "relationType"
        )

        node = edge.get(
            "node"
        )

        if not node:
            continue

        if relation_type not in (
            "SEQUEL",
            "PREQUEL"
        ):
            continue

        if relation_type == "SEQUEL":

            candidates.append(
                node
            )


    if not candidates:
        return None


    # Prefer the earliest announced
    # upcoming sequel.

    candidates.sort(
        key=lambda x: (
            x.get("seasonYear") or 9999,
            x.get("startDate", {}).get("month") or 99,
            x.get("startDate", {}).get("day") or 99
        )
    )


    return candidates[0]


# ============================================================
# DETAILS CAPTION
# ============================================================

def build_anime_caption(anime):

    title = escape(
        anime_title(anime)
    )

    native = escape(
        native_title(anime)
    )

    score = rating(anime)

    votes = vote_count(anime)

    pop = popularity(anime)

    fav = favourites(anime)

    episodes = (
        anime.get("episodes")
        or "Unknown"
    )

    duration = (
        anime.get("duration")
        or "Unknown"
    )

    status = escape(
        status_text(anime)
    )

    format_name = escape(
        str(
            anime.get("format")
            or "N/A"
        ).replace(
            "_",
            " "
        ).title()
    )

    source = escape(
        format_source(anime)
    )

    season = escape(
        format_season(anime)
    )

    studios = format_studios(
        anime
    )

    genres = format_genres(
        anime
    )

    start_date = escape(
        format_date(
            anime.get("startDate")
        )
    )

    end_date = escape(
        format_date(
            anime.get("endDate")
        )
    )


    # --------------------------------------------------------
    # NEXT EPISODE
    # --------------------------------------------------------

    airing = format_airing(
        anime
    )


    if airing:

        next_episode = (
            f"Episode {airing['episode']}"
        )

        airing_time = (
            airing["datetime"]
            .strftime(
                "%d %b %Y, %I:%M %p IST"
            )
        )

    else:

        next_episode = (
            "No upcoming episode"
        )

        airing_time = "N/A"


    # --------------------------------------------------------
    # NEXT SEASON
    # --------------------------------------------------------

    sequel = find_next_season(
        anime
    )


    if sequel:

        sequel_title = escape(
            anime_title(sequel)
        )

        sequel_date = escape(
            format_date(
                sequel.get(
                    "startDate"
                )
            )
        )

        sequel_status = status_text(
            sequel
        )

        if sequel.get("seasonYear"):

            sequel_season = (
                f"{str(sequel.get('season') or '').title()} "
                f"{sequel.get('seasonYear')}"
            ).strip()

        else:

            sequel_season = "Not announced"


        next_season_text = (
            f"{sequel_title}\n"
            f"📅 {sequel_season}\n"
            f"🗓 Air Date: {sequel_date}\n"
            f"📡 Status: {escape(sequel_status)}"
        )

    else:

        next_season_text = (
            "No confirmed sequel/next season found."
        )


    # --------------------------------------------------------
    # SYNOPSIS
    # --------------------------------------------------------

    description = (
        anime.get("description")
        or "No synopsis available."
    )


    # Remove excessive whitespace.

    description = (
        description
        .replace(
            "\r",
            ""
        )
        .strip()
    )


    # Telegram media caption safety.
    # Keep the complete message comfortably
    # below Telegram's 1024-character media
    # caption limit.

    fixed_part = (

        "🎬 <b>Aɴɪᴍᴇ Iɴғᴏ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"🏷 <b>Title:</b> {title}\n"
        f"🇯🇵 <b>Japanese:</b> {native}\n"
        f"🎞 <b>Format:</b> {format_name}\n"
        f"📡 <b>Status:</b> {status}\n\n"

        f"⭐ <b>Rating:</b> {score}\n"
        f"👥 <b>Votes:</b> {votes}\n"
        f"🔥 <b>Popularity:</b> {pop}\n"
        f"❤️ <b>Favourites:</b> {fav}\n\n"

        f"📺 <b>Episodes:</b> {episodes}\n"
        f"⏱ <b>Duration:</b> {duration} min\n"
        f"📅 <b>Season:</b> {season}\n\n"

        f"🏢 <b>Studios:</b> {studios}\n"
        f"📚 <b>Source:</b> {source}\n"
        f"🏷 <b>Genres:</b> {genres}\n\n"

        f"🗓 <b>Started:</b> {start_date}\n"
        f"🗓 <b>Ended:</b> {end_date}\n\n"

        "⏭ <b>Nᴇxᴛ Eᴘɪsᴏᴅᴇ</b>\n"
        f"📺 {escape(next_episode)}\n"
        f"⏰ {escape(airing_time)}\n\n"

        "🔮 <b>Nᴇxᴛ Sᴇᴀsᴏɴ</b>\n"
        f"{next_season_text}\n\n"

        "📝 <b>Sʏɴᴏᴘsɪs</b>\n"
    )


    footer = (
        "\n\n━━━━━━━━━━━━━━━━━━\n"
        "✦ <b>Source:</b> AniList"
    )


    # --------------------------------------------------------
    # Escape description
    # --------------------------------------------------------

    safe_description = escape(
        description
    )


    # --------------------------------------------------------
    # Calculate available synopsis size
    # --------------------------------------------------------

    available = (
        1000
        - len(fixed_part)
        - len(footer)
    )


    if available < 100:

        available = 100


    if len(safe_description) > available:

        safe_description = (
            safe_description[
                :available - 3
            ]
            + "..."
        )


    caption = (
        fixed_part
        + safe_description
        + footer
    )


    # Final emergency protection.

    if len(caption) > 1000:

        caption = (
            caption[:997]
            + "..."
        )


    return caption


# ============================================================
# BUTTONS
# ============================================================

def build_anime_buttons(anime):

    rows = []

    row = []

    site_url = anime.get(
        "siteUrl"
    )

    trailer = trailer_url(
        anime
    )


    if site_url:

        row.append(
            InlineKeyboardButton(
                "📖 AniList",
                url=site_url
            )
        )


    if trailer:

        row.append(
            InlineKeyboardButton(
                "▶️ Trailer",
                url=trailer
            )
        )


    if row:

        rows.append(row)


    # --------------------------------------------------------
    # Next season button
    # --------------------------------------------------------

    sequel = find_next_season(
        anime
    )


    if sequel and sequel.get(
        "siteUrl"
    ):

        rows.append(
            [
                InlineKeyboardButton(
                    "🔮 Next Season",
                    url=sequel["siteUrl"]
                )
            ]
        )


    if not rows:

        return None


    return InlineKeyboardMarkup(
        rows
    )


# ============================================================
# SEND ANIME
# ============================================================

async def send_anime_result(
    client,
    chat_id,
    anime
):

    caption = build_anime_caption(
        anime
    )

    image = cover_image(
        anime
    )

    buttons = build_anime_buttons(
        anime
    )


    if image:

        try:

            await client.send_photo(

                chat_id=chat_id,

                photo=image,

                caption=caption,

                parse_mode=ParseMode.HTML,

                reply_markup=buttons
            )

            return True


        except Exception as e:

            logger.warning(
                "Photo send failed: %s",
                e
            )


    try:

        await client.send_message(

            chat_id=chat_id,

            text=caption,

            parse_mode=ParseMode.HTML,

            reply_markup=buttons,

            disable_web_page_preview=False
        )

        return True


    except Exception as e:

        logger.error(
            "Anime result send failed: %s",
            e
        )

        return False


# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(message):

    if not message.from_user:

        return False

    return (
        message.from_user.id
        in ADMIN_IDS
    )


# ============================================================
# /ANIME
# ============================================================

@Client.on_message(
    filters.command(
        "anime"
    )
)
async def anime_command(
    client,
    message: Message
):

    if len(message.command) < 2:

        await message.reply_text(

            "🔎 <b>Anime Search</b>\n\n"

            "Use:\n"
            "<code>/anime anime name</code>\n\n"

            "Example:\n"
            "<code>/anime One Piece</code>",

            parse_mode=ParseMode.HTML
        )

        return


    query = " ".join(
        message.command[1:]
    ).strip()


    loading = await message.reply_text(

        "🔎 <b>Searching AniList...</b>",

        parse_mode=ParseMode.HTML
    )


    anime = await search_anime(
        query
    )


    if not anime:

        await loading.edit_text(

            "❌ <b>Anime not found.</b>\n\n"

            "Try another title.",

            parse_mode=ParseMode.HTML
        )

        return


    try:

        await loading.delete()

    except Exception:

        pass


    await send_anime_result(

        client,

        message.chat.id,

        anime
    )


# ============================================================
# LIST QUERY
# ============================================================

LIST_QUERY = """
query (
    $sort: [MediaSort]
    $status: MediaStatus
) {

    Page(
        page: 1
        perPage: 10
    ) {

        media(
            type: ANIME
            sort: $sort
            status: $status
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
            popularity
            favourites

            episodes

            status

            genres

            season
            seasonYear

            siteUrl

            trailer {
                id
                site
                thumbnail
            }

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


async def fetch_anime_list(
    sort,
    status=None
):

    data = await anilist_request(

        LIST_QUERY,

        {
            "sort": [sort],
            "status": status
        }
    )


    if not data:

        return []


    return (
        data
        .get("Page", {})
        .get("media", [])
    )


# ============================================================
# LIST CAPTION
# ============================================================

def list_caption(
    anime,
    index,
    heading
):

    title = escape(
        anime_title(anime)
    )

    score = rating(
        anime
    )

    votes = vote_count(
        anime
    )

    episodes = (
        anime.get("episodes")
        or "?"
    )

    status = escape(
        status_text(anime)
    )

    genres = anime.get(
        "genres"
    ) or []


    genre_text = escape(
        " • ".join(
            genres[:5]
        )
    ) or "N/A"


    url = anime.get(
        "siteUrl"
    )


    if url:

        title_html = (
            f'<a href="'
            f'{escape(url, quote=True)}'
            f'">'
            f'<b>{title}</b>'
            f'</a>'
        )

    else:

        title_html = (
            f"<b>{title}</b>"
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


    return (

        f"{rank} <b>{heading}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        f"🎬 {title_html}\n\n"

        f"⭐ <b>Rating:</b> {score}\n"
        f"👥 <b>Votes:</b> {votes}\n"
        f"📺 <b>Episodes:</b> {episodes}\n"
        f"📡 <b>Status:</b> {status}\n"
        f"🏷 <b>Genres:</b> {genre_text}"

    )


async def send_list(
    client,
    message,
    anime_list,
    heading
):

    for index, anime in enumerate(
        anime_list,
        start=1
    ):

        try:

            caption = list_caption(
                anime,
                index,
                heading
            )

            image = cover_image(
                anime
            )

            buttons = build_anime_buttons(
                anime
            )


            if image:

                try:

                    await client.send_photo(

                        chat_id=message.chat.id,

                        photo=image,

                        caption=caption,

                        parse_mode=ParseMode.HTML,

                        reply_markup=buttons
                    )

                except Exception:

                    await client.send_message(

                        chat_id=message.chat.id,

                        text=caption,

                        parse_mode=ParseMode.HTML,

                        reply_markup=buttons
                    )

            else:

                await client.send_message(

                    chat_id=message.chat.id,

                    text=caption,

                    parse_mode=ParseMode.HTML,

                    reply_markup=buttons
                )


            await asyncio.sleep(
                0.6
            )


        except Exception as e:

            logger.warning(
                "List item %s failed: %s",
                index,
                e
            )

            continue


# ============================================================
# /TRENDING
# ============================================================

@Client.on_message(
    filters.command(
        "trending"
    )
)
async def trending_command(
    client,
    message
):

    loading = await message.reply_text(

        "🔥 <b>Fetching trending anime...</b>",

        parse_mode=ParseMode.HTML
    )


    anime_list = await fetch_anime_list(
        "TRENDING_DESC"
    )


    if not anime_list:

        return await loading.edit_text(

            "❌ <b>Unable to fetch trending anime.</b>",

            parse_mode=ParseMode.HTML
        )


    await loading.delete()


    await send_list(

        client,

        message,

        anime_list,

        "🔥 Tʀᴇɴᴅɪɴɢ"
    )


# ============================================================
# /NEW
# ============================================================

@Client.on_message(
    filters.command(
        "new"
    )
)
async def new_command(
    client,
    message
):

    loading = await message.reply_text(

        "🆕 <b>Fetching currently airing anime...</b>",

        parse_mode=ParseMode.HTML
    )


    anime_list = await fetch_anime_list(

        "START_DATE_DESC",

        "RELEASING"
    )


    if not anime_list:

        return await loading.edit_text(

            "❌ <b>Unable to fetch new anime.</b>",

            parse_mode=ParseMode.HTML
        )


    await loading.delete()


    await send_list(

        client,

        message,

        anime_list,

        "🆕 Nᴇᴡ Aɴɪᴍᴇ"
    )


# ============================================================
# /TOP
# ============================================================

@Client.on_message(
    filters.command(
        "top"
    )
)
async def top_command(
    client,
    message
):

    loading = await message.reply_text(

        "🏆 <b>Fetching highest-rated anime...</b>",

        parse_mode=ParseMode.HTML
    )


    anime_list = await fetch_anime_list(
        "SCORE_DESC"
    )


    if not anime_list:

        return await loading.edit_text(

            "❌ <b>Unable to fetch top anime.</b>",

            parse_mode=ParseMode.HTML
        )


    await loading.delete()


    await send_list(

        client,

        message,

        anime_list,

        "🏆 Hɪɢʜᴇsᴛ Rᴀᴛᴇᴅ"
    )


# ============================================================
# /RANDOM
# ============================================================

@Client.on_message(
    filters.command(
        "random"
    )
)
async def random_command(
    client,
    message
):

    loading = await message.reply_text(

        "🎲 <b>Choosing random anime...</b>",

        parse_mode=ParseMode.HTML
    )


    anime_list = await fetch_anime_list(
        "POPULARITY_DESC"
    )


    if not anime_list:

        return await loading.edit_text(

            "❌ <b>Unable to fetch anime.</b>",

            parse_mode=ParseMode.HTML
        )


    anime = random.choice(
        anime_list
    )


    await loading.delete()


    await send_anime_result(

        client,

        message.chat.id,

        anime
    )


# ============================================================
# /WEEKLY
# ============================================================

@Client.on_message(
    filters.command(
        [
            "weekly",
            "weeklytest"
        ]
    )
)
async def weekly_command(
    client,
    message
):

    if not is_admin(message):

        await message.reply_text(

            "⛔ <b>Admin only.</b>",

            parse_mode=ParseMode.HTML
        )

        return


    loading = await message.reply_text(

        "🏆 <b>Generating Weekly Top 16...</b>",

        parse_mode=ParseMode.HTML
    )


    try:

        await send_weekly_anime(
            client
        )


        await loading.edit_text(

            "✅ <b>Weekly Top 16 job completed.</b>",

            parse_mode=ParseMode.HTML
        )


    except Exception as e:

        logger.exception(
            "Manual weekly failed"
        )


        await loading.edit_text(

            "❌ <b>Weekly job failed.</b>\n\n"
            f"<code>{escape(str(e)[:800])}</code>",

            parse_mode=ParseMode.HTML
        )


# ============================================================
# /PREVIEW
# ============================================================

@Client.on_message(
    filters.command(
        "preview"
    )
)
async def preview_command(
    client,
    message
):

    if not is_admin(message):

        return await message.reply_text(

            "⛔ <b>Admin only.</b>",

            parse_mode=ParseMode.HTML
        )


    loading = await message.reply_text(

        "👀 <b>Preparing Weekly Top 16 preview...</b>",

        parse_mode=ParseMode.HTML
    )


    try:

        anime_list = await fetch_top_anime()


        if not anime_list:

            return await loading.edit_text(

                "❌ <b>No anime found.</b>",

                parse_mode=ParseMode.HTML
            )


        await loading.delete()


        await send_list(

            client,

            message,

            anime_list[:16],

            "👀 Wᴇᴇᴋʟʏ Pʀᴇᴠɪᴇᴡ"
        )


    except Exception as e:

        logger.exception(
            "Preview failed"
        )


        await loading.edit_text(

            "❌ <b>Preview failed.</b>\n\n"
            f"<code>{escape(str(e)[:800])}</code>",

            parse_mode=ParseMode.HTML
        )


# ============================================================
# /SETWEEKLY
# ============================================================

@Client.on_message(
    filters.command(
        "setweekly"
    )
)
async def setweekly_command(
    client,
    message
):

    if not is_admin(message):

        return await message.reply_text(

            "⛔ <b>Admin only.</b>",

            parse_mode=ParseMode.HTML
        )


    if len(message.command) < 2:

        return await message.reply_text(

            "⚙️ <b>Usage:</b>\n\n"
            "<code>/setweekly 20:00</code>\n\n"
            "Time is <b>IST</b>.\n"
            "The job runs every Sunday.",

            parse_mode=ParseMode.HTML
        )


    time_text = (
        message.command[1]
        .strip()
    )


    try:

        hour_text, minute_text = (
            time_text.split(":")
        )

        hour = int(
            hour_text
        )

        minute = int(
            minute_text
        )


        if not (
            0 <= hour <= 23
            and
            0 <= minute <= 59
        ):

            raise ValueError


    except Exception:

        return await message.reply_text(

            "❌ <b>Invalid time.</b>\n\n"
            "Example:\n"
            "<code>/setweekly 20:00</code>",

            parse_mode=ParseMode.HTML
        )


    if not client.scheduler:

        return await message.reply_text(

            "❌ <b>Scheduler is not running.</b>",

            parse_mode=ParseMode.HTML
        )


    try:

        client.scheduler.add_job(

            send_weekly_anime,

            "cron",

            day_of_week="sun",

            hour=hour,

            minute=minute,

            second=0,

            args=[client],

            id="weekly_top16_anime",

            replace_existing=True,

            max_instances=1,

            coalesce=True
        )


        await message.reply_text(

            "✅ <b>Weekly schedule updated!</b>\n\n"

            "📅 <b>Day:</b> Sunday\n"
            f"⏰ <b>Time:</b> "
            f"{hour:02d}:{minute:02d} IST",

            parse_mode=ParseMode.HTML
        )


        logger.info(
            "Weekly schedule changed: Sunday %02d:%02d IST",
            hour,
            minute
        )


    except Exception as e:

        logger.exception(
            "Unable to update weekly schedule"
        )


        await message.reply_text(

            "❌ <b>Failed to update schedule.</b>\n\n"
            f"<code>{escape(str(e)[:800])}</code>",

            parse_mode=ParseMode.HTML
        )


# ============================================================
# /WEEKLYINFO
# ============================================================

@Client.on_message(
    filters.command(
        "weeklyinfo"
    )
)
async def weeklyinfo_command(
    client,
    message
):

    if not is_admin(message):

        return await message.reply_text(

            "⛔ <b>Admin only.</b>",

            parse_mode=ParseMode.HTML
        )


    try:

        job = client.scheduler.get_job(
            "weekly_top16_anime"
        )


        if not job:

            return await message.reply_text(

                "❌ <b>Weekly job is not configured.</b>",

                parse_mode=ParseMode.HTML
            )


        next_run = job.next_run_time


        if next_run:

            next_text = (
                next_run
                .astimezone(IST)
                .strftime(
                    "%d %B %Y, %I:%M %p IST"
                )
            )

        else:

            next_text = "N/A"


        await message.reply_text(

            "🏆 <b>Wᴇᴇᴋʟʏ Tᴏᴘ 𝟷𝟼</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "📅 <b>Day:</b> Sunday\n"
            f"⏰ <b>Next Run:</b> {next_text}",

            parse_mode=ParseMode.HTML
        )


    except Exception as e:

        await message.reply_text(

            "❌ <b>Unable to read schedule.</b>\n\n"
            f"<code>{escape(str(e)[:800])}</code>",

            parse_mode=ParseMode.HTML
        )


# ============================================================
# BOT
# ============================================================

class AnimeBot(Client):

    def __init__(self):

        super().__init__(

            # IMPORTANT:
            # Fixed session name.
            # Do NOT generate a random session name
            # on every Render restart.

            name="anime_session",

            api_id=API_ID,

            api_hash=API_HASH,

            bot_token=BOT_TOKEN,

            plugins=dict(
                root="plugins"
            )
        )


        self.web_runner = None

        self.scheduler = None


    # ========================================================
    # START
    # ========================================================

    async def start(self):

        # ----------------------------------------------------
        # TELEGRAM FLOODWAIT PROTECTION
        # ----------------------------------------------------

        max_attempts = 3

        for attempt in range(
            1,
            max_attempts + 1
        ):

            try:

                await super().start()

                break


            except FloodWait as e:

                wait_seconds = int(
                    getattr(
                        e,
                        "value",
                        60
                    )
                )


                logger.error(

                    "Telegram FloodWait during startup: "
                    "%s seconds remaining "
                    "(attempt %s/%s)",

                    wait_seconds,

                    attempt,

                    max_attempts
                )


                if attempt >= max_attempts:

                    logger.error(

                        "Startup FloodWait is still active. "
                        "Stopping instead of repeatedly "
                        "authorizing the bot."
                    )

                    raise


                # Add a small safety buffer.

                wait_seconds += 10


                logger.info(

                    "Waiting %s seconds before "
                    "retrying Telegram authorization...",

                    wait_seconds
                )


                await asyncio.sleep(
                    wait_seconds
                )


        logger.info(
            "✅ Pyrogram Client Started"
        )


        # ----------------------------------------------------
        # SCHEDULER
        # ----------------------------------------------------

        self.scheduler = AsyncIOScheduler(
            timezone=IST
        )


        # ----------------------------------------------------
        # RSS NEWS JOB
        # ----------------------------------------------------

        self.scheduler.add_job(

            broadcast_news,

            "interval",

            minutes=UPDATE_INTERVAL,

            args=[self],

            id="broadcast_job",

            replace_existing=True,

            max_instances=1,

            coalesce=True
        )


        # ----------------------------------------------------
        # WEEKLY TOP 16
        # ----------------------------------------------------

        self.scheduler.add_job(

            send_weekly_anime,

            "cron",

            day_of_week="sun",

            hour=20,

            minute=0,

            second=0,

            args=[self],

            id="weekly_top16_anime",

            replace_existing=True,

            max_instances=1,

            coalesce=True
        )


        # ----------------------------------------------------
        # START SCHEDULER
        # ----------------------------------------------------

        self.scheduler.start()


        logger.info(
            "✅ RSS scheduler started — "
            "every %s minute(s)",
            UPDATE_INTERVAL
        )


        logger.info(
            "🏆 Weekly Top 16 scheduled — "
            "Sunday 8:00 PM IST"
        )


        # ----------------------------------------------------
        # FIRST RSS CHECK
        # ----------------------------------------------------

        asyncio.create_task(
            self.safe_broadcast()
        )


        logger.info(
            "✅ First RSS broadcast task launched"
        )


        # ----------------------------------------------------
        # RENDER HEALTH SERVER
        # ----------------------------------------------------

        async def health(request):

            return web.Response(

                text=(
                    "Anime News Bot is running! ✅"
                ),

                status=200
            )


        app = web.Application()


        app.router.add_get(
            "/",
            health
        )


        app.router.add_get(
            "/health",
            health
        )


        self.web_runner = web.AppRunner(
            app
        )


        await self.web_runner.setup()


        site = web.TCPSite(

            self.web_runner,

            "0.0.0.0",

            PORT
        )


        await site.start()


        logger.info(
            "✅ Web server running on "
            "0.0.0.0:%s",
            PORT
        )


    # ========================================================
    # SAFE RSS
    # ========================================================

    async def safe_broadcast(self):

        try:

            await broadcast_news(
                self
            )

        except Exception as e:

            logger.exception(
                "Initial RSS broadcast failed: %s",
                e
            )


    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
        *args
    ):

        # ----------------------------------------------------
        # SCHEDULER
        # ----------------------------------------------------

        if self.scheduler:

            try:

                self.scheduler.shutdown(
                    wait=False
                )

                logger.info(
                    "🛑 Scheduler stopped"
                )

            except Exception as e:

                logger.error(
                    "Scheduler shutdown error: %s",
                    e
                )


        # ----------------------------------------------------
        # WEB SERVER
        # ----------------------------------------------------

        if self.web_runner:

            try:

                await self.web_runner.cleanup()

                logger.info(
                    "🛑 Web server stopped"
                )

            except Exception as e:

                logger.error(
                    "Web server shutdown error: %s",
                    e
                )


        # ----------------------------------------------------
        # PYROGRAM
        # ----------------------------------------------------

        try:

            await super().stop()

        except Exception as e:

            logger.error(
                "Pyrogram shutdown error: %s",
                e
            )


        logger.info(
            "🛑 Bot Stopped"
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    logger.info(
        "🚀 Starting Anime News Bot..."
    )

    AnimeBot().run()