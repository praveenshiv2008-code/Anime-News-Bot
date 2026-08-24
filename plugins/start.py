from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.enums import ParseMode

from config import *

import logging


logger = logging.getLogger(__name__)


# ============================================================
# START COMMAND
# ============================================================

@Client.on_message(
    filters.command("start") & filters.private
)
async def start_command(
    client: Client,
    message: Message
):

    user = message.from_user

    # --------------------------------------------------------
    # USER INFORMATION
    # --------------------------------------------------------

    first = user.first_name or ""
    last = user.last_name or ""

    username = (
        f"@{user.username}"
        if user.username
        else "None"
    )

    mention = user.mention
    user_id = user.id

    # --------------------------------------------------------
    # START TEXT
    # --------------------------------------------------------

    try:

        start_text = START_MSG.format(
            first=first,
            last=last,
            username=username,
            mention=mention,
            id=user_id
        )

    except Exception as e:

        logger.error(
            "START_MSG formatting failed: %s",
            e
        )

        start_text = (
            f"ʜᴇʟʟᴏ {mention}!\n\n"
            "ɪ'ᴍ ᴀɴ ᴀɴɪᴍᴇ ɴᴇᴡs ʙᴏᴛ."
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
    # TRY START IMAGE
    # --------------------------------------------------------

    if START_PIC:

        try:

            await message.reply_photo(
                photo=START_PIC,
                caption=start_text,
                parse_mode=ParseMode.HTML,
                reply_markup=buttons
            )

            logger.info(
                "/start sent with photo to %s",
                user_id
            )

            return

        except Exception as e:

            logger.warning(
                "START_PIC failed: %s",
                e
            )

    # --------------------------------------------------------
    # TEXT FALLBACK
    # --------------------------------------------------------

    try:

        await message.reply_text(
            text=start_text,
            parse_mode=ParseMode.HTML,
            reply_markup=buttons,
            disable_web_page_preview=True
        )

        logger.info(
            "/start sent as text to %s",
            user_id
        )

    except Exception as e:

        logger.exception(
            "/start completely failed: %s",
            e
        )