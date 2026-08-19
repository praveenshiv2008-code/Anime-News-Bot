import asyncio
import logging
import re
from io import BytesIO
from urllib.parse import quote

import httpx

from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto

from config import TMDB_API_KEY


logger = logging.getLogger("AnimeImages")

TMDB_URL = "https://api.themoviedb.org/3"
KITSU_URL = "https://kitsu.io/api/edge"
ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"

DEFAULT_LIMIT = 30
MAX_LIMIT = 100
BATCH_SIZE = 10
MIN_FILE_SIZE = 5000
TIMEOUT = 25

# ------------------------------------------------------------
# SOURCE ALIASES
# ------------------------------------------------------------

SOURCE_ALIASES = {
    "tmdb": "tmdb",
    "fanart": "fanart",
    "kitsu": "kitsu",
    "animeplanet": "animeplanet",
    "anilist": "anilist",
    "jikan": "jikan",
    "mal": "jikan",
}

# Stores the numbered results temporarily.
# key = (chat_id, user_id)
IMAGE_RESULTS = {}

# ------------------------------------------------------------
# HTTP
# ------------------------------------------------------------

async def get_json(client, url, params=None, json_data=None, headers=None):
    try:
        if json_data is not None:
            response = await client.post(
                url,
                json=json_data,
                headers=headers,
            )
        else:
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
        logger.warning("Request failed: %s", e)
        return None


async def download_image(client, url):
    try:
        response = await client.get(url)

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


# ------------------------------------------------------------
# UNIQUE
# ------------------------------------------------------------

def unique_urls(urls):
    result = []
    seen = set()

    for url in urls:
        if not url:
            continue

        clean = url.split("?")[0].strip().lower()

        if clean in seen:
            continue

        seen.add(clean)
        result.append(url)

    return result


# ------------------------------------------------------------
# TMDB
# ------------------------------------------------------------

async def tmdb_images(client, name):
    if not TMDB_API_KEY:
        logger.warning("TMDB_API_KEY is missing")
        return []

    result = []

    for endpoint, media_type in (
        ("search/tv", "tv"),
        ("search/movie", "movie"),
    ):
        data = await get_json(
            client,
            f"{TMDB_URL}/{endpoint}",
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

        for item in data.get("results", [])[:5]:
            item_id = item.get("id")

            if not item_id:
                continue

            artwork = await get_json(
                client,
                f"{TMDB_URL}/{media_type}/{item_id}/images",
                params={
                    "api_key": TMDB_API_KEY,
                    "include_image_language": "en,null",
                },
            )

            if not artwork:
                continue

            for poster in artwork.get("posters", []):
                path = poster.get("file_path")

                if path:
                    result.append(
                        f"https://image.tmdb.org/t/p/original{path}"
                    )

            for backdrop in artwork.get("backdrops", []):
                path = backdrop.get("file_path")

                if path:
                    result.append(
                        f"https://image.tmdb.org/t/p/original{path}"
                    )

    return unique_urls(result)


# ------------------------------------------------------------
# FANART.TV
#
# Requires FANART_API_KEY in config.py:
#
# FANART_API_KEY = "your_key"
# ------------------------------------------------------------

async def fanart_images(client, name):
    try:
        from config import FANART_API_KEY
    except ImportError:
        return []

    if not FANART_API_KEY:
        logger.warning("FANART_API_KEY is missing")
        return []

    # First search TMDB to find the TV ID.
    data = await get_json(
        client,
        f"{TMDB_URL}/search/tv",
        params={
            "api_key": TMDB_API_KEY,
            "query": name,
            "language": "en-US",
            "page": 1,
        },
    )

    if not data:
        return []

    results = []

    for show in data.get("results", [])[:3]:
        tv_id = show.get("id")

        if not tv_id:
            continue

        url = (
            f"https://webservice.fanart.tv/v3/tv/"
            f"{tv_id}?api_key={FANART_API_KEY}"
        )

        artwork = await get_json(client, url)

        if not artwork:
            continue

        for key in (
            "tvposter",
            "tvbanner",
            "tvthumb",
            "showbackground",
            "clearart",
            "clearlogo",
        ):
            for item in artwork.get(key, []):
                image_url = item.get("url")

                if image_url:
                    results.append(image_url)

    return unique_urls(results)


# ------------------------------------------------------------
# KITSU
# ------------------------------------------------------------

async def kitsu_images(client, name):
    data = await get_json(
        client,
        f"{KITSU_URL}/anime",
        params={
            "filter[text]": name,
            "page[limit]": 10,
        },
    )

    if not data:
        return []

    results = []

    for anime in data.get("data", []):
        attributes = anime.get("attributes", {})

        poster = attributes.get("posterImage") or {}

        for key in (
            "original",
            "large",
            "medium",
        ):
            if poster.get(key):
                results.append(poster[key])
                break

        cover = attributes.get("coverImage") or {}

        for key in (
            "original",
            "large",
            "medium",
        ):
            if cover.get(key):
                results.append(cover[key])
                break

    return unique_urls(results)


# ------------------------------------------------------------
# ANILIST
# ------------------------------------------------------------

async def anilist_images(client, name):
    query = """
    query ($search: String!) {
        Media(
            search: $search,
            type: ANIME
        ) {
            coverImage {
                extraLarge
            }
            bannerImage
            trailer {
                thumbnail
            }
        }
    }
    """

    data = await get_json(
        client,
        ANILIST_URL,
        json_data={
            "query": query,
            "variables": {
                "search": name,
            },
        },
    )

    if not data:
        return []

    media = (
        data.get("data", {})
        .get("Media")
    )

    if not media:
        return []

    results = []

    cover = media.get("coverImage") or {}

    if cover.get("extraLarge"):
        results.append(
            cover["extraLarge"]
        )

    if media.get("bannerImage"):
        results.append(
            media["bannerImage"]
        )

    trailer = media.get("trailer") or {}

    if trailer.get("thumbnail"):
        results.append(
            trailer["thumbnail"]
        )

    return unique_urls(results)


# ------------------------------------------------------------
# JIKAN / MAL
# ------------------------------------------------------------

async def jikan_images(client, name):
    data = await get_json(
        client,
        f"{JIKAN_URL}/anime",
        params={
            "q": name,
            "limit": 5,
            "sfw": "true",
        },
    )

    if not data:
        return []

    results = []

    for anime in data.get("data", []):
        images = anime.get("images") or {}

        jpg = images.get("jpg") or {}

        url = (
            jpg.get("large_image_url")
            or jpg.get("image_url")
        )

        if url:
            results.append(url)

        webp = images.get("webp") or {}

        url = (
            webp.get("large_image_url")
            or webp.get("image_url")
        )

        if url:
            results.append(url)

    return unique_urls(results)


# ------------------------------------------------------------
# ANIME-PLANET
#
# Anime-Planet does not provide a simple official public API.
# This source uses its public search page and extracts artwork.
# ------------------------------------------------------------

async def animeplanet_images(client, name):
    try:
        search_url = (
            "https://www.anime-planet.com/anime/"
            + quote(name.lower().replace(" ", "-"))
        )

        response = await client.get(
            search_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36"
                )
            },
        )

        if response.status_code != 200:
            return []

        html = response.text

        patterns = [
            r'https://cdn\.anime-planet\.com/anime/[^"\']+',
            r'https://www\.anime-planet\.com/images/anime/[^"\']+',
        ]

        results = []

        for pattern in patterns:
            results.extend(
                re.findall(
                    pattern,
                    html,
                    flags=re.I,
                )
            )

        return unique_urls(results)

    except Exception as e:
        logger.warning(
            "Anime-Planet failed: %s",
            e,
        )
        return []


# ------------------------------------------------------------
# SOURCE SEARCH
# ------------------------------------------------------------

async def search_source(client, source, name):
    if source == "tmdb":
        return await tmdb_images(client, name)

    if source == "fanart":
        return await fanart_images(client, name)

    if source == "kitsu":
        return await kitsu_images(client, name)

    if source == "animeplanet":
        return await animeplanet_images(client, name)

    if source == "anilist":
        return await anilist_images(client, name)

    if source == "jikan":
        return await jikan_images(client, name)

    return []


# ------------------------------------------------------------
# COMMAND PARSER
# ------------------------------------------------------------

def parse_command(message):
    command = message.command or []

    if len(command) < 2:
        return None, None, DEFAULT_LIMIT

    args = command[1:]

    limit = DEFAULT_LIMIT

    # Last argument can be the requested number.
    if args and args[-1].isdigit():
        limit = int(args[-1])
        args = args[:-1]

    if limit < 1:
        limit = 1

    if limit > MAX_LIMIT:
        limit = MAX_LIMIT

    source = "tmdb"

    if args:
        possible_source = args[0].lower()

        if possible_source in SOURCE_ALIASES:
            source = SOURCE_ALIASES[possible_source]
            args = args[1:]

    name = " ".join(args).strip()

    return source, name, limit


# ------------------------------------------------------------
# HELP
# ------------------------------------------------------------

HELP_TEXT = """
<b>✦ /IMG COMMAND</b>

<b>Default:</b>
/img Naruto
/img Naruto 20

<b>TMDB:</b>
/img tmdb Naruto 30

<b>Fanart:</b>
/img fanart Naruto 30

<b>Kitsu:</b>
/img kitsu Naruto 30

<b>Anime-Planet:</b>
/img animeplanet Naruto 30

<b>AniList:</b>
/img anilist Naruto 10

<b>Jikan / MAL:</b>
/img jikan Naruto 10

<b>Number selection:</b>

The bot first sends numbered direct links.

Example:

1. https://example.com/image1.jpg
2. https://example.com/image2.jpg
3. https://example.com/image3.jpg

Reply with:

<code>1</code>

or:

<code>1 3 5</code>

Only the selected images will be downloaded.
"""


# ------------------------------------------------------------
# /IMG
# ------------------------------------------------------------

@Client.on_message(filters.command("img"))
async def image_command(client: Client, message: Message):

    source, anime_name, requested_limit = parse_command(message)

    if not anime_name:
        await message.reply_text(
            HELP_TEXT,
            parse_mode="html",
        )
        return

    loading = await message.reply_text(
        "✦ sᴇᴀʀᴄʜɪɴɢ ʜᴅ ᴀʀᴛᴡᴏʀᴋ..."
    )

    timeout = httpx.Timeout(
        TIMEOUT,
        connect=15,
    )

    limits = httpx.Limits(
        max_connections=15,
        max_keepalive_connections=10,
    )

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
        ) as http:

            # IMPORTANT:
            # Only ONE source is searched.
            urls = await search_source(
                http,
                source,
                anime_name,
            )

            urls = unique_urls(urls)

            # HARD LIMIT BEFORE ANYTHING IS SENT.
            urls = urls[:requested_limit]

            if not urls:
                await loading.edit_text(
                    "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ."
                )
                return

            # Store only this command's results.
            key = (
                message.chat.id,
                message.from_user.id
                if message.from_user
                else 0,
            )

            IMAGE_RESULTS[key] = urls

            # ------------------------------------------------
            # SEND NUMBERED DIRECT LINKS
            # ------------------------------------------------

            lines = []

            for index, url in enumerate(
                urls,
                start=1,
            ):
                lines.append(
                    f"{index}. {url}"
                )

            await loading.edit_text(
                "✦ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ\n\n"
                + "\n".join(lines)
                + "\n\n"
                "↳ Reply with image number(s) to download.\n"
                "Example: 1 3 5"
            )

    except Exception as e:
        logger.exception(
            "Image search failed: %s",
            e,
        )

        try:
            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ.\n\n"
                "ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ."
            )
        except Exception:
            pass


# ------------------------------------------------------------
# NUMBER SELECTION
# ------------------------------------------------------------

@Client.on_message(
    filters.text
    & ~filters.command(["img"])
)
async def image_number_selection(
    client: Client,
    message: Message,
):

    if not message.text:
        return

    text = message.text.strip()

    # Only accept numbers such as:
    # 1
    # 1 2 3
    # 1,2,3
    if not re.fullmatch(
        r"[\d,\s]+",
        text,
    ):
        return

    key = (
        message.chat.id,
        message.from_user.id
        if message.from_user
        else 0,
    )

    urls = IMAGE_RESULTS.get(key)

    if not urls:
        return

    try:
        numbers = [
            int(x)
            for x in re.findall(
                r"\d+",
                text,
            )
        ]

    except Exception:
        return

    # Remove duplicate selections.
    selected_numbers = []

    seen = set()

    for number in numbers:
        if number in seen:
            continue

        seen.add(number)
        selected_numbers.append(number)

    selected_urls = []

    for number in selected_numbers:
        if 1 <= number <= len(urls):
            selected_urls.append(
                urls[number - 1]
            )

    if not selected_urls:
        await message.reply_text(
            "❌ ɪɴᴠᴀʟɪᴅ ɪᴍᴀɢᴇ ɴᴜᴍʙᴇʀ."
        )
        return

    uploading = await message.reply_text(
        "✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs..."
    )

    timeout = httpx.Timeout(
        TIMEOUT,
        connect=15,
    )

    limits = httpx.Limits(
        max_connections=10,
        max_keepalive_connections=5,
    )

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
        ) as http:

            downloaded = await asyncio.gather(
                *[
                    download_image(
                        http,
                        url,
                    )
                    for url in selected_urls
                ],
                return_exceptions=True,
            )

        photos = []

        for data in downloaded:
            if isinstance(data, bytes):
                photos.append(data)

        if not photos:
            await uploading.edit_text(
                "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
            )
            return

        # ------------------------------------------------
        # TELEGRAM ALBUMS — MAX 10 PER ALBUM
        # ------------------------------------------------

        for start in range(
            0,
            len(photos),
            BATCH_SIZE,
        ):
            batch = photos[
                start:start + BATCH_SIZE
            ]

            media = [
                InputMediaPhoto(
                    BytesIO(data)
                )
                for data in batch
            ]

            try:
                await client.send_media_group(
                    chat_id=message.chat.id,
                    media=media,
                )

            except Exception as e:
                logger.warning(
                    "Album upload failed: %s",
                    e,
                )

                # Fallback to individual photos.
                for data in batch:
                    try:
                        await client.send_photo(
                            chat_id=message.chat.id,
                            photo=BytesIO(data),
                        )
                    except Exception as upload_error:
                        logger.warning(
                            "Photo upload failed: %s",
                            upload_error,
                        )

        # DELETE UPLOADING MESSAGE AFTER COMPLETE UPLOAD.
        try:
            await uploading.delete()
        except Exception:
            pass

        # Keep the stored links available for another selection.

    except Exception as e:
        logger.exception(
            "Image upload failed: %s",
            e,
        )

        try:
            await uploading.edit_text(
                "❌ ɪᴍᴀɢᴇ ᴜᴘʟᴏᴀᴅ ғᴀɪʟᴇᴅ."
            )
        except Exception:
            pass