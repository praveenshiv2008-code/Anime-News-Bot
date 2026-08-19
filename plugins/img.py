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


# ============================================================
# API
# ============================================================

TMDB_URL = "https://api.themoviedb.org/3"
ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"
KITSU_URL = "https://kitsu.io/api/edge"

# ============================================================
# SETTINGS
# ============================================================

DEFAULT_LIMIT = 30
MAX_LIMIT = 100

ALBUM_SIZE = 10

MIN_FILE_SIZE = 5000

REQUEST_TIMEOUT = 25

SOURCE_ALIASES = {
    "tmdb": "tmdb",
    "fanart": "fanart",
    "kitsu": "kitsu",
    "anilist": "anilist",
    "jikan": "jikan",
    "mal": "jikan",
    "animeplanet": "animeplanet",
}


# ============================================================
# TEMP RESULT STORAGE
# ============================================================

# {
#   (chat_id, user_id): {
#       "1": url,
#       "2": url,
#       ...
#   }
# }

IMAGE_RESULTS = {}


# ============================================================
# HTTP
# ============================================================

async def get_json(
    client,
    url,
    params=None,
    json_data=None,
    headers=None,
):
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

        logger.warning(
            "HTTP request failed: %s",
            e,
        )

        return None


# ============================================================
# UNIQUE
# ============================================================

def unique_items(items):

    result = []

    seen = set()

    for item in items:

        url = item.get("url")

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

        result.append(item)

    return result


# ============================================================
# TMDB
# ============================================================

async def tmdb_images(
    client,
    name,
):

    if not TMDB_API_KEY:

        logger.warning(
            "TMDB_API_KEY is missing"
        )

        return []

    results = []

    searches = [
        ("tv", "search/tv"),
        ("movie", "search/movie"),
    ]

    for media_type, endpoint in searches:

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

        for item in data.get(
            "results",
            [],
        )[:5]:

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
                        "en,null",
                },
            )

            if not artwork:
                continue

            # ------------------------------------------------
            # POSTERS
            # ------------------------------------------------

            for image in artwork.get(
                "posters",
                [],
            ):

                path = image.get(
                    "file_path"
                )

                width = image.get(
                    "width",
                    0,
                )

                height = image.get(
                    "height",
                    0,
                )

                if (
                    path
                    and width >= 300
                    and height >= 450
                ):

                    results.append({
                        "url":
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + path,
                        "type": "poster",
                    })

            # ------------------------------------------------
            # BACKDROPS / LANDSCAPE
            # ------------------------------------------------

            for image in artwork.get(
                "backdrops",
                [],
            ):

                path = image.get(
                    "file_path"
                )

                width = image.get(
                    "width",
                    0,
                )

                height = image.get(
                    "height",
                    0,
                )

                if (
                    path
                    and width >= 500
                    and height >= 250
                ):

                    results.append({
                        "url":
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + path,
                        "type": "landscape",
                    })

            # ------------------------------------------------
            # LOGOS
            # ------------------------------------------------

            for image in artwork.get(
                "logos",
                [],
            ):

                path = image.get(
                    "file_path"
                )

                width = image.get(
                    "width",
                    0,
                )

                if (
                    path
                    and width >= 200
                ):

                    results.append({
                        "url":
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + path,
                        "type": "logo",
                    })

    return unique_items(results)


# ============================================================
# TMDB EPISODE STILLS
# ============================================================

async def tmdb_episode_images(
    client,
    name,
):

    if not TMDB_API_KEY:
        return []

    results = []

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

    for show in data.get(
        "results",
        [],
    )[:3]:

        tv_id = show.get("id")

        if not tv_id:
            continue

        details = await get_json(
            client,
            f"{TMDB_URL}/tv/{tv_id}",
            params={
                "api_key": TMDB_API_KEY,
                "language": "en-US",
            },
        )

        if not details:
            continue

        seasons = details.get(
            "seasons",
            [],
        )

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
                    "language": "en-US",
                },
            )

            if not season_data:
                continue

            for episode in season_data.get(
                "episodes",
                [],
            ):

                still = episode.get(
                    "still_path"
                )

                if still:

                    results.append({
                        "url":
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + still,
                        "type": "still",
                    })

    return unique_items(results)


# ============================================================
# FANART.TV
# ============================================================

async def fanart_images(
    client,
    name,
):

    try:

        from config import FANART_API_KEY

    except ImportError:

        logger.warning(
            "FANART_API_KEY is not configured"
        )

        return []

    if not FANART_API_KEY:

        logger.warning(
            "FANART_API_KEY is empty"
        )

        return []

    if not TMDB_API_KEY:

        return []

    search = await get_json(
        client,
        f"{TMDB_URL}/search/tv",
        params={
            "api_key": TMDB_API_KEY,
            "query": name,
            "language": "en-US",
            "page": 1,
        },
    )

    if not search:

        return []

    results = []

    for show in search.get(
        "results",
        [],
    )[:3]:

        tv_id = show.get("id")

        if not tv_id:
            continue

        data = await get_json(
            client,
            f"https://webservice.fanart.tv/v3/tv/"
            f"{tv_id}",
            params={
                "api_key": FANART_API_KEY,
            },
        )

        if not data:
            continue

        mapping = {
            "tvposter": "poster",
            "tvbanner": "landscape",
            "tvthumb": "landscape",
            "showbackground": "landscape",
            "clearlogo": "logo",
            "clearart": "other",
        }

        for key, image_type in mapping.items():

            for image in data.get(
                key,
                [],
            ):

                url = image.get("url")

                if url:

                    results.append({
                        "url": url,
                        "type": image_type,
                    })

    return unique_items(results)


# ============================================================
# KITSU
# ============================================================

async def kitsu_images(
    client,
    name,
):

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

    for anime in data.get(
        "data",
        [],
    ):

        attributes = anime.get(
            "attributes",
            {},
        )

        poster = (
            attributes.get(
                "posterImage"
            )
            or {}
        )

        url = (
            poster.get("original")
            or poster.get("large")
            or poster.get("medium")
        )

        if url:

            results.append({
                "url": url,
                "type": "poster",
            })

        cover = (
            attributes.get(
                "coverImage"
            )
            or {}
        )

        url = (
            cover.get("original")
            or cover.get("large")
            or cover.get("medium")
        )

        if url:

            results.append({
                "url": url,
                "type": "landscape",
            })

    return unique_items(results)


# ============================================================
# ANILIST
# ============================================================

async def anilist_images(
    client,
    name,
):

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

    cover = (
        media.get(
            "coverImage"
        )
        or {}
    )

    if cover.get("extraLarge"):

        results.append({
            "url":
                cover["extraLarge"],
            "type":
                "poster",
        })

    banner = media.get(
        "bannerImage"
    )

    if banner:

        results.append({
            "url": banner,
            "type": "landscape",
        })

    trailer = (
        media.get(
            "trailer"
        )
        or {}
    )

    thumbnail = trailer.get(
        "thumbnail"
    )

    if thumbnail:

        results.append({
            "url": thumbnail,
            "type": "other",
        })

    return unique_items(results)


# ============================================================
# JIKAN / MAL
# ============================================================

async def jikan_images(
    client,
    name,
):

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

    for anime in data.get(
        "data",
        [],
    ):

        images = anime.get(
            "images",
            {},
        )

        jpg = images.get(
            "jpg",
            {},
        )

        url = (
            jpg.get(
                "large_image_url"
            )
            or jpg.get(
                "image_url"
            )
        )

        if url:

            results.append({
                "url": url,
                "type": "poster",
            })

        webp = images.get(
            "webp",
            {},
        )

        url = (
            webp.get(
                "large_image_url"
            )
            or webp.get(
                "image_url"
            )
        )

        if url:

            results.append({
                "url": url,
                "type": "poster",
            })

    return unique_items(results)


# ============================================================
# ANIME-PLANET
# ============================================================

async def animeplanet_images(
    client,
    name,
):

    try:

        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            name.lower(),
        ).strip("-")

        url = (
            "https://www.anime-planet.com/anime/"
            + slug
        )

        response = await client.get(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36",
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

            for image_url in re.findall(
                pattern,
                html,
                flags=re.I,
            ):

                results.append({
                    "url":
                        image_url,
                    "type":
                        "poster",
                })

        return unique_items(results)

    except Exception as e:

        logger.warning(
            "Anime-Planet failed: %s",
            e,
        )

        return []


# ============================================================
# SOURCE SELECTOR
# ============================================================

async def search_source(
    client,
    source,
    name,
):

    if source == "tmdb":

        # TMDB source includes:
        # poster + landscape + logo
        # and episode stills.

        normal = await tmdb_images(
            client,
            name,
        )

        stills = await tmdb_episode_images(
            client,
            name,
        )

        return unique_items(
            normal + stills
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

    if source == "anilist":

        return await anilist_images(
            client,
            name,
        )

    if source == "jikan":

        return await jikan_images(
            client,
            name,
        )

    if source == "animeplanet":

        return await animeplanet_images(
            client,
            name,
        )

    return []


# ============================================================
# PARSER
# ============================================================

def parse_img_command(
    message,
):

    command = message.command or []

    if len(command) < 2:

        return None, None, DEFAULT_LIMIT

    args = command[1:]

    limit = DEFAULT_LIMIT

    # Last argument is number.

    if args and args[-1].isdigit():

        limit = int(
            args[-1]
        )

        args = args[:-1]

    limit = max(
        1,
        min(
            limit,
            MAX_LIMIT,
        ),
    )

    source = "tmdb"

    if args:

        possible_source = (
            args[0]
            .lower()
        )

        if possible_source in SOURCE_ALIASES:

            source = SOURCE_ALIASES[
                possible_source
            ]

            args = args[1:]

    name = " ".join(
        args
    ).strip()

    return source, name, limit


# ============================================================
# CATEGORY NAMES
# ============================================================

CATEGORY_NAMES = {
    "poster":
        "🖼 ᴘᴏsᴛᴇʀs",

    "landscape":
        "🌄 ʟᴀɴᴅsᴄᴀᴘᴇ",

    "still":
        "🎬 ᴇᴘɪsᴏᴅᴇ sᴛɪʟʟs",

    "logo":
        "🔰 ʟᴏɢᴏs",

    "other":
        "🖼 ᴏᴛʜᴇʀ",
}


# ============================================================
# BUILD NUMBERED MESSAGE
# ============================================================

def build_result_message(
    results,
):

    grouped = {
        "poster": [],
        "landscape": [],
        "still": [],
        "logo": [],
        "other": [],
    }

    for index, item in enumerate(
        results,
        start=1,
    ):

        item = dict(item)

        item["number"] = index

        image_type = item.get(
            "type",
            "other",
        )

        if image_type not in grouped:

            image_type = "other"

        grouped[
            image_type
        ].append(item)

    lines = [
        "✦ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ",
        "",
    ]

    for category in (
        "poster",
        "landscape",
        "still",
        "logo",
        "other",
    ):

        items = grouped[
            category
        ]

        if not items:
            continue

        lines.append(
            CATEGORY_NAMES[
                category
            ]
        )

        lines.append("")

        for item in items:

            lines.append(
                f'{item["number"]}. '
                f'{item["url"]}'
            )

        lines.append("")

    lines.append(
        "↳ ᴛʏᴘᴇ ᴛʜᴇ ɴᴜᴍʙᴇʀ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ."
    )

    lines.append(
        "ᴇxᴀᴍᴘʟᴇ: 1 3 5"
    )

    return "\n".join(lines)


# ============================================================
# HELP
# ============================================================

HELP_TEXT = """
<b>✦ /IMG</b>

<b>Default = TMDB</b>

/img Naruto
/img Naruto 30

<b>Specific source:</b>

/img tmdb Naruto 30
/img fanart Naruto 30
/img kitsu Naruto 30
/img anilist Naruto 30
/img jikan Naruto 30
/img animeplanet Naruto 30

<b>TMDB results are separated into:</b>

🖼 Posters
🌄 Landscape
🎬 Episode Stills
🔰 Logos
🖼 Other

The number is the total maximum.

Example:

/img tmdb Naruto 30

The bot will never intentionally show more than 30 results.

Reply with:

<code>1</code>

or:

<code>1 3 5</code>

to download only those images.
"""


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

    source, name, limit = (
        parse_img_command(
            message
        )
    )

    if not name:

        await message.reply_text(
            HELP_TEXT,
            parse_mode="html",
        )

        return

    loading = await message.reply_text(
        "✦ sᴇᴀʀᴄʜɪɴɢ ʜᴅ ᴀʀᴛᴡᴏʀᴋ..."
    )

    timeout = httpx.Timeout(
        REQUEST_TIMEOUT,
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
            #
            # Only ONE source is searched.
            #
            results = await search_source(
                http,
                source,
                name,
            )

        # ----------------------------------------------------
        # REMOVE DUPLICATES FIRST
        # ----------------------------------------------------

        results = unique_items(
            results
        )

        # ----------------------------------------------------
        # STRICT TOTAL LIMIT
        # ----------------------------------------------------

        results = results[
            :limit
        ]

        if not results:

            await loading.edit_text(
                "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ."
            )

            return

        # ----------------------------------------------------
        # SAVE NUMBERED LINKS
        # ----------------------------------------------------

        user_id = (
            message.from_user.id
            if message.from_user
            else 0
        )

        key = (
            message.chat.id,
            user_id,
        )

        IMAGE_RESULTS[
            key
        ] = {
            index + 1:
                item["url"]
            for index, item
            in enumerate(
                results
            )
        }

        # ----------------------------------------------------
        # SEND SEPARATED LINKS
        # ----------------------------------------------------

        result_text = (
            build_result_message(
                results
            )
        )

        await loading.edit_text(
            result_text
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


# ============================================================
# NUMBER DOWNLOAD
# ============================================================

@Client.on_message(
    filters.text
    & ~filters.command("img")
)
async def image_number_selection(
    client: Client,
    message: Message,
):

    if not message.text:
        return

    text = message.text.strip()

    # Only accept:
    #
    # 1
    # 1 2 3
    # 1,2,3

    if not re.fullmatch(
        r"[\d,\s]+",
        text,
    ):

        return

    user_id = (
        message.from_user.id
        if message.from_user
        else 0
    )

    key = (
        message.chat.id,
        user_id,
    )

    results = IMAGE_RESULTS.get(
        key
    )

    if not results:
        return

    numbers = []

    for value in re.findall(
        r"\d+",
        text,
    ):

        number = int(value)

        if number in numbers:
            continue

        numbers.append(
            number
        )

    selected_urls = []

    for number in numbers:

        url = results.get(
            number
        )

        if url:

            selected_urls.append(
                url
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
        REQUEST_TIMEOUT,
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

            if isinstance(
                data,
                bytes,
            ):

                photos.append(
                    data
                )

        if not photos:

            await uploading.edit_text(
                "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
            )

            return

        # ----------------------------------------------------
        # UPLOAD IN ALBUMS OF 10
        # ----------------------------------------------------

        for start in range(
            0,
            len(photos),
            ALBUM_SIZE,
        ):

            batch = photos[
                start:
                start + ALBUM_SIZE
            ]

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
                    media=media,
                )

            except Exception as e:

                logger.warning(
                    "Album upload failed: %s",
                    e,
                )

                # Individual fallback.

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

        # ----------------------------------------------------
        # DELETE UPLOADING MESSAGE
        # ----------------------------------------------------

        try:

            await uploading.delete()

        except Exception:

            pass

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