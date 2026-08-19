import os
import re
import logging
from io import BytesIO
from urllib.parse import quote

import httpx

logger = logging.getLogger("AnimeImages")

============================================================

CONFIG

============================================================

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
FANART_API_KEY = os.getenv("FANART_API_KEY", "").strip()

TMDB_URL = "https://api.themoviedb.org/3"
KITSU_URL = "https://kitsu.io/api/edge"
ANILIST_URL = "https://graphql.anilist.co"
JIKAN_URL = "https://api.jikan.moe/v4"

FANART_URL = "https://webservice.fanart.tv/v3"

ANIMEPLANET_URL = "https://www.anime-planet.com"

REQUEST_TIMEOUT = 25

MIN_FILE_SIZE = 5_000

MAX_ALLOWED_LIMIT = 100

============================================================

HTTP

============================================================

async def get_json(
client,
url,
params=None,
headers=None,
):
try:
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
        "JSON request failed: %s",
        e,
    )
    return None

============================================================

NORMALIZE

============================================================

def normalize_url(url):
if not url:
return ""

return (
    url
    .strip()
    .split("?")[0]
    .lower()
)

def unique_urls(urls):
result = []
seen = set()

for url in urls:
    if not url:
        continue

    url = url.strip()

    clean = normalize_url(url)

    if not clean:
        continue

    if clean in seen:
        continue

    seen.add(clean)
    result.append(url)

return result

def limit_urls(urls, limit):
"""
HARD LIMIT.

This function is intentionally called after
duplicate removal and before returning results.
"""

try:
    limit = int(limit)
except Exception:
    limit = 30

limit = max(1, limit)
limit = min(limit, MAX_ALLOWED_LIMIT)

return unique_urls(urls)[:limit]

============================================================

TMDB SEARCH

============================================================

async def tmdb_search(
client,
name,
):
if not TMDB_API_KEY:
logger.warning("TMDB_API_KEY missing")
return []

results = []

for endpoint in (
    "search/tv",
    "search/movie",
):
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

    results.extend(
        data.get("results", [])
    )

return results

============================================================

TMDB

============================================================

async def get_tmdb_images(
client,
name,
limit=30,
):
if not TMDB_API_KEY:
return []

urls = []

try:
    results = await tmdb_search(
        client,
        name,
    )

    # Only inspect the best few search matches.
    for item in results[:5]:

        item_id = item.get("id")

        if not item_id:
            continue

        media_type = (
            "tv"
            if "first_air_date" in item
            else "movie"
        )

        data = await get_json(
            client,
            f"{TMDB_URL}/{media_type}/{item_id}/images",
            params={
                "api_key": TMDB_API_KEY,
                "include_image_language": "en,null",
            },
        )

        if not data:
            continue

        # ------------------------------
        # Posters
        # ------------------------------

        for image in data.get(
            "posters",
            [],
        ):
            path = image.get("file_path")
            width = image.get("width", 0)
            height = image.get("height", 0)

            if (
                path
                and width >= 300
                and height >= 400
            ):
                urls.append(
                    "https://image.tmdb.org/t/p/original"
                    + path
                )

        # ------------------------------
        # Backdrops
        # ------------------------------

        for image in data.get(
            "backdrops",
            [],
        ):
            path = image.get("file_path")
            width = image.get("width", 0)
            height = image.get("height", 0)

            if (
                path
                and width >= 500
                and height >= 300
            ):
                urls.append(
                    "https://image.tmdb.org/t/p/original"
                    + path
                )

        # ------------------------------
        # Logos
        # ------------------------------

        for image in data.get(
            "logos",
            [],
        ):
            path = image.get("file_path")
            width = image.get("width", 0)

            if (
                path
                and width >= 300
            ):
                urls.append(
                    "https://image.tmdb.org/t/p/original"
                    + path
                )

        # HARD STOP while collecting.
        if len(unique_urls(urls)) >= limit:
            break

except Exception as e:
    logger.exception(
        "TMDB failed: %s",
        e,
    )

return limit_urls(
    urls,
    limit,
)

============================================================

FANART.TV

============================================================

async def fanart_search(
client,
name,
):
"""
Fanart.tv search endpoint.

FANART_API_KEY should be the Fanart.tv client key.
"""

if not FANART_API_KEY:
    logger.warning(
        "FANART_API_KEY missing"
    )
    return []

urls = []

try:
    url = (
        f"{FANART_URL}/search/"
        f"{quote(name)}"
    )

    data = await get_json(
        client,
        url,
        headers={
            "api-key": FANART_API_KEY,
            "Accept": "application/json",
        },
    )

    if not data:
        return []

    # Fanart search can return TV/movie results.
    if isinstance(data, list):
        items = data
    else:
        items = (
            data.get("results")
            or data.get("data")
            or []
        )

    for item in items:

        if not isinstance(item, dict):
            continue

        for key in (
            "tvposter",
            "tvbanner",
            "tvthumb",
            "showbackground",
            "clearlogo",
            "hdtvlogo",
            "characterart",
            "movieposter",
            "moviebackground",
            "moviebanner",
            "moviethumb",
        ):
            values = item.get(key, [])

            if isinstance(values, dict):
                values = [values]

            if not isinstance(values, list):
                continue

            for value in values:

                if isinstance(value, str):
                    url = value
                elif isinstance(value, dict):
                    url = value.get("url")
                else:
                    continue

                if url:
                    urls.append(url)

except Exception as e:
    logger.exception(
        "Fanart search failed: %s",
        e,
    )

return urls

async def get_fanart_images(
client,
name,
limit=30,
):
urls = await fanart_search(
client,
name,
)

return limit_urls(
    urls,
    limit,
)

============================================================

KITSU

============================================================

async def get_kitsu_images(
client,
name,
limit=30,
):
urls = []

try:
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

        for key in (
            "original",
            "large",
            "medium",
        ):
            url = poster.get(key)

            if url:
                urls.append(url)
                break

        cover = attributes.get(
            "coverImage",
            {},
        )

        for key in (
            "original",
            "large",
            "medium",
        ):
            url = cover.get(key)

            if url:
                urls.append(url)
                break

        if len(unique_urls(urls)) >= limit:
            break

except Exception as e:
    logger.exception(
        "Kitsu failed: %s",
        e,
    )

return limit_urls(
    urls,
    limit,
)

============================================================

ANIME-PLANET

============================================================

async def get_animeplanet_images(
client,
name,
limit=30,
):
"""
Anime-Planet does not provide a simple public artwork API,
so this uses the public search page and extracts image URLs.
"""

urls = []

try:
    search_url = (
        f"{ANIMEPLANET_URL}/anime/"
        f"search?name={quote(name)}"
    )

    response = await client.get(
        search_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Linux; Android 10) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    if response.status_code != 200:
        logger.warning(
            "Anime-Planet HTTP %s",
            response.status_code,
        )
        return []

    html = response.text

    # Extract image URLs.
    patterns = [
        r'https?://[^"\']+\.(?:jpg|jpeg|png|webp)',
        r'//[^"\']+\.(?:jpg|jpeg|png|webp)',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for url in matches:

            if url.startswith("//"):
                url = "https:" + url

            urls.append(url)

            if len(unique_urls(urls)) >= limit:
                break

        if len(unique_urls(urls)) >= limit:
            break

except Exception as e:
    logger.exception(
        "Anime-Planet failed: %s",
        e,
    )

return limit_urls(
    urls,
    limit,
)

============================================================

ANILIST

============================================================

ANILIST_QUERY = """
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

async def get_anilist_images(
client,
name,
limit=30,
):
urls = []

try:
    response = await client.post(
        ANILIST_URL,
        json={
            "query": ANILIST_QUERY,
            "variables": {
                "search": name,
            },
        },
        headers={
            "Content-Type": "application/json",
        },
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

    cover = media.get(
        "coverImage",
        {},
    )

    # IMPORTANT:
    # Only ONE quality URL is used.
    # This prevents extraLarge/large/medium
    # from becoming duplicate artwork.

    url = (
        cover.get("extraLarge")
        or cover.get("large")
        or cover.get("medium")
    )

    if url:
        urls.append(url)

    banner = media.get(
        "bannerImage"
    )

    if banner:
        urls.append(banner)

    trailer = media.get(
        "trailer"
    )

    if trailer:
        thumbnail = trailer.get(
            "thumbnail"
        )

        if thumbnail:
            urls.append(thumbnail)

except Exception as e:
    logger.warning(
        "AniList failed: %s",
        e,
    )

return limit_urls(
    urls,
    limit,
)

============================================================

JIKAN

============================================================

async def get_jikan_images(
client,
name,
limit=30,
):
urls = []

try:
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
            urls.append(url)

        trailer = anime.get(
            "trailer",
            {},
        )

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
            urls.append(trailer_url)

        if len(unique_urls(urls)) >= limit:
            break

except Exception as e:
    logger.warning(
        "Jikan failed: %s",
        e,
    )

return limit_urls(
    urls,
    limit,
)

============================================================

SOURCE DISPATCHER

============================================================

SUPPORTED_SOURCES = {
"tmdb",
"fanart",
"animeplanet",
"kitsu",
"anilist",
"jikan",
}

async def search_source(
client,
source,
name,
limit,
):
"""
IMPORTANT:
This searches ONLY the selected source.

It NEVER searches all sources.
"""

source = source.lower().strip()

limit = max(
    1,
    min(
        int(limit),
        MAX_ALLOWED_LIMIT,
    ),
)

if source == "tmdb":
    return await get_tmdb_images(
        client,
        name,
        limit,
    )

if source == "fanart":
    return await get_fanart_images(
        client,
        name,
        limit,
    )

if source == "animeplanet":
    return await get_animeplanet_images(
        client,
        name,
        limit,
    )

if source == "kitsu":
    return await get_kitsu_images(
        client,
        name,
        limit,
    )

if source == "anilist":
    return await get_anilist_images(
        client,
        name,
        limit,
    )

if source == "jikan":
    return await get_jikan_images(
        client,
        name,
        limit,
    )

return []

============================================================

DOWNLOAD

============================================================

async def download_image(
client,
url,
):
try:
response = await client.get(
url,
headers={
"User-Agent": (
"Mozilla/5.0 "
"AppleWebKit/537.36 "
"Chrome/120 Safari/537.36"
),
},
)

    if response.status_code != 200:
        return None

    content_type = (
        response
        .headers
        .get(
            "content-type",
            "",
        )
        .lower()
    )

    if "image" not in content_type:
        return None

    data = response.content

    if len(data) < MIN_FILE_SIZE:
        return None

    return BytesIO(data)

except Exception as e:
    logger.warning(
        "Download failed: %s",
        e,
    )
    return None

============================================================

DOWNLOAD SELECTED

============================================================

async def download_selected(
client,
urls,
):
"""
Downloads EXACTLY the URLs supplied.

No extra images can be downloaded here.
"""

downloaded = []

for url in urls:

    image = await download_image(
        client,
        url,
    )

    if image:
        image.seek(0)
        downloaded.append(image)

return downloaded

============================================================

SOURCE DISPLAY NAME

============================================================

def source_title(source):
names = {
"tmdb": "TMDB",
"fanart": "Fanart.tv",
"animeplanet": "Anime-Planet",
"kitsu": "Kitsu",
"anilist": "AniList",
"jikan": "Jikan",
}

return names.get(
    source.lower(),
    source.title(),
)