import os

API_ID = int(os.environ.get("API_ID", ""))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", ""))
ADMIN_ID = int(os.environ.get("ADMIN_ID", ""))

# ADMIN_IDS is used by helper/news_job.py
ADMIN_IDS = [OWNER_ID, ADMIN_ID]

LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "")
UPDATE_INTERVAL = int(os.environ.get("UPDATE_INTERVAL", "5"))  # minutes
PORT = int(os.environ.get("PORT", "8080"))  # for web health checks
DB_NAME = "anime_news"
DB_URL = os.environ.get("DB_URI", "")

# Messages (you can override via env vars)
START_MSG = os.environ.get("START_MSG", "Bᴀᴋᴀᴀᴀᴀ {mention}... \n<blockquote><b>Iᴀᴍ ᴀ ᴀᴅᴠᴀɴᴄᴇ Aᴜᴛᴏ ᴀɴɪᴍᴇ ɴᴇᴡs Bᴏᴛ ᴡʜɪᴄʜ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴜᴘʟᴏᴀᴅs ᴛʜᴇ ʟᴀᴛᴇsᴛ ᴀɴɪᴍᴇ ɴᴇᴡs ɪɴ ᴛʜᴇ ᴄʜᴀɴɴᴇʟ.</b></blockquote>")
HELP_MSG = os.environ.get("HELP_MSG", "<b><u>Hᴇʀᴇ ᴍʏ Cᴏᴍᴍᴀɴᴅs</u></b>:- \n\n<blockquote>• /add_rss - ᴛᴏ ᴀᴅᴅ ɴᴇᴡ ғᴇᴇᴅ (Mᴀx 2 ᴀᴛ ᴏɴᴄᴇ) \n• /rem_rss - ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴀɴʏ ʀss ғᴇᴇᴅ. \n• /view_rss - ᴛᴏ ᴠɪᴇᴡ ᴀᴅᴅᴇᴅ ʀss ғᴇᴇᴅs. \n• /add_chnl - ʀᴏᴜᴛᴇ ɴᴇᴡs ᴛᴏ ᴄʜᴀɴɴᴇʟ. \n• /rem_chnl  : Rᴇᴍᴏᴠᴇ ᴄʜᴀɴɴᴇʟ ʀᴏᴜᴛᴇ. \n•/view_chnl : ᴛᴏ ᴠɪᴇᴡ ᴀᴄᴛɪᴠᴇ ᴄʜᴀɴɴᴇʟ ʀᴏᴜᴛᴇs. \n•/status : ᴛᴏ ᴄʜᴇᴄᴋ ᴛʜᴇ ʙᴏᴛ sᴛᴀᴛᴜs.</blockquote>")
ABOUT_MSG = os.environ.get("ABOUT_MSG", "<i><b><blockquote>◈ ᴄʀᴇᴀᴛᴏʀ: <a href=https://t.me/CantarellaBots>RexBots</a>\n◈ ꜰᴏᴜɴᴅᴇʀ ᴏꜰ : <a href=https://t.me/CantarellaBots>CANTARELLABOTS</a>\n◈ ᴅᴇᴠᴇʟᴏᴘᴇʀ: <a href='https://t.me/about_zani/117'>ZANI</a>\n◈ ᴅᴀᴛᴀʙᴀsᴇ: <a href='https://www.mongodb.com/docs/'>ᴍᴏɴɢᴏ ᴅʙ</a>\n» ᴅᴇᴠᴇʟᴏᴘᴇʀ: <a href='https://t.me/about_zani/117'>ZANI</a></blockquote></b></i>")

# ⚠️ CHANGE THESE TO DIRECT IMAGE URLs (ending with .jpg/.png)
START_PIC = os.environ.get("START_PIC", "https://files.catbox.moe/t3c8bc.jpg")
HELP_PIC = os.environ.get("HELP_PIC", "https://files.catbox.moe/t3c8bc.jpg")
ABOUT_PIC = os.environ.get("ABOUT_PIC", "https://files.catbox.moe/t3c8bc.jpg")

# (Unused, but kept for compatibility)
CHNL_USERNAME = "@Anicore_Animes"

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
FANART_API_KEY = os.getenv("FANART_API_KEY", "")   # added for img command
RESTART_LOG_CHAT = os.getenv("RESTART_LOG_CHAT", "")