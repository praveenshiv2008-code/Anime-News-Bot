from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import *

@Client.on_message(filters.command('start') & filters.private)
async def start_command(client: Client, message: Message):
    inline_buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("• ᴀʙᴏᴜᴛ", callback_data="about"),
                InlineKeyboardButton("Hᴇʟᴘ •", callback_data="help")
            ]
        ]
    )
    try:
        await message.reply_photo(
            photo=START_PIC,
            caption=START_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name or "",
                username="@" + message.from_user.username if message.from_user.username else None,
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=inline_buttons
        )
    except Exception as e:
        logger.error(f"Error in start_command: {e}")
        await message.reply_text("An error occurred while processing your request.")