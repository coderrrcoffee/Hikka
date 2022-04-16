from .. import loader
import logging
import asyncio
from .._types import LoadError
import json
import re
import websockets
from telethon.tl.functions.messages import SendReactionRequest

logger = logging.getLogger(__name__)

ALLOWED_ORIGINS = [
    "https://github.com/morisummerz/ftg-mods/raw/main",
    "https://raw.githubusercontent.com/morisummerz/ftg-mods/main",
    "https://mods.morisummer.ml",
    "https://gitlab.com/cakestwix/friendly-userbot-modules/-/raw/master",
    "https://twix.nonfalse-networks.net.ua/modules",
    "https://mods.hikariatama.ru",
    "https://raw.githubusercontent.com/hikariatama/ftg/master",
    "https://github.com/hikariatama/ftg/raw/master",
    "https://raw.githubusercontent.com/hikariatama/host/master",
    "https://github.com/hikariatama/host/raw/master",
]


@loader.tds
class OwODLMod(loader.Module):
    """Downloads stuff"""

    strings = {"name": "OwODL"}

    _connected = False

    async def _wss(self) -> None:
        async with websockets.connect("wss://hikka.hikariatama.ru/ws") as wss:
            await wss.send(self.get("token"))

            while True:
                ans = json.loads(await wss.recv())
                self._connected = True
                if ans["event"] == "dlmod":
                    try:
                        msg = (
                            await self._client.get_messages(
                                ans["channel"],
                                ids=[ans["message_id"]],
                            )
                        )[0]
                    except Exception:
                        await wss.send("msg_404")
                        continue

                    try:
                        link = re.search(
                            r".dlmod (https?://.*?\.py)",
                            msg.raw_text,
                        ).group(1)
                    except Exception:
                        await wss.send("link_404")
                        continue

                    if "/".join(link.split("/")[:-1]).lower() not in ALLOWED_ORIGINS:
                        await wss.send("🚫 Origin is not allowed")
                        continue

                    # Modules' creators spend so much time to create cool modules
                    # so this code part is a little propriety gesture. Send a ❤
                    # to a message with a link to currently downloading module
                    try:
                        await self._client(
                            SendReactionRequest(
                                peer=ans["channel"],
                                msg_id=ans["message_id"],
                                reaction="❤️",
                            )
                        )
                    except Exception:
                        pass

                    m = await self._client.send_message("me", f".dlmod {link}")
                    await self.allmodules.commands["dlmod"](m)
                    load = (await self._client.get_messages(m.peer_id, ids=[m.id]))[0]
                    await wss.send(load.raw_text.splitlines()[0])
                    await m.delete()

    async def _connect(self) -> None:
        while True:
            try:
                await self._wss()
            except websockets.exceptions.ConnectionClosedError:
                logger.debug("Token became invalid, revoking...")
                self._connected = False
                await self._get_token()
            except Exception:
                logger.debug("Socket disconnected, retry in 10 sec")
                self._connected = False

            await asyncio.sleep(10)

    async def _get_token(self) -> None:
        async with self._client.conversation(self._bot) as conv:
            m = await conv.send_message("/token")
            r = await conv.get_response()
            token = r.raw_text
            await m.delete()
            await r.delete()

            if not token.startswith("kirito_") and not token.startswith("asuna_"):
                raise LoadError("Can't get token")

            self.set("token", token)

        await self._client.delete_dialog(self._bot)

    async def client_ready(self, client, db) -> None:
        self._db = db
        self._client = client
        self._bot = "@OwO_userbot"

        if not self.get("token"):
            await self._get_token()

        self._task = asyncio.ensure_future(self._connect())

    async def on_unload(self) -> None:
        self._task.cancel()
