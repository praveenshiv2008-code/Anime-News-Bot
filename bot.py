import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message
from pyrogram import filters

from config import API_ID, API_HASH, BOT_TOKEN, UPDATE_INTERVAL
from helper.news_job import broadcast_news
from helper.weekly_anime import send_weekly_anime

# Try to import route.py for health checks, fallback to Flask if not available
try:
    from route import web_server
    HAS_ROUTE = True
except ImportError:
    HAS_ROUTE = False
    logging.warning("route.py not found - health checks may not work")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- Pyrogram Client ----------
app = Client(
    "anime_news_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# ---------- Load All Plugins (this registers their handlers) ----------
import plugins.help
import plugins.admin
import plugins.anime
import plugins.img
import plugins.trending
import plugins.weekly
import plugins.start   # make sure this file exists

logger.info("✅ All plugins loaded")

# ---------- CATCH‑ALL ECHO HANDLER (for diagnostics) ----------
@app.on_message(filters.text & filters.private)
async def echo(client: Client, message: Message):
    logger.info(f"📩 Received text: {message.text} from {message.from_user.id}")
    try:
        await message.reply_text(f"I received your message: `{message.text}`")
    except Exception as e:
        logger.error(f"❌ Echo reply failed: {e}")

# ---------- Background Tasks ----------
async def news_scheduler():
    interval = max(1, UPDATE_INTERVAL) * 60
    while True:
        try:
            await broadcast_news(app)
        except Exception as e:
            logger.error(f"News broadcast error: {e}")
        await asyncio.sleep(interval)

async def weekly_scheduler():
    ist = ZoneInfo("Asia/Kolkata")
    while True:
        now = datetime.now(ist)
        days_until_sunday = (6 - now.weekday()) % 7
        if days_until_sunday == 0 and now.hour == 0 and now.minute == 0:
            try:
                await send_weekly_anime(app)
            except Exception as e:
                logger.error(f"Weekly anime error: {e}")
            await asyncio.sleep(86400)
        else:
            await asyncio.sleep(60)

# ---------- Start Bot with FloodWait Retry ----------
async def start_bot_with_retry(max_retries=10):
    retries = 0
    while retries < max_retries:
        try:
            await app.start()
            logger.info("✅ Bot started successfully.")
            return
        except FloodWait as e:
            wait = e.value
            logger.warning(f"⏳ FloodWait: need to wait {wait}s before retrying.")
            await asyncio.sleep(wait)
            retries += 1
        except Exception as e:
            logger.error(f"❌ Fatal error starting bot: {e}")
            raise
    raise Exception("Max retries exceeded – could not start bot.")

# ---------- Simple HTTP Health Check Server (if route.py is missing) ----------
async def health_server():
    """Fallback HTTP server for Render health checks"""
    try:
        from aiohttp import web
        app_web = web.Application()
        async def handle(request):
            return web.Response(text="Bot is running and healthy!")
        app_web.add_routes([web.get('/', handle), web.get('/health', handle)])
        runner = web.AppRunner(app_web)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
        await site.start()
        logger.info("🌐 Health-check web server started (fallback).")
    except ImportError:
        logger.warning("aiohttp not installed - health checks disabled")

# ---------- Main ----------
async def main():
    # Start health‑check web server
    if HAS_ROUTE:
        await web_server()
        logger.info("🌐 Health‑check web server started (route.py).")
    else:
        await health_server()

    # Start bot
    await start_bot_with_retry()

    # Start background tasks
    asyncio.create_task(news_scheduler())
    asyncio.create_task(weekly_scheduler())

    # Keep the event loop running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())