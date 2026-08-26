import os
import logging

from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message

from config import API_ID, API_HASH, BOT_TOKEN


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("TEST_BOT")


bot = Client(
    "anime_test_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


@bot.on_message(filters.private & filters.command("start"))
async def start(client: Client, message: Message):

    logger.info(
        "START RECEIVED FROM USER %s",
        message.from_user.id
    )

    await message.reply_text(
        "╭━━━━━「 ɪɴꜰᴏ 」━━━━━╮\n\n"
        "🔥 ʙᴏᴛ ɪs ᴡᴏʀᴋɪɴɢ!\n\n"
        "ʏᴏᴜʀ /start ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇᴀᴄʜɪɴɢ ᴛʜᴇ ʙᴏᴛ.\n\n"
        "╰━━━━━━━━━━━━━━╯\n\n"
        "⚡ Sᴛᴀʏ Uᴘᴅᴀᴛᴇᴅ"
    )


@bot.on_message(filters.private & filters.text)
async def test_message(client: Client, message: Message):

    logger.info(
        "MESSAGE RECEIVED: %s",
        message.text
    )


async def health(request):

    return web.Response(
        text="Anime News Bot is running!"
    )


async def main():

    await bot.start()

    me = await bot.get_me()

    logger.info(
        "===================================="
    )

    logger.info(
        "BOT CONNECTED"
    )

    logger.info(
        "USERNAME: @%s",
        me.username
    )

    logger.info(
        "BOT ID: %s",
        me.id
    )

    logger.info(
        "===================================="
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

    runner = web.AppRunner(app)

    await runner.setup()

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    logger.info(
        "HEALTH SERVER: %s",
        port
    )

    await bot.idle()


if __name__ == "__main__":

    import asyncio

    asyncio.run(main())