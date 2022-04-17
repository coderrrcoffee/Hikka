#              © Copyright 2022
#
#          https://t.me/codercoffee

from .. import loader
import logging
from aiogram.types import CallbackQuery
from random import choice
import os

logger = logging.getLogger(__name__)
imgs = [
    "https://pa1.narvii.com/6644/16e88ec137d2ad2583937e7909b6a166c70f3f2a_hq.gif",
    "https://c.tenor.com/O3qIam1dAQQAAAAC/hug-cuddle.gif",
    "https://pa1.narvii.com/6853/8efac13a077dac28e6a500a5dd2a7f97dec668fd_hq.gif",
    "https://static.tumblr.com/ef1af4bfc7f5a5be30a24539d536e1ce/cehtffd/k3Hpiifhs/tumblr_static_tumblr_static__focused_v3.gif",
    "https://i.gifer.com/W9IO.gif",
    "https://c.tenor.com/6w7XKLSqFEUAAAAC/anime-hug.gif",
    "https://i2.wp.com/metanorn.net/wp-content/uploads/2011/08/NS3-04b.gif",
]

TEXT = """🌘🇬🇧 <b>Hello.</b> You've just installed <b>Hikka</b> userbot.

❓ <b>Need help?</b> Feel free to join our support chat. We help <b>everyone</b>.

📼 <b>Official modules sources: </b>
▫️ @hikarimods
▫️ @hikarimods_database
▫️ <code>.dlmod</code>

"""


TEXT_RU = """🌘🇷🇺 <b>Привет.</b> Твой юзербот <b>Hikka</b> установлен.

❓ <b>Нужна помощь?</b> Вступай в наш чат поддержки. Мы помогаем <b>всем</b>.

📼 <b>Официальные источники модулей: </b>
▫️ @hikarimods
▫️ @hikarimods_database
▫️ <code>.dlmod</code>

"""

if "OKTETO" in os.environ:
    TEXT += "☁️ <b>Your userbot is installed on Okteto</b>. Don't worry, you will get some notifications from @WebpageBot. Do not block him."
    TEXT_RU += "☁️ <b>Твой юзербот установлен на Okteto</b>. Не пугайся, когда будешь получать уведомления от @WebpageBot и не блокируй его."


@loader.tds
class QuickstartMod(loader.Module):
    """Notifies user about userbot installation"""

    strings = {"name": "Quickstart"}

    async def client_ready(self, client, db) -> None:
        self._me = (await client.get_me()).id

        mark = self.inline._generate_markup(
            [
                [{"text": "🥷 Support chat", "url": "https://t.me/hikka_talks"}],
                [{"text": "🇷🇺 Русский", "data": "hikka_qs_sw_lng_ru"}],
            ]
        )

        await self.inline.bot.send_animation(
            self._me,
            animation=choice(imgs),
            caption=TEXT,
            parse_mode="HTML",
            reply_markup=mark,
        )

        db.set("hikka", "disable_quickstart", True)

    async def quickstart_callback_handler(self, call: CallbackQuery) -> None:
        if not call.data.startswith("hikka_qs_sw_lng_"):
            return

        lang = call.data.split("_")[-1]
        if lang == "ru":
            mark = self.inline._generate_markup(
                [
                    [{"text": "🥷 Чат помощи", "url": "https://t.me/hikka_talks"}],
                    [{"text": "🇬🇧 English", "data": "hikka_qs_sw_lng_en"}],
                ]
            )

            await self.inline.bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=TEXT_RU,
                parse_mode="HTML",
                reply_markup=mark,
            )
        elif lang == "en":
            mark = self.inline._generate_markup(
                [
                    [{"text": "🥷 Support chat", "url": "https://t.me/hikka_talks"}],
                    [{"text": "🇷🇺 Русский", "data": "hikka_qs_sw_lng_ru"}],
                ]
            )

            await self.inline.bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=TEXT,
                parse_mode="HTML",
                reply_markup=mark,
            )
