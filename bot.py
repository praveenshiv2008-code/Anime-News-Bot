import logging
import asyncio

from datetime import datetime
from zoneinfo import ZoneInfo

from pyrogram import Client
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

from config import *
from helper.news_job import broadcast_news
from helper.weekly_anime import send_weekly_anime


# --------------------------------------------------
# PROFESSIONAL LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("AnimeBot")


# --------------------------------------------------
# TIMEZONE
# --------------------------------------------------

IST = ZoneInfo("Asia/Kolkata")


# --------------------------------------------------
# BOT
# --------------------------------------------------

class AnimeBot(Client):

    def __init__(self):

        super().__init__(
            name="anime_session",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            plugins=dict(root="plugins")
        )

        self.web_runner = None
        self.scheduler = None


    # --------------------------------------------------
    # START
    # --------------------------------------------------

    async def start(self):

        await super().start()

        logger.info("✅ Pyrogram Client Started")


        # --------------------------------------------------
        # SCHEDULER
        # --------------------------------------------------

        self.scheduler = AsyncIOScheduler(
            timezone=IST
        )


        # --------------------------------------------------
        # EXISTING RSS NEWS JOB
        # --------------------------------------------------

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


        # --------------------------------------------------
        # WEEKLY TOP 16 ANIME
        #
        # EVERY SUNDAY
        # 8:00 PM IST
        # --------------------------------------------------

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


        # --------------------------------------------------
        # START SCHEDULER
        # --------------------------------------------------

        self.scheduler.start()


        logger.info(
            "✅ RSS scheduler started — checking every "
            f"{UPDATE_INTERVAL} minute(s)"
        )

        logger.info(
            "🏆 Weekly Top 16 Anime scheduled — "
            "Every Sunday at 8:00 PM IST"
        )


        # --------------------------------------------------
        # FIRST RSS CHECK
        # --------------------------------------------------

        asyncio.create_task(
            broadcast_news(self)
        )

        logger.info(
            "✅ First broadcast task launched"
        )


        # --------------------------------------------------
        # RENDER HEALTH CHECK SERVER
        # --------------------------------------------------

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


        self.web_runner = web.AppRunner(app)

        await self.web_runner.setup()


        site = web.TCPSite(
            self.web_runner,
            "0.0.0.0",
            PORT
        )


        await site.start()


        logger.info(
            f"✅ Web server running on 0.0.0.0:{PORT}"
        )


    # --------------------------------------------------
    # STOP
    # --------------------------------------------------

    async def stop(self, *args):

        # --------------------------------------------------
        # STOP SCHEDULER
        # --------------------------------------------------

        if self.scheduler:

            try:

                self.scheduler.shutdown(
                    wait=False
                )

                logger.info(
                    "🛑 Scheduler stopped"
                )

            except Exception as e:

                logger.error(
                    f"Scheduler shutdown error: {e}"
                )


        # --------------------------------------------------
        # STOP WEB SERVER
        # --------------------------------------------------

        if self.web_runner:

            try:

                await self.web_runner.cleanup()

                logger.info(
                    "🛑 Web server stopped"
                )

            except Exception as e:

                logger.error(
                    f"Web server shutdown error: {e}"
                )


        # --------------------------------------------------
        # STOP PYROGRAM
        # --------------------------------------------------

        await super().stop()


        logger.info(
            "🛑 Bot Stopped"
        )


# --------------------------------------------------
# RUN BOT
# --------------------------------------------------

if __name__ == "__main__":

    AnimeBot().run()