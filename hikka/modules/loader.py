"""Loads and registers modules"""

#              © Copyright 2022
#
#          https://t.me/codercoffee

import asyncio
import importlib
import inspect
import logging
import os
import re
import sys
import urllib
import uuid
from importlib.abc import SourceLoader
from importlib.machinery import ModuleSpec
import telethon
from telethon.tl.types import Message
import functools
from typing import Any, Union
from aiogram.types import CallbackQuery

import requests

from .. import loader, utils, main
from ..compat import geek

logger = logging.getLogger(__name__)

VALID_URL = r"[-[\]_.~:/?#@!$&'()*+,;%<=>a-zA-Z0-9]+"

VALID_PIP_PACKAGES = re.compile(
    r"^\s*# ?requires:(?: ?)((?:{url} )*(?:{url}))\s*$".format(url=VALID_URL),
    re.MULTILINE,
)

USER_INSTALL = "PIP_TARGET" not in os.environ and "VIRTUAL_ENV" not in os.environ

GIT_REGEX = re.compile(
    r"^https?://github\.com((?:/[a-z0-9-]+){2})(?:/tree/([a-z0-9-]+)((?:/[a-z0-9-]+)*))?/?$",
    flags=re.IGNORECASE,
)


class StringLoader(SourceLoader):  # pylint: disable=W0223
    """Load a python module/file from a string"""

    def __init__(self, data, origin):
        self.data = data.encode("utf-8") if isinstance(data, str) else data
        self.origin = origin

    def get_code(self, fullname):
        source = self.get_source(fullname)
        if source is None:
            return None
        return compile(source, self.origin, "exec", dont_inherit=True)

    def get_filename(self, fullname):
        return self.origin

    def get_data(self, filename):  # pylint: disable=W0221,W0613
        # W0613 is not fixable, we are overriding
        # W0221 is a false positive assuming docs are correct
        return self.data


def unescape_percent(text):
    i = 0
    ln = len(text)
    is_handling_percent = False
    out = ""

    while i < ln:
        char = text[i]

        if char == "%" and not is_handling_percent:
            is_handling_percent = True
            i += 1
            continue

        if char == "d" and is_handling_percent:
            out += "."
            is_handling_percent = False
            i += 1
            continue

        out += char
        is_handling_percent = False
        i += 1

    return out


def get_git_api(url):
    m = GIT_REGEX.search(url)

    if m is None:
        return None

    branch = m.group(2)
    path_ = m.group(3)
    api_url = "https://api.github.com/repos{}/contents".format(m.group(1))

    if path_ is not None and len(path_) > 0:
        api_url += path_

    if branch:
        api_url += f"?ref={branch}"

    return api_url


@loader.tds
class LoaderMod(loader.Module):
    """Loads modules"""

    strings = {
        "name": "Loader",
        "repo_config_doc": "Fully qualified URL to a module repo",
        "avail_header": "<b>📲 Official modules from repo</b>",
        "select_preset": "<b>⚠️ Please select a preset</b>",
        "no_preset": "<b>🚫 Preset not found</b>",
        "preset_loaded": "<b>✅ Preset loaded</b>",
        "no_module": "<b>🚫 Module not available in repo.</b>",
        "no_file": "<b>🚫 File not found</b>",
        "provide_module": "<b>⚠️ Provide a module to load</b>",
        "bad_unicode": "<b>🚫 Invalid Unicode formatting in module</b>",
        "load_failed": "<b>🚫 Loading failed. See logs for details</b>",
        "loaded": "<b>🪁 Module </b><code>{}</code>{}<b> loaded.</b>{}",
        "no_class": "<b>What class needs to be unloaded?</b>",
        "unloaded": "<b>🔥 Module unloaded.</b>",
        "not_unloaded": "<b>🚫 Module not unloaded.</b>",
        "requirements_failed": "<b>🚫 Requirements installation failed</b>",
        "requirements_installing": "<b>🔄 Installing requirements...</b>",
        "requirements_restart": "<b>🔄 Requirements installed, but a restart is required</b>",
        "all_modules_deleted": "<b>✅ All modules deleted</b>",
        "single_cmd": "\n📍 <code>{}{}</code> 👉🏻 ",
        "undoc_cmd": "👁‍🗨 No docs",
        "ihandler": "\n🎹 <i>Inline</i>: <code>{}</code> 👉🏻 ",
        "undoc_ihandler": "👁‍🗨 No docs",
        "inline_init_failed": (
            "🚫 <b>This module requires Hikka inline feature and "
            "initialization of InlineManager failed</b>\n"
            "<i>Please, remove one of your old bots from @BotFather and "
            "restart userbot to load this module</i>"
        ),
        "version_incompatible": "🚫 <b>This module requires Hikka {}+\nPlease, update with </b><code>.update</code>",
        "ffmpeg_required": "🚫 <b>This module requires FFMPEG, which is not installed</b>",
        "developer": "\n\n🧑‍💻 <b>Developer: </b><code>{}</code>",
        "module_fs": "💿 <b>Would you like to save this module to filesystem, so it won't get unloaded after restart?</b>",
        "save": "💿 Save",
        "no_save": "🚫 Don't save",
        "save_for_all": "💽 Always save to fs",
        "never_save": "🚫 Never save to fs",
        "will_save_fs": "💽 Now all modules, loaded with .loadmod will be saved to filesystem",
    }

    def __init__(self):
        super().__init__()
        self.config = loader.ModuleConfig(
            "MODULES_REPO",
            "https://mods.hikariatama.ru/",
            lambda m: self.strings("repo_config_doc", m),
        )

    def _update_modules_in_db(self) -> None:
        self._db.set(
            __name__,
            "loaded_modules",
            {
                module.__class__.__name__: module.__origin__
                for module in self.allmodules.modules
                if module.__origin__.startswith("http")
            },
        )

    @loader.owner
    async def dlmodcmd(self, message: Message) -> None:
        """Downloads and installs a module from the official module repo"""
        if args := utils.get_args(message):
            args = args[0] if urllib.parse.urlparse(args[0]).netloc else args[0].lower()

            await self.download_and_install(args, message)
            self._update_modules_in_db()
        else:
            available = "\n".join(
                f"<code>{i}</code>"
                for i in sorted(
                    [
                        utils.escape_html(i)
                        for i in (await self.get_repo_list("full")).values()
                    ]
                )
            )

            await utils.answer(
                message,
                f"<b>{self.strings('avail_header')}</b>\n{available}",
            )

    @loader.owner
    async def dlpresetcmd(self, message: Message) -> None:
        """Set modules preset"""
        args = utils.get_args(message)

        if not args:
            await utils.answer(message, self.strings("select_preset", message))
            return

        try:
            await self.get_repo_list(args[0])
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                await utils.answer(message, self.strings("no_preset", message))
                return

            raise

        self._db.set(__name__, "chosen_preset", args[0])
        self._db.set(__name__, "loaded_modules", {})

        await utils.answer(message, self.strings("preset_loaded", message))
        await self.allmodules.commands["restart"](await message.reply("_"))

    async def _get_modules_to_load(self):
        todo = await self.get_repo_list(self._db.get(__name__, "chosen_preset", None))
        todo.update(**self._db.get(__name__, "loaded_modules", {}))
        return todo

    async def get_repo_list(self, preset=None):
        if preset is None or preset == "none":
            preset = "minimal"

        r = await utils.run_sync(
            requests.get,
            f'{self.config["MODULES_REPO"].strip("/")}/{preset}.txt',
        )
        r.raise_for_status()
        return {
            f"Preset_mod_{i}": link
            for i, link in enumerate(set(filter(lambda x: x, r.text.split("\n"))))
        }

    async def download_and_install(self, module_name, message=None):
        try:
            if urllib.parse.urlparse(module_name).netloc:
                url = module_name
            else:
                url = f'{self.config["MODULES_REPO"].strip("/")}/{module_name}.py'

            r = await utils.run_sync(requests.get, url)

            if r.status_code == 404:
                if message is not None:
                    await utils.answer(message, self.strings("no_module", message))

                return False

            r.raise_for_status()
            return await self.load_module(
                r.content.decode("utf-8"),
                message,
                module_name,
                url,
            )
        except Exception:
            logger.exception(f"Failed to load {module_name}")

    async def _inline__load(
        self,
        call: CallbackQuery,
        doc: str,
        path_: Union[str, None],
        mode: str,
    ) -> None:
        save = False
        if mode == "all_yes":
            self._db.set(main.__name__, "permanent_modules_fs", True)
            self._db.set(main.__name__, "disable_modules_fs", False)
            await call.answer(self.strings("will_save_fs"))
            save = True
        elif mode == "all_no":
            self._db.set(main.__name__, "disable_modules_fs", True)
            self._db.set(main.__name__, "permanent_modules_fs", False)
        elif mode == "once":
            save = True

        if path_ is not None:
            await self.load_module(doc, call, origin=path_, save_fs=save)
        else:
            await self.load_module(doc, call, save_fs=save)

    @loader.owner
    async def loadmodcmd(self, message: Message) -> None:
        """Loads the module file"""
        msg = message if message.file else (await message.get_reply_message())

        if msg is None or msg.media is None:
            if args := utils.get_args(message):
                try:
                    path_ = args[0]
                    with open(path_, "rb") as f:
                        doc = f.read()
                except FileNotFoundError:
                    await utils.answer(message, self.strings("no_file", message))
                    return
            else:
                await utils.answer(message, self.strings("provide_module", message))
                return
        else:
            path_ = None
            doc = await msg.download_media(bytes)

        logger.debug("Loading external module...")

        try:
            doc = doc.decode("utf-8")
        except UnicodeDecodeError:
            await utils.answer(message, self.strings("bad_unicode", message))
            return

        if not self._db.get(
            main.__name__,
            "disable_modules_fs",
            False,
        ) and not self._db.get(main.__name__, "permanent_modules_fs", False):
            if message.file:
                await message.edit("")
                message = await message.respond("🌘")

            if await self.inline.form(
                self.strings("module_fs"),
                message=message,
                reply_markup=[
                    [
                        {
                            "text": self.strings("save"),
                            "callback": self._inline__load,
                            "args": (doc, path_, "once"),
                        },
                        {
                            "text": self.strings("no_save"),
                            "callback": self._inline__load,
                            "args": (doc, path_, "no"),
                        },
                    ],
                    [
                        {
                            "text": self.strings("save_for_all"),
                            "callback": self._inline__load,
                            "args": (doc, path_, "all_yes"),
                        }
                    ],
                    [
                        {
                            "text": self.strings("never_save"),
                            "callback": self._inline__load,
                            "args": (doc, path_, "all_no"),
                        }
                    ],
                ],
            ):
                return

        if path_ is not None:
            await self.load_module(
                doc,
                message,
                origin=path_,
                save_fs=self._db.get(main.__name__, "permanent_modules_fs", False)
                and not self._db.get(main.__name__, "disable_modules_fs", False),
            )
        else:
            await self.load_module(
                doc,
                message,
                save_fs=self._db.get(main.__name__, "permanent_modules_fs", False)
                and not self._db.get(main.__name__, "disable_modules_fs", False),
            )

    async def load_module(
        self,
        doc: str,
        message: Message,
        name: Union[str, None] = None,
        origin: str = "<string>",
        did_requirements: bool = False,
        save_fs: bool = False,
    ) -> None:
        if any(
            line.replace(" ", "") == "#scope:ffmpeg" for line in doc.splitlines()
        ) and os.system("ffmpeg -version"):
            if isinstance(message, Message):
                await utils.answer(message, self.strings("ffmpeg_required"))
            return

        if (
            any(line.replace(" ", "") == "#scope:inline" for line in doc.splitlines())
            and not self.inline.init_complete
        ):
            if isinstance(message, Message):
                await utils.answer(message, self.strings("inline_init_failed"))
            return

        if re.search(r"# ?scope: ?hikka_min", doc):
            ver = re.search(
                r"# ?scope: ?hikka_min ([0-9]+\.[0-9]+\.[0-9]+)",
                doc,
            ).group(1)
            ver_ = tuple(map(int, ver.split(".")))
            if main.__version__ < ver_:
                if isinstance(message, Message):
                    await utils.answer(
                        message,
                        self.strings("version_incompatible").format(ver),
                    )
                return

        developer = re.search(r"# ?meta developer: ?(.+)", doc)
        developer = developer.group(1) if developer else False
        developer = self.strings("developer").format(developer) if developer else ""

        if name is None:
            uid = "__extmod_" + str(uuid.uuid4())
        else:
            if name.startswith(self.config["MODULES_REPO"]):
                name = name.split("/")[-1].split(".py")[0]

            uid = name.replace("%", "%%").replace(".", "%d")

        module_name = "hikka.modules." + uid

        doc = geek.compat(doc)

        try:
            try:
                spec = ModuleSpec(module_name, StringLoader(doc, origin), origin=origin)
                instance = self.allmodules.register_module(
                    spec,
                    module_name,
                    origin,
                    save_fs=save_fs,
                )
            except ImportError as e:
                logger.info(
                    "Module loading failed, attemping dependency installation",
                    exc_info=True,
                )
                # Let's try to reinstall dependencies
                try:
                    requirements = list(
                        filter(
                            lambda x: x and x[0] not in ("-", "_", "."),
                            map(
                                str.strip,
                                VALID_PIP_PACKAGES.search(doc)[1].split(" "),
                            ),
                        )
                    )
                except TypeError:
                    logger.warning("No valid pip packages specified in code, attemping installation from error")  # fmt: skip
                    requirements = [e.name]

                logger.debug(f"Installing requirements: {requirements}")

                if not requirements:
                    raise Exception("Nothing to install") from e

                if did_requirements:
                    if message is not None:
                        await utils.answer(
                            message,
                            self.strings("requirements_restart", message),
                        )

                    return

                if message is not None:
                    await utils.answer(
                        message,
                        self.strings("requirements_installing", message),
                    )

                pip = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "-q",
                    "--disable-pip-version-check",
                    "--no-warn-script-location",
                    *["--user"] if USER_INSTALL else [],
                    *requirements,
                )

                rc = await pip.wait()

                if rc != 0:
                    if message is not None:
                        await utils.answer(
                            message,
                            self.strings("requirements_failed", message),
                        )

                    return

                importlib.invalidate_caches()

                return await self.load_module(
                    doc,
                    message,
                    name,
                    origin,
                    True,
                    save_fs,
                )  # Try again
            except loader.LoadError as e:
                if message:
                    await utils.answer(message, f"🚫 <b>{utils.escape_html(str(e))}</b>")
                return
        except BaseException as e:
            logger.exception(f"Loading external module failed due to {e}")

            if message is not None:
                await utils.answer(message, self.strings("load_failed", message))

            return

        instance.inline = self.inline
        instance.get = functools.partial(
            self._mod_get,
            mod=instance.strings["name"],
        )
        instance.set = functools.partial(
            self._mod_set,
            mod=instance.strings["name"],
        )

        if hasattr(instance, "__version__") and isinstance(instance.__version__, tuple):
            version = f"<b><i> (v{'.'.join(list(map(str, list(instance.__version__))))})</i></b>"
        else:
            version = ""

        try:
            try:
                self.allmodules.send_config_one(instance, self._db, self.translator)
                await self.allmodules.send_ready_one(
                    instance,
                    self._client,
                    self._db,
                    self.allclients,
                )
            except loader.LoadError as e:
                if message:
                    await utils.answer(message, f"🚫 <b>{utils.escape_html(str(e))}</b>")
                return
        except Exception as e:
            logger.exception(f"Module threw because {e}")

            if message is not None:
                await utils.answer(message, self.strings("load_failed", message))

            return

        if message is not None:
            try:
                modname = instance.strings("name", message)
            except KeyError:
                modname = getattr(instance, "name", "ERROR")

            modhelp = ""
            prefix = utils.escape_html(
                (self._db.get(main.__name__, "command_prefix", False) or ".")
            )

            if instance.__doc__:
                modhelp += (
                    f"<i>\nℹ️ {utils.escape_html(inspect.getdoc(instance))}</i>\n"
                )

            if any(
                line.replace(" ", "") == "#scope:disable_onload_docs"
                for line in doc.splitlines()
            ):
                await utils.answer(
                    message,
                    self.strings("loaded", message).format(
                        modname.strip(), version, modhelp
                    )
                    + developer,
                )
                return

            for _name, fun in sorted(
                instance.commands.items(),
                key=lambda x: x[0],
            ):
                modhelp += self.strings("single_cmd", message).format(prefix, _name)

                if fun.__doc__:
                    modhelp += utils.escape_html(inspect.getdoc(fun))
                else:
                    modhelp += self.strings("undoc_cmd", message)

            if self.inline.init_complete:
                if hasattr(instance, "inline_handlers"):
                    for _name, fun in sorted(
                        instance.inline_handlers.items(),
                        key=lambda x: x[0],
                    ):
                        modhelp += self.strings("ihandler", message).format(
                            f"@{self.inline.bot_username} {_name}"
                        )

                        if fun.__doc__:
                            modhelp += utils.escape_html(
                                "\n".join(
                                    [
                                        line.strip()
                                        for line in inspect.getdoc(fun).splitlines()
                                        if not line.strip().startswith("@")
                                    ]
                                )
                            )
                        else:
                            modhelp += self.strings("undoc_ihandler", message)

            try:
                await utils.answer(
                    message,
                    self.strings("loaded", message).format(
                        modname.strip(),
                        version,
                        modhelp,
                    )
                    + developer,
                )
            except telethon.errors.rpcerrorlist.MediaCaptionTooLongError:
                await message.reply(
                    self.strings("loaded", message).format(
                        modname.strip(),
                        version,
                        modhelp,
                    )
                    + developer
                )

        return

    @loader.owner
    async def unloadmodcmd(self, message: Message) -> None:
        """Unload module by class name"""
        args = utils.get_args_raw(message)

        if not args:
            await utils.answer(message, self.strings("no_class", message))
            return

        worked = self.allmodules.unload_module(args)

        self._db.set(
            __name__,
            "loaded_modules",
            {
                mod: link
                for mod, link in self._db.get(__name__, "loaded_modules", {}).items()
                if mod not in worked
            },
        )

        await utils.answer(
            message,
            self.strings("unloaded" if worked else "not_unloaded", message),
        )

    def _mod_get(self, *args, mod: str = None) -> Any:
        return self._db.get(mod, *args)

    def _mod_set(self, *args, mod: str = None) -> bool:
        return self._db.set(mod, *args)

    @loader.owner
    async def clearmodulescmd(self, message: Message) -> None:
        """Delete all installed modules"""
        self._db.set(__name__, "loaded_modules", {})

        await utils.answer(message, self.strings("all_modules_deleted", message))

        self._db.set(__name__, "chosen_preset", "none")

        await self.allmodules.commands["restart"](await message.reply("_"))

    async def _update_modules(self):
        todo = await self._get_modules_to_load()
        for mod in todo.values():
            await self.download_and_install(mod)

        self._update_modules_in_db()

    async def client_ready(self, client, db):
        self._db = db
        self._client = client

        # Legacy db migration
        if isinstance(self._db.get(__name__, "loaded_modules", {}), list):
            self._db.set(
                __name__,
                "loaded_modules",
                {
                    f"Loaded_module_{i}": link
                    for i, link in enumerate(
                        self._db.get(__name__, "loaded_modules", {})
                    )
                },
            )

        await self._update_modules()
