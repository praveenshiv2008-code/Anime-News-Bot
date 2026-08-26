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

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
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

# Start web server in background thread
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

# ---------- All your existing functions: load_seen, save_seen, load_image_cache, save_image_cache,
# load_rss_feeds, save_rss_feeds, load_last_update_id, save_last_update_id, fetch_news,
# get_anime_image, build_caption, send_telegram_message, fetch_anime_info, build_anime_caption,
# fetch_top_anime, build_weekly_caption, fetch_anime_image_fanart, process_command, handle_updates, job
# ---------- (Keep all of them exactly as in the previous full code)

# ... (paste all the remaining functions here, unchanged) ...

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