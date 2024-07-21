"""Listener.py"""
import sys
from datetime import datetime
from json import decoder
from traceback import format_exception

from aiohttp import ClientError, client_exceptions
from discord import Embed, Interaction, errors
from discord.app_commands import (AppCommandError, CheckFailure, Command,
                                  CommandOnCooldown)
from discord.ext.commands import Cog
from pytz import timezone

from Utils import utils
from Utils.constants import config_ids, date_format


class Listener(Cog):
    """Listener / Events"""

    def __init__(self, bot):
        self.bot = bot
        self.bot.tree.on_error = self.on_app_command_error

    @Cog.listener()
    async def on_app_command_completion(self, interaction: Interaction, command: Command):
        """Commands Counter"""
        if "name" not in interaction.data or not command:
            return
        msg = self.__get_error_msg(interaction)

        my_cogs = sorted([cog for cog in self.bot.cogs if cog != "Listener"] + ["BlackMarket"])
        channel_name = f"{str(command.name).lower().split()[-1].replace('+', '-plus')}"
        guild = self.bot.get_guild(config_ids["commands_server_id"])
        cog_name = command.module.split(".")[-1]
        if cog_name == "__main__":
            return
        category = guild.categories[my_cogs.index(cog_name)]
        channels = {channel.name: channel for channel in category.channels}
        if channel_name in channels:
            await channels[channel_name].send(msg)
        else:
            channel = await category.create_text_channel(name=channel_name)
            await channel.send(msg)

        # update commands count
        commands_count = await utils.find_one("collection", "commands_count")
        if str(command.name) not in commands_count:
            commands_count[str(command.name)] = 0
        commands_count[str(command.name)] += 1

        await utils.replace_one("collection", "commands_count", commands_count)

    @staticmethod
    def __get_error_msg(interaction: Interaction):
        """Get error message"""
        data = interaction.data["name"] + " " + " ".join(
            f"**{x.get('name')}**: {x.get('value')}" for x in interaction.data.get('options', []))
        return f"[{datetime.now().astimezone(timezone('Europe/Berlin')).strftime(date_format)}] : {data}"

    @Cog.listener()
    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError):
        """on app command error"""
        error = getattr(error, 'original', error)
        msg = self.__get_error_msg(interaction)

        error_channel = self.bot.get_channel(config_ids["error_channel_id"])
        exc_type, exc_value, exc_traceback = sys.exc_info()
        locals_before_exception = (exc_traceback.tb_next or exc_traceback).tb_frame.f_locals
        locals_before_exception.pop("self", None)
        locals_before_exception.pop("interaction", None)
        error_msg = f"{locals_before_exception}\n{msg}\n```{''.join(format_exception(type(error), error, error.__traceback__))}```"
        if len(error_msg) > 2000:
            error_msg = error_msg[:990] + "\n...\n" + error_msg[-990:]
        await error_channel.send(error_msg)

        if isinstance(error, CheckFailure):
            return await utils.custom_followup(interaction, str(error))

        user_error = "Unknown error"

        if isinstance(error, errors.NotFound):
            #     interaction.command.reset_cooldown(interaction)
            # AttributeError: 'Command' object has no attribute 'reset_cooldown'
            # await utils.reset_cooldown(interaction)
            return
        elif isinstance(error, CommandOnCooldown):
            return await utils.custom_followup(
                interaction,
                f"{error}\nYou can buy premium and remove all cooldowns at https://www.buymeacoffee.com/RipEsim")

        elif isinstance(error, (decoder.JSONDecodeError, OSError, client_exceptions.ClientConnectorError,
                                ClientError)) or "Cannot connect to host" in str(error) or not str(error).strip():
            user_error = 'Ooops, Houston we have a problem, it is either e-sim fault or YOU broke something!\n\n' \
                         'If you did everything right - its probably e-sim fault. You may simply try again.\n' \
                         'Otherwise - react with :information_source:' \
                         '\n(If you tried multiple times, consider using `/delay`)'

        elif isinstance(error, (TypeError, KeyError, IndexError, AttributeError, UnboundLocalError)):
            user_error = f"Possibly my fault. Please contact <@{config_ids['OWNER_ID']}>" \
                         f" or report it in the support server: {config_ids['support_invite']}"

        embed = Embed(colour=0xFF0000, title="There was an error.", timestamp=interaction.created_at,
                      description=f"- [Support Server]({config_ids['support_invite']})\n\n" +
                                  (f"Command - `{interaction.command.name}`" if interaction.command else ""))
        embed.add_field(name="Error:", value=user_error, inline=False)
        try:
            await utils.custom_followup(interaction, embed=embed)
        except Exception:
            await interaction.user.send("I am unable to send messages to the channel.\n"
                                        "If you don't see me on the Member List on the right panel, "
                                        "you should give me more access.")


async def setup(bot):
    """Setup"""
    await bot.add_cog(Listener(bot))
