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

            # Automatically load everything inside plugins/
            plugins={
                "root": "plugins"
            }
        )

        self.web_runner = None
        self.scheduler = None


    # ========================================================
    # START
    # ========================================================

    async def start(self):

        # ----------------------------------------------------
        # START PYROGRAM
        # ----------------------------------------------------

        await super().start()

        logger.info(
            "✅ Pyrogram Client Started"
        )


        # ----------------------------------------------------
        # BOT INFORMATION
        # ----------------------------------------------------

        try:

            me = await self.get_me()

            logger.info(
                "🤖 Bot: @%s",
                me.username
            )

        except Exception as e:

            logger.warning(
                "Could not get bot information: %s",
                e
            )


        # ----------------------------------------------------
        # RESTART NOTIFICATION
        # ----------------------------------------------------
        #
        # Add this to Render environment variables:
        #
        # RESTART_LOG_CHAT=-100xxxxxxxxxx
        #
        # Leave empty if you don't want restart messages.
        #

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

        except Exception as e:

            logger.warning(
                "Could not send restart notification: %s",
                e
            )


        # ====================================================
        # SCHEDULER
        # ====================================================

        self.scheduler = AsyncIOScheduler(
            timezone=IST
        )


        # ====================================================
        # RSS NEWS JOB
        # ====================================================

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


        # ====================================================
        # WEEKLY TOP 16
        #
        # EVERY SUNDAY
        # 8:00 PM IST
        # ====================================================

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


        # ====================================================
        # START SCHEDULER
        # ====================================================

        self.scheduler.start()


        logger.info(
            "✅ RSS scheduler started — "
            "checking every %s minute(s)",
            UPDATE_INTERVAL
        )


        logger.info(
            "🏆 Weekly Top 16 Anime scheduled — "
            "Every Sunday at 8:00 PM IST"
        )


        # ====================================================
        # FIRST RSS CHECK
        # ====================================================

        try:

            asyncio.create_task(
                broadcast_news(self)
            )

            logger.info(
                "✅ First RSS broadcast task launched"
            )

        except Exception as e:

            logger.warning(
                "Could not launch first RSS check: %s",
                e
            )


        # ====================================================
        # RENDER HEALTH SERVER
        # ====================================================

        async def health(request):

            return web.Response(
                text="Anime News Bot is running! ✅",
                status=200
            )


        app = web.Application()


        app.router.add_get(
            "/",
            health
        )


        app.router.add_get(
            "/health",
            health
        )


        # ----------------------------------------------------
        # WEB RUNNER
        # ----------------------------------------------------

        self.web_runner = web.AppRunner(
            app
        )

        await self.web_runner.setup()


        # ----------------------------------------------------
        # PORT
        # ----------------------------------------------------

        port = int(
            globals().get(
                "PORT",
                10000
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

            except Exception as e:

                logger.warning(
                    "Scheduler shutdown error: %s",
                    e
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

            except Exception as e:

                logger.warning(
                    "Web server shutdown error: %s",
                    e
                )


        # ----------------------------------------------------
        # STOP PYROGRAM
        # ----------------------------------------------------

        try:

            await super().stop()

            logger.info(
                "🛑 Bot stopped"
            )

        except Exception as e:

            logger.warning(
                "Pyrogram shutdown error: %s",
                e
            )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:

        AnimeBot().run()

    except KeyboardInterrupt:

        logger.info(
            "🛑 Bot stopped manually"
        )

    except Exception as e:

        logger.exception(
            "❌ Fatal bot error: %s",
            e
        )