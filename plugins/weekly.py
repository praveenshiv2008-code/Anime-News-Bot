from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from config import OWNER_ID, ADMIN_ID
from helper.weekly_anime import send_weekly_anime


ADMIN_IDS = [OWNER_ID, ADMIN_ID]


def is_admin(_, __, message: Message):
    return bool(
        message.from_user
        and message.from_user.id in ADMIN_IDS
    )


admin = filters.create(is_admin)


@Client.on_message(filters.command("weekly") & admin)
async def weekly_command(client: Client, message: Message):

    msg = await message.reply_text(
        "⏳ <b>Fetching the current Top 16 anime...</b>",
        parse_mode=ParseMode.HTML
    )

    try:

        await send_weekly_anime(client)

        await msg.edit_text(
            "✅ <b>Weekly Top 16 posted successfully!</b>",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:

        await msg.edit_text(
            "❌ <b>Weekly post failed.</b>\n\n"
            f"<code>{str(e)[:3000]}</code>",
            parse_mode=ParseMode.HTML
        )


@Client.on_message(filters.command("weeklytest") & admin)
async def weekly_test_command(client: Client, message: Message):

    msg = await message.reply_text(
        "🧪 <b>Testing Weekly Top 16...</b>",
        parse_mode=ParseMode.HTML
    )

    try:

        await send_weekly_anime(client)

        await msg.edit_text(
            "✅ <b>Weekly Top 16 test completed!</b>",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:

        await msg.edit_text(
            "❌ <b>Test failed.</b>\n\n"
            f"<code>{str(e)[:3000]}</code>",
            parse_mode=ParseMode.HTML
        )