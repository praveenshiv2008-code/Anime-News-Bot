import os
import logging
import asyncio

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
# BOT
# ============================================================

class AnimeBot(Client):

    def __init__(self):

        super().__init__(
            name="anime_session",

            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,

            # Load every .py file inside plugins/
            plugins={
                "root": "plugins"
            }
        )

        self.web_runner = None
        self.scheduler = None


    # ========================================================
    # SAFE RSS TASK
    # ========================================================

    async def safe_news_check(self):

        try:

            logger.info(
                "📰 Starting first RSS news check..."
            )

            await broadcast_news(self)

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
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        logger.info(
            "✅ Pyrogram Client Started"
        )

        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


        # ----------------------------------------------------
        # BOT INFORMATION
        # ----------------------------------------------------

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
        # CHECK PLUGINS DIRECTORY
        # ====================================================

        logger.info(
            "🔌 Checking plugins directory..."
        )

        try:

            plugins_dir = "plugins"

            if not os.path.isdir(
                plugins_dir
            ):

                logger.error(
                    "❌ plugins/ directory does not exist!"
                )

            else:

                plugin_files = sorted(
                    filename
                    for filename in os.listdir(
                        plugins_dir
                    )
                    if (
                        filename.endswith(".py")
                        and filename != "__init__.py"
                    )
                )

                if not plugin_files:

                    logger.warning(
                        "⚠️ No plugin files found!"
                    )

                else:

                    logger.info(
                        "📦 Found %s plugin file(s)",
                        len(plugin_files)
                    )

                    for filename in plugin_files:

                        logger.info(
                            "   ├─ %s",
                            filename
                        )

        except Exception:

            logger.exception(
                "❌ Could not inspect plugins directory"
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
            # RSS NEWS JOB
            # ------------------------------------------------

            self.scheduler.add_job(

                broadcast_news,

                "interval",

                minutes=UPDATE_INTERVAL,

                args=[self],

                id="broadcast_job",

                replace_existing=True,

                max_instances=1,

                coalesce=True

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

                coalesce=True

            )


            self.scheduler.start()

            logger.info(
                "✅ RSS scheduler started — "
                "checking every %s minute(s)",
                UPDATE_INTERVAL
            )

            logger.info(
                "🏆 Weekly Top 16 scheduled — "
                "Every Sunday at 8:00 PM IST"
            )

        except Exception:

            logger.exception(
                "❌ Scheduler startup failed"
            )


        # ====================================================
        # FIRST RSS CHECK
        # ====================================================

        try:

            asyncio.create_task(
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
        # READY
        # ====================================================

        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
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
            "🔌 Plugins        : LOADED"
        )

        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


    # ========================================================
    # STOP
    # ========================================================

    async def stop(self, *args):

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

        bot = AnimeBot()

        bot.run()

    except KeyboardInterrupt:

        logger.info(
            "🛑 Bot stopped manually"
        )

    except Exception:

        logger.exception(
            "❌ Fatal bot error"
        )