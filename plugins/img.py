# plugins/img.py

import os
import asyncio
import logging
import tempfile
from pathlib import Path

import httpx

from pyrogram import Client, filters
from pyrogram.types import Message, InputMediaPhoto

from config import TMDB_API_KEY


logger = logging.getLogger("AnimeImages")

ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"
TMDB_URL = "https://api.themoviedb.org/3"

MAX_IMAGES = 30

# Don't reject small valid images too aggressively.
MIN_FILE_SIZE = 5_000

REQUEST_TIMEOUT = 30


# ============================================================
# HTTP GET JSON
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
                timeout=REQUEST_TIMEOUT
            )

        else:

            response = await client.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT
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
            "HTTP request failed: %s",
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

            recommendations(
                sort: RATING_DESC
                perPage: 5
            ) {
                nodes {
                    media {
                        id

                        coverImage {
                            extraLarge
                            large
                            medium
                        }

                        bannerImage
                    }
                }
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

        # ----------------------------------------------------
        # MAIN COVER
        # ----------------------------------------------------

        cover = media.get(
            "coverImage",
            {}
        )

        for key in (
            "extraLarge",
            "large",
            "medium"
        ):

            url = cover.get(key)

            if url:

                result.append(url)

        # ----------------------------------------------------
        # BANNER
        # ----------------------------------------------------

        banner = media.get(
            "bannerImage"
        )

        if banner:

            result.append(
                banner
            )

        # ----------------------------------------------------
        # TRAILER THUMBNAIL
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # RECOMMENDATION ARTWORK
        # ----------------------------------------------------

        recommendations = (
            media
            .get("recommendations", {})
            .get("nodes", [])
        )

        for node in recommendations:

            recommended = node.get(
                "media"
            )

            if not recommended:

                continue

            rec_cover = recommended.get(
                "coverImage",
                {}
            )

            for key in (
                "extraLarge",
                "large",
                "medium"
            ):

                url = rec_cover.get(key)

                if url:

                    result.append(
                        url
                    )

            rec_banner = recommended.get(
                "bannerImage"
            )

            if rec_banner:

                result.append(
                    rec_banner
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

        anime_list = data.get(
            "data",
            []
        )

        for anime in anime_list:

            images = anime.get(
                "images",
                {}
            )

            # ------------------------------------------------
            # JPG
            # ------------------------------------------------

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

            # ------------------------------------------------
            # WEBP
            # ------------------------------------------------

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

            # ------------------------------------------------
            # TRAILER
            # ------------------------------------------------

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
            "Jikan failed: %s",
            e
        )

        return []


# ============================================================
# TMDB
# ============================================================

async def tmdb_images(
    client,
    name
):

    if not TMDB_API_KEY:

        logger.info(
            "TMDB API key not configured"
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

            results = data.get(
                "results",
                []
            )

            # Use top 3 matching results.
            for item in results[:3]:

                item_id = item.get(
                    "id"
                )

                if not item_id:

                    continue

                # ------------------------------------------------
                # Main poster
                # ------------------------------------------------

                poster_path = item.get(
                    "poster_path"
                )

                if poster_path:

                    result.append(
                        "https://image.tmdb.org"
                        "/t/p/original"
                        + poster_path
                    )

                # ------------------------------------------------
                # Main backdrop
                # ------------------------------------------------

                backdrop_path = item.get(
                    "backdrop_path"
                )

                if backdrop_path:

                    result.append(
                        "https://image.tmdb.org"
                        "/t/p/original"
                        + backdrop_path
                    )

                # ------------------------------------------------
                # Full artwork
                # ------------------------------------------------

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

                posters = artwork.get(
                    "posters",
                    []
                )

                posters = sorted(
                    posters,
                    key=lambda x: (
                        x.get("width", 0)
                        * x.get("height", 0)
                    ),
                    reverse=True
                )

                for poster in posters[:10]:

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

                backdrops = artwork.get(
                    "backdrops",
                    []
                )

                backdrops = sorted(
                    backdrops,
                    key=lambda x: (
                        x.get("width", 0)
                        * x.get("height", 0)
                    ),
                    reverse=True
                )

                for backdrop in backdrops[:10]:

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

        return result

    except Exception as e:

        logger.warning(
            "TMDB failed: %s",
            e
        )

        return []


# ============================================================
# UNIQUE URLS
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

        if len(result) >= MAX_IMAGES:

            break

    return result


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

async def download_image(
    client,
    url,
    path
):

    try:

        headers = {
            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131 Safari/537.36",
            "Accept":
                "image/avif,image/webp,image/apng,"
                "image/svg+xml,image/*,*/*;q=0.8"
        }

        async with client.stream(
            "GET",
            url,
            headers=headers,
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT
        ) as response:

            if response.status_code != 200:

                logger.warning(
                    "Image HTTP %s: %s",
                    response.status_code,
                    url
                )

                return None

            content_type = response.headers.get(
                "content-type",
                ""
            ).lower()

            # Some CDNs don't return a perfect content-type.
            # Don't reject the image only because of that.

            file_size = 0

            with open(
                path,
                "wb"
            ) as file:

                async for chunk in response.aiter_bytes(
                    1024 * 128
                ):

                    if not chunk:

                        continue

                    file.write(
                        chunk
                    )

                    file_size += len(
                        chunk
                    )

            if file_size < MIN_FILE_SIZE:

                try:

                    os.remove(path)

                except Exception:

                    pass

                return None

            return path

    except Exception as e:

        logger.warning(
            "Image download failed: %s",
            e
        )

        try:

            if os.path.exists(path):

                os.remove(path)

        except Exception:

            pass

        return None


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

    if len(message.command) < 2:

        await message.reply_text(
            "ᴜsᴀɢᴇ:\n\n"
            "<code>/img Naruto</code>",
            parse_mode="html"
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
            timeout=REQUEST_TIMEOUT
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

            if not urls:

                await loading.edit_text(
                    "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ ғᴏʀ "
                    f"<b>{anime_name}</b>.",
                    parse_mode="html"
                )

                return

            await loading.edit_text(
                f"✦ ғᴏᴜɴᴅ <b>{len(urls)}</b> ɪᴍᴀɢᴇs\n"
                "ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ...",
                parse_mode="html"
            )

            # ------------------------------------------------
            # TEMP DIRECTORY
            # ------------------------------------------------

            with tempfile.TemporaryDirectory(
                prefix="anime_img_"
            ) as temp_dir:

                tasks = []

                for index, url in enumerate(
                    urls
                ):

                    extension = ".jpg"

                    lower = url.lower()

                    if ".png" in lower:

                        extension = ".png"

                    elif ".webp" in lower:

                        extension = ".webp"

                    file_path = os.path.join(
                        temp_dir,
                        f"image_{index}{extension}"
                    )

                    tasks.append(
                        download_image(
                            http,
                            url,
                            file_path
                        )
                    )

                downloaded = await asyncio.gather(
                    *tasks,
                    return_exceptions=True
                )

                files = []

                for item in downloaded:

                    if (
                        isinstance(
                            item,
                            str
                        )
                        and os.path.exists(item)
                    ):

                        files.append(
                            item
                        )

                if not files:

                    await loading.edit_text(
                        "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ "
                        "ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
                    )

                    return

                await loading.edit_text(
                    f"✦ sᴇɴᴅɪɴɢ <b>{len(files)}</b> "
                    "ʜᴅ ɪᴍᴀɢᴇs...",
                    parse_mode="html"
                )

                # ------------------------------------------------
                # TELEGRAM ALLOWS MAX 10 MEDIA ITEMS
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

                        try:

                            media.append(
                                InputMediaPhoto(
                                    media=file_path
                                )
                            )

                        except Exception as e:

                            logger.warning(
                                "Media creation failed: %s",
                                e
                            )

                    if not media:

                        continue

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

                        # ----------------------------------------
                        # INDIVIDUAL FALLBACK
                        # ----------------------------------------

                        for file_path in batch:

                            try:

                                await client.send_photo(
                                    chat_id=message.chat.id,
                                    photo=file_path
                                )

                            except Exception as individual_error:

                                logger.warning(
                                    "Individual image failed: %s",
                                    individual_error
                                )

                            await asyncio.sleep(
                                0.5
                            )

                    await asyncio.sleep(
                        1
                    )

        # ----------------------------------------------------
        # DELETE LOADING MESSAGE
        # ----------------------------------------------------

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
                f"<code>{str(e)[:500]}</code>",
                parse_mode="html"
            )

        except Exception:

            pass