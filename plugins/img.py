# plugins/img.py

import asyncio
import logging
import re
from io import BytesIO
from urllib.parse import quote

import httpx

from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto

from config import TMDB_API_KEY


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("AnimeImages")


# ============================================================
# API
# ============================================================

ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"
TMDB_URL = "https://api.themoviedb.org/3"
KITSU_URL = "https://kitsu.io/api/edge"

# Fanart.tv
FANART_URL = "https://webservice.fanart.tv/v3"

# Anime-Planet
ANIMEPLANET_SEARCH = "https://www.anime-planet.com/anime/all"


# ============================================================
# SETTINGS
# ============================================================

DEFAULT_LIMIT = 30
MAX_LIMIT = 100

ALBUM_SIZE = 10

MIN_FILE_SIZE = 5_000

REQUEST_TIMEOUT = 30

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/120.0 Mobile Safari/537.36"
)


# ============================================================
# FANART API KEY
# ============================================================
#
# Put this in config.py:
#
# FANART_API_KEY = "YOUR_FANART_API_KEY"
#
# OR put it in environment:
#
# FANART_API_KEY=xxxxxxxx
#
# This code supports both.
# ============================================================

try:
    from config import FANART_API_KEY
except Exception:
    FANART_API_KEY = None

if not FANART_API_KEY:
    FANART_API_KEY = None


# ============================================================
# HTTP
# ============================================================

async def get_response(
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

        return response

    except Exception as e:

        logger.warning(
            "HTTP error: %s",
            e
        )

        return None


async def get_json(
    client,
    url,
    params=None,
    headers=None
):

    response = await get_response(
        client,
        url,
        params=params,
        headers=headers
    )

    if response is None:
        return None

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


async def post_json(
    client,
    url,
    json_data,
    headers=None
):

    try:

        response = await client.post(
            url,
            json=json_data,
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
            "POST error: %s",
            e
        )

        return None


# ============================================================
# HELPERS
# ============================================================

def unique_urls(urls):

    result = []

    seen = set()

    for url in urls:

        if not url:
            continue

        if not isinstance(url, str):
            continue

        clean = url.strip()

        if not clean:
            continue

        # Remove query parameters.
        key = clean.split("?")[0].lower()

        if key in seen:
            continue

        seen.add(key)

        result.append(clean)

    return result


def clean_name(name):

    name = name.strip()

    # Remove accidental trailing number.
    name = re.sub(
        r"\s+\d+$",
        "",
        name
    )

    return name.strip()


def image_url_from_tmdb(path):

    if not path:
        return None

    return (
        "https://image.tmdb.org/t/p/original"
        + path
    )


def image_url_from_fanart(path):

    if not path:
        return None

    if path.startswith("http://"):
        return path

    if path.startswith("https://"):
        return path

    return "https://assets.fanart.tv" + path


# ============================================================
# ANILIST
# ============================================================

async def anilist_images(
    client,
    name
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

            trailer {
                thumbnail
            }
        }
    }
    """

    data = await post_json(
        client,
        ANILIST_URL,
        {
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

    url = (
        cover.get("extraLarge")
        or cover.get("large")
    )

    if url:
        result.append(url)

    banner = media.get(
        "bannerImage"
    )

    if banner:
        result.append(banner)

    trailer = media.get(
        "trailer"
    )

    if trailer:

        thumbnail = trailer.get(
            "thumbnail"
        )

        if thumbnail:
            result.append(thumbnail)

    return unique_urls(result)


# ============================================================
# JIKAN
# ============================================================

async def jikan_images(
    client,
    name
):

    data = await get_json(
        client,
        f"{JIKAN_URL}/anime",
        params={
            "q": name,
            "limit": 10,
            "sfw": "true"
        },
        headers={
            "User-Agent": USER_AGENT
        }
    )

    if not data:
        return []

    result = []

    for anime in data.get(
        "data",
        []
    ):

        images = anime.get(
            "images",
            {}
        )

        jpg = images.get(
            "jpg",
            {}
        )

        webp = images.get(
            "webp",
            {}
        )

        url = (
            jpg.get("large_image_url")
            or jpg.get("image_url")
            or webp.get("large_image_url")
            or webp.get("image_url")
        )

        if url:
            result.append(url)

        trailer = anime.get(
            "trailer",
            {}
        )

        trailer_images = trailer.get(
            "images",
            {}
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
    name
):

    data = await get_json(
        client,
        f"{KITSU_URL}/anime",
        params={
            "filter[text]": name,
            "page[limit]": 20
        },
        headers={
            "Accept": "application/vnd.api+json"
        }
    )

    if not data:
        return []

    result = []

    for anime in data.get(
        "data",
        []
    ):

        attributes = anime.get(
            "attributes",
            {}
        )

        poster = attributes.get(
            "posterImage",
            {}
        )

        url = (
            poster.get("original")
            or poster.get("large")
            or poster.get("medium")
        )

        if url:
            result.append(url)

        cover = attributes.get(
            "coverImage",
            {}
        )

        url = (
            cover.get("original")
            or cover.get("large")
            or cover.get("medium")
        )

        if url:
            result.append(url)

    return unique_urls(result)


# ============================================================
# TMDB SEARCH
# ============================================================

async def tmdb_search(
    client,
    endpoint,
    name,
    page=1
):

    if not TMDB_API_KEY:
        return []

    data = await get_json(
        client,
        f"{TMDB_URL}/{endpoint}",
        params={
            "api_key": TMDB_API_KEY,
            "query": name,
            "language": "en-US",
            "include_adult": "false",
            "page": page
        }
    )

    if not data:
        return []

    return data.get(
        "results",
        []
    )


# ============================================================
# TMDB
# ============================================================

async def tmdb_images(
    client,
    name
):

    if not TMDB_API_KEY:
        return []

    result = []

    # Search TV and movies.
    for media_type, endpoint in (
        ("tv", "search/tv"),
        ("movie", "search/movie")
    ):

        for page in range(1, 4):

            results = await tmdb_search(
                client,
                endpoint,
                name,
                page
            )

            if not results:
                break

            for item in results:

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
                            "en,null"
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
                        and height >= 500
                    ):

                        result.append(
                            image_url_from_tmdb(
                                path
                            )
                        )

                # Backdrops
                for backdrop in artwork.get(
                    "backdrops",
                    []
                ):

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
                        and width >= 500
                        and height >= 500
                    ):

                        result.append(
                            image_url_from_tmdb(
                                path
                            )
                        )

                # Logos are included too.
                for logo in artwork.get(
                    "logos",
                    []
                ):

                    path = logo.get(
                        "file_path"
                    )

                    width = logo.get(
                        "width",
                        0
                    )

                    if (
                        path
                        and width >= 300
                    ):

                        result.append(
                            image_url_from_tmdb(
                                path
                            )
                        )

    return unique_urls(result)


# ============================================================
# FANART.TV
# ============================================================

async def fanart_search_tmdb_id(
    client,
    name
):

    if not FANART_API_KEY:
        return None

    # Fanart.tv's movie/tv endpoints use IDs.
    # First use TMDB to identify the title.

    tv_results = await tmdb_search(
        client,
        "search/tv",
        name
    )

    if tv_results:

        return (
            "tv",
            tv_results[0].get("id")
        )

    movie_results = await tmdb_search(
        client,
        "search/movie",
        name
    )

    if movie_results:

        return (
            "movie",
            movie_results[0].get("id")
        )

    return None


async def fanart_images(
    client,
    name
):

    if not FANART_API_KEY:

        logger.warning(
            "Fanart API key not configured"
        )

        return []

    identity = await fanart_search_tmdb_id(
        client,
        name
    )

    if not identity:
        return []

    media_type, tmdb_id = identity

    if not tmdb_id:
        return []

    endpoint = (
        "tv"
        if media_type == "tv"
        else "movies"
    )

    url = (
        f"{FANART_URL}/"
        f"{endpoint}/"
        f"{tmdb_id}"
    )

    data = await get_json(
        client,
        url,
        params={
            "api_key": FANART_API_KEY
        }
    )

    if not data:
        return []

    result = []

    # Common Fanart TV artwork fields.
    artwork_fields = [
        "tvposter",
        "tvthumb",
        "showbackground",
        "tvbanner",
        "seasonposter",
        "seasonthumb",
        "clearlogo",
        "hdtvlogo",
        "clearart",
        "hdclearart",
        "characterart",
        "movieposter",
        "moviebackground",
        "moviebanner",
        "moviethumb",
        "movieart"
    ]

    for field in artwork_fields:

        items = data.get(
            field,
            []
        )

        if not isinstance(
            items,
            list
        ):
            continue

        for item in items:

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
    name
):

    # Anime-Planet does not provide a normal public
    # artwork API like TMDB/Kitsu.
    #
    # We use the search page and extract image URLs
    # from the HTML.

    try:

        search_url = (
            f"{ANIMEPLANET_SEARCH}/"
            f"?name={quote(name)}"
        )

        response = await client.get(
            search_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html"
            }
        )

        if response.status_code != 200:
            return []

        html = response.text

        result = []

        # Find image URLs in page HTML.
        patterns = [
            r'https://cdn\.anime-planet\.com/images/[^"\']+',
            r'https://www\.anime-planet\.com/images/[^"\']+',
            r'//cdn\.anime-planet\.com/images/[^"\']+'
        ]

        for pattern in patterns:

            matches = re.findall(
                pattern,
                html,
                re.IGNORECASE
            )

            for url in matches:

                if url.startswith("//"):
                    url = "https:" + url

                url = (
                    url
                    .replace("\\/", "/")
                    .replace("&amp;", "&")
                )

                result.append(url)

        return unique_urls(result)

    except Exception as e:

        logger.warning(
            "Anime-Planet failed: %s",
            e
        )

        return []


# ============================================================
# SOURCE MAP
# ============================================================

SOURCE_FUNCTIONS = {
    "tmdb": tmdb_images,
    "fanart": fanart_images,
    "animeplanet": animeplanet_images,
    "kitsu": kitsu_images,
    "anilist": anilist_images,
    "jikan": jikan_images
}


SOURCE_ALIASES = {
    "tmdb": "tmdb",
    "fanart": "fanart",
    "animeplanet": "animeplanet",
    "planet": "animeplanet",
    "kitsu": "kitsu",
    "anilist": "anilist",
    "jikan": "jikan",
    "mal": "jikan"
}


# ============================================================
# PARSE /IMG
# ============================================================

def parse_img_command(message):

    args = list(
        message.command[1:]
    )

    if not args:
        return None, None, DEFAULT_LIMIT

    source = "tmdb"

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    first = args[0].lower()

    if first in SOURCE_ALIASES:

        source = SOURCE_ALIASES[first]

        args = args[1:]

    # --------------------------------------------------------
    # LIMIT
    # --------------------------------------------------------

    requested_limit = DEFAULT_LIMIT

    if args:

        if args[-1].isdigit():

            requested_limit = int(
                args[-1]
            )

            args = args[:-1]

    if requested_limit < 1:
        requested_limit = 1

    if requested_limit > MAX_LIMIT:
        requested_limit = MAX_LIMIT

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = " ".join(
        args
    ).strip()

    title = clean_name(
        title
    )

    if not title:
        return None, None, requested_limit

    return (
        source,
        title,
        requested_limit
    )


# ============================================================
# DOWNLOAD
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

        # Telegram works better with BytesIO.
        file = BytesIO(data)

        file.name = (
            "image.jpg"
        )

        file.seek(0)

        return file

    except Exception as e:

        logger.debug(
            "Image download failed: %s",
            e
        )

        return None


# ============================================================
# DOWNLOAD EXACT NUMBER
# ============================================================

async def download_exact_images(
    client,
    urls,
    requested_limit,
    loading
):

    downloaded = []

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Never download/send more than requested_limit.
    # --------------------------------------------------------

    urls = unique_urls(
        urls
    )

    checked = 0

    for index, url in enumerate(urls):

        if len(downloaded) >= requested_limit:
            break

        checked += 1

        image = await download_image(
            client,
            url
        )

        if image is not None:

            downloaded.append(
                image
            )

        # Update occasionally.
        if (
            checked % 5 == 0
            or len(downloaded) == requested_limit
        ):

            try:

                await loading.edit_text(
                    "✦ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs...\n\n"
                    f"✓ {len(downloaded)}/{requested_limit}"
                )

            except Exception:
                pass

    return downloaded


# ============================================================
# SEND ALBUMS
# ============================================================

async def send_albums(
    client,
    chat_id,
    images,
    loading
):

    total = len(images)

    sent = 0

    # --------------------------------------------------------
    # ALWAYS SEND MAX 10 PER ALBUM
    # --------------------------------------------------------

    for start in range(
        0,
        total,
        ALBUM_SIZE
    ):

        batch = images[
            start:start + ALBUM_SIZE
        ]

        media = []

        for image in batch:

            image.seek(0)

            media.append(
                InputMediaPhoto(
                    image
                )
            )

        try:

            await loading.edit_text(
                "✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...\n\n"
                f"↑ {sent}/{total}"
            )

        except Exception:
            pass

        try:

            await client.send_media_group(
                chat_id=chat_id,
                media=media
            )

            sent += len(batch)

        except Exception as e:

            logger.warning(
                "Album upload failed: %s",
                e
            )

            # Individual fallback.
            for image in batch:

                try:

                    image.seek(0)

                    await client.send_photo(
                        chat_id,
                        image
                    )

                    sent += 1

                except Exception as upload_error:

                    logger.warning(
                        "Single upload failed: %s",
                        upload_error
                    )

        await asyncio.sleep(1)

    return sent


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

    source, title, requested_limit = (
        parse_img_command(
            message
        )
    )

    # --------------------------------------------------------
    # EMPTY COMMAND
    # --------------------------------------------------------

    if not title:

        await message.reply_text(
            "✦ ᴜsᴀɢᴇ ᴏғ /ɪᴍɢ\n\n"

            "ᴅᴇғᴀᴜʟᴛ — ᴛᴍᴅʙ\n"
            "/img Naruto\n"
            "/img Naruto 30\n\n"

            "sᴏᴜʀᴄᴇs\n"
            "/img tmdb Naruto 30\n"
            "/img fanart Naruto 30\n"
            "/img animeplanet Naruto 30\n"
            "/img kitsu Naruto 30\n"
            "/img anilist Naruto 30\n"
            "/img jikan Naruto 30\n\n"

            "ᴍᴀxɪᴍᴜᴍ: "
            f"{MAX_LIMIT} ɪᴍᴀɢᴇs\n\n"

            "ᴏɴʟʏ ᴏɴᴇ sᴏᴜʀᴄᴇ ɪs ᴜsᴇᴅ ᴘᴇʀ ᴄᴏᴍᴍᴀɴᴅ."
        )

        return

    loading = await message.reply_text(
        "✦ sᴇᴀʀᴄʜɪɴɢ...\n\n"
        f"◈ sᴏᴜʀᴄᴇ: {source.upper()}\n"
        f"◈ ᴛɪᴛʟᴇ: {title}\n"
        f"◈ ʟɪᴍɪᴛ: {requested_limit}"
    )

    try:

        timeout = httpx.Timeout(
            REQUEST_TIMEOUT,
            connect=15
        )

        limits = httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10
        )

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*"
        }

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
            headers=headers
        ) as http:

            # ------------------------------------------------
            # ONLY ONE SOURCE IS CALLED
            # ------------------------------------------------

            source_function = (
                SOURCE_FUNCTIONS.get(
                    source
                )
            )

            if not source_function:

                await loading.edit_text(
                    "❌ ᴜɴᴋɴᴏᴡɴ sᴏᴜʀᴄᴇ."
                )

                return

            await loading.edit_text(
                "✦ sᴇᴀʀᴄʜɪɴɢ...\n\n"
                f"◈ sᴏᴜʀᴄᴇ: {source.upper()}\n"
                f"◈ ʟɪᴍɪᴛ: {requested_limit}"
            )

            try:

                urls = await source_function(
                    http,
                    title
                )

            except Exception as e:

                logger.exception(
                    "%s source failed",
                    source
                )

                urls = []

            # ------------------------------------------------
            # REMOVE DUPLICATES FIRST
            # ------------------------------------------------

            urls = unique_urls(
                urls
            )

            logger.info(
                "[IMG] %s returned %s unique URLs",
                source,
                len(urls)
            )

            if not urls:

                await loading.edit_text(
                    "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ.\n\n"
                    f"◈ sᴏᴜʀᴄᴇ: {source.upper()}\n"
                    f"◈ ᴛɪᴛʟᴇ: {title}"
                )

                return

            # ------------------------------------------------
            # DOWNLOAD ONLY WHAT IS NEEDED
            # ------------------------------------------------

            images = await download_exact_images(
                http,
                urls,
                requested_limit,
                loading
            )

        # ----------------------------------------------------
        # STRICT RESULT
        # ----------------------------------------------------

        if not images:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
            )

            return

        # ----------------------------------------------------
        # SEND ALBUMS
        # ----------------------------------------------------

        await loading.edit_text(
            "✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...\n\n"
            f"↑ 0/{len(images)}"
        )

        sent = await send_albums(
            client,
            message.chat.id,
            images,
            loading
        )

        # ----------------------------------------------------
        # DONE
        # ----------------------------------------------------

        try:

            await loading.edit_text(
                "✓ ᴅᴏɴᴇ\n\n"
                f"◈ sᴏᴜʀᴄᴇ: {source.upper()}\n"
                f"◈ ᴛɪᴛʟᴇ: {title}\n"
                f"◈ sᴇɴᴛ: {sent}/{requested_limit}"
            )

        except Exception:
            pass

        # Delete status after a few seconds.
        await asyncio.sleep(3)

        try:
            await loading.delete()
        except Exception:
            pass

    except Exception:

        logger.exception(
            "Fatal /img error"
        )

        try:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ.\n\n"
                "ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ."
            )

        except Exception:
            pass