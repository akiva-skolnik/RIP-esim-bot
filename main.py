"""Main Module."""
import asyncio
import importlib
import logging
import os
import subprocess
from sys import modules
from traceback import format_exc

import matplotlib
from discord import Interaction
from discord.app_commands import guilds
from discord.utils import setup_logging

from Utils import utils, db_utils
from Utils.constants import all_servers, config_ids
from bot.bot import bot, load_extensions
from exts.Battle import (motivate_func, ping_func, watch_auction_func,
                         watch_func)
from exts.General import remind_func

matplotlib.use('Agg')
bot.utils = utils
bot.db_utils = db_utils


@bot.event
async def on_error(*args, **kwargs) -> None:
    """Error Handling."""
    if len(args) > 1 and hasattr(args[1], "clean_content"):
        msg = f"[{utils.get_current_time_str()}] {args[1].clean_content}"
    else:
        msg = " "
    msg += kwargs.get('msg', '')
    error_channel = bot.get_channel(config_ids["error_channel_id"])
    await error_channel.send(f"{msg}\n```{format_exc()}"[:1900] + "```")


async def activate_reminder() -> None:
    """Activating Reminder Function at Restart."""
    db_dict = await utils.find_one("collection", "remind")
    for reminder_id in list(db_dict):
        inner_dict = db_dict[reminder_id]
        channel = bot.get_channel(int(reminder_id.split()[0]))
        if channel:
            bot.loop.create_task(
                remind_func(channel, inner_dict["when"], reminder_id, inner_dict["msg"]))
            await asyncio.sleep(1)
        else:
            db_dict = await utils.find_one("collection", "remind")
            del db_dict[reminder_id]
            await utils.replace_one("collection", "remind", db_dict)
    await utils.replace_one("collection", "remind", db_dict)


async def activate_watch_and_ping() -> None:
    """Activating Watch, Auction and Ping Function at Restart."""
    db_dict = await utils.find_one("collection", "auctions") or {"auctions": []}
    for inner_dict in list(db_dict["auctions"]):
        channel = bot.get_channel(inner_dict["channel_id"])
        if channel and not inner_dict.get("removed"):
            bot.loop.create_task(
                watch_auction_func(channel, inner_dict['link'], inner_dict['t'],
                                   inner_dict['custom'], inner_dict["author_id"]))
            await asyncio.sleep(1.5)
        else:
            db_dict = await utils.find_one("collection", "auctions") or {"auctions": []}
            db_dict["auctions"].remove(inner_dict)
            await utils.replace_one("collection", "auctions", db_dict)
        await asyncio.sleep(5)

    db_dict = await utils.find_one("collection", "watch") or {"watch": []}
    for inner_dict in list(db_dict["watch"]):
        channel = bot.get_channel(inner_dict["channel_id"])
        if channel and not inner_dict.get("removed"):
            bot.loop.create_task(
                watch_func(bot, channel, inner_dict['link'], inner_dict['t'],
                           inner_dict['role'], inner_dict['custom'], inner_dict["author_id"]))
            await asyncio.sleep(1.5)  # To avoid race condition and ratelimit
        else:
            # It may have changed in the meantime
            db_dict = await utils.find_one("collection", "watch") or {"watch": []}
            db_dict["watch"].remove(inner_dict)
            await utils.replace_one("collection", "watch", db_dict)

        await asyncio.sleep(5)

    db_dict = await utils.find_one("collection", "ping")
    for key in list(db_dict):
        # channel_id, reminder_id = key.split()
        channel = bot.get_channel(int(key.split()[0]))
        if channel:
            bot.loop.create_task(ping_func(
                channel=channel, t=db_dict[key]["t"], server=db_dict[key]["server"],
                ping_id=key, country=db_dict[key]["country"],
                role=db_dict[key]["role"], author_id=db_dict[key]["author_id"]))
            await asyncio.sleep(10)
        else:
            db_dict = await utils.find_one("collection", "ping")
            del db_dict[key]
            await utils.replace_one("collection", "ping", db_dict)


async def activate_motivate() -> None:
    """Activating Motivate Function at Restart."""
    db_dict = await utils.find_one("collection", "motivate")
    for server in db_dict:
        if server in all_servers:
            bot.loop.create_task(motivate_func(bot, server, db_dict))
            await asyncio.sleep(20)


async def start() -> None:
    """Starter Function."""
    await bot.wait_until_ready()
    print(bot.user.name)
    # update_donors.start()
    if bot.config.get("test_mode"):
        return

    utils.alert.start()
    await activate_reminder()
    await activate_watch_and_ping()
    await activate_motivate()
    print("Bot is ready")


@bot.tree.command()
@guilds(utils.hidden_guild)
async def update_from_source(interaction: Interaction) -> None:
    """Updates the code from the source."""
    if not bot.config.get("test_mode"):
        process = subprocess.Popen(["git", "pull"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=bot.root)
        output = process.communicate()[0]
        await utils.custom_followup(interaction, output.decode("utf-8") or "Error")
    else:  # local
        await utils.custom_followup(interaction, "Reloading all extensions...")
    await load_extensions(reload=True)
    importlib.reload(modules["Utils"])


async def main() -> None:
    """Main Function."""
    async with bot:
        bot.loop.create_task(start())
        # bot.tree.copy_global_to(guild=Object(id=937490523227312200))

        handler = logging.FileHandler(filename=os.path.join(bot.root, "ripesim.log"))
        setup_logging(handler=handler, level=logging.INFO)
        await bot.start(bot.config["TOKEN"])


asyncio.run(main())
