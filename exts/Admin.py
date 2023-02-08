"""Admin.py"""
import textwrap
import traceback
from contextlib import redirect_stdout
from datetime import date
from io import BytesIO, StringIO

from discord import File, HTTPException, Interaction, User
from discord.app_commands import command, guilds
from discord.ext.commands import Cog

from Help import utils


class Admin(Cog):
    """Admin Commands"""
    def __init__(self, bot) -> None:
        self.bot = bot

    @command()
    @guilds(utils.hidden_guild)
    async def execute(self, interaction: Interaction, code: str) -> None:
        # https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/admin.py#L215
        """Executes a given code"""
        await interaction.response.defer()
        env = {
            'bot': self.bot,
            'interaction': interaction,
            'channel': interaction.channel,
            'author': interaction.user,
            'guild': interaction.guild
        }

        env.update(globals())

        # remove ```py\n```
        if code.startswith('```') and code.endswith('```'):
            code = '\n'.join(code.split('\n')[1:-1])
        else:  # remove `foo`
            code = code.strip('` \n')

        to_compile = f'async def func():\n{textwrap.indent(code, "  ")}'
        stdout = StringIO()
        try:
            exec(to_compile, env)
        except Exception as error:
            await utils.custom_followup(
                interaction, f'```py\n{error.__class__.__name__}: {error}\n```')
            return
        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            if value:
                await utils.custom_followup(
                    interaction, f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            if value:
                try:
                    await utils.custom_followup(interaction, f'```py\n{value}{ret or ""}\n```')
                except HTTPException:
                    io_output = BytesIO()
                    io_output.write((value + (ret or "")).encode())
                    io_output.seek(0)
                    await utils.custom_followup(interaction,
                                                file=File(fp=io_output, filename="output.txt"))

    @command()
    @guilds(utils.hidden_guild)
    async def load(self, interaction: Interaction, cmd: str) -> None:
        """Load Extensions"""
        await self.bot.reload_extension("exts." + cmd)
        await utils.custom_followup(interaction, f"{cmd} loaded", ephemeral=True)

    @command()
    @guilds(utils.hidden_guild)
    async def update(self, interaction: Interaction, user: User, level: int = 1,
                     reason: str = "donation") -> None:
        """Update Donors"""
        if level >= 0:
            self.bot.premium_users[str(user.id)] = {
                "level": level, "reason": reason, "nick": user.name, "added_at": str(date.today())}
        elif str(user.id) in self.bot.premium_users:
            del self.bot.premium_users[str(user.id)]

        await utils.replace_one("collection", "donors", self.bot.premium_users)
        await utils.custom_followup(interaction, "Done.", ephemeral=True)

    @command()
    @guilds(utils.hidden_guild)
    async def sync(self, interaction: Interaction, this_guild: bool = True) -> None:
        """Sync Commands"""
        await interaction.response.defer()
        if this_guild:
            synced = await self.bot.tree.sync(guild=interaction.guild)
        else:
            synced = await self.bot.tree.sync()
        await interaction.followup.send(f"Synced {len(synced)} commands")


async def setup(bot) -> None:
    """Setup"""
    await bot.add_cog(Admin(bot))
