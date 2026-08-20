import os
import sys
import asyncio
import logging
import importlib
import traceback

from zoneinfo import ZoneInfo

from pyrogram import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

from config import *
from helper.news_job import broadcast_news
from helper.weekly_anime import send_weekly_anime


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("AnimeBot")


# ============================================================
# TIMEZONE
# ============================================================

IST = ZoneInfo("Asia/Kolkata")


# ============================================================
# PLUGINS
# ============================================================

PLUGIN_LIST = [
    "plugins.admin",
    "plugins.anime",
    "plugins.help",
    "plugins.img",
    "plugins.start",
    "plugins.trending",
    "plugins.weekly",
]


# ============================================================
# PLUGIN LOADER
# ============================================================

def load_plugins():
    """
    Load every plugin separately.

    If one plugin fails, the remaining plugins continue loading.

    The complete traceback of a failed plugin is printed so the
    exact import/dependency error can be seen in Render logs.
    """

    logger.info("")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("🔌 STARTING PLUGIN LOADER")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    loaded = []
    failed = []

    for plugin_name in PLUGIN_LIST:

        filename = plugin_name.replace(
            "plugins.",
            ""
        )

        logger.info("")
        logger.info(
            "🔍 Loading plugin: %s",
            filename
        )

        try:

            # ------------------------------------------------
            # If previously imported, reload it.
            # ------------------------------------------------

            if plugin_name in sys.modules:

                importlib.reload(
                    sys.modules[plugin_name]
                )

            else:

                importlib.import_module(
                    plugin_name
                )

            loaded.append(
                plugin_name
            )

            logger.info(
                "✅ Plugin loaded successfully: %s",
                filename
            )

        except Exception as e:

            failed.append(
                (
                    plugin_name,
                    e
                )
            )

            logger.error(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            logger.error(
                "❌ PLUGIN FAILED: %s",
                filename
            )

            logger.error(
                "❌ ERROR TYPE: %s",
                type(e).__name__
            )

            logger.error(
                "❌ ERROR: %s",
                str(e)
            )

            logger.error(
                "❌ FULL TRACEBACK:"
            )

            traceback.print_exc()

            logger.error(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

    # ========================================================
    # SUMMARY
    # ========================================================

    logger.info("")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("📦 PLUGIN LOADING SUMMARY")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    logger.info(
        "✅ Loaded: %s / %s",
        len(loaded),
        len(PLUGIN_LIST)
    )

    for plugin_name in loaded:

        logger.info(
            "   ✅ %s",
            plugin_name
        )

    if failed:

        logger.info("")

        logger.error(
            "❌ Failed: %s / %s",
            len(failed),
            len(PLUGIN_LIST)
        )

        for plugin_name, error in failed:

            logger.error(
                "   ❌ %s → %s: %s",
                plugin_name,
                type(error).__name__,
                str(error)
            )

    else:

        logger.info("")
        logger.info(
            "🎉 ALL 7 PLUGINS LOADED SUCCESSFULLY"
        )

    logger.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    logger.info("")

    return loaded, failed


# ============================================================
# LOAD PLUGINS BEFORE BOT STARTS
# ============================================================

LOADED_PLUGINS, FAILED_PLUGINS = load_plugins()


# ============================================================
# BOT
# ============================================================

class AnimeBot(Client):

    def __init__(self):

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # No:
        #
        # plugins={"root": "plugins"}
        #
        # because plugins are loaded manually above.
        # ----------------------------------------------------

        super().__init__(
            name="anime_session",

            api_id=API_ID,
            api_hash=API_HASH,

            bot_token=BOT_TOKEN,
        )

        self.web_runner = None
        self.scheduler = None
        self.news_task = None


    # ========================================================
    # SAFE NEWS CHECK
    # ========================================================

    async def safe_news_check(self):

        try:

            logger.info(
                "📰 Starting first RSS news check..."
            )

            await broadcast_news(
                self
            )

            logger.info(
                "✅ First RSS news check completed"
            )

        except asyncio.CancelledError:

            logger.info(
                "🛑 RSS news task cancelled"
            )

            raise

        except Exception:

            logger.exception(
                "❌ First RSS news check failed"
            )


    # ========================================================
    # START
    # ========================================================

    async def start(self):

        # ----------------------------------------------------
        # START PYROGRAM
        # ----------------------------------------------------

        await super().start()

        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        logger.info(
            "✅ Pyrogram Client Started"
        )

        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


        # ====================================================
        # BOT INFORMATION
        # ====================================================

        try:

            me = await self.get_me()

            logger.info(
                "🤖 Bot: @%s",
                me.username or "unknown"
            )

            logger.info(
                "🆔 Bot ID: %s",
                me.id
            )

        except Exception:

            logger.exception(
                "❌ Could not get bot information"
            )


        # ====================================================
        # PLUGIN STATUS
        # ====================================================

        logger.info("")

        logger.info(
            "🔌 Registered plugin status:"
        )

        for plugin_name in PLUGIN_LIST:

            short_name = plugin_name.replace(
                "plugins.",
                ""
            )

            if plugin_name in LOADED_PLUGINS:

                logger.info(
                    "   🟢 %s",
                    short_name
                )

            else:

                logger.error(
                    "   🔴 %s",
                    short_name
                )


        # ====================================================
        # RESTART NOTIFICATION
        # ====================================================

        try:

            restart_chat = globals().get(
                "RESTART_LOG_CHAT",
                ""
            )

            if restart_chat:

                await self.send_message(
                    chat_id=restart_chat,
                    text="✦ ʙᴏᴛ ʀᴇsᴛᴀʀᴛᴇᴅ ✓"
                )

                logger.info(
                    "✅ Restart notification sent"
                )

        except Exception:

            logger.exception(
                "⚠️ Could not send restart notification"
            )


        # ====================================================
        # SCHEDULER
        # ====================================================

        try:

            self.scheduler = AsyncIOScheduler(
                timezone=IST
            )


            # ------------------------------------------------
            # RSS NEWS
            # ------------------------------------------------

            self.scheduler.add_job(

                broadcast_news,

                "interval",

                minutes=UPDATE_INTERVAL,

                args=[self],

                id="broadcast_job",

                replace_existing=True,

                max_instances=1,

                coalesce=True,

            )


            # ------------------------------------------------
            # WEEKLY TOP 16
            # ------------------------------------------------

            self.scheduler.add_job(

                send_weekly_anime,

                "cron",

                day_of_week="sun",

                hour=20,

                minute=0,

                second=0,

                args=[self],

                id="weekly_top16_anime",

                replace_existing=True,

                max_instances=1,

                coalesce=True,

            )


            self.scheduler.start()

            logger.info(
                "✅ RSS scheduler started — "
                "every %s minute(s)",
                UPDATE_INTERVAL
            )

            logger.info(
                "🏆 Weekly Top 16 scheduled — "
                "Sunday 8:00 PM IST"
            )

        except Exception:

            logger.exception(
                "❌ Scheduler startup failed"
            )


        # ====================================================
        # FIRST RSS CHECK
        # ====================================================

        try:

            self.news_task = asyncio.create_task(
                self.safe_news_check()
            )

            logger.info(
                "✅ First RSS broadcast task launched"
            )

        except Exception:

            logger.exception(
                "❌ Could not launch first RSS check"
            )


        # ====================================================
        # RENDER HEALTH SERVER
        # ====================================================

        async def health(request):

            return web.Response(
                text="Anime News Bot is running! ✅",
                status=200
            )


        try:

            app = web.Application()


            app.router.add_get(
                "/",
                health
            )

            app.router.add_get(
                "/health",
                health
            )


            self.web_runner = web.AppRunner(
                app
            )

            await self.web_runner.setup()


            # ------------------------------------------------
            # Render PORT
            # ------------------------------------------------

            port = int(
                os.environ.get(
                    "PORT",
                    "10000"
                )
            )


            site = web.TCPSite(

                self.web_runner,

                "0.0.0.0",

                port

            )

            await site.start()


            logger.info(
                "✅ Web server running on "
                "0.0.0.0:%s",
                port
            )

        except Exception:

            logger.exception(
                "❌ Web server startup failed"
            )


        # ====================================================
        # FINAL STATUS
        # ====================================================

        logger.info("")
        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        logger.info(
            "🚀 ANIME NEWS BOT IS ONLINE"
        )

        logger.info(
            "📡 RSS News       : ONLINE"
        )

        logger.info(
            "🏆 Weekly Top 16  : ONLINE"
        )

        logger.info(
            "🔎 Anime Search   : ONLINE"
        )

        logger.info(
            "🖼 HD Images      : ONLINE"
        )

        logger.info(
            "🔥 Trending       : ONLINE"
        )

        logger.info(
            "🔌 Plugins        : %s / %s",
            len(LOADED_PLUGINS),
            len(PLUGIN_LIST)
        )

        if FAILED_PLUGINS:

            logger.error(
                "⚠️ Some plugins failed to load!"
            )

            logger.error(
                "Check the PLUGIN FAILED traceback above."
            )

        else:

            logger.info(
                "✅ ALL PLUGINS READY"
            )

        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        logger.info("")


    # ========================================================
    # STOP
    # ========================================================

    async def stop(self, *args):

        # ----------------------------------------------------
        # CANCEL NEWS TASK
        # ----------------------------------------------------

        if self.news_task:

            try:

                if not self.news_task.done():

                    self.news_task.cancel()

                    try:

                        await self.news_task

                    except asyncio.CancelledError:

                        pass

                logger.info(
                    "🛑 First RSS task stopped"
                )

            except Exception:

                logger.exception(
                    "⚠️ RSS task shutdown error"
                )


        # ----------------------------------------------------
        # STOP SCHEDULER
        # ----------------------------------------------------

        if self.scheduler:

            try:

                self.scheduler.shutdown(
                    wait=False
                )

                logger.info(
                    "🛑 Scheduler stopped"
                )

            except Exception:

                logger.exception(
                    "⚠️ Scheduler shutdown error"
                )


        # ----------------------------------------------------
        # STOP WEB SERVER
        # ----------------------------------------------------

        if self.web_runner:

            try:

                await self.web_runner.cleanup()

                logger.info(
                    "🛑 Web server stopped"
                )

            except Exception:

                logger.exception(
                    "⚠️ Web server shutdown error"
                )


        # ----------------------------------------------------
        # STOP PYROGRAM
        # ----------------------------------------------------

        try:

            await super().stop()

            logger.info(
                "🛑 Bot stopped"
            )

        except Exception:

            logger.exception(
                "⚠️ Pyrogram shutdown error"
            )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        logger.info("")
        logger.info(
            "🚀 Starting Anime News Bot..."
        )

        bot = AnimeBot()

        bot.run()

    except KeyboardInterrupt:

        logger.info(
            "🛑 Bot stopped manually"
        )

    except Exception:

        logger.exception(
            "❌ FATAL BOT ERROR"
        )