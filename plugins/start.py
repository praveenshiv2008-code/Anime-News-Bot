from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from config import START_MSG, START_PIC

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    user = message.from_user
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("• ᴀʙᴏᴜᴛ", callback_data="about"),
            InlineKeyboardButton("ʜᴇʟᴘ •", callback_data="help")
        ]
    ])
    try:
        await client.send_photo(
            chat_id=message.chat.id,
            photo=START_PIC,
            caption=START_MSG.format(
                first=user.first_name,
                last=user.last_name or "",
                username=f"@{user.username}" if user.username else "None",
                mention=user.mention,
                id=user.id
            ),
            reply_markup=buttons,
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await message.reply_text(
            START_MSG.format(
                first=user.first_name,
                last=user.last_name or "",
                username=f"@{user.username}" if user.username else "None",
                mention=user.mention,
                id=user.id
            ),
            reply_markup=buttons,
            parse_mode=ParseMode.HTML
        )