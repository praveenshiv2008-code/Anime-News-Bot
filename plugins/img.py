import os
import asyncio
import logging

import httpx

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InputMediaPhoto
)

from config import TMDB_API_KEY


logger = logging.getLogger("AnimeImages")


ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"
TMDB_URL = "https://api.themoviedb.org/3"

MAX_IMAGES = 30

MIN_FILE_SIZE = 10_000


# ============================================================
# HTTP
# ============================================================

async def get_json(
    url,
    params=None,
    json_data=None
):

    try:

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True
        ) as session:

            response = await session.get(
                url,
                params=params
            ) if json_data is None else await session.post(
                url,
                json=json_data
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
            "HTTP error: %s",
            e
        )

        return None


# ============================================================
# ANILIST
# ============================================================

async def anilist_images(
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

    try:

        data = await get_json(

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


        for key in (
            "extraLarge",
            "large",
            "medium"
        ):

            if cover.get(key):

                result.append(
                    cover[key]
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
    name
):

    try:

        data = await get_json(

            f"{JIKAN_URL}/anime",

            params={
                "q": name,
                "limit": 3,
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


            for source in (
                images.get("jpg", {}),
                images.get("webp", {})
            ):

                for key in (
                    "large_image_url",
                    "image_url"
                ):

                    url = source.get(
                        key
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


                thumbnail = trailer_images.get(
                    "medium_image_url"
                )


                if thumbnail:

                    result.append(
                        thumbnail
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
            ("tv", "search/tv"),
            ("movie", "search/movie")
        ]


        for media_type, endpoint in searches:

            data = await get_json(

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


                artwork = await get_json(

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
                )[:10]:

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
                )[:10]:

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


    return result[:MAX_IMAGES]


# ============================================================
# CHECK IMAGE
# ============================================================

async def valid_image(
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
            "<code>/img Naruto</code>",
            parse_mode="html"
        )

        return


    anime_name = " ".join(
        message.command[1:]
    ).strip()


    loading = await message.reply_text(
        "✦ sᴇᴀʀᴄʜɪɴɢ ʜᴅ ᴀʀᴛᴡᴏʀᴋ..."
    )


    try:

        results = await asyncio.gather(

            anilist_images(
                anime_name
            ),

            jikan_images(
                anime_name
            ),

            tmdb_images(
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
                "❌ ɴᴏ ʜɪɢʜ-ǫᴜᴀʟɪᴛʏ ɪᴍᴀɢᴇs ғᴏᴜɴᴅ."
            )

            return


        await loading.edit_text(
            "✦ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ɪᴍᴀɢᴇs..."
        )


        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True
        ) as http:

            tasks = [
                valid_image(
                    http,
                    url
                )
                for url in urls
            ]


            downloaded = await asyncio.gather(
                *tasks,
                return_exceptions=True
            )


        photos = []


        for data in downloaded:

            if isinstance(
                data,
                bytes
            ):

                photos.append(
                    data
                )


        if not photos:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
            )

            return


        await loading.delete()


        # Telegram media groups:
        # maximum 10 images.

        for start in range(
            0,
            len(photos),
            10
        ):

            batch = photos[
                start:start + 10
            ]


            media = []


            for data in batch:

                media.append(
                    InputMediaPhoto(
                        data
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

                for data in batch:

                    try:

                        await client.send_photo(
                            message.chat.id,
                            data
                        )

                    except Exception:

                        pass


            await asyncio.sleep(
                1
            )


    except Exception as e:

        logger.exception(
            "Image command error"
        )


        try:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ."
            )

        except Exception:

            pass