import httpx

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode


ANILIST_URL = "https://graphql.anilist.co"


QUERY = """
query ($search: String!) {

    Media(
        search: $search,
        type: ANIME
    ) {

        id

        title {
            romaji
            english
            native
        }

        description(
            asHtml: false
        )

        episodes

        duration

        status

        averageScore

        meanScore

        popularity

        favourites

        genres

        season

        seasonYear

        startDate {
            year
            month
            day
        }

        endDate {
            year
            month
            day
        }

        nextAiringEpisode {
            airingAt
            timeUntilAiring
            episode
        }

        studios(
            isMain: true
        ) {
            nodes {
                name
            }
        }

        coverImage {
            extraLarge
        }

        siteUrl
    }
}
"""


def clean_description(
    text
):

    if not text:

        return "N/A"


    text = text.replace(
        "<br>",
        "\n"
    )

    text = text.replace(
        "<br/>",
        "\n"
    )

    text = text.replace(
        "<br />",
        "\n"
    )


    # Remove remaining basic HTML.

    import re

    text = re.sub(
        r"<[^>]+>",
        "",
        text
    )


    text = " ".join(
        text.split()
    )


    if len(text) > 700:

        text = text[:700] + "..."


    return text


@Client.on_message(
    filters.command("anime")
)
async def anime_command(
    client: Client,
    message: Message
):

    if len(message.command) < 2:

        await message.reply_text(
            "ᴜsᴀɢᴇ:\n\n"
            "<code>/anime Naruto</code>",
            parse_mode=ParseMode.HTML
        )

        return


    name = " ".join(
        message.command[1:]
    )


    loading = await message.reply_text(
        "✦ sᴇᴀʀᴄʜɪɴɢ ᴀɴɪᴍᴇ..."
    )


    try:

        async with httpx.AsyncClient(
            timeout=30
        ) as http:

            response = await http.post(

                ANILIST_URL,

                json={
                    "query": QUERY,
                    "variables": {
                        "search": name
                    }
                }
            )


        if response.status_code != 200:

            await loading.edit_text(
                "❌ ᴀɴɪʟɪsᴛ sᴇʀᴠᴇʀ ᴇʀʀᴏʀ."
            )

            return


        data = response.json()


        anime = (
            data
            .get("data", {})
            .get("Media")
        )


        if not anime:

            await loading.edit_text(
                "❌ ᴀɴɪᴍᴇ ɴᴏᴛ ғᴏᴜɴᴅ."
            )

            return


        title = (
            anime
            .get("title", {})
            .get("english")
            or
            anime
            .get("title", {})
            .get("romaji")
            or
            name
        )


        native = (
            anime
            .get("title", {})
            .get("native")
            or "N/A"
        )


        score = (
            anime.get(
                "averageScore"
            )
            or anime.get(
                "meanScore"
            )
            or "N/A"
        )


        popularity = (
            anime.get(
                "popularity"
            )
            or "N/A"
        )


        favourites = (
            anime.get(
                "favourites"
            )
            or 0
        )


        episodes = (
            anime.get(
                "episodes"
            )
            or "N/A"
        )


        duration = (
            anime.get(
                "duration"
            )
            or "N/A"
        )


        status = (
            anime.get(
                "status"
            )
            or "N/A"
        )


        season = (
            anime.get(
                "season"
            )
            or "N/A"
        )


        year = (
            anime.get(
                "seasonYear"
            )
            or "N/A"
        )


        genres = anime.get(
            "genres"
        ) or []


        genre_text = ", ".join(
            genres
        ) if genres else "N/A"


        studios = (
            anime
            .get("studios", {})
            .get("nodes", [])
        )


        studio_text = ", ".join(
            x.get("name", "")
            for x in studios
            if x.get("name")
        )


        if not studio_text:

            studio_text = "N/A"


        description = clean_description(
            anime.get(
                "description"
            )
        )


        next_episode = (
            anime.get(
                "nextAiringEpisode"
            )
        )


        if next_episode:

            episode_number = (
                next_episode.get(
                    "episode"
                )
            )

            airing_at = (
                next_episode.get(
                    "airingAt"
                )
            )

            if airing_at:

                from datetime import datetime

                date = datetime.fromtimestamp(
                    airing_at
                )

                next_text = (
                    f"Episode {episode_number} — "
                    f"{date.strftime('%d %b %Y, %H:%M')}"
                )

            else:

                next_text = (
                    f"Episode {episode_number}"
                )

        else:

            next_text = "N/A"


        text = (
            f"🎬 <b>{title}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"

            f"🌐 <b>Nᴀᴛɪᴠᴇ:</b> "
            f"{native}\n"

            f"⭐ <b>Rᴀᴛɪɴɢ:</b> "
            f"{score}/100\n"

            f"👥 <b>Pᴏᴘᴜʟᴀʀɪᴛʏ:</b> "
            f"{popularity}\n"

            f"❤️ <b>Fᴀᴠᴏᴜʀɪᴛᴇs:</b> "
            f"{favourites}\n\n"

            f"📺 <b>Eᴘɪsᴏᴅᴇs:</b> "
            f"{episodes}\n"

            f"⏱ <b>Dᴜʀᴀᴛɪᴏɴ:</b> "
            f"{duration} min\n"

            f"📡 <b>Sᴛᴀᴛᴜs:</b> "
            f"{status}\n"

            f"📅 <b>Sᴇᴀsᴏɴ:</b> "
            f"{season} {year}\n\n"

            f"🏷 <b>Gᴇɴʀᴇs:</b> "
            f"{genre_text}\n"

            f"🏢 <b>Sᴛᴜᴅɪᴏ:</b> "
            f"{studio_text}\n\n"

            f"⏭ <b>Nᴇxᴛ Eᴘɪsᴏᴅᴇ:</b> "
            f"{next_text}\n\n"

            f"📝 <b>Sʏɴᴏᴘsɪs:</b>\n"
            f"{description}\n\n"

            f"✦ <b>Sᴏᴜʀᴄᴇ:</b> AɴɪLɪsᴛ"
        )


        image = (
            anime
            .get("coverImage", {})
            .get("extraLarge")
        )


        await loading.delete()


        if image:

            try:

                await client.send_photo(

                    chat_id=message.chat.id,

                    photo=image,

                    caption=text,

                    parse_mode=ParseMode.HTML

                )

                return

            except Exception:

                pass


        await message.reply_text(
            text,
            parse_mode=ParseMode.HTML
        )


    except Exception as e:

        print(
            "Anime command error:",
            e
        )


        try:

            await loading.edit_text(
                "❌ ᴀɴɪᴍᴇ sᴇᴀʀᴄʜ ғᴀɪʟᴇᴅ."
            )

        except Exception:

            pass