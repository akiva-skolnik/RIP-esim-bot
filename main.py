"""Main Module"""
import asyncio
import importlib
import subprocess
from datetime import datetime
from os import walk
from sys import modules
from traceback import format_exc

import matplotlib
from discord import Interaction
from discord.app_commands import guilds
from discord.utils import setup_logging
from pytz import timezone

from bot.bot import bot
from exts.Battle import (motivate_func, ping_func, watch_auction_func,
                         watch_func)
from exts.General import remind_func
from Help import utils

matplotlib.use('Agg')

@bot.event
async def on_error(*args, **kwargs) -> None:
    """Error Handling"""
    if len(args) > 1 and hasattr(args[1], "clean_content"):
        now = datetime.now().astimezone(timezone('Europe/Berlin'))
        msg = f"[{now.strftime(bot.date_format)}] {args[1].clean_content}"
    else:
        msg = " "
    msg += kwargs.get('msg', '')
    channel = bot.get_channel(int(bot.config_ids["error_channel"]))
    await channel.send(f"{msg}\n```{format_exc()}"[:1900] + "```")


async def delete_cup(coll: str) -> None:
    """Deleting Cup Function at Restart"""
    cup_db = await utils.find_one("collection", coll)
    for query, channels in cup_db.items():
        for channel_as_key in channels:
            for channel_id, _ in channel_as_key.items():
                channel = bot.get_channel(int(channel_id))
                if channel:
                    await channel.send(f"Error. Cup query `{query}` has been reset.")
                    await asyncio.sleep(1)
    await utils.replace_one("collection", coll, {})


async def activate_reminder() -> None:
    """Activating Reminder Function at Restart"""
    db_dict = await utils.find_one("collection", "remind")
    for reminder_id in list(db_dict):
        inner_dict = db_dict[reminder_id]
        channel = bot.get_channel(int(reminder_id.split()[0]))
        if channel:
            bot.loop.create_task(
                remind_func(channel, inner_dict["when"], reminder_id, inner_dict["msg"]))
            await asyncio.sleep(1)
        else:
            del db_dict[reminder_id]
            await utils.replace_one("collection", "remind", db_dict)
    await utils.replace_one("collection", "remind", db_dict)


async def activate_watch_and_ping() -> None:
    """Activating Watch, Auction and Ping Function at Restart"""
    db_dict = await utils.find_one("collection", "auction") or {"auction": []}
    for inner_dict in list(db_dict["auction"]):
        channel = bot.get_channel(int(inner_dict["channel"]))
        if channel:
            bot.loop.create_task(
                watch_auction_func(bot, channel, inner_dict['link'], inner_dict['t'],
                                   inner_dict['custom'], inner_dict["author_id"]))
        else:
            db_dict["auction"].remove(inner_dict)
            await utils.replace_one("collection", "auction", db_dict)
        await asyncio.sleep(5)

    db_dict = await utils.find_one("collection", "watch") or {"watch": []}
    for inner_dict in list(db_dict["watch"]):
        channel = bot.get_channel(int(inner_dict["channel"]))
        if channel:
            bot.loop.create_task(
                watch_func(bot, channel, inner_dict['link'], inner_dict['t'],
                           inner_dict['role'], inner_dict['custom'], inner_dict["author_id"]))
        else:
            db_dict["watch"].remove(inner_dict)
            await utils.replace_one("collection", "watch", db_dict)

        await asyncio.sleep(5)

    db_dict = await utils.find_one("collection", "ping")
    for key in list(db_dict):
        # channel_id, reminder_id = key.split()
        channel = bot.get_channel(int(key.split()[0]))
        if channel:
            bot.loop.create_task(ping_func(
                bot, channel=channel, t=db_dict[key]["t"], server=db_dict[key]["server"],
                ping_id=key, country=db_dict[key]["country"],
                role=db_dict[key]["role"], author_id=db_dict[key]["author_id"]))
            await asyncio.sleep(10)
        else:
            del db_dict[key]
            await utils.replace_one("collection", "ping", db_dict)


async def activate_motivate() -> None:
    """Activating Motivate Function at Restart"""
    db_dict = await utils.find_one("collection", "motivate")
    for server in db_dict:
        if server in bot.all_servers:
            bot.loop.create_task(motivate_func(bot, server, db_dict))
            await asyncio.sleep(20)


async def start() -> None:
    """Starter Function"""
    await bot.wait_until_ready()
    print(bot.user.name)
    # update_donors.start()
    if bot.config.get("test_mode"):
        return

    utils.alert.start()
    for coll in ("cup", "cup_plus"):
        await delete_cup(coll)
    await activate_reminder()
    await activate_watch_and_ping()
    await activate_motivate()


@bot.tree.command()
@guilds(utils.hidden_guild)
async def update_from_source(interaction: Interaction) -> None:
    """Updates the code from the source."""

    process = subprocess.Popen(["git", "pull"], stdout=subprocess.PIPE)
    output = process.communicate()[0]
    await interaction.response.send_message(output.decode("utf-8"))
    for (_, _, filenames) in walk("exts"):
        for file_name in filenames:
            if file_name.endswith(".py"):
                await bot.reload_extension(f'exts.{file_name.replace(".py", "")}')
    importlib.reload(modules["Help.utils"])


async def main() -> None:
    """Main Function"""
    async with bot:
        bot.loop.create_task(start())
        # bot.tree.copy_global_to(guild=Object(id=937490523227312200))
        setup_logging()
        await bot.start(bot.config["TOKEN"])


asyncio.run(main())
