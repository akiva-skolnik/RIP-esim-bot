"""Setup.py"""
from discord import Interaction
from discord.app_commands import Range, Transform, checks, command, describe
from discord.ext.commands import Cog

from Utils import utils
from Utils.constants import all_servers
from Utils.transformers import Server


class Setup(Cog):
    """Battle Commands"""

    def __init__(self, bot) -> None:
        self.bot = bot

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @command()
    async def cancel(self, interaction: Interaction, command_name: str) -> None:
        """Cancels a given (long) command."""
        self.bot.cancel_command[interaction.user.id] = command_name
        await utils.custom_followup(
            interaction, "If you are running that command now, i will try to cancel it. "
                         "You have my word! (it might take some time tho)",
            ephemeral=True)

    @command()
    @describe(server="If you do not have preference, it will add the nick to all servers.",
              nick="Write `-` if you wish to cancel the default nick detection")
    async def default(self, interaction: Interaction, server: Transform[str, Server], nick: str) -> None:
        """Set default nick (per server) for all commands."""

        user_id = str(interaction.user.id)
        d = self.bot.default_nick_dict
        if server in d.get(user_id, {}):
            del d[user_id][server]
            await utils.custom_followup(
                interaction, f"You no longer have a default nick at `{server}`\n"
                             f"If you wish to set a default nick, invoke the command again", ephemeral=True)
            if not d[user_id]:
                del d[user_id]
        elif user_id not in d:
            if nick != "-":
                nick = (await utils.get_content(f'https://{server}.e-sim.org/apiCitizenByName.html?name={nick}'))["login"]
            d[user_id] = {server: nick}
            await utils.custom_followup(interaction, f"`{nick}` is now your default nick at `{server}`", ephemeral=True)
        else:
            for server in all_servers:
                if user_id not in d:
                    d[user_id] = {}
                d[user_id][server] = nick
            await utils.custom_followup(interaction, f"`{nick}` is now your default nick in all the active servers",
                                        ephemeral=True)
        await utils.replace_one("collection", interaction.command.name, d)

    @command()
    @describe(seconds="Default is set to 0.4 seconds, and you can raise it up to 2 seconds.")
    async def delay(self, interaction: Interaction, seconds: Range[float, 0.4, 2.0]) -> None:
        """Set custom delay between requests to e-sim to prevent some of e-sim errors."""

        if seconds == 0.4:
            if str(interaction.user.id) in self.bot.custom_delay_dict:
                del self.bot.custom_delay_dict[str(interaction.user.id)]
            await utils.custom_followup(interaction, "I will now wait 0.4 second (the default) between each request!",
                                        ephemeral=True)
        else:
            self.bot.custom_delay_dict[str(interaction.user.id)] = seconds
            await utils.custom_followup(
                interaction, f"I will now wait `{seconds}` seconds between each request! "
                             f"Let's hope e-sim won't block this too.",
                ephemeral=True)
        await utils.replace_one("collection", interaction.command.name, self.bot.custom_delay_dict)

    @command()
    async def phone(self, interaction: Interaction) -> None:
        """Auto-convert all embeds to phone format."""
        if str(interaction.user.id) in self.bot.phone_users:
            self.bot.phone_users.remove(str(interaction.user.id))
            await utils.custom_followup(
                interaction, "Embeds will be sent to you now at computer format! To change it invoke the command again.",
                ephemeral=True)

        else:
            self.bot.phone_users.append(str(interaction.user.id))
            await utils.custom_followup(
                interaction, "Embeds will be sent to you now at phone format! To change it invoke the command again.",
                ephemeral=True)

        await utils.replace_one("collection", interaction.command.name, {"users": self.bot.phone_users})


async def setup(bot) -> None:
    """Setup"""
    await bot.add_cog(Setup(bot))
