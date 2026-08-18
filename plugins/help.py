from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode


HELP_TEXT = """
<b>✦ ᴀɴɪᴍᴇ ɴᴇᴡs ʙᴏᴛ ✦</b>

/start - sᴛᴀʀᴛ ᴛʜᴇ ᴀɴɪᴍᴇ ɴᴇᴡs ʙᴏᴛ

/help - sʜᴏᴡ ʜᴇʟᴘ ᴀɴᴅ ғᴇᴀᴛᴜʀᴇs

/anime Naruto - sᴇᴀʀᴄʜ ᴀɴ ᴀɴɪᴍᴇ
ᴀɴᴅ sʜᴏᴡ ɪᴛs ɪɴғᴏʀᴍᴀᴛɪᴏɴ

/img Naruto - ɢᴇᴛ ʜᴅ ᴀɴɪᴍᴇ ᴀʀᴛᴡᴏʀᴋ

/trending - sʜᴏᴡ ᴛʀᴇɴᴅɪɴɢ ᴀɴɪᴍᴇ

/weekly - sʜᴏᴡ ᴡᴇᴇᴋʟʏ ᴛᴏᴘ 𝟷𝟼

━━━━━━━━━━━━━━━━━━

✦ ʀss ᴀɴɪᴍᴇ ɴᴇᴡs
✦ ᴛʀᴀɪʟᴇʀs & ᴛᴇᴀsᴇʀs
✦ ʜᴅ ᴀɴɪᴍᴇ ɪᴍᴀɢᴇs
✦ ᴀɴɪᴍᴇ ɪɴғᴏʀᴍᴀᴛɪᴏɴ
"""


@Client.on_message(
    filters.command("help")
)
async def help_command(
    client: Client,
    message: Message
):

    await message.reply_text(
        HELP_TEXT,
        parse_mode=ParseMode.HTML
    )