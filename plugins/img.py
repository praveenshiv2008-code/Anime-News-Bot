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
# API URLS
# ============================================================

ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"
TMDB_URL = "https://api.themoviedb.org/3"
KITSU_URL = "https://kitsu.io/api/edge"


# ============================================================
# SETTINGS
# ============================================================

DEFAULT_LIMIT = 30

MAX_ALLOWED_LIMIT = 100

TELEGRAM_BATCH_SIZE = 10

MIN_FILE_SIZE = 5_000

REQUEST_TIMEOUT = 25


# ============================================================
# HTTP CLIENT
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
            "Request failed %s: %s",
            url,
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

    # Only use the highest quality version.
    # Do NOT count medium/large/extraLarge
    # as different artwork.

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
# JIKAN / MYANIMELIST
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

    anime_list = data.get(
        "data",
        []
    )

    for anime in anime_list:

        images = anime.get(
            "images",
            {}
        )

        # JPG

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

        # WEBP

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

        # Trailer

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

    params = {
        "filter[text]": name,
        "page[limit]": 10
    }

    data = await get_json(
        client,
        f"{KITSU_URL}/anime",
        params=params
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

        # Prefer original/high quality.

        url = (
            poster.get("original")
            or poster.get("large")
            or poster.get("medium")
        )

        if url:

            result.append(
                url
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

        return []

    return data.get(
        "results",
        []
    )


# ============================================================
# TMDB IMAGES
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

        try:

            results = await tmdb_search(
                client,
                endpoint,
                name
            )

            # Use more matching results.

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

                # ------------------------------------------------
                # POSTERS
                # ------------------------------------------------

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

                # ------------------------------------------------
                # BACKDROPS
                # ------------------------------------------------

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

                # ------------------------------------------------
                # LOGOS
                # ------------------------------------------------

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

        except Exception as e:

            logger.warning(
                "TMDB %s failed: %s",
                media_type,
                e
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

            # Get seasons.

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

            # Only inspect a few seasons.

            for season in seasons[:5]:

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

                episodes = season_data.get(
                    "episodes",
                    []
                )

                for episode in episodes:

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
            "TMDB episode artwork failed: %s",
            e
        )

    return result


# ============================================================
# CLEAN NAME
# ============================================================

def clean_name(
    name
):

    name = re.sub(
        r"\s+\d+$",
        "",
        name
    )

    return name.strip()


# ============================================================
# UNIQUE ARTWORK
# ============================================================

def unique_urls(
    urls
):

    result = []

    seen = set()

    for url in urls:

        if not url:
            continue

        # Remove query parameters.

        clean = (
            url
            .split("?")[0]
            .strip()
            .lower()
        )

        # TMDB original/other resolution
        # should count based on file path.

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

        if len(response.content) < MIN_FILE_SIZE:

            return None

        return response.content

    except Exception:

        return None


# ============================================================
# PARSE COMMAND
# ============================================================

def parse_img_command(
    message
):

    command = message.command

    if len(command) < 2:

        return None, DEFAULT_LIMIT

    args = command[1:]

    requested_limit = DEFAULT_LIMIT

    # Check whether final argument is a number.

    if args:

        last = args[-1]

        if last.isdigit():

            requested_limit = int(
                last
            )

            args = args[:-1]

    if requested_limit < 1:

        requested_limit = 1

    if requested_limit > MAX_ALLOWED_LIMIT:

        requested_limit = MAX_ALLOWED_LIMIT

    anime_name = " ".join(
        args
    ).strip()

    anime_name = clean_name(
        anime_name
    )

    return anime_name, requested_limit


# ============================================================
# /IMG COMMAND
# ============================================================

@Client.on_message(
    filters.command("img")
)
async def image_command(
    client: Client,
    message: Message
):

    anime_name, requested_limit = parse_img_command(
        message
    )

    if not anime_name:

        await message.reply_text(
            "ᴜsᴀɢᴇ:\n\n"
            "/img Naruto\n"
            "/img Naruto 50\n"
            "/img One Piece 100"
        )

        return

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

            # ====================================================
            # SEARCH ALL SOURCES AT ONCE
            # ====================================================

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

                kitsu_images(
                    http,
                    anime_name
                ),

                tmdb_episode_images(
                    http,
                    anime_name
                ),

                return_exceptions=True
            )

            urls = []

            source_names = [
                "AniList",
                "Jikan",
                "TMDB",
                "Kitsu",
                "TMDB Episodes"
            ]

            for index, result in enumerate(
                results
            ):

                if isinstance(
                    result,
                    list
                ):

                    urls.extend(
                        result
                    )

                    logger.info(
                        "%s returned %s images",
                        source_names[index],
                        len(result)
                    )

                elif isinstance(
                    result,
                    Exception
                ):

                    logger.warning(
                        "%s failed: %s",
                        source_names[index],
                        result
                    )

            # ====================================================
            # REMOVE DUPLICATES
            # ====================================================

            urls = unique_urls(
                urls
            )

            logger.info(
                "Unique artwork found: %s",
                len(urls)
            )

            if not urls:

                await loading.edit_text(
                    "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ."
                )

                return

            # ====================================================
            # HARD LIMIT
            # ====================================================

            # This is critical.
            #
            # Even if APIs return 500 images,
            # we only process the requested amount.

            urls = urls[
                :requested_limit
            ]

            logger.info(
                "Requested: %s | Processing: %s",
                requested_limit,
                len(urls)
            )

            await loading.edit_text(
                f"✦ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ "
                f"{len(urls)} ɪᴍᴀɢᴇs..."
            )

            # ====================================================
            # DOWNLOAD
            # ====================================================

            download_tasks = []

            for url in urls:

                download_tasks.append(
                    download_image(
                        http,
                        url
                    )
                )

            downloaded = await asyncio.gather(
                *download_tasks,
                return_exceptions=True
            )

        # ========================================================
        # VALID DOWNLOADED IMAGES
        # ========================================================

        photos = []

        for data in downloaded:

            if isinstance(
                data,
                bytes
            ):

                photos.append(
                    data
                )

        # ========================================================
        # HARD LIMIT AGAIN
        #
        # Some failed downloads don't matter,
        # but we still enforce the limit here.
        # ========================================================

        photos = photos[
            :requested_limit
        ]

        if not photos:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
            )

            return

        # ========================================================
        # DELETE LOADING
        # ========================================================

        try:

            await loading.delete()

        except Exception:

            pass

        # ========================================================
        # SEND BATCHES
        #
        # Telegram media groups allow max 10 photos.
        # ========================================================

        total_sent = 0

        for start in range(
            0,
            len(photos),
            TELEGRAM_BATCH_SIZE
        ):

            batch = photos[
                start:
                start + TELEGRAM_BATCH_SIZE
            ]

            # Final safety limit.

            remaining = (
                requested_limit
                - total_sent
            )

            if remaining <= 0:

                break

            batch = batch[
                :remaining
            ]

            if not batch:

                break

            media = []

            for data in batch:

                try:

                    media.append(
                        InputMediaPhoto(
                            BytesIO(data)
                        )
                    )

                except Exception as e:

                    logger.warning(
                        "Could not prepare image: %s",
                        e
                    )

            if not media:

                continue

            try:

                await client.send_media_group(
                    chat_id=message.chat.id,
                    media=media
                )

                total_sent += len(
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

                    if total_sent >= requested_limit:

                        break

                    try:

                        await client.send_photo(
                            chat_id=message.chat.id,
                            photo=BytesIO(data)
                        )

                        total_sent += 1

                    except Exception as individual_error:

                        logger.warning(
                            "Individual image failed: %s",
                            individual_error
                        )

            # Small delay between Telegram albums.

            if total_sent < len(photos):

                await asyncio.sleep(
                    1
                )

        logger.info(
            "/img completed: %s/%s images sent for '%s'",
            total_sent,
            requested_limit,
            anime_name
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