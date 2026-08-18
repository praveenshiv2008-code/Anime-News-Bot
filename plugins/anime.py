import asyncio
import logging
import random
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import httpx

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import OWNER_ID, ADMIN_ID
from helper.weekly_anime import (
    fetch_top_anime,
    send_weekly_anime,
    get_anime_title,
    get_vote_count,
    format_votes,
    format_score,
    get_cover_image,
    get_status,
)


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("AnimeFeatures")


# ============================================================
# CONFIG
# ============================================================

ANILIST_URL = "https://graphql.anilist.co"

IST = ZoneInfo("Asia/Kolkata")

REQUEST_TIMEOUT = 30

ADMIN_IDS = {
    int(OWNER_ID),
    int(ADMIN_ID),
}


# ============================================================
# ANILIST CLIENT
# ============================================================

async def anilist_request(
    query,
    variables=None
):

    try:

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT
        ) as client:

            response = await client.post(

                ANILIST_URL,

                json={
                    "query": query,
                    "variables": variables or {},
                },

                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Anime-News-Bot",
                },
            )


            response.raise_for_status()

            data = response.json()


        if data.get("errors"):

            logger.warning(
                "[AniList] GraphQL error: %s",
                data.get("errors")
            )

            return None


        return data.get("data")


    except Exception as e:

        logger.error(
            "[AniList] Request failed: %s",
            e
        )

        return None


# ============================================================
# HELPERS
# ============================================================

def is_admin(message: Message):

    return bool(
        message.from_user
        and message.from_user.id in ADMIN_IDS
    )


def get_title(anime):

    title = anime.get("title") or {}

    return (
        title.get("english")
        or title.get("romaji")
        or title.get("native")
        or "Unknown Anime"
    )


def get_votes(anime):

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

    return total


def get_image(anime):

    cover = anime.get(
        "coverImage"
    ) or {}

    return (
        cover.get("extraLarge")
        or cover.get("large")
        or cover.get("medium")
    )


def get_studios(anime):

    studios = (
        anime
        .get("studios", {})
        .get("nodes", [])
    )

    names = []

    for studio in studios[:5]:

        name = studio.get("name")

        if name:
            names.append(name)

    return (
        ", ".join(names)
        if names
        else "N/A"
    )


def format_date(date_data):

    if not date_data:

        return "N/A"

    year = date_data.get("year")
    month = date_data.get("month")
    day = date_data.get("day")

    if not year:

        return "N/A"

    if month and day:

        return f"{day:02d}/{month:02d}/{year}"

    if month:

        return f"{month:02d}/{year}"

    return str(year)


def format_airing(anime):

    airing = anime.get(
        "nextAiringEpisode"
    )

    if not airing:

        return "N/A"

    episode = airing.get(
        "episode"
    )

    timestamp = airing.get(
        "airingAt"
    )

    if not timestamp:

        return (
            f"Episode {episode}"
            if episode
            else "N/A"
        )

    try:

        dt = datetime.fromtimestamp(
            int(timestamp),
            tz=IST
        )

        return (
            f"Ep {episode} — "
            f"{dt.strftime('%d %b %Y, %I:%M %p')} IST"
        )

    except Exception:

        return (
            f"Episode {episode}"
            if episode
            else "N/A"
        )


def get_trailer(anime):

    trailer = anime.get(
        "trailer"
    )

    if not trailer:

        return None

    site = trailer.get(
        "site"
    )

    trailer_id = trailer.get(
        "id"
    )

    if site == "youtube" and trailer_id:

        return (
            f"https://www.youtube.com/watch?v="
            f"{trailer_id}"
        )

    if site == "dailymotion" and trailer_id:

        return (
            f"https://www.dailymotion.com/video/"
            f"{trailer_id}"
        )

    return None


# ============================================================
# DETAILS QUERY
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

    coverImage {
      extraLarge
      large
      medium
    }

    bannerImage

    description(
      asHtml: false
    )

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

    airingSchedule {
      nodes {
        episode
        airingAt
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

async def search_anime(
    name
):

    data = await anilist_request(
        DETAIL_QUERY,
        {
            "search": name
        }
    )

    if not data:

        return None

    return data.get(
        "Media"
    )


# ============================================================
# TRENDING / NEW / TOP QUERY
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


async def fetch_list(
    sort,
    status=None
):

    data = await anilist_request(

        LIST_QUERY,

        {
            "sort": [sort],

            "status": status,
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
# BUILD SMALL CARD
# ============================================================

def build_card(
    anime,
    index=None,
    heading="ANIME"
):

    title = escape(
        get_title(anime)
    )

    score = format_score(
        anime.get("averageScore")
    )

    votes = format_votes(
        get_votes(anime)
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
        escape(str(x))
        for x in genres[:4]
    ]

    genre_text = (
        ", ".join(genres)
        if genres
        else "N/A"
    )


    prefix = ""

    if index is not None:

        medals = {
            1: "🥇",
            2: "🥈",
            3: "🥉",
        }

        prefix = medals.get(
            index,
            f"🏅 #{index}"
        )


    title_url = anime.get(
        "siteUrl"
    )


    if title_url:

        title_text = (
            f'<a href="'
            f'{escape(title_url, quote=True)}'
            f'">'
            f'<b>{title}</b>'
            f'</a>'
        )

    else:

        title_text = (
            f"<b>{title}</b>"
        )


    return (

        f"{prefix} "
        f"<b>{heading}</b>\n"

        f"━━━━━━━━━━━━━━━━━━\n\n"

        f"🎬 {title_text}\n\n"

        f"⭐ <b>Rᴀᴛɪɴɢ:</b> "
        f"{score}\n"

        f"👥 <b>Vᴏᴛᴇs:</b> "
        f"{votes}\n"

        f"📺 <b>Eᴘɪsᴏᴅᴇs:</b> "
        f"{episodes}\n"

        f"📡 <b>Sᴛᴀᴛᴜs:</b> "
        f"{status}\n"

        f"🏷 <b>Gᴇɴʀᴇs:</b> "
        f"{genre_text}"

    )


# ============================================================
# BUTTONS
# ============================================================

def build_buttons(
    anime
):

    rows = []

    site_url = anime.get(
        "siteUrl"
    )

    trailer_url = get_trailer(
        anime
    )


    first_row = []


    if site_url:

        first_row.append(
            InlineKeyboardButton(
                "📖 AɴɪLɪsᴛ",
                url=site_url
            )
        )


    if trailer_url:

        first_row.append(
            InlineKeyboardButton(
                "▶️ Tʀᴀɪʟᴇʀ",
                url=trailer_url
            )
        )


    if first_row:

        rows.append(
            first_row
        )


    return (
        InlineKeyboardMarkup(rows)
        if rows
        else None
    )


# ============================================================
# SEND ANIME
# ============================================================

async def send_anime(
    client,
    chat_id,
    anime,
    heading="ANIME",
    index=None
):

    if not anime:

        return False


    caption = build_card(
        anime,
        index=index,
        heading=heading
    )


    image = get_image(
        anime
    )


    buttons = build_buttons(
        anime
    )


    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    if image:

        try:

            await client.send_photo(

                chat_id=chat_id,

                photo=image,

                caption=caption,

                parse_mode=ParseMode.HTML,

                reply_markup=buttons,
            )

            return True

        except Exception as e:

            logger.warning(
                "Image send failed: %s",
                e
            )


    # --------------------------------------------------------
    # TEXT FALLBACK
    # --------------------------------------------------------

    try:

        await client.send_message(

            chat_id=chat_id,

            text=caption,

            parse_mode=ParseMode.HTML,

            reply_markup=buttons,

            disable_web_page_preview=False,
        )

        return True


    except Exception as e:

        logger.error(
            "Anime send failed: %s",
            e
        )

        return False


# ============================================================
# FULL DETAILS CAPTION
# ============================================================

def build_details(
    anime
):

    title = escape(
        get_title(anime)
    )

    score = format_score(
        anime.get("averageScore")
    )

    votes = format_votes(
        get_votes(anime)
    )

    episodes = (
        anime.get("episodes")
        or "?"
    )

    duration = (
        anime.get("duration")
        or "?"
    )

    status = escape(
        get_status(anime)
    )

    format_name = escape(
        anime.get("format")
        or "N/A"
    )

    source = escape(
        str(
            anime.get("source")
            or "N/A"
        ).replace("_", " ").title()
    )

    season = anime.get(
        "season"
    )

    season_year = anime.get(
        "seasonYear"
    )

    season_text = (

        f"{str(season).title()} "
        f"{season_year}"

        if season and season_year

        else str(season_year or "N/A")

    )


    studios = escape(
        get_studios(anime)
    )


    genres = anime.get(
        "genres"
    ) or []


    genre_text = escape(
        ", ".join(genres[:6])
        if genres
        else "N/A"
    )


    start_date = format_date(
        anime.get("startDate")
    )

    end_date = format_date(
        anime.get("endDate")
    )


    airing = escape(
        format_airing(anime)
    )


    description = (
        anime.get("description")
        or "No description available."
    )


    description = escape(
        description
    )


    # Telegram caption safety
    if len(description) > 1800:

        description = (
            description[:1797]
            + "..."
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


    return (

        "🎬 <b>Aɴɪᴍᴇ Dᴇᴛᴀɪʟs</b>\n"

        "━━━━━━━━━━━━━━━━━━\n\n"

        f"🎞 {title_line}\n\n"

        f"⭐ <b>Rᴀᴛɪɴɢ:</b> "
        f"{score}\n"

        f"👥 <b>Vᴏᴛᴇs:</b> "
        f"{votes}\n"

        f"📺 <b>Eᴘɪsᴏᴅᴇs:</b> "
        f"{episodes}\n"

        f"⏱ <b>Dᴜʀᴀᴛɪᴏɴ:</b> "
        f"{duration} min\n"

        f"📡 <b>Sᴛᴀᴛᴜs:</b> "
        f"{status}\n"

        f"🎞 <b>Fᴏʀᴍᴀᴛ:</b> "
        f"{format_name}\n"

        f"📚 <b>Sᴏᴜʀᴄᴇ:</b> "
        f"{source}\n"

        f"📅 <b>Sᴇᴀsᴏɴ:</b> "
        f"{escape(str(season_text))}\n"

        f"🏢 <b>Sᴛᴜᴅɪᴏs:</b> "
        f"{studios}\n"

        f"🏷 <b>Gᴇɴʀᴇs:</b> "
        f"{genre_text}\n\n"

        f"🗓 <b>Sᴛᴀʀᴛ:</b> "
        f"{start_date}\n"

        f"🗓 <b>Eɴᴅ:</b> "
        f"{end_date}\n"

        f"⏰ <b>Nᴇxᴛ:</b> "
        f"{airing}\n\n"

        f"📝 <b>Sʏɴᴏᴘsɪs</b>\n"
        f"{description}\n\n"

        "━━━━━━━━━━━━━━━━━━\n"

        "✦ <b>Sᴏᴜʀᴄᴇ:</b> AɴɪLɪsᴛ"

    )


# ============================================================
# /ANIME
# ============================================================

@Client.on_message(
    filters.command("anime")
)
async def anime_search_command(
    client: Client,
    message: Message
):

    if len(message.command) < 2:

        return await message.reply_text(
            "🔍 <b>Usage:</b>\n"
            "<code>/anime Solo Leveling</code>",
            parse_mode=ParseMode.HTML
        )


    query = " ".join(
        message.command[1:]
    ).strip()


    status = await message.reply_text(
        "🔎 <b>Searching AniList...</b>",
        parse_mode=ParseMode.HTML
    )


    anime = await search_anime(
        query
    )


    if not anime:

        return await status.edit_text(
            "❌ <b>Anime not found.</b>",
            parse_mode=ParseMode.HTML
        )


    caption = build_details(
        anime
    )


    image = get_image(
        anime
    )


    buttons = build_buttons(
        anime
    )


    try:

        if image:

            await message.reply_photo(

                photo=image,

                caption=caption,

                parse_mode=ParseMode.HTML,

                reply_markup=buttons,
            )

        else:

            await message.reply_text(

                caption,

                parse_mode=ParseMode.HTML,

                reply_markup=buttons,
            )


        await status.delete()


    except Exception as e:

        logger.error(
            "/anime error: %s",
            e
        )

        await status.edit_text(
            "❌ <b>Unable to send anime details.</b>",
            parse_mode=ParseMode.HTML
        )


# ============================================================
# /TRENDING
# ============================================================

@Client.on_message(
    filters.command("trending")
)
async def trending_command(
    client: Client,
    message: Message
):

    msg = await message.reply_text(
        "🔥 <b>Fetching trending anime...</b>",
        parse_mode=ParseMode.HTML
    )


    anime_list = await fetch_list(
        "TRENDING_DESC"
    )


    if not anime_list:

        return await msg.edit_text(
            "❌ <b>Unable to fetch trending anime.</b>",
            parse_mode=ParseMode.HTML
        )


    await msg.delete()


    for index, anime in enumerate(
        anime_list,
        start=1
    ):

        try:

            await send_anime(

                client,

                message.chat.id,

                anime,

                heading="🔥 Tʀᴇɴᴅɪɴɢ",

                index=index
            )


            await asyncio.sleep(
                0.5
            )


        except Exception as e:

            logger.warning(
                "Trending #%s failed: %s",
                index,
                e
            )


# ============================================================
# /NEW
# ============================================================

@Client.on_message(
    filters.command("new")
)
async def new_anime_command(
    client: Client,
    message: Message
):

    msg = await message.reply_text(
        "🆕 <b>Fetching new anime...</b>",
        parse_mode=ParseMode.HTML
    )


    anime_list = await fetch_list(
        "START_DATE_DESC",
        "RELEASING"
    )


    if not anime_list:

        return await msg.edit_text(
            "❌ <b>Unable to fetch new anime.</b>",
            parse_mode=ParseMode.HTML
        )


    await msg.delete()


    for index, anime in enumerate(
        anime_list,
        start=1
    ):

        try:

            await send_anime(

                client,

                message.chat.id,

                anime,

                heading="🆕 Nᴇᴡ Aɴɪᴍᴇ",

                index=index
            )


            await asyncio.sleep(
                0.5
            )


        except Exception as e:

            logger.warning(
                "New anime #%s failed: %s",
                index,
                e
            )


# ============================================================
# /TOP
# ============================================================

@Client.on_message(
    filters.command("top")
)
async def top_anime_command(
    client: Client,
    message: Message
):

    msg = await message.reply_text(
        "🏆 <b>Fetching highest-rated anime...</b>",
        parse_mode=ParseMode.HTML
    )


    anime_list = await fetch_list(
        "SCORE_DESC"
    )


    if not anime_list:

        return await msg.edit_text(
            "❌ <b>Unable to fetch top anime.</b>",
            parse_mode=ParseMode.HTML
        )


    await msg.delete()


    for index, anime in enumerate(
        anime_list,
        start=1
    ):

        try:

            await send_anime(

                client,

                message.chat.id,

                anime,

                heading="🏆 Hɪɢʜᴇsᴛ Rᴀᴛᴇᴅ",

                index=index
            )


            await asyncio.sleep(
                0.5
            )


        except Exception as e:

            logger.warning(
                "Top anime #%s failed: %s",
                index,
                e
            )


# ============================================================
# /RANDOM
# ============================================================

@Client.on_message(
    filters.command("random")
)
async def random_anime_command(
    client: Client,
    message: Message
):

    msg = await message.reply_text(
        "🎲 <b>Choosing a random anime...</b>",
        parse_mode=ParseMode.HTML
    )


    anime_list = await fetch_list(
        "POPULARITY_DESC"
    )


    if not anime_list:

        return await msg.edit_text(
            "❌ <b>Unable to get anime.</b>",
            parse_mode=ParseMode.HTML
        )


    anime = random.choice(
        anime_list
    )


    await msg.delete()


    await send_anime(

        client,

        message.chat.id,

        anime,

        heading="🎲 Rᴀɴᴅᴏᴍ Aɴɪᴍᴇ"
    )


# ============================================================
# /PREVIEW
# ============================================================

@Client.on_message(
    filters.command("preview")
)
async def preview_command(
    client: Client,
    message: Message
):

    if not is_admin(message):

        return await message.reply_text(
            "⛔ <b>Admin only.</b>",
            parse_mode=ParseMode.HTML
        )


    msg = await message.reply_text(
        "👀 <b>Generating Weekly Top 16 preview...</b>",
        parse_mode=ParseMode.HTML
    )


    anime_list = await fetch_top_anime()


    if not anime_list:

        return await msg.edit_text(
            "❌ <b>Unable to generate preview.</b>",
            parse_mode=ParseMode.HTML
        )


    await msg.delete()


    for index, anime in enumerate(
        anime_list,
        start=1
    ):

        try:

            await send_anime(

                client,

                message.chat.id,

                anime,

                heading="👀 Wᴇᴇᴋʟʏ Pʀᴇᴠɪᴇᴡ",

                index=index
            )


            await asyncio.sleep(
                0.5
            )


        except Exception as e:

            logger.warning(
                "Preview #%s failed: %s",
                index,
                e
            )


# ============================================================
# /SETWEEKLY
# ============================================================

@Client.on_message(
    filters.command("setweekly")
)
async def set_weekly_command(
    client: Client,
    message: Message
):

    if not is_admin(message):

        return await message.reply_text(
            "⛔ <b>Admin only.</b>",
            parse_mode=ParseMode.HTML
        )


    if len(message.command) < 2:

        return await message.reply_text(

            "⚙️ <b>Usage:</b>\n"
            "<code>/setweekly 20:00</code>\n\n"

            "The time is in <b>IST</b>.\n"

            "The weekly job always runs on "
            "<b>Sunday</b>.",

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

            "Use 24-hour IST format:\n"

            "<code>/setweekly 20:00</code>",

            parse_mode=ParseMode.HTML
        )


    if not getattr(
        client,
        "scheduler",
        None
    ):

        return await message.reply_text(

            "❌ <b>Scheduler is not running.</b>",

            parse_mode=ParseMode.HTML
        )


    try:

        # ----------------------------------------------------
        # Remove existing weekly job
        # ----------------------------------------------------

        try:

            client.scheduler.remove_job(
                "weekly_top16_anime"
            )

        except Exception:

            pass


        # ----------------------------------------------------
        # Add new Sunday job
        # ----------------------------------------------------

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

            f"📅 <b>Day:</b> Sunday\n"

            f"⏰ <b>Time:</b> "
            f"{hour:02d}:{minute:02d} IST",

            parse_mode=ParseMode.HTML
        )


        logger.info(

            "Weekly schedule changed to "
            "Sunday %02d:%02d IST",

            hour,

            minute
        )


    except Exception as e:

        logger.exception(
            "Failed to change weekly schedule"
        )


        await message.reply_text(

            "❌ <b>Could not update schedule.</b>\n\n"

            f"<code>{escape(str(e)[:1000])}</code>",

            parse_mode=ParseMode.HTML
        )


# ============================================================
# /WEEKLYINFO
# ============================================================

@Client.on_message(
    filters.command("weeklyinfo")
)
async def weekly_info_command(
    client: Client,
    message: Message
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

            f"📅 <b>Nᴇxᴛ:</b> "
            f"{next_text}\n\n"

            "✦ <b>Day:</b> Sunday",

            parse_mode=ParseMode.HTML
        )


    except Exception as e:

        await message.reply_text(

            "❌ <b>Unable to read schedule.</b>\n\n"

            f"<code>{escape(str(e)[:1000])}</code>",

            parse_mode=ParseMode.HTML
        )