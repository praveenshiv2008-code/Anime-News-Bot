import os
import sys
import asyncio
import logging
import importlib
import traceback

from zoneinfo import ZoneInfo

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.enums import ParseMode

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
#
# IMPORTANT:
# plugins.start has been removed.
# /start is registered directly in this file.
# ============================================================

PLUGIN_LIST = [
    "plugins.admin",
    "plugins.anime",
    "plugins.help",
    "plugins.img",
    "plugins.trending",
    "plugins.weekly",
]


# ============================================================
# DIRECT /START COMMAND
# ============================================================

@Client.on_message(
    filters.command("start") & filters.private
)
async def direct_start(
    client: Client,
    message: Message
):

    user = message.from_user

    if not user:
        return

    mention = user.mention
    user_id = user.id

    # --------------------------------------------------------
    # CREATE START MESSAGE
    # --------------------------------------------------------

    try:

        text = START_MSG.format(
            first=user.first_name or "",
            last=user.last_name or "",
            username=(
                f"@{user.username}"
                if user.username
                else "None"
            ),
            mention=mention,
            id=user_id
        )

    except Exception as e:

        logger.error(
            "START_MSG formatting failed: %s",
            e
        )

        text = (
            f"ʜᴇʟʟᴏ {mention}! 👋\n\n"
            "ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴀɴɪᴍᴇ ɴᴇᴡs ʙᴏᴛ.\n\n"
            "ᴜsᴇ /help ᴛᴏ sᴇᴇ ᴍʏ ᴄᴏᴍᴍᴀɴᴅs."
        )

    # --------------------------------------------------------
    # BUTTONS
    # --------------------------------------------------------

    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "• ᴀʙᴏᴜᴛ",
                    callback_data="about"
                ),
                InlineKeyboardButton(
                    "ʜᴇʟᴘ •",
                    callback_data="help"
                )
            ]
        ]
    )

    # --------------------------------------------------------
    # TRY PHOTO
    # --------------------------------------------------------

    if START_PIC:

        try:

            await message.reply_photo(
                photo=START_PIC,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=buttons
            )

            logger.info(
                "✅ /start photo sent to %s",
                user_id
            )

            return

        except Exception as e:

            logger.warning(
                "⚠️ START_PIC failed: %s",
                e
            )

    # --------------------------------------------------------
    # TEXT FALLBACK
    # --------------------------------------------------------

    try:

        await message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons,
            disable_web_page_preview=True
        )

        logger.info(
            "✅ /start text sent to %s",
            user_id
        )

    except Exception as e:

        logger.exception(
            "❌ /start completely failed: %s",
            e
        )


# ============================================================
# PLUGIN LOADER
# ============================================================

def load_plugins():

    logger.info("")
    logger.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    logger.info(
        "🔌 STARTING PLUGIN LOADER"
    )
    logger.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

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
                "✅ Plugin loaded: %s",
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

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    logger.info("")
    logger.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    logger.info(
        "📦 PLUGIN LOADING SUMMARY"
    )

    logger.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    logger.info(
        "✅ Loaded: %s / %s",
        len(loaded),
        len(PLUGIN_LIST)
    )

    for plugin_name in loaded:

        logger.info(
            "   🟢 %s",
            plugin_name
        )

    if failed:

        logger.error("")
        logger.error(
            "❌ Failed: %s / %s",
            len(failed),
            len(PLUGIN_LIST)
        )

        for plugin_name, error in failed:

            logger.error(
                "   🔴 %s → %s: %s",
                plugin_name,
                type(error).__name__,
                str(error)
            )

    else:

        logger.info("")
        logger.info(
            "🎉 ALL PLUGINS LOADED SUCCESSFULLY"
        )

    logger.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    return loaded, failed


# ============================================================
# LOAD PLUGINS
# ============================================================

LOADED_PLUGINS, FAILED_PLUGINS = load_plugins()


# ============================================================
# BOT CLASS
# ============================================================

class AnimeBot(Client):

    def __init__(self):

        super().__init__(
            name="anime_session",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN
        )

        self.web_runner = None
        self.scheduler = None
        self.news_task = None

    # ========================================================
    # NEWS CHECK
    # ========================================================

    async def safe_news_check(self):

        try:

            logger.info(
                "📰 Starting RSS news check..."
            )

            await broadcast_news(
                self
            )

            logger.info(
                "✅ RSS news check completed"
            )

        except asyncio.CancelledError:

            logger.info(
                "🛑 RSS task cancelled"
            )

            raise

        except Exception:

            logger.exception(
                "❌ RSS news check failed"
            )

    # ========================================================
    # START BOT
    # ========================================================

    async def start(self):

        await super().start()

        logger.info("")
        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        logger.info(
            "✅ PYROGRAM CLIENT STARTED"
        )

        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        # ----------------------------------------------------
        # BOT INFO
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
                "❌ Failed to get bot information"
            )

        # ----------------------------------------------------
        # PLUGIN STATUS
        # ----------------------------------------------------

        logger.info("")
        logger.info(
            "🔌 PLUGIN STATUS:"
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

        # ----------------------------------------------------
        # START STATUS
        # ----------------------------------------------------

        logger.info(
            "   🟢 start (direct handler)"
        )

        # ====================================================
        # RESTART LOG
        # ====================================================

        try:

            if RESTART_LOG_CHAT:

                await self.send_message(
                    chat_id=RESTART_LOG_CHAT,
                    text="✦ ʙᴏᴛ ʀᴇsᴛᴀʀᴛᴇᴅ ✓"
                )

        except Exception:

            logger.exception(
                "⚠️ Restart log failed"
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
                "✅ RSS scheduler: every %s minute(s)",
                UPDATE_INTERVAL
            )

            logger.info(
                "🏆 Weekly Top 16: Sunday 8:00 PM IST"
            )

        except Exception:

            logger.exception(
                "❌ Scheduler startup failed"
            )

        # ====================================================
        # FIRST NEWS CHECK
        # ====================================================

        try:

            self.news_task = asyncio.create_task(
                self.safe_news_check()
            )

            logger.info(
                "✅ First RSS task launched"
            )

        except Exception:

            logger.exception(
                "❌ Could not launch RSS task"
            )

        # ====================================================
        # RENDER WEB SERVER
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
                    str(PORT)
                )
            )

            site = web.TCPSite(
                self.web_runner,
                "0.0.0.0",
                port
            )

            await site.start()

            logger.info(
                "✅ Health server: 0.0.0.0:%s",
                port
            )

        except Exception:

            logger.exception(
                "❌ Health server failed"
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
            "📡 RSS News      : ONLINE"
        )

        logger.info(
            "🏆 Weekly Top 16 : ONLINE"
        )

        logger.info(
            "🔎 Anime Search  : ONLINE"
        )

        logger.info(
            "🖼 HD Images     : ONLINE"
        )

        logger.info(
            "🔥 Trending      : ONLINE"
        )

        logger.info(
            "▶ /start        : ONLINE"
        )

        logger.info(
            "▶ /help         : PLUGIN"
        )

        logger.info(
            "🔌 Plugins       : %s / %s",
            len(LOADED_PLUGINS),
            len(PLUGIN_LIST)
        )

        if FAILED_PLUGINS:

            logger.warning(
                "⚠️ Some plugins failed."
            )

        else:

            logger.info(
                "✅ ALL PLUGINS READY"
            )

        logger.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

    # ========================================================
    # STOP
    # ========================================================

    async def stop(self, *args):

        # ----------------------------------------------------
        # RSS TASK
        # ----------------------------------------------------

        if self.news_task:

            try:

                if not self.news_task.done():

                    self.news_task.cancel()

                    try:

                        await self.news_task

                    except asyncio.CancelledError:

                        pass

            except Exception:

                logger.exception(
                    "⚠️ RSS task shutdown error"
                )

        # ----------------------------------------------------
        # SCHEDULER
        # ----------------------------------------------------

        if self.scheduler:

            try:

                self.scheduler.shutdown(
                    wait=False
                )

            except Exception:

                logger.exception(
                    "⚠️ Scheduler shutdown error"
                )

        # ----------------------------------------------------
        # WEB SERVER
        # ----------------------------------------------------

        if self.web_runner:

            try:

                await self.web_runner.cleanup()

            except Exception:

                logger.exception(
                    "⚠️ Web server shutdown error"
                )

        # ----------------------------------------------------
        # PYROGRAM
        # ----------------------------------------------------

        try:

            await super().stop()

        except Exception:

            logger.exception(
                "⚠️ Pyrogram shutdown error"
            )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    logger.info(
        "🚀 Starting Anime News Bot..."
    )

    try:

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