# plugins/img.py

import asyncio
import logging
import os
import re
from io import BytesIO

import httpx

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InputMediaPhoto


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("AnimeImages")


# ============================================================
# API URLS
# ============================================================

TMDB_URL = "https://api.themoviedb.org/3"
ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"
KITSU_URL = "https://kitsu.io/api/edge"

# Fanart.tv
FANART_URL = "https://webservice.fanart.tv/v3"

# Anime-Planet
ANIMEPLANET_SEARCH = "https://www.anime-planet.com/anime/all"


# ============================================================
# CONFIG
# ============================================================

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
FANART_API_KEY = os.getenv("FANART_API_KEY", "").strip()

# /img has no number anymore.
# This is the maximum number the bot will send.
MAX_IMAGES = 30

# Telegram allows maximum 10 photos per media group.
ALBUM_SIZE = 10

MIN_FILE_SIZE = 5_000

REQUEST_TIMEOUT = 30

DOWNLOAD_CONCURRENCY = 10


# ============================================================
# SOURCE NAMES
# ============================================================

SOURCES = {
    "tmdb",
    "fanart",
    "animeplanet",
    "kitsu",
    "anilist",
    "jikan",
}

# /img = TMDB
DEFAULT_SOURCE = "tmdb"


# ============================================================
# HTTP
# ============================================================

async def get_response(
    client,
    url,
    params=None,
    headers=None,
):

    try:

        response = await client.get(
            url,
            params=params,
            headers=headers,
        )

        return response

    except Exception as e:

        logger.warning(
            "GET failed: %s | %s",
            url,
            e,
        )

        return None


async def get_json(
    client,
    url,
    params=None,
    headers=None,
):

    response = await get_response(
        client,
        url,
        params=params,
        headers=headers,
    )

    if response is None:
        return None

    if response.status_code != 200:

        logger.warning(
            "HTTP %s: %s",
            response.status_code,
            url,
        )

        return None

    try:

        return response.json()

    except Exception:

        return None


# ============================================================
# CLEAN TITLE
# ============================================================

def clean_title(title):

    title = title.strip()

    # Remove unnecessary surrounding quotes.
    title = title.strip("\"'")

    # Remove duplicate spaces.
    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    return title.strip()


# ============================================================
# URL DEDUPLICATION
# ============================================================

def unique_urls(urls):

    result = []
    seen = set()

    for url in urls:

        if not url:
            continue

        url = str(url).strip()

        if not url:
            continue

        # Normalize URL.
        clean = url.split("?")[0].rstrip("/").lower()

        if clean in seen:
            continue

        seen.add(clean)

        result.append(url)

    return result


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

async def download_image(
    client,
    url,
    semaphore,
):

    async with semaphore:

        try:

            response = await client.get(
                url,
                headers={
                    "User-Agent":
                        "Mozilla/5.0 "
                        "(Android 10; Mobile) "
                        "AppleWebKit/537.36 "
                        "Chrome/120 Safari/537.36"
                },
            )

            if response.status_code != 200:
                return None

            content_type = response.headers.get(
                "content-type",
                "",
            ).lower()

            if "image" not in content_type:
                return None

            data = response.content

            if len(data) < MIN_FILE_SIZE:
                return None

            return data

        except Exception as e:

            logger.debug(
                "Image download failed: %s",
                e,
            )

            return None


# ============================================================
# TMDB SEARCH
# ============================================================

async def tmdb_search(
    client,
    endpoint,
    title,
):

    if not TMDB_API_KEY:

        logger.error(
            "TMDB_API_KEY is missing"
        )

        return []

    data = await get_json(
        client,
        f"{TMDB_URL}/{endpoint}",
        params={
            "api_key": TMDB_API_KEY,
            "query": title,
            "language": "en-US",
            "include_adult": "false",
            "page": 1,
        },
    )

    if not data:
        return []

    return data.get(
        "results",
        [],
    )


# ============================================================
# TMDB
# ============================================================

async def tmdb_images(
    client,
    title,
):

    result = []

    searches = [
        ("tv", "search/tv"),
        ("movie", "search/movie"),
    ]

    for media_type, endpoint in searches:

        results = await tmdb_search(
            client,
            endpoint,
            title,
        )

        # Search only the best matching results.
        for item in results[:5]:

            item_id = item.get("id")

            if not item_id:
                continue

            artwork = await get_json(
                client,
                f"{TMDB_URL}/"
                f"{media_type}/"
                f"{item_id}/images",
                params={
                    "api_key": TMDB_API_KEY,
                    "include_image_language":
                        "en,null",
                },
            )

            if not artwork:
                continue

            # Posters
            for poster in artwork.get(
                "posters",
                [],
            ):

                path = poster.get(
                    "file_path"
                )

                width = poster.get(
                    "width",
                    0,
                )

                height = poster.get(
                    "height",
                    0,
                )

                if (
                    path
                    and width >= 500
                    and height >= 500
                ):

                    result.append(
                        "https://image.tmdb.org"
                        "/t/p/original"
                        + path
                    )

            # Backdrops
            for backdrop in artwork.get(
                "backdrops",
                [],
            ):

                path = backdrop.get(
                    "file_path"
                )

                width = backdrop.get(
                    "width",
                    0,
                )

                height = backdrop.get(
                    "height",
                    0,
                )

                if (
                    path
                    and width >= 500
                    and height >= 500
                ):

                    result.append(
                        "https://image.tmdb.org"
                        "/t/p/original"
                        + path
                    )

    return unique_urls(result)


# ============================================================
# ANILIST
# ============================================================

async def anilist_images(
    client,
    title,
):

    query = """
    query ($search: String!) {

        Media(
            search: $search,
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
            }

            bannerImage
        }
    }
    """

    data = await get_json(
        client,
        ANILIST_URL,
    )

    # GraphQL requires POST, so use direct request here.
    try:

        response = await client.post(
            ANILIST_URL,
            json={
                "query": query,
                "variables": {
                    "search": title,
                },
            },
        )

        if response.status_code != 200:
            return []

        data = response.json()

    except Exception as e:

        logger.warning(
            "AniList failed: %s",
            e,
        )

        return []

    media = (
        data
        .get("data", {})
        .get("Media")
    )

    if not media:
        return []

    result = []

    cover = media.get(
        "coverImage",
        {},
    )

    cover_url = (
        cover.get("extraLarge")
        or cover.get("large")
    )

    if cover_url:
        result.append(cover_url)

    banner = media.get(
        "bannerImage"
    )

    if banner:
        result.append(banner)

    return unique_urls(result)


# ============================================================
# JIKAN
# ============================================================

async def jikan_images(
    client,
    title,
):

    data = await get_json(
        client,
        f"{JIKAN_URL}/anime",
        params={
            "q": title,
            "limit": 10,
            "sfw": "true",
        },
    )

    if not data:
        return []

    result = []

    for anime in data.get(
        "data",
        [],
    ):

        images = anime.get(
            "images",
            {},
        )

        jpg = images.get(
            "jpg",
            {},
        )

        url = (
            jpg.get("large_image_url")
            or jpg.get("image_url")
        )

        if url:
            result.append(url)

        trailer = anime.get(
            "trailer",
            {},
        )

        trailer_images = trailer.get(
            "images",
            {},
        )

        trailer_url = (
            trailer_images.get(
                "maximum_image_url"
            )
            or trailer_images.get(
                "large_image_url"
            )
            or trailer_images.get(
                "medium_image_url"
            )
        )

        if trailer_url:
            result.append(trailer_url)

    return unique_urls(result)


# ============================================================
# KITSU
# ============================================================

async def kitsu_images(
    client,
    title,
):

    data = await get_json(
        client,
        f"{KITSU_URL}/anime",
        params={
            "filter[text]": title,
            "page[limit]": 10,
        },
    )

    if not data:
        return []

    result = []

    for anime in data.get(
        "data",
        [],
    ):

        attributes = anime.get(
            "attributes",
            {},
        )

        poster = attributes.get(
            "posterImage",
            {},
        )

        poster_url = (
            poster.get("original")
            or poster.get("large")
            or poster.get("medium")
        )

        if poster_url:
            result.append(poster_url)

        cover = attributes.get(
            "coverImage",
            {},
        )

        cover_url = (
            cover.get("original")
            or cover.get("large")
            or cover.get("medium")
        )

        if cover_url:
            result.append(cover_url)

    return unique_urls(result)


# ============================================================
# FANART.TV
# ============================================================

async def fanart_images(
    client,
    title,
):

    if not FANART_API_KEY:

        logger.warning(
            "FANART_API_KEY is not configured"
        )

        return []

    # First search TMDB to identify the show.
    tmdb_results = await tmdb_search(
        client,
        "search/tv",
        title,
    )

    if not tmdb_results:

        return []

    result = []

    # Fanart.tv normally works best with the
    # show's TVDB ID. TMDB can expose external IDs.
    for show in tmdb_results[:3]:

        tmdb_id = show.get("id")

        if not tmdb_id:
            continue

        external = await get_json(
            client,
            f"{TMDB_URL}/tv/"
            f"{tmdb_id}/external_ids",
            params={
                "api_key": TMDB_API_KEY,
            },
        )

        if not external:
            continue

        tvdb_id = external.get(
            "tvdb_id"
        )

        if not tvdb_id:
            continue

        data = await get_json(
            client,
            f"{FANART_URL}/tv/"
            f"{tvdb_id}",
            headers={
                "api-key": FANART_API_KEY,
            },
        )

        if not data:
            continue

        # Posters
        for item in data.get(
            "tvposter",
            [],
        ):

            url = item.get(
                "url"
            )

            if url:
                result.append(url)

        # Backgrounds
        for item in data.get(
            "showbackground",
            [],
        ):

            url = item.get(
                "url"
            )

            if url:
                result.append(url)

        # HD backgrounds
        for item in data.get(
            "tvthumb",
            [],
        ):

            url = item.get(
                "url"
            )

            if url:
                result.append(url)

        # Season posters
        for item in data.get(
            "seasonposter",
            [],
        ):

            url = item.get(
                "url"
            )

            if url:
                result.append(url)

        # Clearart
        for item in data.get(
            "clearart",
            [],
        ):

            url = item.get(
                "url"
            )

            if url:
                result.append(url)

    return unique_urls(result)


# ============================================================
# ANIME-PLANET
# ============================================================

async def animeplanet_images(
    client,
    title,
):

    # Anime-Planet does not provide a simple public
    # artwork API like TMDB/Kitsu.
    #
    # We use the search page and extract image URLs.
    #
    # This source can change its HTML structure, so
    # failure here will simply return no results.

    try:

        response = await client.get(
            ANIMEPLANET_SEARCH,
            params={
                "q": title,
            },
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36",
                "Accept":
                    "text/html,application/xhtml+xml",
            },
        )

        if response.status_code != 200:
            return []

        html = response.text

        result = []

        # Extract image URLs from HTML.
        patterns = [
            r'https://[^"\']+\.(?:jpg|jpeg|png|webp)',
            r'//[^"\']+\.(?:jpg|jpeg|png|webp)',
        ]

        for pattern in patterns:

            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE,
            )

            for url in matches:

                if url.startswith("//"):
                    url = "https:" + url

                result.append(url)

        # Remove obvious tiny/icon assets.
        filtered = []

        for url in result:

            low = url.lower()

            if any(
                x in low
                for x in (
                    "logo",
                    "icon",
                    "avatar",
                    "sprite",
                    "favicon",
                )
            ):
                continue

            filtered.append(url)

        return unique_urls(filtered)

    except Exception as e:

        logger.warning(
            "Anime-Planet failed: %s",
            e,
        )

        return []


# ============================================================
# SOURCE SEARCH
# ============================================================

async def search_source(
    client,
    source,
    title,
):

    if source == "tmdb":

        return await tmdb_images(
            client,
            title,
        )

    if source == "fanart":

        return await fanart_images(
            client,
            title,
        )

    if source == "animeplanet":

        return await animeplanet_images(
            client,
            title,
        )

    if source == "kitsu":

        return await kitsu_images(
            client,
            title,
        )

    if source == "anilist":

        return await anilist_images(
            client,
            title,
        )

    if source == "jikan":

        return await jikan_images(
            client,
            title,
        )

    return []


# ============================================================
# COMMAND PARSER
# ============================================================

def parse_img_command(
    message: Message,
):

    command = message.command or []

    if len(command) < 2:

        return None, None

    args = list(
        command[1:]
    )

    source = DEFAULT_SOURCE

    # ========================================================
    # /img fanart Naruto
    # /img tmdb Naruto
    # ========================================================

    first = args[0].lower()

    if first in SOURCES:

        source = first

        args = args[1:]

    title = " ".join(args).strip()

    title = clean_title(title)

    if not title:

        return source, None

    return source, title


# ============================================================
# USAGE MESSAGE
# ============================================================

USAGE_TEXT = """
<b>✦ /IMG USAGE</b>

<b>Default:</b>
<code>/img Naruto</code>

<b>TMDB:</b>
<code>/img tmdb Naruto</code>

<b>Fanart:</b>
<code>/img fanart Naruto</code>

<b>Anime-Planet:</b>
<code>/img animeplanet Naruto</code>

<b>Kitsu:</b>
<code>/img kitsu Naruto</code>

<b>AniList:</b>
<code>/img anilist Naruto</code>

<b>Jikan:</b>
<code>/img jikan Naruto</code>

<i>Only one source is searched for each command.</i>
"""


# ============================================================
# /IMG
# ============================================================

@Client.on_message(
    filters.command(
        "img",
        prefixes="/",
    )
)
async def image_command(
    client: Client,
    message: Message,
):

    source, title = parse_img_command(
        message
    )

    # ========================================================
    # EMPTY COMMAND
    # ========================================================

    if not title:

        await message.reply_text(
            USAGE_TEXT,
            parse_mode=enums.ParseMode.HTML,
        )

        return

    # ========================================================
    # LOADING
    # ========================================================

    loading = await message.reply_text(
        f"✦ sᴇᴀʀᴄʜɪɴɢ {source.upper()} ᴀʀᴛᴡᴏʀᴋ...",
    )

    try:

        timeout = httpx.Timeout(
            REQUEST_TIMEOUT,
            connect=15,
        )

        limits = httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
        ) as http:

            # =================================================
            # IMPORTANT:
            # ONLY ONE SOURCE
            # =================================================

            urls = await search_source(
                http,
                source,
                title,
            )

            urls = unique_urls(
                urls
            )

            logger.info(
                "[IMG] Source=%s | Title=%s | Found=%s",
                source,
                title,
                len(urls),
            )

            if not urls:

                await loading.edit_text(
                    "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ.\n\n"
                    "ᴛʀʏ ᴀɢᴀɪɴ ᴡɪᴛʜ ᴀ ᴅɪғғᴇʀᴇɴᴛ ᴛɪᴛʟᴇ "
                    "ᴏʀ sᴏᴜʀᴄᴇ.",
                )

                return

            # =================================================
            # STRICT LIMIT
            # =================================================

            # /img has no number.
            # MAX_IMAGES controls the maximum.
            urls = urls[:MAX_IMAGES]

            # =================================================
            # DOWNLOAD
            # =================================================

            await loading.edit_text(
                f"✦ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs...\n"
                f"0/{len(urls)}",
            )

            semaphore = asyncio.Semaphore(
                DOWNLOAD_CONCURRENCY
            )

            tasks = []

            for url in urls:

                tasks.append(
                    download_image(
                        http,
                        url,
                        semaphore,
                    )
                )

            downloaded = await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            # =================================================
            # KEEP ONLY VALID IMAGES
            # =================================================

            photos = []

            for data in downloaded:

                if isinstance(
                    data,
                    bytes,
                ):

                    photos.append(
                        data
                    )

            if not photos:

                await loading.edit_text(
                    "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ "
                    "ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ.",
                )

                return

            # =================================================
            # HARD LIMIT AGAIN
            # =================================================

            # This prevents a source or future code change
            # from ever sending more than MAX_IMAGES.
            photos = photos[:MAX_IMAGES]

            total = len(photos)

            await loading.edit_text(
                f"✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs...\n"
                f"0/{total}",
            )

            # =================================================
            # ALBUM UPLOAD
            # =================================================

            uploaded = 0

            for start in range(
                0,
                total,
                ALBUM_SIZE,
            ):

                batch = photos[
                    start:start + ALBUM_SIZE
                ]

                media = []

                for index, data in enumerate(
                    batch
                ):

                    bio = BytesIO(
                        data
                    )

                    bio.name = (
                        f"image_{start + index + 1}.jpg"
                    )

                    media.append(
                        InputMediaPhoto(
                            media=bio
                        )
                    )

                try:

                    await client.send_media_group(
                        chat_id=message.chat.id,
                        media=media,
                    )

                    uploaded += len(
                        batch
                    )

                    # =================================================
                    # PROGRESS MESSAGE
                    # =================================================

                    await loading.edit_text(
                        f"✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs...\n"
                        f"{uploaded}/{total}",
                    )

                except Exception as e:

                    logger.warning(
                        "Album upload failed: %s",
                        e,
                    )

                    # Individual fallback.
                    # This is only used if Telegram rejects
                    # the album.

                    for data in batch:

                        try:

                            bio = BytesIO(
                                data
                            )

                            bio.name = "image.jpg"

                            await client.send_photo(
                                chat_id=message.chat.id,
                                photo=bio,
                            )

                            uploaded += 1

                        except Exception as photo_error:

                            logger.warning(
                                "Individual upload failed: %s",
                                photo_error,
                            )

                await asyncio.sleep(
                    0.5
                )

            # =================================================
            # FINISHED
            # =================================================

            try:

                await loading.edit_text(
                    f"✦ ᴅᴏɴᴇ\n"
                    f"ᴜᴘʟᴏᴀᴅᴇᴅ: {uploaded}/{total}\n"
                    f"sᴏᴜʀᴄᴇ: {source.upper()}",
                )

                # Remove status message after a short delay.
                await asyncio.sleep(
                    2
                )

                await loading.delete()

            except Exception:

                pass

    except Exception as e:

        logger.exception(
            "[IMG] Fatal error",
        )

        try:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ.\n\n"
                "ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.",
            )

        except Exception:

            pass