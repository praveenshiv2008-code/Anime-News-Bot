import logging
from datetime import datetime

import httpx
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.db import db
from config import LOG_CHANNEL

logger = logging.getLogger("WeeklyAnime")

ANILIST_URL = "https://graphql.anilist.co"

TOP_COUNT = 16


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


def resolve_chat_id(channel):
    """
    Convert numeric channel IDs to int.
    Keep @username strings as strings.
    """
    if isinstance(channel, str):
        return int(channel) if channel.lstrip("-").isdigit() else channel

    return int(channel)


def get_anime_title(anime):
    """
    Prefer English title, then Romaji, then Native.
    """
    title = anime.get("title") or {}

    return (
        title.get("english")
        or title.get("romaji")
        or title.get("native")
        or "Unknown Anime"
    )


def get_status(anime):
    status = anime.get("status")

    status_map = {
        "RELEASING": "Airing",
        "FINISHED": "Finished",
        "NOT_YET_RELEASED": "Not Yet Released",
        "CANCELLED": "Cancelled",
        "HIATUS": "Hiatus",
    }

    return status_map.get(status, status or "Unknown")


def format_score(score):
    if score is None:
        return "N/A"

    return f"{score / 10:.1f}/10"


async def fetch_top_anime():
    """
    Fetch currently airing anime from AniList
    and return the highest-rated 16.
    """

    try:
        async with httpx.AsyncClient(timeout=30) as client:
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

        if "errors" in data:
            logger.error(
                "[WeeklyAnime] AniList API error: %s",
                data["errors"]
            )
            return []

        media = data.get("data", {}).get("Page", {}).get("media", [])

        if not media:
            logger.warning("[WeeklyAnime] AniList returned no anime.")
            return []

        # Remove anime without a score.
        media = [
            anime
            for anime in media
            if anime.get("averageScore") is not None
        ]

        # Sort highest score first.
        media.sort(
            key=lambda x: x.get("averageScore", 0),
            reverse=True
        )

        return media[:TOP_COUNT]

    except Exception as e:
        logger.exception(
            "[WeeklyAnime] Failed to fetch AniList data: %s",
            e
        )
        return []


def build_caption(anime_list):
    """
    Build Telegram HTML caption.
    """

    now = datetime.now()

    lines = [
        "<blockquote><b>🏆 Wᴇᴇᴋʟʏ Tᴏᴘ 𝟷𝟼 Aɴɪᴍᴇ</b></blockquote>",
        "",
        f"<b>📅 Wᴇᴇᴋ:</b> {now.strftime('%d %B %Y')}",
        "",
    ]

    medals = {
        1: "🥇",
        2: "🥈",
        3: "🥉",
    }

    for index, anime in enumerate(anime_list, start=1):

        title = get_anime_title(anime)
        score = format_score(anime.get("averageScore"))
        episodes = anime.get("episodes") or "?"
        status = get_status(anime)

        genres = anime.get("genres") or []

        if genres:
            genre_text = ", ".join(genres[:3])
        else:
            genre_text = "N/A"

        marker = medals.get(index, f"#{index}")

        site_url = anime.get("siteUrl")

        if site_url:
            title_text = (
                f'<a href="{site_url}"><b>{title}</b></a>'
            )
        else:
            title_text = f"<b>{title}</b>"

        lines.extend(
            [
                f"{marker} {title_text}",
                f"   ⭐ <b>Rᴀᴛɪɴɢ:</b> {score}",
                f"   🎬 <b>Eᴘɪsᴏᴅᴇs:</b> {episodes}",
                f"   📡 <b>Sᴛᴀᴛᴜs:</b> {status}",
                f"   🏷 <b>Gᴇɴʀᴇs:</b> {genre_text}",
                "",
            ]
        )

    lines.extend(
        [
            "<blockquote>",
            "✦ Rᴀɴᴋɪɴɢs ᴜᴘᴅᴀᴛᴇᴅ ᴇᴠᴇʀʏ Sᴜɴᴅᴀʏ",
            "✦ Sᴏᴜʀᴄᴇ: AɴɪLɪsᴛ",
            "</blockquote>",
        ]
    )

    return "\n".join(lines)


async def send_weekly_anime(app: Client):
    """
    Send the Weekly Top 16 anime list
    to all configured target channels.
    """

    logger.info(
        "[WeeklyAnime] Starting weekly Top %s job...",
        TOP_COUNT
    )

    anime_list = await fetch_top_anime()

    if not anime_list:
        logger.warning(
            "[WeeklyAnime] No anime available. Job cancelled."
        )
        return

    target_channels = await db.get_all_channels()

    if not target_channels:
        logger.warning(
            "[WeeklyAnime] No target channels configured."
        )
        return

    caption = build_caption(anime_list)

    sent_count = 0

    for channel in target_channels:

        chat_id = resolve_chat_id(channel)

        try:
            # Send the first anime's poster.
            # Telegram will display the full Top 16 list as caption.
            first_anime = anime_list[0]

            image_url = (
                first_anime
                .get("coverImage", {})
                .get("large")
            )

            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✦ AɴɪLɪsᴛ",
                            url="https://anilist.co"
                        )
                    ]
                ]
            )

            if image_url:
                await app.send_photo(
                    chat_id=chat_id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
            else:
                await app.send_message(
                    chat_id=chat_id,
                    text=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    disable_web_page_preview=True
                )

            sent_count += 1

            logger.info(
                "[WeeklyAnime] Successfully sent Top %s to %s",
                TOP_COUNT,
                chat_id
            )

        except Exception as e:

            logger.exception(
                "[WeeklyAnime] Failed to send to %s: %s",
                chat_id,
                e
            )

    # Optional log channel.
    if LOG_CHANNEL:

        try:
            log_id = resolve_chat_id(LOG_CHANNEL)

            log_text = (
                "<b>📊 WEEKLY ANIME LOG</b>\n\n"
                f"Successfully sent to: <code>{sent_count}</code> "
                f"channel(s).\n\n"
                f"Top anime: <b>{get_anime_title(anime_list[0])}</b>\n"
                f"Rating: <b>{format_score(anime_list[0].get('averageScore'))}</b>"
            )

            await app.send_message(
                chat_id=log_id,
                text=log_text,
                parse_mode=ParseMode.HTML
            )

        except Exception as e:
            logger.warning(
                "[WeeklyAnime] Could not send log: %s",
                e
            )

    logger.info(
        "[WeeklyAnime] Weekly job completed. Sent to %s channel(s).",
        sent_count
    )