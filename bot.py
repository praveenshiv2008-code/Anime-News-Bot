import logging
import asyncio
import os

from datetime import datetime
from zoneinfo import ZoneInfo

from aiohttp import web

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from html import escape

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import *

from helper.news_job import broadcast_news
from helper.weekly_anime import send_weekly_anime
from helper.anime_images import send_all_anime_images


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
# /IMG COMMAND
# ============================================================

@Client.on_message(
    filters.command("img")
)
async def img_command(
    client,
    message: Message
):

    # --------------------------------------------------------
    # Check anime name
    # --------------------------------------------------------

    if len(message.command) < 2:

        await message.reply_text(
            "🖼️ <b>Anime Image Search</b>\n\n"
            "Use:\n"
            "<code>/img anime name</code>\n\n"
            "Example:\n"
            "<code>/img Solo Leveling</code>",
            parse_mode=ParseMode.HTML
        )

        return


    anime_name = " ".join(
        message.command[1:]
    ).strip()


    if not anime_name:

        await message.reply_text(
            "❌ Please enter an anime name.",
            parse_mode=ParseMode.HTML
        )

        return


    # --------------------------------------------------------
    # Loading message
    # --------------------------------------------------------

    loading = await message.reply_text(
        "🖼️ <b>Searching anime artwork...</b>",
        parse_mode=ParseMode.HTML
    )


    try:

        count = await send_all_anime_images(

            client,

            message.chat.id,

            anime_name

        )


        # ----------------------------------------------------
        # Remove loading message
        # ----------------------------------------------------

        try:

            await loading.delete()

        except Exception:

            pass


        # ----------------------------------------------------
        # No images
        # ----------------------------------------------------

        if count == 0:

            await message.reply_text(
                "❌ <b>No suitable images found.</b>\n\n"
                f"Anime: <code>{escape(anime_name)}</code>",
                parse_mode=ParseMode.HTML
            )

            return


        # ----------------------------------------------------
        # Success
        #
        # No message is sent here.
        #
        # /img is supposed to send images only.
        # ----------------------------------------------------

        logger.info(
            "[IMG] Sent %s images for '%s'",
            count,
            anime_name
        )


    except Exception as e:

        logger.exception(
            "[IMG] Image search failed"
        )


        try:

            await loading.edit_text(

                "❌ <b>Image search failed.</b>\n\n"
                f"<code>{escape(str(e)[:800])}</code>",

                parse_mode=ParseMode.HTML

            )

        except Exception:

            pass


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

            plugins=dict(
                root="plugins"
            )

        )


        self.web_runner = None

        self.scheduler = None


    # ========================================================
    # START
    # ========================================================

    async def start(self):

        # ----------------------------------------------------
        # Start Pyrogram
        # ----------------------------------------------------

        await super().start()


        logger.info(
            "✅ Pyrogram Client Started"
        )


        # ----------------------------------------------------
        # Get bot information
        # ----------------------------------------------------

        try:

            me = await self.get_me()

            logger.info(
                "🤖 Logged in as @%s",
                me.username
            )

        except Exception as e:

            logger.warning(
                "Could not get bot information: %s",
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

        asyncio.create_task(
            self._run_first_news_check()
        )


        logger.info(
            "✅ First broadcast task launched"
        )


        # ====================================================
        # RENDER HEALTH SERVER
        # ====================================================

        async def health(request):

            return web.Response(

                text=(
                    "Anime News Bot is running! ✅"
                ),

                status=200

            )


        # ----------------------------------------------------
        # Create web application
        # ----------------------------------------------------

        app = web.Application()


        # ----------------------------------------------------
        # Routes
        # ----------------------------------------------------

        app.router.add_get(
            "/",
            health
        )

        app.router.add_get(
            "/health",
            health
        )


        # ----------------------------------------------------
        # Runner
        # ----------------------------------------------------

        self.web_runner = web.AppRunner(
            app
        )


        await self.web_runner.setup()


        # ----------------------------------------------------
        # Render PORT
        # ----------------------------------------------------

        port = int(
            os.environ.get(
                "PORT",
                PORT
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


    # ========================================================
    # FIRST NEWS CHECK
    # ========================================================

    async def _run_first_news_check(self):

        try:

            await broadcast_news(
                self
            )

        except Exception as e:

            logger.exception(
                "Initial RSS broadcast failed: %s",
                e
            )


    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
        *args
    ):

        # ----------------------------------------------------
        # Stop scheduler
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

                logger.error(
                    "Scheduler shutdown error: %s",
                    e
                )


        # ----------------------------------------------------
        # Stop web server
        # ----------------------------------------------------

        if self.web_runner:

            try:

                await self.web_runner.cleanup()


                logger.info(
                    "🛑 Web server stopped"
                )


            except Exception as e:

                logger.error(
                    "Web server shutdown error: %s",
                    e
                )


        # ----------------------------------------------------
        # Stop Pyrogram
        # ----------------------------------------------------

        try:

            await super().stop()

            logger.info(
                "🛑 Bot Stopped"
            )

        except Exception as e:

            logger.error(
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