import os
import feedparser
import requests
import time
import schedule
import json
import threading
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask

# Load environment variables
load_dotenv()

# ----------------- CONFIGURATION -----------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ADMIN_CHAT_ID = TELEGRAM_CHAT_ID
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
FANART_API_KEY = os.getenv("FANART_API_KEY", "")

RSS_FEED_URL = "https://www.animenewsnetwork.com/news/rss.xml"
CHECK_INTERVAL_MINUTES = 5
SEEN_FILE = "seen_links.json"
IMAGE_CACHE_FILE = "image_cache.json"
RSS_FEEDS_FILE = "rss_feeds.json"
LAST_UPDATE_FILE = "last_update_id.txt"
# -------------------------------------------------

# ---------- Flask Web Server (for Render) ----------
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health_check():
    return "OK", 200

def run_web_server():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web_server, daemon=True).start()
# -------------------------------------------------

# ---------- Small Caps Conversion ----------
SMALL_CAPS_MAP = {
    'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ',
    'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ', 'i': 'ɪ', 'j': 'ᴊ',
    'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ',
    'p': 'ᴘ', 'q': 'ǫ', 'r': 'ʀ', 's': 'ꜱ', 't': 'ᴛ',
    'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x', 'y': 'ʏ',
    'z': 'ᴢ'
}

def to_small_caps(text):
    result = []
    for ch in text:
        lower = ch.lower()
        if lower in SMALL_CAPS_MAP:
            result.append(SMALL_CAPS_MAP[lower])
        else:
            result.append(ch)
    return ''.join(result)

# ---------- Persistent storage ----------
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, 'w') as f:
        json.dump(list(seen), f)

def load_image_cache():
    if os.path.exists(IMAGE_CACHE_FILE):
        with open(IMAGE_CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_image_cache(cache):
    with open(IMAGE_CACHE_FILE, 'w') as f:
        json.dump(cache, f)

def load_rss_feeds():
    if os.path.exists(RSS_FEEDS_FILE):
        with open(RSS_FEEDS_FILE, 'r') as f:
            return json.load(f)
    else:
        default_feeds = [RSS_FEED_URL]
        with open(RSS_FEEDS_FILE, 'w') as f:
            json.dump(default_feeds, f)
        return default_feeds

def save_rss_feeds(feeds):
    with open(RSS_FEEDS_FILE, 'w') as f:
        json.dump(feeds, f)

def load_last_update_id():
    if os.path.exists(LAST_UPDATE_FILE):
        with open(LAST_UPDATE_FILE, 'r') as f:
            return int(f.read().strip())
    return 0

def save_last_update_id(update_id):
    with open(LAST_UPDATE_FILE, 'w') as f:
        f.write(str(update_id))

# ---------- Fetch news from all feeds ----------
def fetch_news(limit=10):
    feeds = load_rss_feeds()
    all_entries = {}
    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                link = entry.link
                if link not in all_entries:
                    all_entries[link] = (entry.title, entry.summary, entry.link)
        except Exception as e:
            print(f"Error fetching feed {feed_url}: {e}")
    return list(all_entries.values())[:limit]

# ---------- TMDb Image Fetch (for news, medium quality) ----------
def get_anime_image(title):
    if not TMDB_API_KEY:
        return None
    cache = load_image_cache()
    if title in cache:
        return cache[title]

    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "include_adult": False,
        "language": "en-US"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for res in data.get("results", []):
                poster = res.get("poster_path")
                if poster:
                    img_url = "https://image.tmdb.org/t/p/w500" + poster  # medium
                    cache[title] = img_url
                    save_image_cache(cache)
                    return img_url
        cache[title] = None
        save_image_cache(cache)
        return None
    except Exception as e:
        print(f"Error fetching image: {e}")
        return None

# ---------- TMDb HQ Image Fetch (for /img) ----------
def get_anime_image_hq(title):
    if not TMDB_API_KEY:
        return None
    cache = load_image_cache()
    cache_key = f"{title}_hq"
    if cache_key in cache:
        return cache[cache_key]

    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "include_adult": False
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for res in data.get("results", []):
                poster = res.get("poster_path")
                if poster:
                    img_url = "https://image.tmdb.org/t/p/original" + poster  # original quality
                    cache[cache_key] = img_url
                    save_image_cache(cache)
                    return img_url
        cache[cache_key] = None
        save_image_cache(cache)
        return None
    except Exception as e:
        print(f"Error fetching HQ image: {e}")
        return None

# ---------- Build caption for news ----------
def build_caption(title, summary, link):
    title_sc = to_small_caps(title)
    summary_sc = to_small_caps(summary)
    caption = f"""<blockquote>
╭━━━━━「 ɪɴꜰᴏ 」━━━━━╮

「 {title_sc} 」

{summary_sc}

╰━━━━━━━━━━━━━━╯

⚡ <a href='https://t.me/Anicore_Animes'>ꜱᴛᴀʏ ᴜᴘᴅᴀᴛᴇᴅ</a>
</blockquote>"""
    caption += f"\n\n<a href='{link}'>🔗 Read more</a>"
    return caption

# ---------- Send message ----------
def send_telegram_message(caption, chat_id=None, photo_url=None):
    if chat_id is None:
        chat_id = TELEGRAM_CHAT_ID

    if photo_url:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

    response = requests.post(url, data=payload)
    if response.status_code != 200:
        print(f"Failed to send: {response.text}")
    else:
        print("Message sent successfully.")
    return response

# ---------- Fetch anime info ----------
def fetch_anime_info(query):
    search_url = "https://api.jikan.moe/v4/anime"
    params = {"q": query, "limit": 1}
    try:
        resp = requests.get(search_url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("data", [])
            if results:
                anime = results[0]
                return {
                    "title_romaji": anime.get("title", "N/A"),
                    "title_english": anime.get("title_english", "N/A"),
                    "title_native": anime.get("title_japanese", "N/A"),
                    "synopsis": anime.get("synopsis", "No synopsis available."),
                    "score": anime.get("score", "N/A"),
                    "episodes": anime.get("episodes", "N/A"),
                    "status": anime.get("status", "N/A"),
                    "genres": ", ".join([g["name"] for g in anime.get("genres", [])]),
                    "aired": anime.get("aired", {}).get("string", "N/A"),
                    "studios": ", ".join([s["name"] for s in anime.get("studios", [])]),
                    "source": anime.get("source", "N/A"),
                    "mal_url": anime.get("url", ""),
                    "image_url": anime.get("images", {}).get("jpg", {}).get("image_url", None)
                }
        return None
    except Exception as e:
        print(f"Error fetching anime info: {e}")
        return None

# ---------- Build caption for /anime ----------
def build_anime_caption(info):
    title = info["title_romaji"]
    if info["title_english"] and info["title_english"] != title:
        title_display = f"{title} ({info['title_english']})"
    else:
        title_display = title
    title_sc = to_small_caps(title_display)

    details = f"""
📖 <b>Synopsis</b>:
{info['synopsis'][:500]}{'...' if len(info['synopsis']) > 500 else ''}

⭐ <b>Score</b>: {info['score']}  |  📺 <b>Episodes</b>: {info['episodes']}
📅 <b>Status</b>: {info['status']}  |  📆 <b>Aired</b>: {info['aired']}
🏢 <b>Studios</b>: {info['studios']}
📂 <b>Source</b>: {info['source']}
🎭 <b>Genres</b>: {info['genres']}
"""

    caption = f"""<blockquote>
╭━━━━━「 ᴀɴɪᴍᴇ 」━━━━━╮

「 {title_sc} 」

{details}

╰━━━━━━━━━━━━━━╯

⚡ <a href='https://t.me/Anicore_Animes'>ꜱᴛᴀʏ ᴜᴘᴅᴀᴛᴇᴅ</a>
</blockquote>"""

    if info["mal_url"]:
        caption += f"\n\n<a href='{info['mal_url']}'>🔗 View on MyAnimeList</a>"
    return caption

# ---------- Fetch top anime ----------
def fetch_top_anime(limit=10):
    url = "https://api.jikan.moe/v4/top/anime"
    params = {"limit": min(limit, 50)}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("data", [])
            top_list = []
            for anime in results:
                top_list.append({
                    "rank": anime.get("rank", 0),
                    "title": anime.get("title", "N/A"),
                    "score": anime.get("score", "N/A"),
                    "scored_by": anime.get("scored_by", 0),
                    "image_url": anime.get("images", {}).get("jpg", {}).get("image_url", None),
                    "mal_url": anime.get("url", "")
                })
            return top_list
        return []
    except Exception as e:
        print(f"Error fetching top anime: {e}")
        return []

# ---------- Build caption for /weekly ----------
def build_weekly_caption(top_list):
    lines = []
    for i, item in enumerate(top_list, start=1):
        title_sc = to_small_caps(item['title'])
        score = item['score']
        scored = item['scored_by']
        lines.append(f"{i}. « {title_sc} »  ⭐ {score}  👤 {scored:,}")
    list_text = "\n".join(lines)
    caption = f"""<blockquote>
╭━━━━━「 ᴛᴏᴘ ʀᴀᴛᴇᴅ 」━━━━━╮

📊 <b>Weekly Top {len(top_list)} Anime</b>

{list_text}

╰━━━━━━━━━━━━━━╯

⚡ <a href='https://t.me/Anicore_Animes'>ꜱᴛᴀʏ ᴜᴘᴅᴀᴛᴇᴅ</a>
</blockquote>
"""
    if top_list:
        caption += f"\n<a href='{top_list[0]['mal_url']}'>🔗 View #1 on MyAnimeList</a>"
    return caption

# ---------- Fanart.tv image fetch ----------
def fetch_anime_image_fanart(title):
    if not FANART_API_KEY:
        return None
    search_url = "https://webservice.fanart.tv/v3/movies/search"
    params = {"api_key": FANART_API_KEY, "query": title}
    try:
        resp = requests.get(search_url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("items", [])
            if results:
                movie_id = results[0].get("id")
                if movie_id:
                    detail_url = f"https://webservice.fanart.tv/v3/movies/{movie_id}"
                    detail_params = {"api_key": FANART_API_KEY}
                    detail_resp = requests.get(detail_url, params=detail_params, timeout=10)
                    if detail_resp.status_code == 200:
                        detail_data = detail_resp.json()
                        posters = detail_data.get("movieposter", [])
                        if posters:
                            return posters[0].get("url")
        return None
    except Exception as e:
        print(f"Fanart error: {e}")
        return None

# ---------- Command Handlers ----------
def process_command(text, chat_id):
    if text == "/start":
        msg = """<b>👋 Welcome to the Anime News Bot!</b>

I fetch the latest anime news from multiple RSS feeds and post them here automatically.
You can also use these commands:

/start - Show this welcome message
/help - List all commands
/latest - Get the most recent news right now (with image)
/anime <name> - Search for any anime and get full info + image
/img <name> [source] - Get high-quality images (default: all sources)
                   Sources: tmdb, mal, fanart, imdb
/weekly [count] - Get top-rated anime (default 10, max 50)
/status - Bot status and info
(Admin only)
/add_rss <url> - Add a new RSS feed
/rem_rss <index> - Remove an RSS feed by index (see /view_rss)
/view_rss - List all current RSS feeds

Stay tuned for updates! 🚀"""
        send_telegram_message(msg, chat_id)

    elif text == "/help":
        msg = """<b>📖 Available Commands</b>

/start - Show welcome message
/help - Show this help menu
/latest - Instantly fetch and send the latest news (with image)
/anime <name> - Search for an anime and get detailed info with poster
/img <name> [source] - Get high-quality poster images (default: all sources)
                   Sources: tmdb, mal, fanart, imdb (via tmdb)
/weekly [count] - Get top-rated anime list with scores and ratings count (default 10)
/status - Check bot status and schedule info

<b>👑 Admin Commands</b>
/add_rss <url> - Add a new RSS feed
/rem_rss <index> - Remove an RSS feed by its number (from /view_rss)
/view_rss - List all active RSS feeds

<i>The bot automatically posts new news every 5 minutes.</i>"""
        send_telegram_message(msg, chat_id)

    elif text.startswith("/anime"):
        query = text[len("/anime"):].strip()
        if not query:
            send_telegram_message(
                "❓ Please provide an anime name.\n"
                "<b>Usage</b>: <code>/anime &lt;name&gt;</code>\n"
                "Example: <code>/anime Naruto</code>",
                chat_id
            )
            return
        info = fetch_anime_info(query)
        if not info:
            send_telegram_message(f"❌ Could not find any anime for '<b>{query}</b>'. Please try a different name.", chat_id)
            return
        caption = build_anime_caption(info)
        send_telegram_message(caption, chat_id, photo_url=info["image_url"])

    elif text.startswith("/img"):
        parts = text.split(maxsplit=2)
        if len(parts) < 2:
            send_telegram_message(
                "❓ Please provide an anime name.\n"
                "<b>Usage</b>: <code>/img &lt;name&gt; [source]</code>\n"
                "Example: <code>/img Naruto mal</code> (source optional, default: all)",
                chat_id
            )
            return
        query = parts[1]
        source = "all"
        if len(parts) == 3:
            possible_source = parts[2].lower()
            if possible_source in ["tmdb", "mal", "fanart", "imdb"]:
                source = possible_source

        # Collect images from the chosen source(s)
        images = []
        if source == "all" or source == "tmdb":
            img = get_anime_image_hq(query)
            if img:
                images.append(("TMDb", img))
        if source == "all" or source == "mal":
            info = fetch_anime_info(query)
            if info and info["image_url"]:
                images.append(("MyAnimeList", info["image_url"]))
        if source == "all" or source == "fanart":
            img = fetch_anime_image_fanart(query)
            if img:
                images.append(("Fanart.tv", img))
        if source == "imdb":  # IMDb via TMDb
            img = get_anime_image_hq(query)
            if img:
                images.append(("IMDb (via TMDb)", img))

        if not images:
            send_telegram_message(f"❌ No images found for '<b>{query}</b>'.", chat_id)
            return

        # Send each image as a separate message
        for src, url in images:
            title_sc = to_small_caps(query)
            caption = f"""<blockquote>
╭━━━━━「 ɪᴍᴀɢᴇ 」━━━━━╮

「 {title_sc} 」
Source: <b>{src}</b>

╰━━━━━━━━━━━━━━╯

⚡ <a href='https://t.me/Anicore_Animes'>ꜱᴛᴀʏ ᴜᴘᴅᴀᴛᴇᴅ</a>
</blockquote>"""
            send_telegram_message(caption, chat_id, photo_url=url)
            time.sleep(1)  # avoid rate limits

    elif text.startswith("/weekly"):
        parts = text.split()
        count = 10
        if len(parts) > 1:
            try:
                count = int(parts[1])
                if count < 1:
                    count = 1
                elif count > 50:
                    count = 50
            except ValueError:
                send_telegram_message(
                    "❌ Please provide a valid number.\n"
                    "<b>Usage</b>: <code>/weekly [count]</code>\n"
                    "Example: <code>/weekly 16</code> (max 50)",
                    chat_id
                )
                return
        top_list = fetch_top_anime(count)
        if not top_list:
            send_telegram_message("❌ Could not fetch top anime right now. Please try later.", chat_id)
            return
        caption = build_weekly_caption(top_list)
        send_telegram_message(caption, chat_id, photo_url=top_list[0]["image_url"])

    elif text == "/latest":
        news = fetch_news(limit=1)
        if news:
            title, summary, link = news[0]
            caption = build_caption(title, summary, link)
            img_url = get_anime_image(title)  # medium quality for speed
            send_telegram_message(caption, chat_id, photo_url=img_url)
        else:
            send_telegram_message("❌ Could not fetch the latest news right now.", chat_id)

    elif text == "/status":
        feeds = load_rss_feeds()
        msg = f"""<b>⚙️ Bot Status</b>

📡 Feeds configured: {len(feeds)}
⏱️ Check Interval: Every {CHECK_INTERVAL_MINUTES} minutes
📂 Seen links stored: {len(load_seen())} articles
🖼️ Image cache size: {len(load_image_cache())} titles
✅ Bot is running smoothly."""
        send_telegram_message(msg, chat_id)

    elif text.startswith("/add_rss"):
        if chat_id != ADMIN_CHAT_ID:
            send_telegram_message("⛔ You are not authorized to use this command.", chat_id)
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_telegram_message(
                "❓ Usage: <code>/add_rss &lt;feed_url&gt;</code>\n"
                "Example: <code>/add_rss https://example.com/feed.xml</code>",
                chat_id
            )
            return
        new_url = parts[1].strip()
        feeds = load_rss_feeds()
        if new_url in feeds:
            send_telegram_message(f"ℹ️ Feed already exists: <code>{new_url}</code>", chat_id)
            return
        feeds.append(new_url)
        save_rss_feeds(feeds)
        send_telegram_message(f"✅ Added feed: <code>{new_url}</code>\nNow {len(feeds)} feeds total.", chat_id)

    elif text.startswith("/rem_rss"):
        if chat_id != ADMIN_CHAT_ID:
            send_telegram_message("⛔ You are not authorized to use this command.", chat_id)
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_telegram_message(
                "❓ Usage: <code>/rem_rss &lt;index&gt;</code>\n"
                "Use <code>/view_rss</code> to see the list with indices.",
                chat_id
            )
            return
        try:
            idx = int(parts[1].strip())
        except ValueError:
            send_telegram_message("❌ Please provide a valid index number.", chat_id)
            return
        feeds = load_rss_feeds()
        if idx < 1 or idx > len(feeds):
            send_telegram_message(f"❌ Index out of range. Choose between 1 and {len(feeds)}.", chat_id)
            return
        removed = feeds.pop(idx - 1)
        save_rss_feeds(feeds)
        send_telegram_message(f"✅ Removed feed: <code>{removed}</code>\nNow {len(feeds)} feeds remain.", chat_id)

    elif text == "/view_rss":
        if chat_id != ADMIN_CHAT_ID:
            send_telegram_message("⛔ You are not authorized to use this command.", chat_id)
            return
        feeds = load_rss_feeds()
        if not feeds:
            send_telegram_message("📭 No RSS feeds configured.", chat_id)
            return
        lines = [f"{i+1}. {url}" for i, url in enumerate(feeds)]
        msg = "<b>📡 Current RSS Feeds</b>\n\n" + "\n".join(lines)
        send_telegram_message(msg, chat_id)

    else:
        send_telegram_message("❓ Unknown command. Type /help to see available commands.", chat_id)

# ---------- Poll for incoming commands ----------
last_update_id = load_last_update_id()

def handle_updates():
    global last_update_id
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {
        "offset": last_update_id + 1,
        "timeout": 5
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                for update in data["result"]:
                    last_update_id = update["update_id"]
                    save_last_update_id(last_update_id)
                    message = update.get("message")
                    if message:
                        chat_id = message["chat"]["id"]
                        text = message.get("text")
                        if text and text.startswith("/"):
                            process_command(text, chat_id)
    except Exception as e:
        print(f"Error fetching updates: {e}")

# ---------- Scheduled job ----------
def job():
    print(f"Checking for new news at {datetime.now()}")
    seen = load_seen()
    new_entries = []
    for title, summary, link in fetch_news(limit=10):
        if link not in seen:
            new_entries.append((title, summary, link))
            seen.add(link)
    if new_entries:
        for title, summary, link in new_entries:
            caption = build_caption(title, summary, link)
            img_url = get_anime_image(title)   # medium quality for speed
            send_telegram_message(caption, photo_url=img_url)
            time.sleep(1)
        save_seen(seen)
        print(f"Sent {len(new_entries)} new articles.")
    else:
        print("No new articles.")

# ---------- Main Loop ----------
if __name__ == "__main__":
    job()
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(job)

    print(f"🤖 Bot started. Checking every {CHECK_INTERVAL_MINUTES} minutes.")
    print("📨 Listening for commands...")

    while True:
        schedule.run_pending()
        handle_updates()
        time.sleep(5)