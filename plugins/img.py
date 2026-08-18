# plugins/img.py

import os
import asyncio
import logging
import tempfile

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
TIMEOUT = 30


# ============================================================
# JSON REQUEST
# ============================================================

async def get_json(
    client,
    url,
    params=None,
    json_data=None
):

    try:

        if json_data is not None:

            response = await client.post(
                url,
                json=json_data,
                timeout=TIMEOUT
            )

        else:

            response = await client.get(
                url,
                params=params,
                timeout=TIMEOUT
            )

        if response.status_code != 200:

            logger.warning(
                "HTTP %s: %s",
                response.status_code,
                url
            )

            return None

        return response.json()

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
            search: $search
            type: ANIME
        ) {

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

    try:

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

        # Prefer highest quality first.

        for key in (
            "extraLarge",
            "large",
            "medium"
        ):

            url = cover.get(key)

            if url:

                result.append(url)

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

    except Exception as e:

        logger.warning(
            "AniList failed: %s",
            e
        )

        return []


# ============================================================
# JIKAN / MYANIMELIST
# ============================================================

async def jikan_images(
    client,
    name
):

    try:

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

            # JPG

            jpg = images.get(
                "jpg",
                {}
            )

            for key in (
                "large_image_url",
                "image_url"
            ):

                url = jpg.get(key)

                if url:

                    result.append(
                        url
                    )

            # WEBP

            webp = images.get(
                "webp",
                {}
            )

            for key in (
                "large_image_url",
                "image_url"
            ):

                url = webp.get(key)

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

                for key in (
                    "maximum_image_url",
                    "large_image_url",
                    "medium_image_url",
                    "image_url"
                ):

                    url = trailer_images.get(
                        key
                    )

                    if url:

                        result.append(
                            url
                        )

        return result

    except Exception as e:

        logger.warning(
            "Jikan unavailable: %s",
            e
        )

        # IMPORTANT:
        # Jikan failure must NOT break /img.

        return []


# ============================================================
# TMDB
# ============================================================

async def tmdb_images(
    client,
    name
):

    if not TMDB_API_KEY:

        logger.warning(
            "TMDB API key missing"
        )

        return []

    result = []

    try:

        searches = [
            (
                "tv",
                "search/tv"
            ),
            (
                "movie",
                "search/movie"
            )
        ]

        for media_type, endpoint in searches:

            try:

                data = await get_json(

                    client,

                    f"{TMDB_URL}/{endpoint}",

                    params={
                        "api_key": TMDB_API_KEY,
                        "query": name,
                        "language": "en-US",
                        "include_adult": "false"
                    }
                )

                if not data:

                    continue

                for item in data.get(
                    "results",
                    []
                )[:3]:

                    item_id = item.get(
                        "id"
                    )

                    if not item_id:

                        continue

                    # Main poster

                    poster = item.get(
                        "poster_path"
                    )

                    if poster:

                        result.append(
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + poster
                        )

                    # Main backdrop

                    backdrop = item.get(
                        "backdrop_path"
                    )

                    if backdrop:

                        result.append(
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + backdrop
                        )

                    # Full artwork

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

                    posters = artwork.get(
                        "posters",
                        []
                    )

                    posters.sort(
                        key=lambda x:
                        x.get("width", 0)
                        * x.get("height", 0),
                        reverse=True
                    )

                    for poster in posters[:10]:

                        path = poster.get(
                            "file_path"
                        )

                        if not path:

                            continue

                        result.append(
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + path
                        )

                    # Backdrops

                    backdrops = artwork.get(
                        "backdrops",
                        []
                    )

                    backdrops.sort(
                        key=lambda x:
                        x.get("width", 0)
                        * x.get("height", 0),
                        reverse=True
                    )

                    for backdrop in backdrops[:10]:

                        path = backdrop.get(
                            "file_path"
                        )

                        if not path:

                            continue

                        result.append(
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + path
                        )

            except Exception as e:

                logger.warning(
                    "TMDB %s search failed: %s",
                    media_type,
                    e
                )

                continue

    except Exception as e:

        logger.warning(
            "TMDB failed: %s",
            e
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

        seen.add(clean)

        result.append(
            url
        )

        if len(result) >= MAX_IMAGES:

            break

    return result


# ============================================================
# DOWNLOAD
# ============================================================

async def download_image(
    client,
    url,
    path
):

    try:

        headers = {
            "User-Agent":
                "Mozilla/5.0",
            "Accept":
                "image/*,*/*;q=0.8"
        }

        async with client.stream(
            "GET",
            url,
            headers=headers,
            follow_redirects=True,
            timeout=TIMEOUT
        ) as response:

            if response.status_code != 200:

                return None

            size = 0

            with open(
                path,
                "wb"
            ) as file:

                async for chunk in response.aiter_bytes(
                    128 * 1024
                ):

                    if not chunk:

                        continue

                    file.write(
                        chunk
                    )

                    size += len(
                        chunk
                    )

            if size < MIN_FILE_SIZE:

                try:

                    os.remove(path)

                except Exception:

                    pass

                return None

            return path

    except Exception as e:

        logger.warning(
            "Download failed: %s",
            e
        )

        try:

            if os.path.exists(path):

                os.remove(path)

        except Exception:

            pass

        return None


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

    if len(message.command) < 2:

        await message.reply_text(
            "ᴜsᴀɢᴇ:\n\n"
            "/img Naruto"
        )

        return

    anime_name = " ".join(
        message.command[1:]
    ).strip()

    loading = await message.reply_text(
        "✦ sᴇᴀʀᴄʜɪɴɢ ʜɪɢʜ-ǫᴜᴀʟɪᴛʏ ᴀʀᴛᴡᴏʀᴋ..."
    )

    try:

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=TIMEOUT
        ) as http:

            # ------------------------------------------------
            # ALL SOURCES RUN INDEPENDENTLY
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

            for result in results:

                if isinstance(
                    result,
                    list
                ):

                    urls.extend(
                        result
                    )

            urls = unique_urls(
                urls
            )

            logger.info(
                "Found %s artwork URLs for %s",
                len(urls),
                anime_name
            )

            if not urls:

                await loading.edit_text(
                    "❌ ɴᴏ ɪᴍᴀɢᴇs ғᴏᴜɴᴅ."
                )

                return

            await loading.edit_text(
                f"✦ ғᴏᴜɴᴅ {len(urls)} ɪᴍᴀɢᴇs\n"
                "ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ..."
            )

            # ------------------------------------------------
            # TEMP FILES
            # ------------------------------------------------

            with tempfile.TemporaryDirectory(
                prefix="anime_images_"
            ) as temp_dir:

                tasks = []

                for index, url in enumerate(
                    urls
                ):

                    path = os.path.join(
                        temp_dir,
                        f"{index}.jpg"
                    )

                    tasks.append(
                        download_image(
                            http,
                            url,
                            path
                        )
                    )

                downloaded = await asyncio.gather(
                    *tasks,
                    return_exceptions=True
                )

                files = [
                    item
                    for item in downloaded
                    if isinstance(
                        item,
                        str
                    )
                    and os.path.exists(item)
                ]

                logger.info(
                    "Successfully downloaded %s/%s images",
                    len(files),
                    len(urls)
                )

                if not files:

                    await loading.edit_text(
                        "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ "
                        "ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
                    )

                    return

                await loading.edit_text(
                    f"✦ sᴇɴᴅɪɴɢ {len(files)} ɪᴍᴀɢᴇs..."
                )

                # ------------------------------------------------
                # SEND 10 AT A TIME
                # ------------------------------------------------

                for start in range(
                    0,
                    len(files),
                    10
                ):

                    batch = files[
                        start:start + 10
                    ]

                    media = []

                    for file_path in batch:

                        media.append(
                            InputMediaPhoto(
                                media=file_path
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

                        # Individual fallback

                        for file_path in batch:

                            try:

                                await client.send_photo(
                                    chat_id=message.chat.id,
                                    photo=file_path
                                )

                            except Exception as e2:

                                logger.warning(
                                    "Individual upload failed: %s",
                                    e2
                                )

                            await asyncio.sleep(
                                0.5
                            )

                    await asyncio.sleep(
                        1
                    )

        try:

            await loading.delete()

        except Exception:

            pass

    except Exception as e:

        logger.exception(
            "/img failed"
        )

        try:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ.\n\n"
                "ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ."
            )

        except Exception:

            pass