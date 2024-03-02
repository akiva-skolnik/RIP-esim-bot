"""Bot.py"""
import asyncio
import json
import os
from datetime import date, datetime

import asyncmy
from aiohttp import ClientSession, ClientTimeout
from discord import (AllowedMentions, Forbidden, Game, HTTPException, Intents,
                     Interaction, Message, NotFound, app_commands)
from discord.ext.commands import Bot, when_mentioned

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


async def load_extensions(reload: bool = False) -> None:
    """Loads extensions"""
    exts_path = os.path.join(root, "exts")
    for dirpath, dirnames, filenames in os.walk(exts_path):
        for file_name in filenames:
            if file_name.endswith(".py"):
                if reload:
                    await bot.reload_extension(f'exts.{file_name.replace(".py", "")}', package=exts_path)
                else:
                    await bot.load_extension(f'exts.{file_name.replace(".py", "")}', package=exts_path)
        break  # only walk the first level


def find_one(collection: str, _id: str) -> dict:
    """find one"""
    filename = os.path.join(os.path.dirname(root), f"db/{collection}_{_id}.json")
    if os.path.exists(filename):
        with open(filename, "r", encoding='utf-8') as file:
            return json.load(file)
    else:
        return {}


class MyTree(app_commands.CommandTree):
    """Lock new server"""

    async def interaction_check(self, interaction: Interaction) -> bool:
        """Lock new server"""
        # This is done at the beginning of every interaction.
        await interaction.response.defer()  # type: ignore

        if not any("mega" in str(v) for v in interaction.data.values()):
            return True

        # remove expired users
        expire_at = bot.premium_users.get(str(interaction.user.id), {}).get("expire_at", "")
        if expire_at and datetime.strptime(expire_at, "%d/%m/%Y") < datetime.now():
            del bot.premium_users[str(interaction.user.id)]

        today = str(date.today())
        if bot.premium_users.get(str(interaction.user.id), {}).get("level", -1) >= 1 or (
                interaction.guild and interaction.guild.id in bot.premium_servers):
            return True
        if bot.premium_users.get(str(interaction.user.id), {}).get("added_at", "") != today:
            bot.premium_users[str(interaction.user.id)] = {"added_at": today}
            # await replace_one("collection", "donors", bot.premium_users)
            return True
        try:
            await interaction.response.send_message(  # type: ignore
                "mega server is for premium users only. You can use one command per day for free."
                "\nGet premium at <https://www.buymeacoffee.com/RipEsim> :coffee:"
                "\nSupport: https://discord.com/invite/q96wSd6")
        except HTTPException:
            pass
        return False


class MyClient(Bot):
    """Custom Client"""

    def __init__(self) -> None:
        super().__init__(command_prefix=when_mentioned, case_insensitive=True,
                         activity=Game("type /"), allowed_mentions=AllowedMentions(
                replied_user=False), intents=Intents.default(), tree_cls=MyTree)
        self.root = root
        self.typing_gif = os.path.join(self.root, "files/typing.gif")
        config_path = os.path.join(self.root, "config.json")
        with open(config_path, 'r', encoding="utf-8") as file:
            self.config = json.load(file)
            # {"db_url": "", "TOKEN": ""}
        self.before_invoke(reset_cancel)
        self.should_cancel = should_cancel
        self.cancel_command = {}
        self.orgs = {}
        self.delay = {}

        self.session = None
        self.locked_sessions = {}
        self.phone_users = (find_one("collection", "phone") or {"users": []})["users"]
        self.default_nick_dict = find_one("collection", "default")
        self.premium_users = find_one("collection", "donors")
        self.premium_servers = (find_one("collection", "premium_guilds") or {"guilds": []})["guilds"]
        self.custom_delay_dict = find_one("collection", "delay")
        self.pool: asyncmy.Pool = None  # type: ignore
        self.db_lock = asyncio.Lock()

    async def setup_hook(self) -> None:
        headers = {"User-Agent": self.config["headers"]}
        self.session = ClientSession(timeout=ClientTimeout(total=100), headers=headers)
        self.pool = await asyncmy.create_pool(host=self.config.get("db_host", "localhost"),
                                              user=self.config.get("db_user", "root"),
                                              password=self.config["db_password"], autocommit=True)

        await load_extensions()


async def should_cancel(interaction: Interaction, msg: Message = None) -> bool:
    """Return whether the function should be cancelled"""
    if bot.cancel_command.get(interaction.user.id, "") == interaction.command.name:
        if msg is not None:
            try:
                await msg.delete()
            except (Forbidden, NotFound, HTTPException):
                pass
        del bot.cancel_command[interaction.user.id]
        return True
    return False


# TODO: make it class functions
async def reset_cancel(interaction: Interaction) -> None:
    """Reset the cancel option before each invoke"""
    if isinstance(interaction, Interaction) and await should_cancel(interaction):
        del bot.cancel_command[interaction.user.id]


bot = MyClient()
