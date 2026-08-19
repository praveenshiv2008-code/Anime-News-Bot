import asyncio
import logging
import re

import httpx

from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto

from config import TMDB_API_KEY

try:
    from config import FANART_API_KEY
except ImportError:
    FANART_API_KEY = ""


# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("AnimeImages")


# ============================================================
# API URLS
# ============================================================

ANILIST_URL = "https://graphql.anilist.co"

JIKAN_URL = "https://api.jikan.moe/v4"

TMDB_URL = "https://api.themoviedb.org/3"

KITSU_URL = "https://kitsu.io/api/edge"

FANART_URL = "https://webservice.fanart.tv/v3"


# ============================================================
# SETTINGS
# ============================================================

DEFAULT_LIMIT = 30

MAX_ALLOWED_LIMIT = 100

TELEGRAM_BATCH_SIZE = 10

MIN_FILE_SIZE = 5_000

REQUEST_TIMEOUT = 25


# ============================================================
# HELP MESSAGE
# ============================================================

IMG_HELP = """
✦ ɪᴍɢ ᴄᴏᴍᴍᴀɴᴅ

➜ /img Naruto
➜ /img Naruto 50

sᴏᴜʀᴄᴇ sᴇᴀʀᴄʜ:

➜ /img tmdb Naruto 30
➜ /img kitsu Naruto 30
➜ /img anilist Naruto 30
➜ /img jikan Naruto 30
➜ /img fanart Naruto 30

ᴍᴀxɪᴍᴜᴍ: 100 ɪᴍᴀɢᴇs
"""


# ============================================================
# HTTP
# ============================================================

async def get_json(
    client,
    url,
    params=None,
    json_data=None,
    headers=None
):

    try:

        if json_data is not None:

            response = await client.post(
                url,
                json=json_data,
                headers=headers
            )

        else:

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
            "Request failed: %s",
            e
        )

        return None


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
                medium
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

    cover_url = (
        cover.get("extraLarge")
        or cover.get("large")
        or cover.get("medium")
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

    return result


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
            "limit": 5,
            "sfw": "true"
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

        url = (
            jpg.get("large_image_url")
            or jpg.get("image_url")
        )

        if url:
            result.append(
                url
            )

        webp = images.get(
            "webp",
            {}
        )

        url = (
            webp.get("large_image_url")
            or webp.get("image_url")
        )

        if url:
            result.append(
                url
            )

        trailer = anime.get(
            "trailer"
        )

        if trailer:

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
                result.append(
                    trailer_url
                )

    return result


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
            "page[limit]": 10
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
            {}
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

    return result


# ============================================================
# TMDB SEARCH
# ============================================================

async def tmdb_search(
    client,
    endpoint,
    name
):

    if not TMDB_API_KEY:
        return []

    return_data = await get_json(
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

    if not return_data:
        return []

    return return_data.get(
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

    searches = [
        ("tv", "search/tv"),
        ("movie", "search/movie")
    ]

    for media_type, endpoint in searches:

        results = await tmdb_search(
            client,
            endpoint,
            name
        )

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
                        "https://image.tmdb.org"
                        "/t/p/original"
                        + path
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
                        "https://image.tmdb.org"
                        "/t/p/original"
                        + path
                    )

            # Logos

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
                        "https://image.tmdb.org"
                        "/t/p/original"
                        + path
                    )

    return result


# ============================================================
# TMDB EPISODE STILLS
# ============================================================

async def tmdb_episode_images(
    client,
    name
):

    if not TMDB_API_KEY:
        return []

    result = []

    try:

        results = await tmdb_search(
            client,
            "search/tv",
            name
        )

        for show in results[:3]:

            tv_id = show.get(
                "id"
            )

            if not tv_id:
                continue

            details = await get_json(
                client,
                f"{TMDB_URL}/tv/{tv_id}",
                params={
                    "api_key": TMDB_API_KEY,
                    "language": "en-US"
                }
            )

            if not details:
                continue

            seasons = details.get(
                "seasons",
                []
            )

            # Limit seasons to avoid
            # making hundreds of API requests.

            for season in seasons[:3]:

                season_number = season.get(
                    "season_number"
                )

                if season_number is None:
                    continue

                season_data = await get_json(
                    client,
                    f"{TMDB_URL}/tv/"
                    f"{tv_id}/season/"
                    f"{season_number}",
                    params={
                        "api_key": TMDB_API_KEY,
                        "language": "en-US"
                    }
                )

                if not season_data:
                    continue

                for episode in season_data.get(
                    "episodes",
                    []
                ):

                    still = episode.get(
                        "still_path"
                    )

                    if still:

                        result.append(
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + still
                        )

    except Exception as e:

        logger.warning(
            "TMDB episode error: %s",
            e
        )

    return result


# ============================================================
# FANART.TV
# ============================================================

async def fanart_images(
    client,
    name
):

    if not FANART_API_KEY:
        logger.info(
            "Fanart API key not configured"
        )
        return []

    result = []

    try:

        # First find TMDB IDs.

        results = await tmdb_search(
            client,
            "search/tv",
            name
        )

        results_movie = await tmdb_search(
            client,
            "search/movie",
            name
        )

        # TV

        for item in results[:3]:

            tmdb_id = item.get(
                "id"
            )

            if not tmdb_id:
                continue

            data = await get_json(
                client,
                f"{FANART_URL}/tv/"
                f"{tmdb_id}",
                params={
                    "api_key": FANART_API_KEY
                }
            )

            if data:
                result.extend(
                    extract_fanart_urls(
                        data
                    )
                )

        # Movies

        for item in results_movie[:3]:

            tmdb_id = item.get(
                "id"
            )

            if not tmdb_id:
                continue

            data = await get_json(
                client,
                f"{FANART_URL}/movies/"
                f"{tmdb_id}",
                params={
                    "api_key": FANART_API_KEY
                }
            )

            if data:
                result.extend(
                    extract_fanart_urls(
                        data
                    )
                )

    except Exception as e:

        logger.warning(
            "Fanart failed: %s",
            e
        )

    return result


def extract_fanart_urls(
    data
):

    result = []

    preferred_types = [
        "tvposter",
        "tvthumb",
        "showbackground",
        "tvbanner",
        "movieposter",
        "moviethumb",
        "moviebackground",
        "moviebanner",
        "hdclearart",
        "clearart",
        "hdlogo",
        "clearlogo"
    ]

    for artwork_type in preferred_types:

        items = data.get(
            artwork_type,
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
                result.append(
                    url
                )

    return result


# ============================================================
# UNIQUE
# ============================================================

def unique_urls(
    urls
):

    result = []

    seen = set()

    for url in urls:

        if not url:
            continue

        clean = (
            url
            .split("?")[0]
            .strip()
            .lower()
        )

        if clean in seen:
            continue

        seen.add(
            clean
        )

        result.append(
            url
        )

    return result


# ============================================================
# DOWNLOAD
# ============================================================

async def download_image(
    client,
    url
):

    try:

        response = await client.get(
            url,
            follow_redirects=True
        )

        if response.status_code != 200:
            return None

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if "image" not in content_type:
            return None

        if len(response.content) < MIN_FILE_SIZE:
            return None

        return response.content

    except Exception as e:

        logger.warning(
            "Image download failed: %s",
            e
        )

        return None


# ============================================================
# CLEAN NAME
# ============================================================

def clean_name(
    name
):

    return name.strip()


# ============================================================
# PARSE COMMAND
# ============================================================

def parse_img_command(
    message
):

    command = message.command

    if len(command) < 2:

        return None, DEFAULT_LIMIT, "all"

    args = command[1:]

    source = "all"

    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    supported_sources = {
        "tmdb",
        "kitsu",
        "anilist",
        "jikan",
        "fanart"
    }

    if args:

        possible_source = args[0].lower()

        if possible_source in supported_sources:

            source = possible_source

            args = args[1:]

    # --------------------------------------------------------
    # Number
    # --------------------------------------------------------

    requested_limit = DEFAULT_LIMIT

    if args:

        if args[-1].isdigit():

            requested_limit = int(
                args[-1]
            )

            args = args[:-1]

    # --------------------------------------------------------
    # Limit
    # --------------------------------------------------------

    if requested_limit < 1:

        requested_limit = 1

    if requested_limit > MAX_ALLOWED_LIMIT:

        requested_limit = MAX_ALLOWED_LIMIT

    name = " ".join(
        args
    ).strip()

    return (
        clean_name(name),
        requested_limit,
        source
    )


# ============================================================
# SOURCE SEARCH
# ============================================================

async def get_source_images(
    client,
    source,
    name
):

    if source == "tmdb":

        return await tmdb_images(
            client,
            name
        )

    if source == "kitsu":

        return await kitsu_images(
            client,
            name
        )

    if source == "anilist":

        return await anilist_images(
            client,
            name
        )

    if source == "jikan":

        return await jikan_images(
            client,
            name
        )

    if source == "fanart":

        return await fanart_images(
            client,
            name
        )

    # --------------------------------------------------------
    # ALL SOURCES
    # --------------------------------------------------------

    results = await asyncio.gather(

        anilist_images(
            client,
            name
        ),

        jikan_images(
            client,
            name
        ),

        kitsu_images(
            client,
            name
        ),

        tmdb_images(
            client,
            name
        ),

        tmdb_episode_images(
            client,
            name
        ),

        return_exceptions=True
    )

    urls = []

    for result in results:

        if isinstance(
            result,
            list
        ):

            urls.extend(
                result
            )

    return urls


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

    anime_name, requested_limit, source = parse_img_command(
        message
    )

    # ========================================================
    # HELP
    # ========================================================

    if not anime_name:

        await message.reply_text(
            IMG_HELP
        )

        return

    # ========================================================
    # STATUS
    # ========================================================

    loading = await message.reply_text(
        "✦ sᴇᴀʀᴄʜɪɴɢ ʜᴅ ᴀʀᴛᴡᴏʀᴋ..."
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

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits
        ) as http:

            # =================================================
            # SEARCH
            # =================================================

            await loading.edit_text(
                f"✦ sᴇᴀʀᴄʜɪɴɢ...\n\n"
                f"ᴛɪᴛʟᴇ: {anime_name}\n"
                f"sᴏᴜʀᴄᴇ: {source}\n"
                f"ʟɪᴍɪᴛ: {requested_limit}"
            )

            urls = await get_source_images(
                http,
                source,
                anime_name
            )

            # =================================================
            # UNIQUE
            # =================================================

            urls = unique_urls(
                urls
            )

            logger.info(
                "Found %s unique URLs",
                len(urls)
            )

            if not urls:

                await loading.edit_text(
                    "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ."
                )

                return

            # =================================================
            # HARD URL LIMIT
            # =================================================

            urls = urls[
                :requested_limit
            ]

            await loading.edit_text(
                f"✦ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...\n\n"
                f"ᴛᴀʀɢᴇᴛ: {len(urls)} ɪᴍᴀɢᴇs"
            )

            # =================================================
            # DOWNLOAD
            # =================================================

            downloaded = []

            for index, url in enumerate(
                urls,
                start=1
            ):

                data = await download_image(
                    http,
                    url
                )

                if data:

                    downloaded.append(
                        data
                    )

                # Progress every 5

                if (
                    index % 5 == 0
                    or index == len(urls)
                ):

                    await loading.edit_text(
                        f"✦ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs...\n\n"
                        f"ᴘʀᴏɢʀᴇss: "
                        f"{index}/{len(urls)}\n"
                        f"ᴠᴀʟɪᴅ: "
                        f"{len(downloaded)}"
                    )

            # =================================================
            # STRICT FINAL LIMIT
            # =================================================

            downloaded = downloaded[
                :requested_limit
            ]

            if not downloaded:

                await loading.edit_text(
                    "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
                )

                return

            # =================================================
            # UPLOAD
            # =================================================

            total = len(downloaded)

            await loading.edit_text(
                f"✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...\n\n"
                f"ᴘʀᴏɢʀᴇss: 0/{total}"
            )

            uploaded = 0

            # =================================================
            # TELEGRAM BATCHES
            # =================================================

            for start in range(
                0,
                total,
                TELEGRAM_BATCH_SIZE
            ):

                batch = downloaded[
                    start:
                    start + TELEGRAM_BATCH_SIZE
                ]

                media = []

                for data in batch:

                    try:

                        media.append(
                            InputMediaPhoto(
                                data
                            )
                        )

                    except Exception as e:

                        logger.warning(
                            "Media creation failed: %s",
                            e
                        )

                if not media:
                    continue

                # =================================================
                # SEND MEDIA GROUP
                # =================================================

                try:

                    await client.send_media_group(
                        chat_id=message.chat.id,
                        media=media
                    )

                    uploaded += len(
                        media
                    )

                except Exception as e:

                    logger.warning(
                        "Media group failed: %s",
                        e
                    )

                    # ------------------------------------------------
                    # Individual fallback
                    # ------------------------------------------------

                    for data in batch:

                        try:

                            await client.send_photo(
                                chat_id=message.chat.id,
                                photo=data
                            )

                            uploaded += 1

                        except Exception as photo_error:

                            logger.warning(
                                "Photo upload failed: %s",
                                photo_error
                            )

                # =================================================
                # UPDATE PROGRESS
                # =================================================

                await loading.edit_text(
                    f"✦ ᴜᴘʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...\n\n"
                    f"ᴘʀᴏɢʀᴇss: "
                    f"{uploaded}/{total}"
                )

                await asyncio.sleep(
                    0.5
                )

            # =================================================
            # FINISHED
            # =================================================

            if uploaded > requested_limit:

                uploaded = requested_limit

            await loading.edit_text(
                f"✦ ᴄᴏᴍᴘʟᴇᴛᴇᴅ\n\n"
                f"ɪᴍᴀɢᴇs: "
                f"{uploaded}/{requested_limit}\n"
                f"sᴏᴜʀᴄᴇ: {source}"
            )

            # Delete status after a few seconds.

            await asyncio.sleep(
                3
            )

            try:

                await loading.delete()

            except Exception:

                pass

    except Exception as e:

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