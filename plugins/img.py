# plugins/img.py
#
# /img command
#
# Default:
#   /img Naruto 10
#
# Source-specific:
#   /img tmdb Naruto 10
#   /img fanart Naruto 10
#   /img kitsu Naruto 10
#   /img animeplanet Naruto 10
#
# The command searches ONLY the selected source.
#
# After searching, it sends numbered direct image URLs:
#
# 1. https://...
# 2. https://...
# 3. https://...
#
# Send:
#   1
# to download image #1.
#
# Send:
#   2 3 4
# to download images #2, #3 and #4.
#
# Images are uploaded in Telegram albums of maximum 10.
# The temporary "Uploading..." message is deleted afterwards.
#
# IMPORTANT:
# Add FANART_API_KEY to config.py if using Fanart.tv:
#
# FANART_API_KEY = "your_api_key"


import asyncio
import logging
import re
from urllib.parse import quote

import httpx

from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto

from config import TMDB_API_KEY

try:
    from config import FANART_API_KEY
except ImportError:
    FANART_API_KEY = ""


logger = logging.getLogger("AnimeImages")


# ============================================================
# SETTINGS
# ============================================================

DEFAULT_SOURCE = "tmdb"

DEFAULT_LIMIT = 30

# Maximum number returned by one command.
MAX_LIMIT = 100

TELEGRAM_ALBUM_SIZE = 10

MIN_FILE_SIZE = 5_000

REQUEST_TIMEOUT = 30


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

        return response.json()

    except Exception as e:
        logger.warning(
            "GET failed: %s",
            e,
        )
        return None


# ============================================================
# NORMALIZE URL
# ============================================================

def normalize_url(url):
    """
    Normalize an image URL for duplicate detection.
    """

    if not url:
        return ""

    url = url.strip()

    # Remove query string.
    url = url.split("?", 1)[0]

    # Remove trailing slash.
    url = url.rstrip("/")

    return url.lower()


# ============================================================
# UNIQUE IMAGES
# ============================================================

def unique_images(urls):
    """
    Remove duplicate images.

    The actual image URL/path is used as the identity.
    """

    result = []

    seen = set()

    for url in urls:

        if not url:
            continue

        normalized = normalize_url(url)

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)

        result.append(url)

    return result


# ============================================================
# TMDB SEARCH
# ============================================================

async def tmdb_search(
    client,
    name,
):
    if not TMDB_API_KEY:
        return []

    results = []

    for endpoint in (
        "search/tv",
        "search/movie",
    ):

        data = await get_json(
            client,
            f"https://api.themoviedb.org/3/{endpoint}",
            params={
                "api_key": TMDB_API_KEY,
                "query": name,
                "language": "en-US",
                "include_adult": "false",
                "page": 1,
            },
        )

        if not data:
            continue

        for item in data.get("results", []):

            item_id = item.get("id")

            if item_id:

                results.append(
                    (
                        "tv"
                        if endpoint == "search/tv"
                        else "movie",
                        item_id,
                    )
                )

    return results


# ============================================================
# TMDB IMAGES
# ============================================================

async def tmdb_images(
    client,
    name,
):
    """
    Returns:
        {
            "poster": [],
            "landscape": [],
            "logo": [],
            "all": []
        }
    """

    output = {
        "poster": [],
        "landscape": [],
        "logo": [],
        "all": [],
    }

    if not TMDB_API_KEY:
        return output

    searches = await tmdb_search(
        client,
        name,
    )

    # Only inspect the best matching results.
    searches = searches[:5]

    for media_type, item_id in searches:

        data = await get_json(
            client,
            f"https://api.themoviedb.org/3/"
            f"{media_type}/{item_id}/images",
            params={
                "api_key": TMDB_API_KEY,
                "include_image_language": "en,null",
            },
        )

        if not data:
            continue

        # --------------------------------------------------------
        # POSTERS
        # --------------------------------------------------------

        for image in data.get("posters", []):

            path = image.get("file_path")

            width = image.get("width", 0)
            height = image.get("height", 0)

            if not path:
                continue

            if width < 300 or height < 300:
                continue

            url = (
                "https://image.tmdb.org"
                "/t/p/original"
                + path
            )

            output["poster"].append(url)

        # --------------------------------------------------------
        # BACKDROPS / LANDSCAPE
        # --------------------------------------------------------

        for image in data.get("backdrops", []):

            path = image.get("file_path")

            width = image.get("width", 0)
            height = image.get("height", 0)

            if not path:
                continue

            if width < 500 or height < 250:
                continue

            url = (
                "https://image.tmdb.org"
                "/t/p/original"
                + path
            )

            output["landscape"].append(url)

        # --------------------------------------------------------
        # LOGOS
        # --------------------------------------------------------

        for image in data.get("logos", []):

            path = image.get("file_path")

            width = image.get("width", 0)

            if not path:
                continue

            if width < 200:
                continue

            url = (
                "https://image.tmdb.org"
                "/t/p/original"
                + path
            )

            output["logo"].append(url)

    # ------------------------------------------------------------
    # DEDUP EACH CATEGORY
    # ------------------------------------------------------------

    for key in output:
        output[key] = unique_images(
            output[key]
        )

    # ------------------------------------------------------------
    # ALL = UNIQUE COMBINATION
    # ------------------------------------------------------------

    output["all"] = unique_images(
        output["poster"]
        + output["landscape"]
        + output["logo"]
    )

    return output


# ============================================================
# FANART.TV
# ============================================================

async def fanart_images(
    client,
    name,
):
    """
    Fanart.tv source.

    Fanart API works using TVDB/TMDB IDs.
    We first search TMDB and then use the TMDB ID.

    Returns:
        poster
        landscape
        logo
        all
    """

    output = {
        "poster": [],
        "landscape": [],
        "logo": [],
        "all": [],
    }

    if not FANART_API_KEY:
        return output

    if not TMDB_API_KEY:
        return output

    try:

        searches = await tmdb_search(
            client,
            name,
        )

        if not searches:
            return output

        # Fanart supports TV/movie artwork.
        # Use the first matching TV/movie ID.
        for media_type, item_id in searches[:3]:

            # Fanart API endpoint.
            url = (
                "https://webservice.fanart.tv/v3/"
                f"{media_type}/{item_id}"
            )

            data = await get_json(
                client,
                url,
                headers={
                    "api-key": FANART_API_KEY,
                },
            )

            if not data:
                continue

            # ----------------------------------------------------
            # TV POSTERS
            # ----------------------------------------------------

            for item in data.get(
                "tvposter",
                [],
            ):

                image_url = item.get("url")

                if image_url:
                    output["poster"].append(
                        image_url
                    )

            # ----------------------------------------------------
            # MOVIE POSTERS
            # ----------------------------------------------------

            for item in data.get(
                "movieposter",
                [],
            ):

                image_url = item.get("url")

                if image_url:
                    output["poster"].append(
                        image_url
                    )

            # ----------------------------------------------------
            # BACKDROPS
            # ----------------------------------------------------

            for key in (
                "showbackground",
                "moviebackground",
            ):

                for item in data.get(
                    key,
                    [],
                ):

                    image_url = item.get("url")

                    if image_url:
                        output["landscape"].append(
                            image_url
                        )

            # ----------------------------------------------------
            # CLEARLOGOS
            # ----------------------------------------------------

            for key in (
                "clearlogo",
                "hdtvlogo",
                "hdmovielogo",
            ):

                for item in data.get(
                    key,
                    [],
                ):

                    image_url = item.get("url")

                    if image_url:
                        output["logo"].append(
                            image_url
                        )

    except Exception as e:

        logger.warning(
            "Fanart failed: %s",
            e,
        )

    for key in (
        "poster",
        "landscape",
        "logo",
    ):

        output[key] = unique_images(
            output[key]
        )

    output["all"] = unique_images(
        output["poster"]
        + output["landscape"]
        + output["logo"]
    )

    return output


# ============================================================
# KITSU
# ============================================================

async def kitsu_images(
    client,
    name,
):
    output = {
        "poster": [],
        "landscape": [],
        "logo": [],
        "all": [],
    }

    data = await get_json(
        client,
        "https://kitsu.io/api/edge/anime",
        params={
            "filter[text]": name,
            "page[limit]": 10,
        },
    )

    if not data:
        return output

    for anime in data.get("data", []):

        attributes = anime.get(
            "attributes",
            {},
        )

        poster = attributes.get(
            "posterImage",
            {},
        )

        url = (
            poster.get("original")
            or poster.get("large")
            or poster.get("medium")
        )

        if url:
            output["poster"].append(url)

        cover = attributes.get(
            "coverImage",
            {},
        )

        url = (
            cover.get("original")
            or cover.get("large")
            or cover.get("medium")
        )

        if url:
            output["landscape"].append(url)

    for key in (
        "poster",
        "landscape",
        "logo",
    ):

        output[key] = unique_images(
            output[key]
        )

    output["all"] = unique_images(
        output["poster"]
        + output["landscape"]
        + output["logo"]
    )

    return output


# ============================================================
# ANIMEPLANET
# ============================================================

async def animeplanet_images(
    client,
    name,
):
    """
    Anime-Planet does not provide a simple official public API.

    This uses its search page and extracts image URLs.
    """

    output = {
        "poster": [],
        "landscape": [],
        "logo": [],
        "all": [],
    }

    try:

        url = (
            "https://www.anime-planet.com/anime/"
            "?name="
            + quote(name)
        )

        response = await client.get(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Linux; Android 10) "
                    "AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36",
            },
        )

        if response.status_code != 200:
            return output

        html = response.text

        # Extract common Anime-Planet image URLs.
        matches = re.findall(
            r'https?://[^"\']+'
            r'\.(?:jpg|jpeg|png|webp)',
            html,
            flags=re.IGNORECASE,
        )

        for image_url in matches:

            image_url = image_url.replace(
                "\\/",
                "/",
            )

            output["poster"].append(
                image_url
            )

    except Exception as e:

        logger.warning(
            "AnimePlanet failed: %s",
            e,
        )

    output["poster"] = unique_images(
        output["poster"]
    )

    output["all"] = output["poster"][:]

    return output


# ============================================================
# SOURCE SEARCH
# ============================================================

async def search_source(
    client,
    source,
    name,
):
    if source == "tmdb":
        return await tmdb_images(
            client,
            name,
        )

    if source == "fanart":
        return await fanart_images(
            client,
            name,
        )

    if source == "kitsu":
        return await kitsu_images(
            client,
            name,
        )

    if source == "animeplanet":
        return await animeplanet_images(
            client,
            name,
        )

    return {
        "poster": [],
        "landscape": [],
        "logo": [],
        "all": [],
    }


# ============================================================
# COMMAND PARSER
# ============================================================

SOURCES = {
    "tmdb",
    "fanart",
    "kitsu",
    "animeplanet",
}

CATEGORIES = {
    "poster",
    "landscape",
    "logo",
    "all",
}


def parse_img_command(message):
    """
    Examples:

        /img Naruto
        /img Naruto 20

        /img tmdb Naruto 20
        /img fanart Naruto 20
        /img kitsu Naruto 20

        /img tmdb logo Naruto 20
        /img tmdb landscape Naruto 20
        /img tmdb poster Naruto 20
        /img tmdb all Naruto 20
    """

    command = message.command

    if len(command) < 2:
        return None

    args = command[1:]

    source = DEFAULT_SOURCE
    category = "all"
    limit = DEFAULT_LIMIT

    # ----------------------------------------------------------
    # SOURCE
    # ----------------------------------------------------------

    if args and args[0].lower() in SOURCES:

        source = args.pop(0).lower()

    # ----------------------------------------------------------
    # CATEGORY
    # ----------------------------------------------------------

    if args and args[0].lower() in CATEGORIES:

        category = args.pop(0).lower()

    # ----------------------------------------------------------
    # LIMIT
    # ----------------------------------------------------------

    if args and args[-1].isdigit():

        limit = int(
            args.pop()
        )

    if limit < 1:
        limit = 1

    if limit > MAX_LIMIT:
        limit = MAX_LIMIT

    name = " ".join(
        args
    ).strip()

    # Remove accidental trailing number.
    name = re.sub(
        r"\s+\d+$",
        "",
        name,
    ).strip()

    if not name:
        return None

    return source, category, name, limit


# ============================================================
# DOWNLOAD
# ============================================================

async def download_image(
    client,
    url,
):
    try:

        response = await client.get(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0",
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

        if len(response.content) < MIN_FILE_SIZE:
            return None

        return response.content

    except Exception as e:

        logger.warning(
            "Image download failed: %s",
            e,
        )

        return None


# ============================================================
# NUMBER MESSAGE PARSER
# ============================================================

def parse_numbers(text):
    """
    Supports:

        1
        1 2 3
        1,2,3
        1, 2, 3
    """

    numbers = re.findall(
        r"\d+",
        text,
    )

    result = []

    seen = set()

    for number in numbers:

        try:
            number = int(number)
        except Exception:
            continue

        if number <= 0:
            continue

        if number in seen:
            continue

        seen.add(number)

        result.append(number)

    return result


# ============================================================
# STORE SEARCH RESULTS
# ============================================================

# chat_id -> {
#     "urls": [...],
#     "source": "...",
#     "category": "..."
# }

SEARCH_CACHE = {}


# ============================================================
# /IMG
# ============================================================

@Client.on_message(
    filters.command("img")
)
async def image_command(
    client: Client,
    message: Message,
):

    parsed = parse_img_command(
        message
    )

    # ----------------------------------------------------------
    # EMPTY / INVALID COMMAND
    # ----------------------------------------------------------

    if not parsed:

        await message.reply_text(
            "ᴜsᴀɢᴇ:\n\n"
            "/img Naruto\n"
            "/img Naruto 20\n\n"
            "sᴏᴜʀᴄᴇ:\n"
            "/img tmdb Naruto 20\n"
            "/img fanart Naruto 20\n"
            "/img kitsu Naruto 20\n"
            "/img animeplanet Naruto 20\n\n"
            "ᴄᴀᴛᴇɢᴏʀʏ:\n"
            "/img tmdb poster Naruto 20\n"
            "/img tmdb landscape Naruto 20\n"
            "/img tmdb logo Naruto 20\n"
            "/img tmdb all Naruto 20\n\n"
            "sᴇʟᴇᴄᴛ:\n"
            "sᴇɴᴅ 1 ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ #1\n"
            "sᴇɴᴅ 2 3 4 ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ #2 #3 #4"
        )

        return

    source, category, name, limit = parsed

    searching = await message.reply_text(
        f"✦ sᴇᴀʀᴄʜɪɴɢ {source.upper()}..."
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

            artwork = await search_source(
                http,
                source,
                name,
            )

        urls = artwork.get(
            category,
            [],
        )

        # ------------------------------------------------------
        # FINAL DEDUPLICATION
        # ------------------------------------------------------

        urls = unique_images(
            urls
        )

        # ------------------------------------------------------
        # STRICT LIMIT
        # ------------------------------------------------------

        urls = urls[
            :limit
        ]

        if not urls:

            await searching.edit_text(
                "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ.\n\n"
                "ᴛʀʏ ᴀɴᴏᴛʜᴇʀ sᴏᴜʀᴄᴇ ᴏʀ ᴛɪᴛʟᴇ."
            )

            return

        # ------------------------------------------------------
        # SAVE ONLY THE EXACT RESULTS WE SENT
        # ------------------------------------------------------

        SEARCH_CACHE[
            message.chat.id
        ] = {
            "urls": urls,
            "source": source,
            "category": category,
            "name": name,
        }

        # ------------------------------------------------------
        # NUMBERED DIRECT LINKS
        # ------------------------------------------------------

        lines = []

        for index, url in enumerate(
            urls,
            start=1,
        ):

            lines.append(
                f"{index}. {url}"
            )

        text = (
            f"✦ {name}\n"
            f"ᴜsᴇᴅ sᴏᴜʀᴄᴇ: {source.upper()}\n"
            f"ᴛʏᴘᴇ: {category.upper()}\n"
            f"ɪᴍᴀɢᴇs: {len(urls)}\n\n"
            + "\n".join(lines)
            + "\n\n"
            "➜ sᴇɴᴅ ɪᴍᴀɢᴇ ɴᴜᴍʙᴇʀ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ.\n"
            "ᴇxᴀᴍᴘʟᴇ: 1\n"
            "ᴏʀ: 2 3 4"
        )

        await searching.edit_text(
            text,
            disable_web_page_preview=True,
        )

    except Exception as e:

        logger.exception(
            "/img failed"
        )

        try:

            await searching.edit_text(
                "❌ ɪᴍᴀɢᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ.\n\n"
                "ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ."
            )

        except Exception:
            pass


# ============================================================
# NUMBER DOWNLOAD
# ============================================================

@Client.on_message(
    filters.text
    & ~filters.command("img")
)
async def image_number_download(
    client: Client,
    message: Message,
):

    if not message.text:
        return

    # ----------------------------------------------------------
    # IMPORTANT:
    # Only process a number if the user has a previous
    # /img search cached.
    # ----------------------------------------------------------

    cache = SEARCH_CACHE.get(
        message.chat.id
    )

    if not cache:
        return

    text = message.text.strip()

    # Only accept pure numbers.
    if not re.fullmatch(
        r"[\d\s,]+",
        text,
    ):
        return

    numbers = parse_numbers(
        text
    )

    if not numbers:
        return

    urls = cache["urls"]

    # ----------------------------------------------------------
    # VALID NUMBERS ONLY
    # ----------------------------------------------------------

    selected = []

    for number in numbers:

        if number < 1:
            continue

        if number > len(urls):
            continue

        # Convert number to zero-based index.
        url = urls[number - 1]

        # Prevent duplicate selected images.
        if url in selected:
            continue

        selected.append(url)

    if not selected:
        await message.reply_text(
            f"❌ ᴘʟᴇᴀsᴇ ᴄʜᴏᴏsᴇ ɴᴜᴍʙᴇʀs ʙᴇᴛᴡᴇᴇɴ "
            f"1 ᴀɴᴅ {len(urls)}."
        )
        return

    # ----------------------------------------------------------
    # DOWNLOAD MESSAGE
    # ----------------------------------------------------------

    uploading = await message.reply_text(
        "✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs..."
    )

    downloaded = []

    timeout = httpx.Timeout(
        REQUEST_TIMEOUT,
        connect=15,
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
    ) as http:

        # Download ONLY selected images.
        results = await asyncio.gather(
            *[
                download_image(
                    http,
                    url,
                )
                for url in selected
            ],
            return_exceptions=True,
        )

    for data in results:

        if isinstance(
            data,
            bytes,
        ):

            downloaded.append(
                data
            )

    # ----------------------------------------------------------
    # NOTHING DOWNLOADED
    # ----------------------------------------------------------

    if not downloaded:

        try:
            await uploading.delete()
        except Exception:
            pass

        await message.reply_text(
            "❌ ᴄᴏᴜʟᴅ ɴᴏᴛ ᴅᴏᴡɴʟᴏᴀᴅ ᴛʜᴇ sᴇʟᴇᴄᴛᴇᴅ ɪᴍᴀɢᴇ."
        )

        return

    # ----------------------------------------------------------
    # TELEGRAM ALBUMS
    # ----------------------------------------------------------

    try:

        for start in range(
            0,
            len(downloaded),
            TELEGRAM_ALBUM_SIZE,
        ):

            batch = downloaded[
                start:
                start + TELEGRAM_ALBUM_SIZE
            ]

            media = []

            for image_data in batch:

                media.append(
                    InputMediaPhoto(
                        image_data
                    )
                )

            if len(media) >= 2:

                await client.send_media_group(
                    chat_id=message.chat.id,
                    media=media,
                )

            else:

                # Telegram media groups need 2+ items.
                await client.send_photo(
                    chat_id=message.chat.id,
                    photo=batch[0],
                )

            # Small delay between albums.
            if start + TELEGRAM_ALBUM_SIZE < len(
                downloaded
            ):

                await asyncio.sleep(
                    1
                )

    except Exception as e:

        logger.exception(
            "Telegram upload failed: %s",
            e,
        )

        try:
            await uploading.delete()
        except Exception:
            pass

        await message.reply_text(
            "❌ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ."
        )

        return

    # ----------------------------------------------------------
    # DELETE UPLOADING MESSAGE
    # ----------------------------------------------------------

    try:

        await uploading.delete()

    except Exception:
        pass