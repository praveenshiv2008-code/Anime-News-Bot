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
# API
# ============================================================

TMDB_URL = "https://api.themoviedb.org/3"
ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"
KITSU_URL = "https://kitsu.io/api/edge"
FANART_URL = "https://webservice.fanart.tv/v3"

ANIMEPLANET_SEARCH_URL = (
    "https://www.anime-planet.com/anime/all"
)


# ============================================================
# SETTINGS
# ============================================================

TMDB_API_KEY = os.getenv(
    "TMDB_API_KEY",
    ""
).strip()

FANART_API_KEY = os.getenv(
    "FANART_API_KEY",
    ""
).strip()

DEFAULT_LIMIT = 30

MAX_ALLOWED_LIMIT = 100

ALBUM_SIZE = 10

MIN_FILE_SIZE = 5_000

REQUEST_TIMEOUT = 30

DOWNLOAD_CONCURRENCY = 8


# ============================================================
# SOURCES
# ============================================================

SOURCES = {
    "tmdb",
    "fanart",
    "animeplanet",
    "kitsu",
    "anilist",
    "jikan",
}

DEFAULT_SOURCE = "tmdb"


# ============================================================
# USER AGENT
# ============================================================

USER_AGENT = (
    "Mozilla/5.0 "
    "(Linux; Android 10) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/120.0 Mobile Safari/537.36"
)


# ============================================================
# HTTP
# ============================================================

async def get_json(
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

    except Exception as e:

        logger.warning(
            "Request failed: %s",
            e,
        )

        return None


# ============================================================
# POST JSON
# ============================================================

async def post_json(
    client,
    url,
    json_data,
    headers=None,
):

    try:

        response = await client.post(
            url,
            json=json_data,
            headers=headers,
        )

        if response.status_code != 200:

            logger.warning(
                "POST HTTP %s: %s",
                response.status_code,
                url,
            )

            return None

        try:

            return response.json()

        except Exception:

            return None

    except Exception as e:

        logger.warning(
            "POST failed: %s",
            e,
        )

        return None


# ============================================================
# CLEAN TITLE
# ============================================================

def clean_title(
    title,
):

    title = title.strip()

    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    return title.strip(
        "\"'"
    )


# ============================================================
# UNIQUE URLS
# ============================================================

def unique_urls(
    urls,
):

    result = []

    seen = set()

    for url in urls:

        if not url:
            continue

        url = str(url).strip()

        if not url:
            continue

        # Remove query strings for duplicate detection.
        normalized = (
            url
            .split("?")[0]
            .split("#")[0]
            .rstrip("/")
            .lower()
        )

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        result.append(
            url
        )

    return result


# ============================================================
# IMAGE CONTENT HASH
# ============================================================

def image_fingerprint(
    data,
):

    # A lightweight fingerprint to catch duplicate files
    # coming from different URLs.
    #
    # We use the first/middle/last portions rather than
    # relying only on URL equality.

    if not data:
        return None

    length = len(data)

    if length <= 30_000:

        return (
            length,
            data[:5_000],
            data[-5_000:],
        )

    middle = length // 2

    return (
        length,
        data[:2_000],
        data[
            middle - 1_000:
            middle + 1_000
        ],
        data[-2_000:],
    )


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
                    "User-Agent": USER_AGENT,
                    "Accept": "image/avif,image/webp,"
                              "image/apng,image/svg+xml,"
                              "image/*,*/*;q=0.8",
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
                "Download failed: %s",
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
            "TMDB_API_KEY is not configured"
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

    if not TMDB_API_KEY:
        return []

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

        # Only process the best search matches.
        for item in results[:5]:

            item_id = item.get(
                "id"
            )

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

    return unique_urls(
        result
    )


# ============================================================
# FANART.TV
# ============================================================

async def fanart_images(
    client,
    title,
):

    if not FANART_API_KEY:

        logger.error(
            "FANART_API_KEY is not configured"
        )

        return []

    if not TMDB_API_KEY:

        logger.error(
            "TMDB_API_KEY is required to "
            "resolve the Fanart.tv TVDB ID"
        )

        return []

    result = []

    # --------------------------------------------------------
    # Find TV show through TMDB.
    # This does NOT search another artwork source.
    # TMDB is only used to resolve the show's TVDB ID.
    # --------------------------------------------------------

    results = await tmdb_search(
        client,
        "search/tv",
        title,
    )

    for show in results[:3]:

        tmdb_id = show.get(
            "id"
        )

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
                "User-Agent": USER_AGENT,
            },
        )

        if not data:
            continue

        # Fanart categories.
        categories = [
            "tvposter",
            "showbackground",
            "tvthumb",
            "seasonposter",
            "seasonthumb",
            "clearart",
            "hdclearart",
            "tvlogo",
            "hdmovielogo",
        ]

        for category in categories:

            for item in data.get(
                category,
                [],
            ):

                url = item.get(
                    "url"
                )

                if url:

                    result.append(
                        url
                    )

    return unique_urls(
        result
    )


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
            result.append(
                poster_url
            )

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
            result.append(
                cover_url
            )

    return unique_urls(
        result
    )


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

    data = await post_json(
        client,
        ANILIST_URL,
        {
            "query": query,
            "variables": {
                "search": title,
            },
        },
    )

    if not data:
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
        result.append(
            cover_url
        )

    banner = media.get(
        "bannerImage"
    )

    if banner:
        result.append(
            banner
        )

    return unique_urls(
        result
    )


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

        image_url = (
            jpg.get("large_image_url")
            or jpg.get("image_url")
        )

        if image_url:
            result.append(
                image_url
            )

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
            result.append(
                trailer_url
            )

    return unique_urls(
        result
    )


# ============================================================
# ANIME-PLANET
# ============================================================

async def animeplanet_images(
    client,
    title,
):

    try:

        response = await client.get(
            ANIMEPLANET_SEARCH_URL,
            params={
                "q": title,
            },
            headers={
                "User-Agent": USER_AGENT,
                "Accept":
                    "text/html,"
                    "application/xhtml+xml",
            },
        )

        if response.status_code != 200:

            logger.warning(
                "Anime-Planet HTTP %s",
                response.status_code,
            )

            return []

        html = response.text

        result = []

        patterns = [
            r'https://[^"\']+?\.(?:jpg|jpeg|png|webp)',
            r'//[^"\']+?\.(?:jpg|jpeg|png|webp)',
        ]

        for pattern in patterns:

            matches = re.findall(
                pattern,
                html,
                flags=re.IGNORECASE,
            )

            for url in matches:

                if url.startswith("//"):

                    url = (
                        "https:"
                        + url
                    )

                low = url.lower()

                if any(
                    bad in low
                    for bad in (
                        "logo",
                        "icon",
                        "avatar",
                        "sprite",
                        "favicon",
                    )
                ):

                    continue

                result.append(
                    url
                )

        return unique_urls(
            result
        )

    except Exception as e:

        logger.warning(
            "Anime-Planet failed: %s",
            e,
        )

        return []


# ============================================================
# SOURCE DISPATCH
# ============================================================

async def search_source(
    client,
    source,
    title,
):

    # IMPORTANT:
    # This function calls ONLY the selected source.

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

        return None, None, DEFAULT_LIMIT

    args = list(
        command[1:]
    )

    source = DEFAULT_SOURCE

    # --------------------------------------------------------
    # Detect source
    # --------------------------------------------------------

    if args:

        possible_source = args[0].lower()

        if possible_source in SOURCES:

            source = possible_source

            args = args[1:]

    # --------------------------------------------------------
    # Optional number
    # --------------------------------------------------------

    requested_limit = DEFAULT_LIMIT

    if args:

        last = args[-1]

        if last.isdigit():

            requested_limit = int(
                last
            )

            args = args[:-1]

    # --------------------------------------------------------
    # Validate limit
    # --------------------------------------------------------

    if requested_limit < 1:

        requested_limit = 1

    if requested_limit > MAX_ALLOWED_LIMIT:

        requested_limit = MAX_ALLOWED_LIMIT

    title = " ".join(
        args
    ).strip()

    title = clean_title(
        title
    )

    return (
        source,
        title,
        requested_limit,
    )


# ============================================================
# USAGE
# ============================================================

USAGE_TEXT = """
<b>✦ ɪᴍɢ ᴄᴏᴍᴍᴀɴᴅ</b>

<b>Default — TMDB</b>
<code>/img Naruto</code>

<b>TMDB</b>
<code>/img tmdb Naruto</code>

<b>Fanart.tv</b>
<code>/img fanart Naruto</code>

<b>Anime-Planet</b>
<code>/img animeplanet Naruto</code>

<b>Kitsu</b>
<code>/img kitsu Naruto</code>

<b>AniList</b>
<code>/img anilist Naruto</code>

<b>Jikan</b>
<code>/img jikan Naruto</code>

<b>Optional limit</b>
<code>/img Naruto 20</code>
<code>/img tmdb Naruto 50</code>

<i>Only one artwork source is searched per command.</i>
"""


# ============================================================
# /IMG HANDLER
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

    (
        source,
        title,
        requested_limit,
    ) = parse_img_command(
        message
    )

    # --------------------------------------------------------
    # Empty command
    # --------------------------------------------------------

    if not title:

        await message.reply_text(
            USAGE_TEXT,
            parse_mode=enums.ParseMode.HTML,
        )

        return

    logger.info(
        "[IMG] source=%s title=%s limit=%s",
        source,
        title,
        requested_limit,
    )

    # --------------------------------------------------------
    # Loading
    # --------------------------------------------------------

    loading = await message.reply_text(
        f"✦ sᴇᴀʀᴄʜɪɴɢ {source.upper()} ᴀʀᴛᴡᴏʀᴋ..."
    )

    try:

        timeout = httpx.Timeout(
            REQUEST_TIMEOUT,
            connect=15,
        )

        limits = httpx.Limits(
            max_connections=15,
            max_keepalive_connections=8,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
        ) as http:

            # =================================================
            # ONLY SELECTED SOURCE
            # =================================================

            urls = await search_source(
                http,
                source,
                title,
            )

            # =================================================
            # URL DEDUPLICATION
            # =================================================

            urls = unique_urls(
                urls
            )

            logger.info(
                "[IMG] %s unique URLs found",
                len(urls),
            )

            if not urls:

                await loading.edit_text(
                    "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ.\n\n"
                    "ᴛʀʏ ᴀɴᴏᴛʜᴇʀ ᴛɪᴛʟᴇ "
                    "ᴏʀ sᴏᴜʀᴄᴇ.",
                )

                return

            # =================================================
            # STRICT URL LIMIT
            # =================================================

            urls = urls[
                :requested_limit
            ]

            await loading.edit_text(
                f"✦ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...\n"
                f"0/{len(urls)}",
            )

            # =================================================
            # DOWNLOAD
            # =================================================

            semaphore = asyncio.Semaphore(
                DOWNLOAD_CONCURRENCY
            )

            tasks = [
                download_image(
                    http,
                    url,
                    semaphore,
                )
                for url in urls
            ]

            downloaded = await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            # =================================================
            # IMAGE CONTENT DEDUPLICATION
            # =================================================

            photos = []

            fingerprints = set()

            for data in downloaded:

                if not isinstance(
                    data,
                    bytes,
                ):

                    continue

                fingerprint = image_fingerprint(
                    data
                )

                if fingerprint in fingerprints:

                    continue

                fingerprints.add(
                    fingerprint
                )

                photos.append(
                    data
                )

            # =================================================
            # STRICT LIMIT AFTER DOWNLOAD
            # =================================================

            photos = photos[
                :requested_limit
            ]

            if not photos:

                await loading.edit_text(
                    "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ "
                    "ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ.",
                )

                return

            total = min(
                len(photos),
                requested_limit,
            )

            # =================================================
            # UPLOAD
            # =================================================

            await loading.edit_text(
                f"✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs...\n"
                f"0/{total}",
            )

            uploaded = 0

            # =================================================
            # TELEGRAM ALBUMS
            # =================================================

            for start in range(
                0,
                total,
                ALBUM_SIZE,
            ):

                # NEVER go beyond total.
                end = min(
                    start + ALBUM_SIZE,
                    total,
                )

                batch = photos[
                    start:end
                ]

                media = []

                for index, data in enumerate(
                    batch
                ):

                    bio = BytesIO(
                        data
                    )

                    bio.name = (
                        f"img_{start + index + 1}.jpg"
                    )

                    media.append(
                        InputMediaPhoto(
                            media=bio
                        )
                    )

                # ------------------------------------------------
                # IMPORTANT:
                # Send exactly ONE album.
                # No individual fallback that can duplicate
                # the album.
                # ------------------------------------------------

                try:

                    await client.send_media_group(
                        chat_id=message.chat.id,
                        media=media,
                    )

                    uploaded += len(
                        batch
                    )

                except Exception as e:

                    logger.warning(
                        "Album upload failed: %s",
                        e,
                    )

                    # If Telegram rejects the album,
                    # send the batch individually exactly once.
                    for data in batch:

                        try:

                            bio = BytesIO(
                                data
                            )

                            bio.name = (
                                "image.jpg"
                            )

                            await client.send_photo(
                                chat_id=message.chat.id,
                                photo=bio,
                            )

                            uploaded += 1

                        except Exception as photo_error:

                            logger.warning(
                                "Photo upload failed: %s",
                                photo_error,
                            )

                # ------------------------------------------------
                # Progress
                # ------------------------------------------------

                await loading.edit_text(
                    f"✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs...\n"
                    f"{uploaded}/{total}",
                )

                await asyncio.sleep(
                    0.5
                )

            # =================================================
            # DONE
            # =================================================

            await loading.edit_text(
                f"✦ ᴅᴏɴᴇ\n"
                f"ᴜᴘʟᴏᴀᴅᴇᴅ: {uploaded}/{total}\n"
                f"sᴏᴜʀᴄᴇ: {source.upper()}",
            )

            await asyncio.sleep(
                2
            )

            try:

                await loading.delete()

            except Exception:

                pass

    except Exception as e:

        logger.exception(
            "[IMG] Fatal error"
        )

        try:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ.\n\n"
                "ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.",
            )

        except Exception:

            pass