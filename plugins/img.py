import asyncio
import logging
import re
from io import BytesIO
from urllib.parse import quote, urljoin

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

FANART_URL = "https://webservice.fanart.tv/v3"
ANIMEPLANET_URL = "https://www.anime-planet.com"


# ============================================================
# OPTIONAL API KEYS
# ============================================================

# Add these to config.py if you have them.
#
# FANART_API_KEY = "YOUR_FANART_API_KEY"
#
# They are optional. The command will simply skip Fanart.tv
# if no key is configured.

try:
    from config import FANART_API_KEY
except ImportError:
    FANART_API_KEY = ""


# ============================================================
# SETTINGS
# ============================================================

DEFAULT_LIMIT = 30

MAX_ALLOWED_LIMIT = 100

TELEGRAM_BATCH_SIZE = 10

MIN_FILE_SIZE = 5_000

REQUEST_TIMEOUT = 25


# ============================================================
# SOURCE ALIASES
# ============================================================

SOURCE_ALIASES = {
    "tmdb": "tmdb",
    "themoviedb": "tmdb",

    "anilist": "anilist",
    "ani": "anilist",

    "mal": "jikan",
    "jikan": "jikan",

    "kitsu": "kitsu",

    "fanart": "fanart",
    "fanarttv": "fanart",

    "animeplanet": "animeplanet",
    "planet": "animeplanet",

    "all": "all",
}


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

        try:

            return response.json()

        except Exception:

            return None

    except Exception as e:

        logger.warning(
            "Request failed %s: %s",
            url,
            e,
        )

        return None


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
            id

            title {
                romaji
                english
                native
            }

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
        data
        .get("data", {})
        .get("Media")
    )

    if not media:
        return []

    result = []

    cover = media.get(
        "coverImage",
        {},
    )

    cover_url = cover.get(
        "extraLarge"
    )

    if cover_url:
        result.append(cover_url)

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

    return result


# ============================================================
# JIKAN / MYANIMELIST
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
            "limit": 10,
            "sfw": "true",
        },
    )

    if not data:
        return []

    result = []

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
            jpg.get("large_image_url")
            or jpg.get("image_url")
        )

        if url:
            result.append(url)

        webp = images.get(
            "webp",
            {},
        )

        url = (
            webp.get("large_image_url")
            or webp.get("image_url")
        )

        if url:
            result.append(url)

        trailer = anime.get(
            "trailer"
        )

        if trailer:

            trailer_images = trailer.get(
                "images",
                {},
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

    return result


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

    result = []

    for anime in data.get(
        "data",
        [],
    ):

        attributes = anime.get(
            "attributes",
            {},
        )

        poster = attributes.get(
            "posterImage",
            {},
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
            {},
        )

        cover_url = (
            cover.get("original")
            or cover.get("large")
            or cover.get("medium")
        )

        if cover_url:
            result.append(cover_url)

    return result


# ============================================================
# TMDB SEARCH
# ============================================================

async def tmdb_search(
    client,
    endpoint,
    name,
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
            "page": 1,
        },
    )

    if not return_data:
        return []

    return return_data.get(
        "results",
        [],
    )


# ============================================================
# TMDB IMAGES
# ============================================================

async def tmdb_images(
    client,
    name,
):

    if not TMDB_API_KEY:
        return []

    result = []

    searches = [
        ("tv", "search/tv"),
        ("movie", "search/movie"),
    ]

    for media_type, endpoint in searches:

        try:

            results = await tmdb_search(
                client,
                endpoint,
                name,
            )

            for item in results[:5]:

                item_id = item.get("id")

                if not item_id:
                    continue

                artwork = await get_json(
                    client,
                    f"{TMDB_URL}/{media_type}/"
                    f"{item_id}/images",
                    params={
                        "api_key": TMDB_API_KEY,
                        "include_image_language":
                            "en,null",
                    },
                )

                if not artwork:
                    continue

                # Posters

                for poster in artwork.get(
                    "posters",
                    [],
                ):

                    path = poster.get(
                        "file_path"
                    )

                    width = poster.get(
                        "width",
                        0,
                    )

                    height = poster.get(
                        "height",
                        0,
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
                    [],
                ):

                    path = backdrop.get(
                        "file_path"
                    )

                    width = backdrop.get(
                        "width",
                        0,
                    )

                    height = backdrop.get(
                        "height",
                        0,
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
                    [],
                ):

                    path = logo.get(
                        "file_path"
                    )

                    width = logo.get(
                        "width",
                        0,
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
                e,
            )

    return result


# ============================================================
# TMDB EPISODE STILLS
# ============================================================

async def tmdb_episode_images(
    client,
    name,
):

    if not TMDB_API_KEY:
        return []

    result = []

    try:

        results = await tmdb_search(
            client,
            "search/tv",
            name,
        )

        for show in results[:2]:

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

                        result.append(
                            "https://image.tmdb.org"
                            "/t/p/original"
                            + still
                        )

    except Exception as e:

        logger.warning(
            "TMDB episodes failed: %s",
            e,
        )

    return result


# ============================================================
# FANART.TV
# ============================================================

async def fanart_images(
    client,
    name,
):

    if not FANART_API_KEY:

        logger.info(
            "Fanart.tv skipped - no API key"
        )

        return []

    result = []

    try:

        # Search TMDB first to obtain TV information.

        results = await tmdb_search(
            client,
            "search/tv",
            name,
        )

        for show in results[:3]:

            tv_id = show.get(
                "id"
            )

            if not tv_id:
                continue

            external = await get_json(
                client,
                f"{TMDB_URL}/tv/"
                f"{tv_id}/external_ids",
                params={
                    "api_key": TMDB_API_KEY,
                },
            )

            if not external:
                continue

            tvdb_id = external.get(
                "tvdb_id"
            )

            if not tvdb_id:
                continue

            data = await get_json(
                client,
                f"{FANART_URL}/tv/{tvdb_id}",
                headers={
                    "api-key": FANART_API_KEY,
                },
            )

            if not data:
                continue

            image_groups = [
                "tvposter",
                "tvbanner",
                "tvthumb",
                "tvlogo",
                "showbackground",
                "clearart",
                "clearlogo",
            ]

            for group in image_groups:

                for image in data.get(
                    group,
                    [],
                ):

                    url = image.get(
                        "url"
                    )

                    if url:
                        result.append(url)

    except Exception as e:

        logger.warning(
            "Fanart failed: %s",
            e,
        )

    return result


# ============================================================
# ANIME-PLANET
# ============================================================

async def animeplanet_images(
    client,
    name,
):

    result = []

    try:

        search_url = (
            f"{ANIMEPLANET_URL}/anime/"
            f"all?name={quote(name)}"
        )

        headers = {
            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36",
            "Accept":
                "text/html,application/xhtml+xml",
        }

        response = await client.get(
            search_url,
            headers=headers,
        )

        if response.status_code != 200:
            return []

        html = response.text

        # Find og:image

        matches = re.findall(
            r'<meta[^>]+property=["\']og:image["\']'
            r'[^>]+content=["\']([^"\']+)',
            html,
            flags=re.I,
        )

        for url in matches:

            result.append(
                urljoin(
                    ANIMEPLANET_URL,
                    url,
                )
            )

        # Search common image attributes.

        image_matches = re.findall(
            r'<img[^>]+(?:src|data-src)=["\']'
            r'([^"\']+)',
            html,
            flags=re.I,
        )

        for url in image_matches:

            if (
                "anime-planet.com"
                not in url
                and url.startswith("//")
            ):

                url = "https:" + url

            elif url.startswith("/"):

                url = urljoin(
                    ANIMEPLANET_URL,
                    url,
                )

            if url.startswith("http"):

                result.append(url)

    except Exception as e:

        logger.warning(
            "Anime-Planet failed: %s",
            e,
        )

    return result


# ============================================================
# CLEAN NAME
# ============================================================

def clean_name(
    name,
):

    name = re.sub(
        r"\s+\d+$",
        "",
        name,
    )

    return name.strip()


# ============================================================
# UNIQUE URLS
# ============================================================

def unique_urls(
    urls,
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

        result.append(url)

    return result


# ============================================================
# DOWNLOAD
# ============================================================

async def download_image(
    client,
    url,
):

    try:

        response = await client.get(
            url,
        )

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

        logger.debug(
            "Download failed: %s",
            e,
        )

        return None


# ============================================================
# COMMAND PARSER
# ============================================================

def parse_img_command(
    message,
):

    command = message.command

    if len(command) < 2:

        return (
            None,
            DEFAULT_LIMIT,
            "all",
        )

    args = command[1:]

    source = "all"

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

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

    requested_limit = max(
        1,
        min(
            requested_limit,
            MAX_ALLOWED_LIMIT,
        ),
    )

    anime_name = " ".join(
        args
    ).strip()

    anime_name = clean_name(
        anime_name
    )

    return (
        anime_name,
        requested_limit,
        source,
    )


# ============================================================
# SOURCE HELP
# ============================================================

def source_help():

    return (
        "✦ <b>/img command</b>\n\n"

        "<b>All sources:</b>\n"
        "<code>/img Naruto</code>\n"
        "<code>/img Naruto 50</code>\n\n"

        "<b>Specific source:</b>\n"
        "<code>/img tmdb Naruto 30</code>\n"
        "<code>/img anilist Naruto 30</code>\n"
        "<code>/img mal Naruto 30</code>\n"
        "<code>/img jikan Naruto 30</code>\n"
        "<code>/img kitsu Naruto 30</code>\n"
        "<code>/img fanart Naruto 30</code>\n"
        "<code>/img animeplanet Naruto 30</code>\n\n"

        "<b>Sources:</b>\n"
        "• TMDB\n"
        "• AniList\n"
        "• MyAnimeList / Jikan\n"
        "• Kitsu\n"
        "• Fanart.tv\n"
        "• Anime-Planet\n\n"

        "Maximum: <b>100 images</b>"
    )


# ============================================================
# SOURCE SEARCH
# ============================================================

async def get_source_images(
    client,
    source,
    name,
):

    if source == "tmdb":

        return await tmdb_images(
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

    if source == "kitsu":

        return await kitsu_images(
            client,
            name,
        )

    if source == "fanart":

        return await fanart_images(
            client,
            name,
        )

    if source == "animeplanet":

        return await animeplanet_images(
            client,
            name,
        )

    # --------------------------------------------------------
    # ALL SOURCES
    # --------------------------------------------------------

    results = await asyncio.gather(

        anilist_images(
            client,
            name,
        ),

        jikan_images(
            client,
            name,
        ),

        tmdb_images(
            client,
            name,
        ),

        kitsu_images(
            client,
            name,
        ),

        fanart_images(
            client,
            name,
        ),

        animeplanet_images(
            client,
            name,
        ),

        tmdb_episode_images(
            client,
            name,
        ),

        return_exceptions=True,
    )

    result = []

    for item in results:

        if isinstance(
            item,
            list,
        ):

            result.extend(item)

    return result


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
    message: Message,
):

    (
        anime_name,
        requested_limit,
        source,
    ) = parse_img_command(
        message
    )

    # --------------------------------------------------------
    # EMPTY COMMAND
    # --------------------------------------------------------

    if not anime_name:

        await message.reply_text(
            source_help(),
            disable_web_page_preview=True,
        )

        return

    # --------------------------------------------------------
    # LOADING
    # --------------------------------------------------------

    loading = await message.reply_text(
        "✦ sᴇᴀʀᴄʜɪɴɢ ʜᴅ ᴀʀᴛᴡᴏʀᴋ..."
    )

    try:

        timeout = httpx.Timeout(
            REQUEST_TIMEOUT,
            connect=15,
        )

        limits = httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
        )

        headers = {
            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36",
        }

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=limits,
            headers=headers,
        ) as http:

            # ------------------------------------------------
            # SEARCH
            # ------------------------------------------------

            raw_urls = await get_source_images(
                http,
                source,
                anime_name,
            )

            urls = unique_urls(
                raw_urls
            )

            logger.info(
                "[IMG] %s returned %s unique URLs",
                source,
                len(urls),
            )

            if not urls:

                await loading.edit_text(
                    "❌ ɴᴏ ᴀʀᴛᴡᴏʀᴋ ғᴏᴜɴᴅ.\n\n"
                    "Try another source or title."
                )

                return

            # ------------------------------------------------
            # HARD LIMIT BEFORE DOWNLOAD
            # ------------------------------------------------

            urls = urls[
                :requested_limit
            ]

            await loading.edit_text(
                f"✦ ғᴏᴜɴᴅ {len(urls)} ɪᴍᴀɢᴇs.\n"
                f"✦ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ..."
            )

            # ------------------------------------------------
            # DOWNLOAD
            # ------------------------------------------------

            download_tasks = [
                download_image(
                    http,
                    url,
                )
                for url in urls
            ]

            downloaded = await asyncio.gather(
                *download_tasks,
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

            # ------------------------------------------------
            # HARD LIMIT AGAIN
            # ------------------------------------------------

            photos = photos[
                :requested_limit
            ]

            if not photos:

                await loading.edit_text(
                    "❌ ɪᴍᴀɢᴇs ᴄᴏᴜʟᴅ ɴᴏᴛ "
                    "ʙᴇ ᴅᴏᴡɴʟᴏᴀᴅᴇᴅ."
                )

                return

            total = len(photos)

            await loading.edit_text(
                f"✦ ᴜᴘʟᴏᴀᴅɪɴɢ ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...\n"
                f"0/{total}"
            )

            # ------------------------------------------------
            # TELEGRAM UPLOAD
            # ------------------------------------------------

            uploaded = 0

            for start in range(
                0,
                total,
                TELEGRAM_BATCH_SIZE,
            ):

                batch = photos[
                    start:
                    start + TELEGRAM_BATCH_SIZE
                ]

                media = []

                for data in batch:

                    bio = BytesIO(
                        data
                    )

                    bio.name = (
                        "image.jpg"
                    )

                    media.append(
                        InputMediaPhoto(
                            bio
                        )
                    )

                try:

                    await client.send_media_group(
                        chat_id=message.chat.id,
                        media=media,
                    )

                    uploaded += len(
                        batch
                    )

                except Exception as e:

                    logger.warning(
                        "Media group failed: %s",
                        e,
                    )

                    # Individual fallback

                    for data in batch:

                        try:

                            bio = BytesIO(
                                data
                            )

                            bio.name = (
                                "image.jpg"
                            )

                            await client.send_photo(
                                chat_id=message.chat.id,
                                photo=bio,
                            )

                            uploaded += 1

                        except Exception as upload_error:

                            logger.warning(
                                "Individual upload failed: %s",
                                upload_error,
                            )

                # ------------------------------------------------
                # UPLOAD STATUS
                # ------------------------------------------------

                try:

                    await loading.edit_text(
                        f"✦ ᴜᴘʟᴏᴀᴅɪɴɢ ᴛᴏ ᴛᴇʟᴇɢʀᴀᴍ...\n"
                        f"{uploaded}/{total}"
                    )

                except Exception:

                    pass

                await asyncio.sleep(
                    0.5
                )

            # ------------------------------------------------
            # FINISHED
            # ------------------------------------------------

            try:

                if uploaded >= total:

                    await loading.edit_text(
                        f"✓ ᴜᴘʟᴏᴀᴅ ᴄᴏᴍᴘʟᴇᴛᴇ\n"
                        f"{uploaded}/{total}"
                    )

                else:

                    await loading.edit_text(
                        f"✓ ᴜᴘʟᴏᴀᴅ ғɪɴɪsʜᴇᴅ\n"
                        f"{uploaded}/{total}"
                    )

            except Exception:

                pass

            await asyncio.sleep(
                2
            )

            try:

                await loading.delete()

            except Exception:

                pass

    except Exception as e:

        logger.exception(
            "[IMG] Fatal error"
        )

        try:

            await loading.edit_text(
                "❌ ɪᴍᴀɢᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ.\n\n"
                "ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ."
            )

        except Exception:

            pass