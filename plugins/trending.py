import httpx

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode


ANILIST_URL = "https://graphql.anilist.co"


TRENDING_QUERY = """
query {

    Page(
        page: 1,
        perPage: 10
    ) {

        media(
            type: ANIME,
            sort: TRENDING_DESC
        ) {

            title {
                romaji
                english
            }

            averageScore

            popularity

            episodes

            status

            coverImage {
                large
            }

            siteUrl
        }
    }
}
"""


@Client.on_message(
    filters.command("trending")
)
async def trending_command(
    client: Client,
    message: Message
):

    loading = await message.reply_text(
        "✦ ғᴇᴛᴄʜɪɴɢ ᴛʀᴇɴᴅɪɴɢ ᴀɴɪᴍᴇ..."
    )


    try:

        async with httpx.AsyncClient(
            timeout=30
        ) as http:

            response = await http.post(

                ANILIST_URL,

                json={
                    "query": TRENDING_QUERY
                }
            )


        if response.status_code != 200:

            await loading.edit_text(
                "❌ ᴀɴɪʟɪsᴛ ᴇʀʀᴏʀ."
            )

            return


        data = response.json()


        anime_list = (
            data
            .get("data", {})
            .get("Page", {})
            .get("media", [])
        )


        if not anime_list:

            await loading.edit_text(
                "❌ ɴᴏ ᴛʀᴇɴᴅɪɴɢ ᴀɴɪᴍᴇ ғᴏᴜɴᴅ."
            )

            return


        await loading.delete()


        # ----------------------------------------------------
        # Send each anime with image
        # ----------------------------------------------------

        for index, anime in enumerate(
            anime_list,
            start=1
        ):

            title_data = anime.get(
                "title",
                {}
            )


            title = (
                title_data.get(
                    "english"
                )
                or
                title_data.get(
                    "romaji"
                )
                or
                "Unknown"
            )


            score = (
                anime.get(
                    "averageScore"
                )
                or "N/A"
            )


            popularity = (
                anime.get(
                    "popularity"
                )
                or "N/A"
            )


            episodes = (
                anime.get(
                    "episodes"
                )
                or "N/A"
            )


            status = (
                anime.get(
                    "status"
                )
                or "N/A"
            )


            image = (
                anime
                .get("coverImage", {})
                .get("large")
            )


            text = (

                f"🔥 <b>ᴛʀᴇɴᴅɪɴɢ #{index}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"

                f"🎬 <b>{title}</b>\n\n"

                f"⭐ <b>Rᴀᴛɪɴɢ:</b> "
                f"{score}/100\n"

                f"👥 <b>Pᴏᴘᴜʟᴀʀɪᴛʏ:</b> "
                f"{popularity}\n"

                f"📺 <b>Eᴘɪsᴏᴅᴇs:</b> "
                f"{episodes}\n"

                f"📡 <b>Sᴛᴀᴛᴜs:</b> "
                f"{status}\n\n"

                f"✦ <b>Sᴏᴜʀᴄᴇ:</b> AɴɪLɪsᴛ"
            )


            try:

                if image:

                    await client.send_photo(

                        chat_id=message.chat.id,

                        photo=image,

                        caption=text,

                        parse_mode=ParseMode.HTML

                    )

                else:

                    await client.send_message(

                        chat_id=message.chat.id,

                        text=text,

                        parse_mode=ParseMode.HTML

                    )


            except Exception as e:

                print(
                    f"Trending #{index} failed:",
                    e
                )


    except Exception as e:

        print(
            "Trending command error:",
            e
        )


        try:

            await loading.edit_text(
                "❌ ᴛʀᴇɴᴅɪɴɢ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ."
            )

        except Exception:

            pass