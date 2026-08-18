import os
import logging
import asyncio
import hashlib
from io import BytesIO

import httpx

from pyrogram.types import InputMediaPhoto


logger = logging.getLogger("AnimeImages")


# ============================================================
# CONFIG
# ============================================================

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

ANILIST_URL = "https://graphql.anilist.co"

JIKAN_URL = "https://api.jikan.moe/v4"

TMDB_URL = "https://api.themoviedb.org/3"

MIN_WIDTH = 500
MIN_HEIGHT = 500

MAX_IMAGES = 30

TIMEOUT = 30


# ============================================================
# HTTP CLIENT
# ============================================================

async def get_json(
    url,
    params=None,
    headers=None
):

    try:

        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            follow_redirects=True
        ) as client:

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

ANILIST_QUERY = """
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
    }
}
"""


async def get_anilist_images(
    anime_name
):

    images = []

    try:

        async with httpx.AsyncClient(
            timeout=TIMEOUT
        ) as client:

            response = await client.post(

                ANILIST_URL,

                json={
                    "query": ANILIST_QUERY,
                    "variables": {
                        "search": anime_name
                    }
                },

                headers={
                    "Content-Type": "application/json"
                }
            )


            if response.status_code != 200:

                return []


            data = response.json()


        media = (
            data
            .get("data", {})
            .get("Media")
        )


        if not media:

            return []


        cover = (
            media
            .get("coverImage", {})
        )


        # Highest quality first.

        for key in (
            "extraLarge",
            "large",
            "medium"
        ):

            url = cover.get(key)

            if url:

                images.append(url)


        banner = media.get(
            "bannerImage"
        )

        if banner:

            images.append(
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

                images.append(
                    thumbnail
                )


    except Exception as e:

        logger.warning(
            "AniList image search failed: %s",
            e
        )


    return images


# ============================================================
# JIKAN / MYANIMELIST
# ============================================================

async def get_jikan_images(
    anime_name
):

    images = []

    try:

        data = await get_json(

            f"{JIKAN_URL}/anime",

            params={
                "q": anime_name,
                "limit": 3,
                "sfw": "true"
            }
        )


        if not data:

            return []


        results = data.get(
            "data",
            []
        )


        # Give Jikan a moment between
        # requests to respect rate limits.

        await asyncio.sleep(
            0.5
        )


        for anime in results:

            images_data = (
                anime
                .get("images", {})
            )


            jpg = (
                images_data
                .get("jpg", {})
            )


            webp = (
                images_data
                .get("webp", {})
            )


            # Prefer large image.

            for source in (
                jpg,
                webp
            ):

                for key in (
                    "large_image_url",
                    "image_url"
                ):

                    url = source.get(key)

                    if url:

                        images.append(
                            url
                        )


            # Jikan also sometimes gives
            # trailer thumbnails.

            trailer = anime.get(
                "trailer"
            )

            if trailer:

                images_data = (
                    trailer
                    .get("images", {})
                )


                medium = (
                    images_data
                    .get("medium_image_url")
                )

                if medium:

                    images.append(
                        medium
                    )


    except Exception as e:

        logger.warning(
            "Jikan image search failed: %s",
            e
        )


    return images


# ============================================================
# TMDB SEARCH
# ============================================================

async def get_tmdb_images(
    anime_name
):

    if not TMDB_API_KEY:

        logger.warning(
            "TMDB_API_KEY is not configured."
        )

        return []


    images = []


    try:

        # ----------------------------------------------------
        # Search TV
        # ----------------------------------------------------

        tv_data = await get_json(

            f"{TMDB_URL}/search/tv",

            params={
                "api_key": TMDB_API_KEY,
                "query": anime_name,
                "language": "en-US",
                "include_adult": "false"
            }
        )


        # ----------------------------------------------------
        # Search Movie too
        # ----------------------------------------------------

        movie_data = await get_json(

            f"{TMDB_URL}/search/movie",

            params={
                "api_key": TMDB_API_KEY,
                "query": anime_name,
                "language": "en-US",
                "include_adult": "false"
            }
        )


        results = []


        if tv_data:

            results.extend(
                tv_data.get(
                    "results",
                    []
                )[:3]
            )


        if movie_data:

            results.extend(
                movie_data.get(
                    "results",
                    []
                )[:3]
            )


        # ----------------------------------------------------
        # Get artwork for each result
        # ----------------------------------------------------

        for item in results:

            media_type = (
                "tv"
                if "first_air_date"
                in item

                else "movie"
            )


            item_id = item.get(
                "id"
            )


            if not item_id:

                continue


            details = await get_json(

                f"{TMDB_URL}/"
                f"{media_type}/"
                f"{item_id}/images",

                params={
                    "api_key": TMDB_API_KEY,
                    "include_image_language":
                        "en,null"
                }
            )


            if not details:

                continue


            # ------------------------------------------------
            # Posters
            # ------------------------------------------------

            for poster in (
                details.get(
                    "posters",
                    []
                )
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
                    and width >= MIN_WIDTH
                    and height >= MIN_HEIGHT
                ):

                    images.append(

                        "https://image.tmdb.org/"
                        "t/p/original"
                        + path
                    )


            # ------------------------------------------------
            # Backdrops
            # ------------------------------------------------

            for backdrop in (
                details.get(
                    "backdrops",
                    []
                )
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
                    and width >= MIN_WIDTH
                    and height >= MIN_HEIGHT
                ):

                    images.append(

                        "https://image.tmdb.org/"
                        "t/p/original"
                        + path
                    )


    except Exception as e:

        logger.warning(
            "TMDB image search failed: %s",
            e
        )


    return images


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def unique_images(
    images
):

    result = []

    seen = set()


    for url in images:

        if not url:

            continue


        # Normalize.

        url = url.strip()


        # Remove obvious duplicates.

        clean_url = (
            url
            .split("?")[0]
            .lower()
        )


        if clean_url in seen:

            continue


        seen.add(
            clean_url
        )

        result.append(
            url
        )


    return result


# ============================================================
# CHECK IMAGE
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


        content_type = (
            response
            .headers
            .get(
                "content-type",
                ""
            )
            .lower()
        )


        if (
            "image"
            not in content_type
        ):

            return None


        data = response.content


        # Reject tiny/broken files.

        if len(data) < 10_000:

            return None


        return BytesIO(data)


    except Exception as e:

        logger.warning(
            "Image download failed: %s",
            e
        )

        return None


# ============================================================
# GET ALL IMAGES
# ============================================================

async def get_all_anime_images(
    anime_name
):

    logger.info(
        "Searching images for: %s",
        anime_name
    )


    # --------------------------------------------------------
    # Search all sources concurrently.
    # --------------------------------------------------------

    results = await asyncio.gather(

        get_anilist_images(
            anime_name
        ),

        get_jikan_images(
            anime_name
        ),

        get_tmdb_images(
            anime_name
        ),

        return_exceptions=True
    )


    all_images = []


    for result in results:

        if isinstance(
            result,
            Exception
        ):

            continue


        all_images.extend(
            result
        )


    # --------------------------------------------------------
    # Remove duplicates.
    # --------------------------------------------------------

    all_images = unique_images(
        all_images
    )


    # --------------------------------------------------------
    # Limit total images.
    # --------------------------------------------------------

    all_images = all_images[
        :MAX_IMAGES
    ]


    logger.info(
        "Found %s unique image URLs",
        len(all_images)
    )


    return all_images


# ============================================================
# DOWNLOAD ALL
# ============================================================

async def download_all_images(
    urls
):

    downloaded = []


    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True
    ) as client:

        # Download concurrently,
        # but don't overload APIs.

        semaphore = asyncio.Semaphore(
            5
        )


        async def worker(url):

            async with semaphore:

                return await download_image(
                    client,
                    url
                )


        results = await asyncio.gather(

            *[
                worker(url)
                for url in urls
            ],

            return_exceptions=True
        )


    for result in results:

        if isinstance(
            result,
            BytesIO
        ):

            result.seek(0)

            downloaded.append(
                result
            )


    return downloaded


# ============================================================
# SEND ALL IMAGES
# ============================================================

async def send_all_anime_images(
    client,
    chat_id,
    anime_name
):

    urls = await get_all_anime_images(
        anime_name
    )


    if not urls:

        return 0


    images = await download_all_images(
        urls
    )


    if not images:

        return 0


    sent = 0


    # Telegram media groups support
    # maximum 10 media items.

    for start in range(
        0,
        len(images),
        10
    ):

        batch = images[
            start:start + 10
        ]


        media = []


        for image in batch:

            media.append(
                InputMediaPhoto(
                    image
                )
            )


        try:

            await client.send_media_group(

                chat_id=chat_id,

                media=media
            )


            sent += len(
                batch
            )


        except Exception as e:

            logger.warning(
                "Media group failed: %s",
                e
            )


            # Fallback: send individually.

            for image in batch:

                try:

                    image.seek(0)


                    await client.send_photo(

                        chat_id=chat_id,

                        photo=image
                    )


                    sent += 1


                    await asyncio.sleep(
                        0.3
                    )


                except Exception as individual_error:

                    logger.warning(
                        "Individual image failed: %s",
                        individual_error
                    )


        # Avoid Telegram flood limits.

        if start + 10 < len(images):

            await asyncio.sleep(
                1
            )


    return sent