from pyrogram import Client, filters
from pyrogram.types import Message

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
        "⏳ Fetching the current Top 16 anime..."
    )

    try:
        await send_weekly_anime(client)

        await msg.edit_text(
            "✅ <b>Weekly Top 16 posted successfully!</b>",
            parse_mode="html"
        )

    except Exception as e:
        await msg.edit_text(
            f"❌ <b>Weekly post failed.</b>\n\n"
            f"<code>{e}</code>",
            parse_mode="html"
        )


@Client.on_message(filters.command("weeklytest") & admin)
async def weekly_test_command(client: Client, message: Message):
    msg = await message.reply_text(
        "🧪 Testing Weekly Top 16..."
    )

    try:
        await send_weekly_anime(client)

        await msg.edit_text(
            "✅ <b>Weekly Top 16 test completed!</b>",
            parse_mode="html"
        )

    except Exception as e:
        await msg.edit_text(
            f"❌ <b>Test failed.</b>\n\n"
            f"<code>{e}</code>",
            parse_mode="html"
        )