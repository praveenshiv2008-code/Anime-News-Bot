import asyncio
import hashlib
import logging
from io import BytesIO

import httpx

from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto

from config import TMDB_API_KEY


logger = logging.getLogger("AnimeImages")

ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"
TMDB_URL = "https://api.themoviedb.org/3"

MAX_IMAGES = 30
MIN_FILE_SIZE = 5_000

# How many images we try to take from each source
ANILIST_LIMIT = 6
JIKAN_LIMIT = 8
TMDB_LIMIT = 16


# ============================================================
# HTTP CLIENT
# ============================================================

async def get_json(
    client,
    url,
    params=None,
    json_data=None,
    retries=2
):
    for attempt in range(retries + 1):

        try:

            if json_data is not None:
                response = await client.post(
                    url,
                    json=json_data
                )
            else:
                response = await client.get(
                    url,
                    params=params
                )

            if response.status_code == 200:
                return response.json()

            logger.warning(
                "HTTP %s: %s",
                response.status_code,
                url
            )

            # Don't waste time retrying 404
            if response.status_code == 404:
                return None

        except Exception as e:

            logger.warning(
                "HTTP error: %s",
                e
            )

        if attempt < retries:
            await asyncio.sleep(1.5 * (attempt + 1))

    return None


# ============================================================
# URL NORMALIZATION
# ============================================================

def normalize_url(url):
    if not url:
        return None

    url = url.strip()

    if not url.startswith("http"):
        return None

    # Remove query parameters
    url = url.split("?")[0]

    return url


# ============================================================
# IMAGE FINGERPRINT
# ============================================================

def image_fingerprint(data):
    """
    Create a fingerprint from downloaded image bytes.

    This removes exact duplicate images even when they
    come from different URLs.
    """

    if not data:
        return None

    try:
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return None


# ============================================================
# ANILIST
# ============================================================

async def anilist_images(client, name):

    query = """
    query ($search: String!) {

        Media(
            search: $search
            type: ANIME
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
                "search": name
            }
        }
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
        {}
    )

    # IMPORTANT:
    # Don't add large + extraLarge because they
    # are usually the SAME artwork.

    if cover.get("extraLarge"):
        result.append(
            cover["extraLarge"]
        )
    elif cover.get("large"):
        result.append(
            cover["large"]
        )

    banner = media.get(
        "bannerImage"
    )

    if banner:
        result.append(
            banner
        )

    trailer = media.get(
        "trailer"
    )

    if trailer:

        thumbnail = trailer.get(
            "thumbnail"
        )

        if thumbnail:
            result.append(
                thumbnail
            )

    return result[:ANILIST_LIMIT]


# ============================================================
# JIKAN / MYANIMELIST
# ============================================================

async def jikan_images(client, name):

    data = await get_json(
        client,
        f"{JIKAN_URL}/anime",
        params={
            "q": name,
            "limit": 3,
            "sfw": "true"
        },
        retries=2
    )

    if not data:
        return []

    result = []

    anime_list = data.get(
        "data",
        []
    )

    for anime in anime_list:

        images = anime.get(
            "images",
            {}
        )

        # Prefer WebP because it is usually cleaner/smaller.
        webp = images.get(
            "webp",
            {}
        )

        jpg = images.get(
            "jpg",
            {}
        )

        image_url = (
            webp.get("large_image_url")
            or webp.get("image_url")
            or jpg.get("large_image_url")
            or jpg.get("image_url")
        )

        if image_url:
            result.append(
                image_url
            )

        # Trailer thumbnail
        trailer = anime.get(
            "trailer"
        )

        if trailer:

            trailer_images = trailer.get(
                "images",
                {}
            )

            thumbnail = (
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

            if thumbnail:
                result.append(
                    thumbnail
                )

    return result[:JIKAN_LIMIT]


# ============================================================
# TMDB
# ============================================================

async def tmdb_images(client, name):

    if not TMDB_API_KEY:
        logger.warning(
            "TMDB API key is not configured"
        )
        return []

    result = []

    searches = [
        ("tv", "search/tv"),
        ("movie", "search/movie")
    ]

    for media_type, endpoint in searches:

        data = await get_json(
            client,
            f"{TMDB_URL}/{endpoint}",
            params={
                "api_key": TMDB_API_KEY,
                "query": name,
                "language": "en-US",
                "include_adult": "false"
            },
            retries=1
        )

        if not data:
            continue

        results = data.get(
            "results",
            []
        )

        # Only take the best first result.
        # This prevents unrelated Naruto movies/shows
        # from filling the album.
        for item in results[:1]:

            item_id = item.get(
                "id"
            )

            if not item_id:
                continue

            artwork = await get_json(
                client,
                f"{TMDB_URL}/{media_type}/{item_id}/images",
                params={
                    "api_key": TMDB_API_KEY,
                    "include_image_language": "en,null"
                },
                retries=1
            )

            if not artwork:
                continue

            # ------------------------------------------------
            # POSTERS
            # ------------------------------------------------

            posters = artwork.get(
                "posters",
                []
            )

            for poster in posters[:8]:

                path = poster.get(
                    "file_path"
                )

                width = poster.get(
                    "width",
                    0
                )

                height = poster.get(
                    "height",
                    0
                )

                if (
                    path
                    and width >= 500
                    and height >= 700
                ):

                    result.append(
                        "https://image.tmdb.org/t/p/original"
                        + path
                    )

            # ------------------------------------------------
            # BACKDROPS
            # ------------------------------------------------

            backdrops = artwork.get(
                "backdrops",
                []
            )

            for backdrop in backdrops[:8]:

                path = backdrop.get(
                    "file_path"
                )

                width = backdrop.get(
                    "width",
                    0
                )

                height = backdrop.get(
                    "height",
                    0
                )

                if (
                    path
                    and width >= 1000
                    and height >= 500
                ):

                    result.append(
                        "https://image.tmdb.org/t/p/original"
                        + path
                    )

    return result[:TMDB_LIMIT]


# ============================================================
# URL UNIQUE
# ============================================================

def unique_urls(urls):

    result = []

    seen = set()

    for url in urls:

        url = normalize_url(url)

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)

        result.append(url)

    return result


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

        if "image" not in content_type:
            return None

        data = response.content

        if len(data) < MIN_FILE_SIZE:
            return None

        return data

    except Exception as e:

        logger.debug(
            "Image download failed: %s",
            e
        )

        return None


# ============================================================
# DOWNLOAD UNIQUE IMAGES
# ============================================================

async def download_unique_images(
    client,
    urls
):

    photos = []

    fingerprints = set()

    # We still process URLs concurrently,
    # but keep a strict MAX_IMAGES limit.

    tasks = [
        download_image(
            client,
            url
        )
        for url in urls
    ]

    downloaded = await asyncio.gather(
        *tasks,
        return_exceptions=True
    )

    for data in downloaded:

        if not isinstance(
            data,
            bytes
        ):
            continue

        fingerprint = image_fingerprint(
            data
        )

        if not fingerprint:
            continue

        # Exact duplicate image
        if fingerprint in fingerprints:
            continue

        fingerprints.add(
            fingerprint
        )

        photos.append(
            data
        )

        # HARD LIMIT
        if len(photos) >= MAX_IMAGES:
            break

    return photos


# ============================================================
# /IMG
# ============================================================

@Client.on_message(
    filters.command(
        "img"
    )
)
async def image_command(
    client: Client,
    message: Message
):

    if len(message.command) < 2:

        await message.reply_text(
            "ᴜsᴀɢᴇ:\n\n"
            "/img Naruto"
        )

        return

    anime_name = " ".join(
        message.command[1:]
    ).strip()

    if not anime_name:

        await message.reply_text(
            "❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀɴ ᴀɴɪᴍᴇ ɴᴀᴍᴇ."
        )

        return

    loading = await message.reply_text(
        "✦ sᴇᴀʀᴄʜɪɴɢ ʜᴅ ᴀʀᴛᴡᴏʀᴋ..."
    )

    try:

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": "AnimeNewsBot/1.0"
            }
        ) as http:

            # ------------------------------------------------
            # SEARCH ALL SOURCES
            # ------------------------------------------------

            results = await asyncio.gather(

                anilist_images(
                    http,
                    anime_name
                ),

                jikan_images(
                    http,
                    anime_name
                ),

                tmdb_images(
                    http,
                    anime_name
                ),

                return_exceptions=True
            )

            urls = []

            # Keep source order:
            # AniList → Jikan → TMDB

            for result in results:

                if isinstance(
                    result,
                    list
                ):

                    urls.extend(
                        result
                    )

            # ------------------------------------------------
            # REMOVE DUPLICATE URLS
            # ------------------------------------------------

            urls = unique_urls(
                urls
            )

            # HARD URL LIMIT
            urls = urls[
                :MAX_IMAGES
            ]

            if not urls:

                await loading.edit_text(
                    "❌ ɴᴏ ɪᴍᴀɢᴇs ғᴏᴜɴᴅ."
                )

                return

            await loading.edit_text(
                "✦ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ʜᴅ ᴀʀᴛᴡᴏʀᴋ..."
            )

            # ------------------------------------------------
            # DOWNLOAD
            # ------------------------------------------------

            photos = await download_unique_images(
                http,
                urls
            )

        # ----------------------------------------------------
        # NOTHING DOWNLOADED
        # ----------------------------------------------------

        if not photos:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
            )

            return

        # ----------------------------------------------------
        # ABSOLUTE FINAL LIMIT
        # ----------------------------------------------------

        photos = photos[
            :MAX_IMAGES
        ]

        count = len(
            photos
        )

        try:
            await loading.delete()
        except Exception:
            pass

        # ----------------------------------------------------
        # SEND ALBUMS
        # Telegram allows maximum 10 media items
        # per media group.
        # ----------------------------------------------------

        for start in range(
            0,
            count,
            10
        ):

            batch = photos[
                start:start + 10
            ]

            if not batch:
                continue

            media = []

            for data in batch:

                media.append(
                    InputMediaPhoto(
                        BytesIO(data)
                    )
                )

            try:

                await client.send_media_group(
                    chat_id=message.chat.id,
                    media=media
                )

            except Exception as e:

                logger.warning(
                    "Media group failed: %s",
                    e
                )

                # ------------------------------------------------
                # FALLBACK
                # ------------------------------------------------

                for data in batch:

                    try:

                        await client.send_photo(
                            chat_id=message.chat.id,
                            photo=BytesIO(data)
                        )

                    except Exception as photo_error:

                        logger.warning(
                            "Individual image failed: %s",
                            photo_error
                        )

            # Small delay between albums
            if start + 10 < count:

                await asyncio.sleep(
                    1
                )

        logger.info(
            "✅ /img '%s' → sent %s image(s)",
            anime_name,
            count
        )

    except Exception:

        logger.exception(
            "Fatal /img error"
        )

        try:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ."
            )

        except Exception:
            pass