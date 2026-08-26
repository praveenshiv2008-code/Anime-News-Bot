import aiohttp
import asyncio
import feedparser
import logging
import re
from bs4 import BeautifulSoup
from dataclasses import dataclass
from database.db import db
from config import *


@dataclass
class AnimeNews:
    title: str
    link: str
    summary: str
    image_url: str | None   # None = no image, broadcaster sends text-only
    source_url: str


# --- 🔍 IMAGE URL VALIDATOR ---
def is_valid_img(src: str | None) -> bool:
    """
    Checks if a URL looks like a real usable image.
    Filters out tracking pixels, placeholders, SVGs, base64 blobs, etc.
    """
    if not src:
        return False
    src = src.strip()
    if not src.startswith("http"):
        return False
    if src.startswith("data:"):
        return False
    if src.endswith(".svg"):
        return False
    bad_patterns = [
        "pixel", "tracker", "analytics", "beacon",
        "1x1", "blank", "placeholder", "spacer",
        "logo", "icon", "avatar", "favicon"
    ]
    src_lower = src.lower()
    if any(p in src_lower for p in bad_patterns):
        return False
    return True


# --- 🖼 ARTICLE PAGE IMAGE SCRAPER ---
async def fetch_image_from_article(session: aiohttp.ClientSession, article_url: str) -> str | None:
    """
    Fetches the actual article page and extracts the best image from it.
    Priority:
      1. <figure> tag image (usually the main article image)
      2. og:image meta tag
      3. data-src lazy-loaded image
      4. Regular <img> src
    """
    if not article_url:
        return None

    try:
        async with session.get(
            article_url,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        # 1. Figure tag
        figure = soup.find("figure")
        if figure:
            img_tag = figure.find("img")
            if img_tag:
                src = img_tag.get("data-src") or img_tag.get("src")
                if is_valid_img(src):
                    logging.info(f"[ArticleScraper] ✅ Figure image found at: '{article_url}'")
                    return src

        # 2. og:image meta tag
        og_img = soup.find("meta", property="og:image")
        if og_img and is_valid_img(og_img.get("content")):
            logging.info(f"[ArticleScraper] ✅ og:image found at: '{article_url}'")
            return og_img["content"]

        # 3. data-src lazy loaded images
        for img_tag in soup.find_all("img"):
            src = img_tag.get("data-src")
            if is_valid_img(src):
                logging.info(f"[ArticleScraper] ✅ data-src image found at: '{article_url}'")
                return src

        # 4. Regular img src
        for img_tag in soup.find_all("img"):
            src = img_tag.get("src")
            if is_valid_img(src):
                logging.info(f"[ArticleScraper] ✅ img src found at: '{article_url}'")
                return src

        logging.info(f"[ArticleScraper] ❌ No image found at: '{article_url}'")
        return None

    except asyncio.TimeoutError:
        logging.error(f"[ArticleScraper] ⏱️ Timeout fetching: '{article_url}'")
        return None
    except aiohttp.ClientError as e:
        logging.error(f"[ArticleScraper] 🌐 Network error for '{article_url}': {e}")
        return None
    except Exception as e:
        logging.error(f"[ArticleScraper] 💥 Unexpected error for '{article_url}': {e}")
        return None


# ============================================================
# 🔤 IMPROVED REGEX‑BASED ANIME NAME EXTRACTOR
# ============================================================
def extract_anime_names(title: str) -> list[str]:
    """
    Extract possible anime names from a news headline.
    Returns a list of candidates in order of priority.
    """
    title = title.strip()
    candidates = []
    seen = set()

    # ----- Helper to add candidate if not seen and length > 2 -----
    def add_candidate(text):
        text = text.strip().strip('"\'')
        if len(text) > 2 and text not in seen:
            seen.add(text)
            candidates.append(text)

    # ----- 1. Full title (as is) -----
    add_candidate(title)

    # ----- 2. Text inside quotes ("" or '') -----
    quoted = re.findall(r'["\']([^"\']+)["\']', title)
    for q in quoted:
        add_candidate(q)

    # ----- 3. Before first colon, dash, or parentheses -----
    for sep in [':', '–', '—', '(', '【']:
        if sep in title:
            part = title.split(sep, 1)[0].strip()
            add_candidate(part)
            break  # take the first separator that works

    # ----- 4. Strip common suffixes after a dash or colon -----
    # Remove everything after these keywords
    suffixes = [
        r'\s+Season\s+\d+',
        r'\s+Volume\s+\d+',
        r'\s+Episode\s+\d+',
        r'\s+Part\s+\d+',
        r'\s+Announces\s+',
        r'\s+Reveals\s+',
        r'\s+Trailer\s+',
        r'\s+Review\s+',
        r'\s+Premiere\s+',
        r'\s+Release\s+',
        r'\s+Cast\s+',
        r'\s+Dub\s+',
        r'\s+Anime\s*$',
        r'\s+Manga\s*$',
        r'\s+Film\s*$',
        r'\s+Movie\s*$',
        r'\s+OVA\s*$',
        r'\s+Special\s*$',
    ]
    cleaned = title
    for pat in suffixes:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
    if cleaned != title:
        add_candidate(cleaned.strip())

    # ----- 5. First 3–4 words (if the title is long) -----
    words = title.split()
    if len(words) > 4:
        short = ' '.join(words[:4])
        add_candidate(short)
    if len(words) > 3:
        short = ' '.join(words[:3])
        add_candidate(short)

    # ----- 6. Remove common trailing words like "Anime", "Series", "TV" -----
    for word in ['Anime', 'Manga', 'Series', 'TV', 'Film', 'Movie', 'OVA', 'Special']:
        if candidates and candidates[-1].endswith(' ' + word):
            trimmed = candidates[-1][:-len(word)].strip()
            add_candidate(trimmed)

    # ----- Return unique candidates (order preserved) -----
    return candidates


# --- 🖼 ANILIST GRAPHQL POSTER FETCHER (MULTI-SEARCH) ---
async def get_anilist_poster(session: aiohttp.ClientSession, title: str, retries: int = 3) -> str | None:
    """
    1. Extracts ALL possible anime names from the RSS title
    2. Searches AniList for each candidate in priority order
    3. Returns the FIRST successful match (cover > banner)
    4. Supports both ANIME and MANGA types
    """
    url = 'https://graphql.anilist.co'

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    query = '''
    query ($search: String) {
      anime: Media (search: $search, type: ANIME, sort: POPULARITY_DESC) {
        bannerImage
        coverImage {
          extraLarge
        }
      }
      manga: Media (search: $search, type: MANGA, sort: POPULARITY_DESC) {
        bannerImage
        coverImage {
          extraLarge
        }
      }
    }
    '''

    # Get ALL candidate names using the improved extractor
    search_terms = extract_anime_names(title)

    if not search_terms:
        logging.info(f"[AniList] ⏭️ Skipping — no series name in: '{title}'")
        return None

    # Try each candidate until we find an image
    for search_term in search_terms:
        logging.info(f"[AniList] 🔍 Trying: '{search_term}'")

        for attempt in range(1, retries + 1):
            try:
                async with session.post(
                    url,
                    json={'query': query, 'variables': {'search': search_term}},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:

                    if response.status == 429:
                        retry_after = int(response.headers.get('Retry-After', 10))
                        logging.warning(f"[AniList] ⏳ Rate limited. Waiting {retry_after}s (attempt {attempt}/{retries})...")
                        await asyncio.sleep(retry_after)
                        continue

                    if response.status != 200:
                        logging.warning(f"[AniList] ⚠️ HTTP {response.status} for '{search_term}' (attempt {attempt}/{retries})")
                        await asyncio.sleep(2 * attempt)
                        continue

                    data = await response.json()

                    if 'errors' in data:
                        logging.warning(f"[AniList] ⚠️ Partial errors for '{search_term}': {data.get('errors')}")

                    data_section = data.get('data', {})

                    if not data_section:
                        logging.warning(f"[AniList] ❌ Empty data for '{search_term}' (attempt {attempt}/{retries})")
                        await asyncio.sleep(2 * attempt)
                        continue

                    # Check anime first, then manga — cover first, banner as fallback
                    for media_type in ['anime', 'manga']:
                        media = data_section.get(media_type)
                        if not media:
                            continue

                        cover = (media.get('coverImage') or {}).get('extraLarge')
                        banner = media.get('bannerImage')

                        if cover:
                            logging.info(f"[AniList] ✅ SUCCESS! {media_type.upper()} cover found for '{search_term}'")
                            return cover
                        elif banner:
                            logging.info(f"[AniList] ✅ SUCCESS! {media_type.upper()} banner found for '{search_term}'")
                            return banner

                    # No image found for this search term, try next candidate
                    logging.info(f"[AniList] ❌ No images for '{search_term}', trying next candidate...")
                    break  # Exit retry loop, move to next search term

            except asyncio.TimeoutError:
                logging.error(f"[AniList] ⏱️ Timeout for '{search_term}' (attempt {attempt}/{retries})")
                await asyncio.sleep(2 * attempt)

            except aiohttp.ClientError as e:
                logging.error(f"[AniList] 🌐 Network error for '{search_term}' (attempt {attempt}/{retries}): {e}")
                await asyncio.sleep(2 * attempt)

            except Exception as e:
                logging.error(f"[AniList] 💥 Unexpected error for '{search_term}' (attempt {attempt}/{retries}): {e}")
                await asyncio.sleep(2 * attempt)

    logging.error(f"[AniList] ❌ All candidates failed for original title: '{title}'")
    return None


# --- 📰 MAIN RSS FETCHER ---
async def fetch_latest_news() -> list[AnimeNews]:
    """
    Fetches latest news from all RSS feeds in the database.

    Image priority per item:
      🥇 AniList poster  — cover first, then banner (anime before manga)
                          Tries ALL regex-extracted candidates, stops at first success
      🥈 Article page    — scraped from the actual news article URL
      🥉 None            — broadcaster sends text-only post
    """
    rss_urls = await db.get_all_rss()
    if not rss_urls:
        logging.info("[Fetcher] No RSS feeds configured. Nothing to fetch.")
        return []

    news_items = []

    async with aiohttp.ClientSession() as session:
        for rss_url in rss_urls:
            try:
                async with session.get(
                    rss_url,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    content = await response.text()

                feed = feedparser.parse(content)

                for entry in feed.entries[:3]:
                    title = entry.get("title", "No Title")
                    entry_link = entry.get("link", "")

                    # Clean summary text
                    raw_summary = entry.get("summary", "")
                    soup = BeautifulSoup(raw_summary, "html.parser")
                    clean_summary = soup.get_text().strip()
                    if len(clean_summary) > 250:
                        clean_summary = clean_summary[:250] + "..."

                    # 🥇 Try AniList poster first (tries ALL regex candidates)
                    anilist_poster = await get_anilist_poster(session, title)

                    if anilist_poster:
                        final_image = anilist_poster
                        logging.info(f"[Fetcher] 🥇 AniList poster used for: '{title}'")

                    else:
                        # 🥈 All AniList candidates failed, scrape the article page
                        article_image = await fetch_image_from_article(session, entry_link)

                        if article_image:
                            final_image = article_image
                            logging.info(f"[Fetcher] 🥈 Article image used for: '{title}'")
                        else:
                            final_image = None
                            logging.info(f"[Fetcher] 🥉 No image — text-only for: '{title}'")

                    news_items.append(AnimeNews(
                        title=title,
                        link=entry_link,
                        summary=clean_summary,
                        image_url=final_image,
                        source_url=rss_url
                    ))

            except aiohttp.ClientError as e:
                logging.error(f"[Fetcher] 🌐 Network error for feed '{rss_url}': {e}")
            except Exception as e:
                logging.error(f"[Fetcher] 💥 Unexpected error for feed '{rss_url}': {e}")

    logging.info(f"[Fetcher] ✅ Done. {len(news_items)} item(s) ready to broadcast.")
    return news_items