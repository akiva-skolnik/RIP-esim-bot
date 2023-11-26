"""Listener.py"""
from datetime import datetime
from json import decoder
from traceback import format_exception

from aiohttp import ClientError, client_exceptions
from discord import Embed, Interaction, errors
from discord.app_commands import AppCommandError, CheckFailure, Command
from discord.ext.commands import Cog, CommandOnCooldown
from pytz import timezone

from Help import utils
from Help.constants import date_format


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
        data = interaction.data["name"] + " " + " ".join(
            f"**{x['name']}**: {x.get('value')}" for x in interaction.data.get('options', []))

        msg = f"[{datetime.now().astimezone(timezone('Europe/Berlin')).strftime(date_format)}] : {data}"

        my_cogs = sorted([cog for cog in self.bot.cogs if cog != "Listener"] + ["BlackMarket"])
        channel_name = f"{str(command.name).lower().split()[-1].replace('+', '-plus')}"
        guild = self.bot.get_guild(int(self.bot.config_ids["commands_server"]))
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

    @Cog.listener()
    async def on_app_command_error(self, interaction: Interaction, error: AppCommandError):
        """on app command error"""
        error = getattr(error, 'original', error)
        data = interaction.data["name"] + " " + " ".join(
            f"**{x['name']}**: {x.get('value')}" for x in interaction.data.get('options', []))
        msg = f"[{datetime.now().astimezone(timezone('Europe/Berlin')).strftime(date_format)}] : {data}"
        if not isinstance(error, CheckFailure):
            error_channel = self.bot.get_channel(int(self.bot.config_ids["error_channel"]))
            try:
                await error_channel.send(
                    f"{msg}\n```{''.join(format_exception(type(error), error, error.__traceback__))}```")
            except Exception:  # Big msg
                await error_channel.send(f"{msg}\n{error}"[:1950])

        if isinstance(error, errors.NotFound):
            return
        elif isinstance(error, CommandOnCooldown):
            return await utils.custom_followup(
                interaction,
                f"{error}\nYou can buy premium and remove all cooldowns at https://www.buymeacoffee.com/RipEsim")

        elif isinstance(error, (decoder.JSONDecodeError, OSError, client_exceptions.ClientConnectorError,
                                ClientError)) or "Cannot connect to host" in str(error) or not str(error).strip():
            error1 = 'Ooops, Houston we have a problem, it is either e-sim fault or YOU broke something!\n\n' \
                     'If you did everything right - its probably e-sim fault. You may simply try again.\n' \
                     'Otherwise - react with :information_source:' \
                     '\n(If you tried multiple times, consider using `/delay`)'

        elif isinstance(error, (TypeError, KeyError, IndexError, AttributeError, UnboundLocalError)):
            error1 = f"Possibly my fault.\n\n{error}"
        else:
            error1 = str(error)
        if not error1:
            error1 = "Unknown error"
        if not str(error1):
            error1 = "Server takes too long to respond"

        embed = Embed(colour=0xFF0000, title="There was an error.", timestamp=interaction.created_at,
                      description=f"- [Support Server]({self.bot.config_ids['support_invite']})\n\n" +
                                  (f"Command - `{interaction.command.name}`" if interaction.command else ""))
        embed.add_field(name="Error:", value=error1, inline=False)
        try:
            await utils.custom_followup(interaction, embed=embed)
        except Exception:
            await interaction.user.send("I am unable to send messages to the channel.\n"
                                        "If you don't see me on the Member List on the right panel, you should give me more access.")


async def setup(bot):
    """Setup"""
    await bot.add_cog(Listener(bot))
