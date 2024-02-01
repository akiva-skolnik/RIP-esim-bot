"""Help.py"""
from collections import defaultdict

from discord import Embed, Interaction
from discord.app_commands import (command)
from discord.ext.commands import Cog

from Utils import utils
from Utils.paginator import FieldPageSource, Pages


class Help(Cog, command_attrs={"cooldown_after_parsing": True, "ignore_extra": False}):
    def __init__(self, bot) -> None:
        self.bot = bot

    @command()
    async def help(self, interaction: Interaction, compact: bool = False) -> None:
        """Displays the list of commands, grouped by category."""
        cogs_to_commands = defaultdict(list)

        for command_object in self.bot.tree.walk_commands():
            parent = command_object.module.split(".")[-1]
            # for black-market it shows the cog name too.
            if parent in ("Admin", "Help", "Listener", "Setup") or command_object.qualified_name == "black-market":
                continue
            cogs_to_commands[parent].append(command_object)

        if compact:
            embed = Embed(colour=0x3D85C6, title="Help", description="**List of commands by category:**")
            for cog_name, commands in cogs_to_commands.items():
                embed.add_field(name=cog_name, value=", ".join(
                    f"`/{command_object.qualified_name}`" for command_object in
                    sorted(commands, key=lambda x: x.qualified_name)))

            await utils.custom_followup(interaction, embed=await utils.custom_author(embed))
        else:
            entries = []
            for cog_name, commands in cogs_to_commands.items():
                page = []
                for command_object in sorted(commands, key=lambda x: x.qualified_name):
                    name = command_object.name
                    parameters = " ".join(x.name + ":" for x in command_object.parameters)
                    value = f"`/{command_object.qualified_name} {parameters}`\n{command_object.description}"
                    page.append((name, value))
                entries.append(page)

            embed = Embed(colour=0x3D85C6, description="(you can copy-paste the code blocks, "
                                                       "but note that some parameters are optional)")
            # get max of entries[0] first field length
            source = FieldPageSource(entries, titles=list(cogs_to_commands),
                                     clear_description=False, inline=False, per_page=1, embed=embed)
            pages = Pages(source, interaction=interaction, embed=embed)
            await pages.start()


async def setup(bot) -> None:
    """Setup"""
    await bot.add_cog(Help(bot))
