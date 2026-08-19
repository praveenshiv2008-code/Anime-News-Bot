# plugins/img.py

import asyncio
import logging
import os
import re
import time
from html import escape as html_escape
from io import BytesIO
from urllib.parse import quote_plus

import httpx

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InputMediaPhoto


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("AnimeImages")


# ============================================================
# CONFIG
# ============================================================

try:
    from config import TMDB_API_KEY
except Exception:
    TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

try:
    from config import FANART_API_KEY
except Exception:
    FANART_API_KEY = os.getenv("FANART_API_KEY", "")


# ============================================================
# URLS
# ============================================================

TMDB_URL = "https://api.themoviedb.org/3"

KITSU_URL = "https://kitsu.io/api/edge"

FANART_URL = "https://webservice.fanart.tv/v3.2"

ANIMEPLANET_SEARCH = (
    "https://www.anime-planet.com/anime/"
)


# ============================================================
# SETTINGS
# ============================================================

DEFAULT_SOURCE = "tmdb"

DEFAULT_LIMIT = 30

MAX_LIMIT = 100

TELEGRAM_ALBUM_SIZE = 10

REQUEST_TIMEOUT = 30

MIN_IMAGE_SIZE = 3_000

CACHE_TTL = 30 * 60

MAX_CACHE_ITEMS = 500


# ============================================================
# RESULT CACHE
#
# {
#     telegram_message_id: {
#         "created": timestamp,
#         "urls": [...]
#     }
# }
# ============================================================

RESULT_CACHE = {}


# ============================================================
# HTTP
# ============================================================

async def get_json(
    client,
    url,
    params=None,
    headers=None
):

    try:

        response = await client.get(
            url,
            params=params,
            headers=headers
        )

        if response.status_code != 200:

            logger.warning(
                "HTTP %s: %s",
                response.status_code,
                url
            )

            return None

        try:

            return response.json()

        except Exception:

            return None

    except Exception as e:

        logger.warning(
            "HTTP request failed: %s",
            e
        )

        return None


# ============================================================
# UNIQUE URLS
# ============================================================

def unique_urls(
    urls,
    limit
):

    result = []

    seen = set()

    for url in urls:

        if not url:
            continue

        if not isinstance(url, str):
            continue

        url = url.strip()

        if not url:
            continue

        # Remove query string.
        clean = url.split("?", 1)[0].lower()

        if clean in seen:
            continue

        seen.add(clean)

        result.append(url)

        # HARD LIMIT
        if len(result) >= limit:
            break

    return result


# ============================================================
# TMDB SEARCH
# ============================================================

async def tmdb_search(
    client,
    name
):

    if not TMDB_API_KEY:

        logger.warning(
            "TMDB_API_KEY is missing"
        )

        return []

    results = []

    # TV first
    for endpoint, media_type in (
        ("search/tv", "tv"),
        ("search/movie", "movie")
    ):

        data = await get_json(
            client,
            f"{TMDB_URL}/{endpoint}",
            params={
                "api_key": TMDB_API_KEY,
                "query": name,
                "language": "en-US",
                "include_adult": "false",
                "page": 1
            }
        )

        if not data:
            continue

        for item in data.get(
            "results",
            []
        )[:5]:

            item_id = item.get("id")

            if not item_id:
                continue

            title = (
                item.get("name")
                or item.get("title")
                or item.get("original_name")
                or item.get("original_title")
                or name
            )

            results.append({
                "id": item_id,
                "type": media_type,
                "title": title
            })

    return results


# ============================================================
# TMDB IMAGES
# ============================================================

async def tmdb_images(
    client,
    name,
    limit
):

    results = await tmdb_search(
        client,
        name
    )

    if not results:

        return None, []

    urls = []

    selected_title = results[0]["title"]

    for item in results:

        if len(urls) >= limit:
            break

        item_id = item["id"]
        media_type = item["type"]

        artwork = await get_json(
            client,
            f"{TMDB_URL}/{media_type}/"
            f"{item_id}/images",
            params={
                "api_key": TMDB_API_KEY,
                "include_image_language": "en,null"
            }
        )

        if not artwork:
            continue

        # Posters
        for poster in artwork.get(
            "posters",
            []
        ):

            path = poster.get(
                "file_path"
            )

            width = int(
                poster.get(
                    "width",
                    0
                ) or 0
            )

            height = int(
                poster.get(
                    "height",
                    0
                ) or 0
            )

            if (
                path
                and width >= 300
                and height >= 300
            ):

                urls.append(
                    "https://image.tmdb.org"
                    "/t/p/original"
                    + path
                )

            if len(urls) >= limit:
                break

        if len(urls) >= limit:
            break

        # Backdrops
        for backdrop in artwork.get(
            "backdrops",
            []
        ):

            path = backdrop.get(
                "file_path"
            )

            width = int(
                backdrop.get(
                    "width",
                    0
                ) or 0
            )

            height = int(
                backdrop.get(
                    "height",
                    0
                ) or 0
            )

            if (
                path
                and width >= 500
                and height >= 300
            ):

                urls.append(
                    "https://image.tmdb.org"
                    "/t/p/original"
                    + path
                )

            if len(urls) >= limit:
                break

        if len(urls) >= limit:
            break

        # Logos
        for logo in artwork.get(
            "logos",
            []
        ):

            path = logo.get(
                "file_path"
            )

            width = int(
                logo.get(
                    "width",
                    0
                ) or 0
            )

            if (
                path
                and width >= 300
            ):

                urls.append(
                    "https://image.tmdb.org"
                    "/t/p/original"
                    + path
                )

            if len(urls) >= limit:
                break

    urls = unique_urls(
        urls,
        limit
    )

    return selected_title, urls


# ============================================================
# FANART.TV
# ============================================================

async def fanart_images(
    client,
    name,
    limit
):

    if not FANART_API_KEY:

        logger.warning(
            "FANART_API_KEY is missing"
        )

        return None, []

    if not TMDB_API_KEY:

        logger.warning(
            "TMDB_API_KEY is required to resolve "
            "the Fanart movie ID"
        )

        return None, []

    # Fanart movie endpoint accepts TMDB IDs.
    tmdb_results = await get_json(
        client,
        f"{TMDB_URL}/search/movie",
        params={
            "api_key": TMDB_API_KEY,
            "query": name,
            "language": "en-US",
            "include_adult": "false",
            "page": 1
        }
    )

    if not tmdb_results:

        return None, []

    movie_results = tmdb_results.get(
        "results",
        []
    )

    if not movie_results:

        return None, []

    movie = movie_results[0]

    tmdb_id = movie.get(
        "id"
    )

    title = (
        movie.get("title")
        or movie.get("original_title")
        or name
    )

    if not tmdb_id:

        return None, []

    data = await get_json(
        client,
        f"{FANART_URL}/movies/{tmdb_id}",
        params={
            "api_key": FANART_API_KEY
        }
    )

    if not data:

        return title, []

    urls = []

    # Best Fanart categories.
    categories = (
        "moviebackground",
        "movieposter",
        "moviebanner",
        "moviethumb",
        "movieart",
        "hdmovieclearart",
        "hdmovielogo",
        "movielogo",
        "moviedisc"
    )

    for category in categories:

        for image in data.get(
            category,
            []
        ):

            if not isinstance(
                image,
                dict
            ):
                continue

            url = image.get(
                "url"
            )

            if url:
                urls.append(url)

            if len(
                unique_urls(
                    urls,
                    limit
                )
            ) >= limit:

                return (
                    title,
                    unique_urls(
                        urls,
                        limit
                    )
                )

    return (
        title,
        unique_urls(
            urls,
            limit
        )
    )


# ============================================================
# KITSU
# ============================================================

async def kitsu_images(
    client,
    name,
    limit
):

    data = await get_json(
        client,
        f"{KITSU_URL}/anime",
        params={
            "filter[text]": name,
            "page[limit]": 20
        }
    )

    if not data:

        return None, []

    anime_list = data.get(
        "data",
        []
    )

    if not anime_list:

        return None, []

    urls = []

    title = name

    for anime in anime_list:

        attributes = anime.get(
            "attributes",
            {}
        )

        anime_title = (
            attributes.get(
                "canonicalTitle"
            )
            or attributes.get(
                "englishTitle"
            )
            or name
        )

        if title == name:
            title = anime_title

        poster = attributes.get(
            "posterImage",
            {}
        )

        # Original -> large -> medium
        for key in (
            "original",
            "large",
            "medium"
        ):

            url = poster.get(
                key
            )

            if url:

                urls.append(url)

                break

        cover = attributes.get(
            "coverImage",
            {}
        )

        for key in (
            "original",
            "large",
            "small"
        ):

            url = cover.get(
                key
            )

            if url:

                urls.append(url)

                break

        if len(
            unique_urls(
                urls,
                limit
            )
        ) >= limit:

            break

    return (
        title,
        unique_urls(
            urls,
            limit
        )
    )


# ============================================================
# ANIME-PLANET
#
# This source uses the public website search page.
# ============================================================

async def animeplanet_images(
    client,
    name,
    limit
):

    search_url = (
        "https://www.anime-planet.com/anime/all"
        "?name="
        + quote_plus(name)
    )

    try:

        response = await client.get(
            search_url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Linux; Android 10) "
                    "AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36",
                "Accept":
                    "text/html,application/xhtml+xml"
            }
        )

        if response.status_code != 200:

            logger.warning(
                "Anime-Planet HTTP %s",
                response.status_code
            )

            return None, []

        html = response.text

        # Find image URLs from the search page.
        patterns = [
            r'https?://[^"\']+'
            r'\.(?:jpg|jpeg|png|webp)'
            r'(?:\?[^"\']*)?',

            r'data-src=["\']([^"\']+)["\']',

            r'src=["\']([^"\']+)["\']'
        ]

        found = []

        for pattern in patterns:

            matches = re.findall(
                pattern,
                html,
                flags=re.I
            )

            for url in matches:

                if isinstance(
                    url,
                    tuple
                ):
                    url = url[0]

                if not url:
                    continue

                url = url.replace(
                    "&amp;",
                    "&"
                )

                if url.startswith(
                    "//"
                ):

                    url = "https:" + url

                elif url.startswith(
                    "/"
                ):

                    url = (
                        "https://www.anime-planet.com"
                        + url
                    )

                if (
                    "anime-planet.com"
                    not in url
                ):

                    continue

                if not re.search(
                    r"\.(jpg|jpeg|png|webp)",
                    url,
                    re.I
                ):

                    continue

                found.append(url)

        found = unique_urls(
            found,
            limit
        )

        return name, found

    except Exception as e:

        logger.warning(
            "Anime-Planet failed: %s",
            e
        )

        return None, []


# ============================================================
# SOURCE SEARCH
# ============================================================

async def search_source(
    client,
    source,
    name,
    limit
):

    if source == "tmdb":

        return await tmdb_images(
            client,
            name,
            limit
        )

    if source == "fanart":

        return await fanart_images(
            client,
            name,
            limit
        )

    if source == "kitsu":

        return await kitsu_images(
            client,
            name,
            limit
        )

    if source == "animeplanet":

        return await animeplanet_images(
            client,
            name,
            limit
        )

    return None, []


# ============================================================
# COMMAND PARSER
# ============================================================

VALID_SOURCES = {
    "tmdb",
    "fanart",
    "kitsu",
    "animeplanet"
}


def parse_img_command(
    message
):

    command = list(
        message.command or []
    )

    if len(command) < 2:

        return None, None, None

    args = command[1:]

    requested_limit = DEFAULT_LIMIT

    # Last number = requested amount.
    if args and args[-1].isdigit():

        requested_limit = int(
            args[-1]
        )

        args = args[:-1]

    if requested_limit < 1:

        requested_limit = 1

    if requested_limit > MAX_LIMIT:

        requested_limit = MAX_LIMIT

    source = DEFAULT_SOURCE

    # First argument can select source.
    if args:

        possible_source = (
            args[0]
            .lower()
            .strip()
        )

        if possible_source in VALID_SOURCES:

            source = possible_source

            args = args[1:]

    name = " ".join(
        args
    ).strip()

    return (
        source,
        name,
        requested_limit
    )


# ============================================================
# USAGE
# ============================================================

USAGE_TEXT = """
<b>🖼 Image Search</b>

<b>Default:</b>
<code>/img Naruto</code>

<b>TMDB:</b>
<code>/img tmdb Naruto 30</code>

<b>Fanart:</b>
<code>/img fanart Naruto 30</code>

<b>Kitsu:</b>
<code>/img kitsu Naruto 30</code>

<b>Anime-Planet:</b>
<code>/img animeplanet Naruto 30</code>

<b>Download:</b>
Reply to the result with:

<code>1</code>
<code>2 3 4</code>
<code>1,5,8</code>

Only the selected images will be downloaded.
"""


# ============================================================
# CLEAN CACHE
# ============================================================

def cleanup_cache():

    now = time.time()

    expired = []

    for message_id, item in RESULT_CACHE.items():

        if (
            now
            - item["created"]
            > CACHE_TTL
        ):

            expired.append(
                message_id
            )

    for message_id in expired:

        RESULT_CACHE.pop(
            message_id,
            None
        )

    # Prevent unlimited memory usage.
    while len(
        RESULT_CACHE
    ) > MAX_CACHE_ITEMS:

        oldest = next(
            iter(
                RESULT_CACHE
            )
        )

        RESULT_CACHE.pop(
            oldest,
            None
        )


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

async def download_image(
    client,
    url
):

    try:

        response = await client.get(
            url
        )

        if response.status_code != 200:

            return None

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if (
            "image"
            not in content_type
        ):

            return None

        data = response.content

        if len(data) < MIN_IMAGE_SIZE:

            return None

        return data

    except Exception as e:

        logger.warning(
            "Image download failed: %s",
            e
        )

        return None


# ============================================================
# NUMBER PARSER
# ============================================================

def parse_numbers(
    text,
    maximum
):

    if not text:

        return []

    # Accept:
    # 1
    # 1 2 3
    # 1,2,3
    # 1, 2, 3
    # 1  2  3

    numbers = re.findall(
        r"\d+",
        text
    )

    result = []

    seen = set()

    for value in numbers:

        try:

            number = int(value)

        except Exception:

            continue

        if number < 1:
            continue

        if number > maximum:
            continue

        if number in seen:
            continue

        seen.add(number)

        result.append(number)

    return result


# ============================================================
# RESULT MESSAGE
# ============================================================

def build_result_message(
    source,
    query,
    title,
    urls
):

    source_display = {
        "tmdb": "TMDB",
        "fanart": "Fanart.tv",
        "kitsu": "Kitsu",
        "animeplanet": "Anime-Planet"
    }.get(
        source,
        source.title()
    )

    lines = []

    lines.append(
        "<b>🔎 Search Result</b>"
    )

    lines.append(
        f"<b>Query:</b> "
        f"{html_escape(query)}"
    )

    if title:

        lines.append(
            f"<b>Title:</b> "
            f"{html_escape(title)}"
        )

    lines.append(
        f"<b>Source:</b> "
        f"{html_escape(source_display)}"
    )

    lines.append("")

    lines.append(
        f"<b>All Images "
        f"({len(urls)} images):</b>"
    )

    lines.append("")

    for index, url in enumerate(
        urls,
        start=1
    ):

        # Each number points to the
        # actual original image.
        lines.append(
            f'{index}. '
            f'<a href="{html_escape(url, quote=True)}">'
            f'HD Link'
            f'</a>'
        )

    lines.append("")

    lines.append(
        f"<b>Total:</b> {len(urls)} images"
    )

    lines.append("")

    lines.append(
        "💡 <b>Download:</b>\n"
        "Reply to this message with "
        "<code>1</code> or "
        "<code>2 3 4</code>."
    )

    return "\n".join(lines)


# ============================================================
# /IMG
# ============================================================

@Client.on_message(
    filters.command("img")
)
async def image_command(
    client: Client,
    message: Message
):

    cleanup_cache()

    source, anime_name, requested_limit = (
        parse_img_command(
            message
        )
    )

    if not anime_name:

        await message.reply_text(
            USAGE_TEXT,
            parse_mode=ParseMode.HTML
        )

        return

    loading = await message.reply_text(
        "✦ <b>Searching "
        "HD artwork...</b>",
        parse_mode=ParseMode.HTML
    )

    try:

        timeout = httpx.Timeout(
            REQUEST_TIMEOUT,
            connect=15
        )

        limits = httpx.Limits(
            max_connections=15,
            max_keepalive_connections=8
        )

        headers = {
            "User-Agent":
                "Mozilla/5.0 "
                "(Linux; Android 10) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36"
        }

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
            headers=headers
        ) as http:

            # ====================================================
            # IMPORTANT:
            #
            # ONLY ONE SOURCE IS CALLED.
            # ====================================================

            title, urls = await search_source(
                http,
                source,
                anime_name,
                requested_limit
            )

        urls = unique_urls(
            urls,
            requested_limit
        )

        if not urls:

            await loading.edit_text(
                "❌ <b>No artwork found.</b>\n\n"
                f"Source: <code>"
                f"{html_escape(source)}"
                f"</code>\n"
                f"Query: <code>"
                f"{html_escape(anime_name)}"
                f"</code>",
                parse_mode=ParseMode.HTML
            )

            return

        # ========================================================
        # RESULT MESSAGE
        #
        # NO IMAGE IS DOWNLOADED HERE.
        # ========================================================

        result_text = build_result_message(
            source,
            anime_name,
            title or anime_name,
            urls
        )

        await loading.delete()

        result_message = await message.reply_text(
            result_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

        # Save the URLs against this exact result message.
        RESULT_CACHE[
            result_message.id
        ] = {
            "created": time.time(),
            "urls": urls
        }

        cleanup_cache()

        logger.info(
            "/img %s %s -> %s images",
            source,
            anime_name,
            len(urls)
        )

    except Exception:

        logger.exception(
            "Fatal /img error"
        )

        try:

            await loading.edit_text(
                "❌ <b>Image search failed.</b>\n\n"
                "Try again later.",
                parse_mode=ParseMode.HTML
            )

        except Exception:

            pass


# ============================================================
# DOWNLOAD SELECTED IMAGES
# ============================================================

@Client.on_message(
    filters.reply & filters.text
)
async def download_selected_images(
    client: Client,
    message: Message
):

    cleanup_cache()

    replied = message.reply_to_message

    if not replied:

        return

    # Only process replies to our
    # image result messages.
    cached = RESULT_CACHE.get(
        replied.id
    )

    if not cached:

        return

    urls = cached.get(
        "urls",
        []
    )

    if not urls:

        return

    selected_numbers = parse_numbers(
        message.text,
        len(urls)
    )

    if not selected_numbers:

        await message.reply_text(
            f"❌ <b>Invalid image number.</b>\n\n"
            f"Choose between "
            f"<code>1</code> and "
            f"<code>{len(urls)}</code>.",
            parse_mode=ParseMode.HTML
        )

        return

    # ========================================================
    # ONLY SELECTED URLS
    # ========================================================

    selected_urls = []

    for number in selected_numbers:

        index = number - 1

        if (
            0 <= index < len(urls)
        ):

            selected_urls.append(
                (
                    number,
                    urls[index]
                )
            )

    if not selected_urls:

        return

    status = await message.reply_text(
        "✦ <b>Downloading "
        "selected image"
        + (
            "s"
            if len(selected_urls) > 1
            else ""
        )
        + "...</b>",
        parse_mode=ParseMode.HTML
    )

    downloaded = []

    timeout = httpx.Timeout(
        REQUEST_TIMEOUT,
        connect=15
    )

    limits = httpx.Limits(
        max_connections=10,
        max_keepalive_connections=5
    )

    try:

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Linux; Android 10) "
                    "AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36"
            }
        ) as http:

            tasks = []

            for number, url in selected_urls:

                tasks.append(
                    download_image(
                        http,
                        url
                    )
                )

            results = await asyncio.gather(
                *tasks,
                return_exceptions=True
            )

        for position, data in enumerate(
            results
        ):

            if not isinstance(
                data,
                bytes
            ):

                continue

            number = selected_urls[
                position
            ][0]

            downloaded.append(
                (
                    number,
                    data
                )
            )

        if not downloaded:

            await status.edit_text(
                "❌ <b>Selected images "
                "could not be downloaded.</b>",
                parse_mode=ParseMode.HTML
            )

            return

        await status.edit_text(
            "✦ <b>Uploading selected "
            "image"
            + (
                "s"
                if len(downloaded) > 1
                else ""
            )
            + " to Telegram...</b>",
            parse_mode=ParseMode.HTML
        )

        # ========================================================
        # TELEGRAM ALBUMS
        #
        # Maximum 10 images per album.
        # ========================================================

        for start in range(
            0,
            len(downloaded),
            TELEGRAM_ALBUM_SIZE
        ):

            batch = downloaded[
                start:
                start + TELEGRAM_ALBUM_SIZE
            ]

            media = []

            buffers = []

            for number, data in batch:

                buffer = BytesIO(
                    data
                )

                buffer.name = (
                    f"image_{number}.jpg"
                )

                buffer.seek(0)

                buffers.append(
                    buffer
                )

                media.append(
                    InputMediaPhoto(
                        buffer
                    )
                )

            try:

                if len(media) == 1:

                    await client.send_photo(
                        chat_id=message.chat.id,
                        photo=buffers[0]
                    )

                else:

                    await client.send_media_group(
                        chat_id=message.chat.id,
                        media=media
                    )

            except Exception as e:

                logger.warning(
                    "Album upload failed: %s",
                    e
                )

                # Fallback: individual photos.
                for buffer in buffers:

                    try:

                        buffer.seek(0)

                        await client.send_photo(
                            chat_id=message.chat.id,
                            photo=buffer
                        )

                    except Exception as upload_error:

                        logger.warning(
                            "Individual upload failed: %s",
                            upload_error
                        )

            # Small pause between albums.
            await asyncio.sleep(
                0.5
            )

        try:

            await status.delete()

        except Exception:

            pass

    except Exception:

        logger.exception(
            "Selected image download error"
        )

        try:

            await status.edit_text(
                "❌ <b>Download/upload failed.</b>\n\n"
                "Please try again.",
                parse_mode=ParseMode.HTML
            )

        except Exception:

            pass