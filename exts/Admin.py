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
from Help.constants import all_servers, config_ids


class Admin(Cog):
    """Admin Commands"""
    def __init__(self, bot) -> None:
        self.bot = bot

    @command()
    @guilds(utils.hidden_guild)
    async def create_tables(self, interaction: Interaction, servers: str = ""):
        for server in servers.split(",") if servers else all_servers:
            async with self.bot.pool.acquire() as connection:
                async with connection.cursor() as cursor:
                    await cursor.execute("CREATE DATABASE " + server)

                    await cursor.execute(f'''CREATE TABLE {server}.apiBattles
                                          (battle_id INT UNSIGNED PRIMARY KEY,
                                          currentRound TINYINT,
                                          lastVerifiedRound TINYINT,
                                          attackerScore TINYINT,
                                          regionId SMALLINT UNSIGNED,
                                          defenderScore TINYINT,
                                          frozen BOOLEAN,
                                          type VARCHAR(32),
                                          defenderId SMALLINT UNSIGNED,
                                          attackerId SMALLINT UNSIGNED,
                                          totalSecondsRemaining SMALLINT UNSIGNED
                                          )''')

                    await cursor.execute(f'''CREATE TABLE {server}.apiFights
                                          (battle_id INT UNSIGNED,
                                          round_id TINYINT,
                                          damage INT UNSIGNED,
                                          weapon TINYINT,
                                          berserk BOOLEAN,
                                          defenderSide BOOLEAN,
                                          citizenship TINYINT UNSIGNED,
                                          citizenId INT,
                                          time DATETIME(3),  -- 3 for milliseconds
                                          militaryUnit SMALLINT UNSIGNED,
                                          PRIMARY KEY (citizenId, time)
                                          -- FOREIGN KEY (battle_id) REFERENCES apiBattles(battle_id)
                                          -- this does not allow me to update apiBattles because of foreign key
                                          )''')

                    await cursor.execute(f"CREATE INDEX battle_id_index ON {server}.apiFights (battle_id)")
        await interaction.response.send_message("done")

    @command()
    @guilds(utils.hidden_guild)
    async def logout(self, interaction: Interaction) -> None:
        await self.bot.session.close()
        for server, session in self.bot.locked_sessions.items():
            await session.close()
        await interaction.response.send_message("done")
        await self.bot.close()

    @command()
    @guilds(utils.hidden_guild)
    async def execute(self, interaction: Interaction, code: str) -> None:
        # https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/admin.py#L215
        """Executes a given code"""
        if interaction.user.id != config_ids.get("OWNER_ID"):
            return
        await interaction.response.defer()

        env = {
            'bot': self.bot,
            'interaction': interaction,
            'channel': interaction.channel,
            'author': interaction.user,
            'guild': interaction.guild
        }

        env.update(globals())

        code = code.replace(";", "\n")

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
    async def load(self, interaction: Interaction, ext: str) -> None:
        """Load Extensions"""
        await self.bot.reload_extension("exts." + ext)
        await utils.custom_followup(interaction, f"{ext} loaded", ephemeral=True)

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
