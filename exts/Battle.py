"""Battle.py"""
import math
import statistics
import traceback
from asyncio import sleep
from collections import defaultdict
from copy import deepcopy
from csv import reader, writer
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from json import loads
from random import randint
from typing import Optional

from discord import Embed, File, Interaction, Role, TextChannel
from discord.app_commands import Transform, check, checks, command, describe, guild_only
from discord.ext.commands import Cog, Context, hybrid_command
from discord.utils import MISSING
from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
from pytz import timezone

from Help import utils
from Help.transformers import AuctionLink, BattleLink, Country, Server, TournamentLink
from Help.utils import (CoolDownModified, bar, camel_case_merge,
                        dmg_calculator, dmg_trend, draw_pil_table,
                        human_format, not_support)


class Battle(Cog):
    """Battle Commands"""

    def __init__(self, bot) -> None:
        self.bot = bot

    @command()
    async def buffs_links(self, interaction: Interaction) -> None:
        """Displays links of the buff and time trackers"""
        embed = Embed(colour=0x3D85C6)
        description = "**Buff and time trackers:**\n"
        for server, data in self.bot.gids.items():
            description += f"[**{server}**](https://docs.google.com/spreadsheets/d/{data[0]}/edit#gid={data[2]})\n"
        embed.description = description
        return await interaction.response.send_message("You can also use `/buff <server> <country or MU id>`",
                                                       embed=await utils.convert_embed(interaction, embed))

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    async def buffs(self, interaction: Interaction, server: Transform[str, Server], nick: str = "",
                    country: Transform[str, Country] = "", military_unit_id: int = 0) -> None:
        """Displays buffed players per server and country or military unit."""

        if server not in self.bot.gids:
            return await interaction.response.send_message("You can not use this server in this command", ephemeral=True)

        await interaction.response.defer()
        if military_unit_id:
            members = await utils.get_content(
                f'https://{server}.e-sim.org/apiMilitaryUnitMembers.html?id={military_unit_id}')
            members = [row["login"] for row in members]
            mu_name = f"MU id {military_unit_id}"
        else:
            members = []
            mu_name = ""

        result = []
        find_buffs = await utils.find_one("buffs", server)
        now = datetime.now().astimezone(timezone('Europe/Berlin')).strftime(self.bot.date_format)
        total_buff = 0
        total_debuff = 0
        for current_nick, row in find_buffs.items():
            if current_nick == "Nick" or "Last update" in current_nick:
                continue
            link, citizenship, dmg, last, premium, buffed, _, till_change, _, _, _, _ = row[:12]
            if not buffed or (any((country, military_unit_id, nick)) and not any(
                    ((citizenship.lower() == country.lower()), current_nick in members,
                    nick.lower() == current_nick.lower()))):
                continue

            hyperlink = (":star:" if premium else ":lock:") + f" {utils.codes(citizenship) if not country else ''} [{current_nick}]({link})"
            if (datetime.strptime(now, self.bot.date_format) - datetime.strptime(
                    buffed, self.bot.date_format)).total_seconds() < 24 * 60 * 60:
                buff = ":green_circle: "
                total_buff += 1
            else:
                buff = ":red_circle: "
                total_debuff += 1
            row = [hyperlink, buff + last, till_change, dmg]
            if row not in result:
                result.append(row)

        if not result:
            await utils.custom_followup(
                interaction, f"No one is buffed/debuffed at {country or mu_name}, {server} (as far as I can tell)\n"
                             f"See https://docs.google.com/spreadsheets/d/{self.bot.gids[server][0]}/edit#gid="
                             f"{self.bot.gids[server][2]}\n")
            return
        dmg = [int(x[-1].replace(",", "")) for x in result]
        median = statistics.median(dmg)
        result = [[x[0], x[1], (":low_brightness: " if int(x[-1].replace(",", "")) < median else
                                ":high_brightness: ") + x[2]] for x in result]
        result = sorted(result, key=lambda x: datetime.strptime(x[-1].split(": ")[-1], "%H:%M:%S"))
        embed = Embed(colour=0x3D85C6,
                      description=f"**Buffed players {country or mu_name}, {server}**\n"
                                  f"{total_buff} :green_circle:, {total_debuff} :red_circle:",
                      url=f"https://docs.google.com/spreadsheets/d/{self.bot.gids[server][0]}/edit#gid={self.bot.gids[server][2]}")
        embed.set_footer(text="\U00002b50 / \U0001f512 = Premium / Non Premium\n"
                              "\U0001f7e2 / \U0001f534 = Buff / Debuff\n"
                              f"\U0001f505 / \U0001f506 = Below / Above median total dmg ({round(median):,})")
        headers = ["Nick, Citizenship" if not country else "Nick", "Last Seen (game time)", "Till Debuff (over)"]
        await utils.send_long_embed(interaction, embed, headers, result)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @describe(bonuses='options: PD, sewer or bunker, steroids, -tank (debuff), MU, location, DS\n'
                      'Q<wep quality> (default: Q5), X<limits> (default: X1), <bonus dmg>% (default: 0%), new (ignore set and rank)')
    @command()
    async def calc(self, interaction: Interaction, server: Transform[str, Server], nick: str, bonuses: str = "") -> None:
        """DMG calculator"""
        api = await utils.get_content(f"https://{server}.e-sim.org/apiCitizenByName.html?name={nick.lower()}")
        dmg = await dmg_calculator(api, bonuses)

        embed = Embed(colour=0x3D85C6,
                      description=f"[{api['login']}](https://{server}.e-sim.org/profile.html?id={api['id']}),"
                                  f" {utils.codes(api['citizenship'])} {api['citizenship']}")
        embed.add_field(name="Estimate Dmg", value=f"{dmg['avoid']:,}")
        embed.add_field(name="Without Avoid", value=f"{dmg['clutch']:,}")
        embed.add_field(name="Number of hits", value=f"{dmg['hits']}")
        embed.add_field(name="\u200B", value="\u200B", inline=False)
        embed.add_field(name="Stats", value="\n".join([f"**{k}:** {v}".title() for k, v in dmg['stats'].items() if v]))
        embed.add_field(name="Bonuses", value="\n".join([f"**{k}:** {v}".title() for k, v in dmg['bonuses'].items()]))
        await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed, is_columns=False))

    @command()
    @describe(tournament_link='Tournament link',
              nick='Your in-game nick (for showing your score)')
    @check(utils.is_premium_level_1)
    @guild_only()
    async def cup_plus(self, interaction: Interaction, tournament_link: Transform[str, TournamentLink],
                       nick: str = "") -> None:
        """Displays the top 10 players in a cup tournament (faster for premium)"""
        await interaction.response.send_message("Ok")
        link = tournament_link
        server = link.split("https://", 1)[1].split(".e-sim.org", 1)[0]
        await utils.default_nick(interaction, server, nick)
        find_cup = await utils.find_one("collection", interaction.command.name)
        if link not in find_cup or len(find_cup[link]) >= 10:
            if "countryTournament" not in link:
                tree = await utils.get_locked_content(link)
            else:
                tree = await utils.get_locked_content(link + "&hash=%23slideShedule", method="post")
            ids = {int(x) for x in (
                utils.get_ids_from_path(tree, '//*[@class="battle-link"]') if "countryTournament" not in link else
                utils.get_ids_from_path(tree, '//*[@class="getBattle right"]'))}
            if ids:
                find_cup[link] = [
                    {str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}}]
                await utils.replace_one("collection", interaction.command.name, find_cup)
                await self.cup_func(interaction, link, server, ids, True)
            else:
                await interaction.edit_original_response(content="No IDs found. Consider using the `cup` command instead. Example: `/cup 40730 40751 alpha`")
                return
        else:
            find_cup[link].append({str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}})
            await utils.replace_one("collection", interaction.command.name, find_cup)
            return


    @checks.dynamic_cooldown(CoolDownModified(30))
    @command()
    @describe(server='server', first_battle_id='first cup battle', last_battle_id='last cup battle',
              nick='Your in-game nick (for showing your score)')
    @guild_only()
    async def cup(self, interaction: Interaction, server: Transform[str, Server],
                  first_battle_id: int, last_battle_id: int, nick: str = "") -> None:
        """Displays the top 10 players in a cup tournament."""
        if last_battle_id - first_battle_id > 1000:
            return await interaction.response.send_message(
                                           f"You are asking me to check {last_battle_id - first_battle_id} battles.\n"
                                           "I have a reason to believe that you should recheck your request.",
                                           ephemeral=True)
        if last_battle_id - first_battle_id < 1:
            return await interaction.response.send_message(
                                           "You can find the first and last id on the `news` -> `military events` page.",
                                           ephemeral=True)
        await interaction.response.send_message("Ok")
        await utils.default_nick(interaction, server, nick)
        find_cup = await utils.find_one("collection", interaction.command.name)
        db_query = f"{server} {first_battle_id} {last_battle_id}"
        if db_query not in find_cup and any(server in k for k in find_cup):
            for query in find_cup:
                if server in query and query != db_query:
                    view = utils.Confirm()
                    await interaction.edit_original_response(
                        content=f"Would you like to change your request (`{db_query}`) into `{query}`? It will be much faster.\n"
                                f"(Someone else is running the command right now, and you can get their result)",
                        view=view)

                    await view.wait()
                    if view.value:
                        find_cup = await utils.find_one("collection", interaction.command.name)
                        if query in find_cup:
                            await interaction.edit_original_response(content="I'm on it, Sir. Thank you very much.", view=view)
                            find_cup[query].append(
                                {str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}})
                            await utils.replace_one("collection", interaction.command.name, find_cup)
                            return
                    else:
                        await interaction.edit_original_response(content="Ok.", view=view)
                    break
        if db_query not in find_cup or len(find_cup[db_query]) >= 10:
            find_cup[db_query] = [
                {str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}}]
            await utils.replace_one("collection", interaction.command.name, find_cup)

        else:
            find_cup[db_query].append(
                {str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}})
            return await utils.replace_one("collection", interaction.command.name, find_cup)
        ids = range(first_battle_id, last_battle_id + 1)
        await self.cup_func(interaction, db_query, server, ids, False)


    @checks.dynamic_cooldown(CoolDownModified(15))
    @command()
    @describe(battle_link='battle link, or server and battle id',
              nick='Please choose nick, country, or mu id',
              country='Please choose nick, country, or mu id',
              mu_id='Please choose nick, country, or mu id')
    async def dmg(self, interaction: Interaction, battle_link: Transform[dict, BattleLink], nick: str = "",
                  country: Transform[str, Country] = "", mu_id: int = 0) -> None:
        """
        Displays wep used and dmg done (Per player, MU, country, or overall) in a given battle(s).

        **Notes:**
        - If your nick is the same string as some country (or close enough), add a dash before your nick. Example: `-Israel`
        - For range of battles, use `<first>_<last>` instead of `<link>` (`/dmg alpha 1165_1167 Israel`)
        """

        server, battle_id, round_id = battle_link["server"], battle_link["id"], battle_link["round"]
        last_battle = battle_link["last"] if battle_link["last"] else battle_id
        range_of_battles = battle_link["last"]
        if last_battle - battle_id > 1000 and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(
                interaction, "It's too much, sorry. You can buy premium and remove this limit.", ephemeral=True)
            return

        await interaction.response.defer()
        server = utils.server_validation(server or "")
        base_url = f"https://{server}.e-sim.org/"
        attacker, defender = 0, 0
        api = await utils.get_content(f'{base_url}apiBattles.html?battleId={battle_id}')
        key = None
        if country:
            nick = country
            key_id = self.bot.countries_by_name[country.lower()]
            key = 'citizenship'
            header = ["Country", "Q0 wep", "Q1", "Q5", "DMG"]
        elif mu_id:
            nick = mu_id
            mu_api = await utils.get_content(f'{base_url}apiMilitaryUnitById.html?id={mu_id}')
            mu_name = mu_api['name']
            key_id = int(mu_id)
            key = 'militaryUnit'
            header = ["Military Unit", "Q0 wep", "Q1", "Q5", "DMG"]
        elif nick:
            citizen = await utils.get_content(f'{base_url}apiCitizenByName.html?name={nick.lower()}')
            key_id = int(citizen['id'])
            nick = citizen['login']
            key = 'citizenId'
            if not round_id and not range_of_battles:
                header = ["Nick", "Q0 wep", "Q1", "Q5", "DMG", "Top 1", "Top 3", "Top 10", "Total Participation"]
            else:
                header = ["Nick", "Q0 wep", "Q1", "Q5", "DMG"]
        else:
            key_id = ""

        if not key:
            key = "citizenId"
            if api["type"] == "MILITARY_UNIT_CUP_EVENT_BATTLE" and not range_of_battles:
                header = ["Military unit", "Q0 wep", "Q1", "Q5", "DMG"]
                attacker = (await utils.get_content(f'{base_url}apiMilitaryUnitById.html?id={api["attackerId"]}'))["name"]
                defender = (await utils.get_content(f'{base_url}apiMilitaryUnitById.html?id={api["defenderId"]}'))["name"]
            else:
                attacker = api["attackerId"]
                defender = api["defenderId"]
                header = ["Side", "Q0 wep", "Q1", "Q5", "DMG"]

        if attacker != defender and api["type"] != "MILITARY_UNIT_CUP_EVENT_BATTLE":
            attacker = self.bot.countries.get(attacker, "attacker")
            defender = self.bot.countries.get(defender, "defender")
        else:
            attacker, defender = "Attacker", "Defender"

        hit_time = defaultdict(lambda: {"dmg": [], "time": []})
        tops = False
        my_dict = defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0})
        if range_of_battles:
            msg = await utils.custom_followup(interaction,
                                              "Progress status: 1%.\n(I will update you after every 10%)" if
                                              last_battle - battle_id > 10 else "I'm on it, Sir. Be patient.",
                                              file=File("files/typing.gif"))
            empty_sides = {"Total": {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0}}
        else:
            empty_sides = {defender: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0},
                           attacker: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0},
                           "Total": {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0}}
        my_dict.update(empty_sides)

        if not round_id:
            for index, battle_id in enumerate(range(battle_id, last_battle + 1)):
                if range_of_battles:
                    msg = await utils.update_percent(index, last_battle - battle_id, msg)

                if api['defenderScore'] == 8 or api['attackerScore'] == 8:
                    last = api['currentRound']
                else:
                    last = api['currentRound'] + 1
                for round_i in range(1, last):
                    defender_details = defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0})
                    attacker_details = defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0})
                    for hit in reversed(
                            await utils.get_content(
                                f'{base_url}apiFights.html?battleId={battle_id}&roundId={round_i}')):
                        wep = 5 if hit['berserk'] else 1
                        side_string = defender if hit['defenderSide'] else attacker
                        if not range_of_battles:
                            my_dict[side_string]['weps'][hit['weapon']] += wep
                            my_dict[side_string]['dmg'] += hit['damage']
                        my_dict['Total']['weps'][hit['weapon']] += wep
                        my_dict['Total']['dmg'] += hit['damage']
                        if key in hit:
                            my_dict[hit[key]]['weps'][hit['weapon']] += wep
                            my_dict[hit[key]]['dmg'] += hit['damage']

                        hit_time[side_string]["time"].append(utils.get_time(hit["time"]))
                        if hit_time[side_string]["dmg"]:
                            hit_time[side_string]["dmg"].append(hit_time[side_string]["dmg"][-1] + hit['damage'])
                        else:
                            hit_time[side_string]["dmg"].append(hit['damage'])

                        if key == 'citizenId':
                            side = defender_details if hit['defenderSide'] else attacker_details
                            side[hit['citizenId']]['weps'][hit['weapon']] += wep
                            side[hit['citizenId']]['dmg'] += hit['damage']

                    for side in (attacker_details, defender_details):
                        side = sorted(side.items(), key=lambda x: x[1]['dmg'], reverse=True)
                        for (name, value) in side:
                            if "tops" not in my_dict[name]:
                                my_dict[name]["tops"] = [0, 0, 0, 0]
                            my_dict[name]["tops"][3] += 1
                            tops = True
                            if (name, value) in side[:10]:
                                my_dict[name]["tops"][2] += 1
                                if (name, value) in side[:3]:
                                    my_dict[name]["tops"][1] += 1
                                    if (name, value) in side[:1]:
                                        my_dict[name]["tops"][0] += 1

                    await utils.custom_delay(interaction)

        else:
            for index, battle_id in enumerate(range(battle_id, last_battle + 1)):
                if range_of_battles:
                    msg = await utils.update_percent(index, last_battle - battle_id, msg)
                hit = None
                api_fights = await utils.get_content(
                    f'{base_url}apiFights.html?battleId={battle_id}&roundId={round_id}')
                for hit in reversed(api_fights):
                    wep = 5 if hit['berserk'] else 1
                    side = defender if hit['defenderSide'] else attacker
                    if not range_of_battles:
                        my_dict[side]['weps'][hit['weapon']] += wep
                        my_dict[side]['dmg'] += hit['damage']
                    my_dict['Total']['weps'][hit['weapon']] += wep
                    my_dict['Total']['dmg'] += hit['damage']
                    if key not in hit:
                        continue
                    my_dict[hit[key]]['dmg'] += hit['damage']
                    my_dict[hit[key]]['weps'][hit['weapon']] += wep

                    if (not range_of_battles) and (hit[key] == key_id or not key_id):
                        name = nick if key_id else side
                        hit_time[name]["time"].append(utils.get_time(hit["time"]))
                        if hit_time[name]["dmg"]:
                            hit_time[name]["dmg"].append(hit_time[name]["dmg"][-1] + hit['damage'])
                        else:
                            hit_time[name]["dmg"].append(hit['damage'])
                if not hit and not range_of_battles:
                    await utils.custom_followup(
                        interaction, f'Nothing found at <{base_url}apiFights.html?battleId={battle_id}&roundId={round_id}>')
                    return
                if index > 0:
                    await utils.custom_delay(interaction)

        output_buffer = await dmg_trend(hit_time, server, battle_id if not round_id else f"{battle_id}-{round_id}")
        hit_time.clear()
        new_dict = defaultdict(int)
        output = StringIO()
        csv_writer = writer(output)
        row = [key, "dmg"] + [f"Q{x} wep" for x in range(6)]
        if tops:
            row.extend(["Top 1", "Top 3", "Top 10", "Total Participation"])
        csv_writer.writerow(row)
        table = []
        embed_name = "Citizen Id"
        for name, value in sorted(my_dict.items(), key=lambda x: x[1]["dmg"], reverse=True):
            row = [name if key != "citizenship" else self.bot.countries.get(name, name), value["dmg"]] + value["weps"]
            if "tops" in value:
                row.extend(value["tops"])
            if value["dmg"]:
                csv_writer.writerow([x or "" for x in row])
            if len(new_dict) < 10 and isinstance(name, int):
                if key == "citizenship":
                    embed_name = "Country"
                    filed = self.bot.countries[name]
                    filed = f"{utils.codes(filed)} " + filed
                elif key == "militaryUnit":
                    embed_name = "Military Unit Id"
                    filed = f"[{name}]({base_url}militaryUnit.html?id={name})"
                else:
                    filed = f"[{name}]({base_url}profile.html?id={name})"
                new_dict[filed] += value["dmg"]
            if not nick:
                if isinstance(name, str):
                    if not range_of_battles:
                        table.append(
                            [name, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}", f"{value['dmg']:,}"])
                    else:
                        table.append(
                            [name, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}", f"{value['dmg']:,}"])
            else:
                if name == key_id:
                    if key == 'militaryUnit':
                        table.append(
                            [mu_name, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}", f"{value['dmg']:,}"])
                    elif round_id:
                        table.append([nick, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}",
                                      f"{value['dmg']:,}", f'x{value.get("tops", [0])[0]} times'] + value.get("tops", [0] * 4)[1:])
                    elif key == 'citizenId':
                        table.append(
                            [nick, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}", f"{value['dmg']:,}"])
                    else:
                        table.append(
                            [nick, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}", f"{value['dmg']:,}"])
        output.seek(0)
        if not table:
            await utils.custom_followup(
                interaction, f"I did not find {key.replace('Id', '')} `{nick}` at <{base_url}battle.html?id={battle_id}>\n"
                "**Remember:** for __nick__ use `-nick`, for __MU__ use the MU id, and for __country__ - write the country name.")
            return
        embed = Embed(colour=0x3D85C6)
        embed.set_thumbnail(url=f"attachment://{interaction.id}.png")

        embed.add_field(name="**#**", value="\n".join([str(i) for i in list(range(1, len(new_dict) + 1))]))
        embed.add_field(name=f"**{embed_name}**", value="\n".join([str(k) for k, v in new_dict.items()]))
        embed.add_field(name="**DMG**", value="\n".join([f"{v:,}" for k, v in new_dict.items()]))
        keys = {'Military Unit Id': {'api_url': 'apiMilitaryUnitById', 'api_key': 'name', 'cs_key': 'countryId',
                                     'final_link': 'militaryUnit'},
                'Citizen Id': {'api_url': 'apiCitizenById', 'api_key': 'login', 'cs_key': 'citizenshipId',
                               'final_link': 'profile'}}

        files = [File(fp=BytesIO(output.getvalue().encode()), filename="dmg.csv"),
                 File(fp=output_buffer, filename=f"{interaction.id}.png")]
        view = utils.WaitForNext() if "Id" in embed_name else MISSING
        if len(table) == 1 and not range_of_battles:
            if key != 'citizenship':
                citizenship = self.bot.countries[(citizen if embed_name == "Citizen Id" else mu_api)[keys[embed_name]['cs_key']]]
                embed.url = f"{base_url}{key.replace('citizenId', 'profile')}.html?id={key_id}"
            else:
                citizenship = table[0][0]
                embed.url = f"{base_url}countryPoliticalStatistics.html?countryId={key_id}"
            embed.title = f"**{utils.codes(citizenship)} {table[0][0]}** - {table[0][-1]} DMG"
            for num, (name, value) in enumerate(zip(header[1:], table[0][1:])):
                embed.insert_field_at(num, name=name, value=value)
            embed.insert_field_at(-3, name="\u2800", value="\u2800", inline=False)
            msg = await utils.custom_followup(interaction, files=files,
                                              embed=await utils.convert_embed(interaction, deepcopy(embed)), view=view)
        else:
            embed.description = f'**Battle type: {api["type"]}**'
            output_buffer1 = await self.bot.loop.run_in_executor(None, draw_pil_table, table, header)
            msg = await utils.custom_followup(interaction,
                                              embed=await utils.convert_embed(interaction, deepcopy(embed)),
                                              files=[File(fp=output_buffer1,
                                                          filename=f'{battle_id} {server}.jpg')] + files, view=view)
        del my_dict, table
        if "Id" not in embed_name:
            return
        await view.wait()
        if view.value:
            for index, field in enumerate(embed.fields):
                if "Id" not in field.name:
                    continue
                values = field.value.splitlines()
                for num, value in enumerate(values):
                    value = value.split("[")[1].split("]")[0]
                    api = await utils.get_content(f'{base_url}{keys[embed_name]["api_url"]}.html?id={value}')
                    flag = utils.codes(self.bot.countries[api[keys[embed_name]['cs_key']]])
                    values[
                        num] = f"{flag} [{api[keys[embed_name]['api_key'][:20]]}]({base_url}{keys[embed_name]['final_link']}.html?id={value})"
                    await utils.custom_delay(interaction)
                embed.set_field_at(index, name=field.name[:-5] + "**", value="\n".join(values))
        await msg.edit(embed=await utils.convert_embed(interaction, embed), view=view)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(battle_link="Battle link, or server and battle id", bonus="Bonus drops (default: 0)",
              nick="Your nick (for showing your stats)")
    async def drops(self, interaction: Interaction, battle_link: Transform[dict, BattleLink], bonus: int = 0,
                    nick: str = "") -> None:
        """Displays the expected amount of drops in a given battle."""

        server, battle_id = battle_link["server"], battle_link["id"]
        link = f"https://{server}.e-sim.org/battle.html?id={battle_id}"
        await interaction.response.defer()
        nick = await utils.default_nick(interaction, server, nick)

        tops_per_player = defaultdict(lambda: {'hits': 0, 'tops': [0, 0, 0]})  # Top 1, 3, 10 (respectively).
        hits_per_player = defaultdict(int)

        api = await utils.get_content(link.replace("battle", "apiBattles").replace("id", "battleId"))
        if api['defenderScore'] == 8 or api['attackerScore'] == 8:
            last = api['currentRound']
        else:
            last = api['currentRound'] + 1

        top1, top3, top10 = range(3)

        for round_id in range(1, last):
            defender = defaultdict(int)
            attacker = defaultdict(int)
            for hit in await utils.get_content(
                    link.replace("battle", "apiFights").replace("id", "battleId") + f'&roundId={round_id}'):
                side = defender if hit['defenderSide'] else attacker
                side[hit['citizenId']] += hit['damage']
                tops_per_player[hit['citizenId']]['hits'] += 5 if hit['berserk'] else 1
                hits_per_player[hit["citizenId"]] += 5 if hit['berserk'] else 1

            for side in (attacker, defender):
                side = sorted(side.items(), key=lambda x: x[1], reverse=True)
                for (player, dmg) in side:
                    if (player, dmg) in side[:10]:
                        tops_per_player[player]["tops"][top10] += 1
                        if (player, dmg) in side[:3]:
                            tops_per_player[player]["tops"][top3] += 1
                            if (player, dmg) in side[:1]:
                                tops_per_player[player]["tops"][top1] += 1
            await utils.custom_delay(interaction)

        del attacker, defender, side

        hits = sum(hits_per_player.values())
        hits_with_bonus = hits + hits * bonus / 100
        next_upgrade = (hits // 3000 + 1) * 3000 - hits
        embed = Embed(colour=0x3D85C6, title=f'**Total hits : ** {hits:,}', url=link)
        hits_for_q = {"Q6": 150000, "Q5": 30000, "Q4": 10000, "Q3": 3000, "Q2": 1000, "Q1": 300}
        # item: [drops, hits for next]
        drops_per_q = {q: [round(hits_with_bonus / v), int(
            ((round(hits_with_bonus / v) + 1) * v - v / 2 - hits_with_bonus) / (bonus + 100) * 100)] for q, v in
                       hits_for_q.items()}
        drops_per_q["Elixir"] = [int(hits_with_bonus / 150), (hits_with_bonus // 150 + 1) * 150 - hits_with_bonus]
        drops_per_q["upg. + shuffle"] = [hits // 1500, next_upgrade]
        embed.add_field(name="**Q : Drops**", value="\n".join([f"**{k} :** {v[0]:,}" for k, v in drops_per_q.items()]))
        embed.add_field(name="**Hits For Next**", value="\n".join([f"{int(v[1]):,}" for v in drops_per_q.values()]))
        if nick:
            try:
                given_user_id = (await utils.get_content(f"https://{server}.e-sim.org/apiCitizenByName.html?name={nick.lower()}"))['id']
                if given_user_id not in hits_per_player:
                    nick = ""
            except Exception:
                nick = ""

        final = defaultdict(lambda: defaultdict(lambda: []))
        qualities = set()
        all_total_tops = {index: sum(x['tops'][index] for x in tops_per_player.values()) for index in range(3)}
        _, ax = plt.subplots()

        indexes = {"Q3": top10, "Q4": top3, "Q5": top1, "Q6": top1}

        for user_id, value in tops_per_player.items():
            player = given_user_id if nick else user_id
            if player == user_id:
                for quality, total_drops in {k: v[0] for k, v in drops_per_q.items()}.items():
                    if quality in indexes:
                        total_tops = all_total_tops[indexes[quality]]
                        my_tops = value['tops'][indexes[quality]] if 'tops' in value else 0
                    elif "upg" in quality:
                        total_tops = hits
                        my_tops = value['hits']
                    else:
                        total_tops = hits_with_bonus
                        my_tops = value['hits'] + value['hits'] * bonus / 100

                    x, y = [], []
                    player_chances = 0
                    likely_b, first_likely_k, last_likely_k = 0, 0, 0
                    n = total_drops
                    p = (my_tops / total_tops) if total_tops else 0
                    mean = n * p  # mu
                    std = math.sqrt(mean * (1 - p))  # sigma
                    added = False
                    for k in range(n + 1):
                        if n * p >= 5 and n * (1 - p) >= 5:  # or: n*p*(1-p) > 10
                            prob = Battle.normal_pdf(k, mean, std)
                        else:
                            prob = math.comb(n, k) * math.pow(p, k) * math.pow(1 - p, n - k)
                        if k == 0 and prob > 0.4:
                            likely_b = 1 - prob
                            last_likely_k = 1
                            break

                        player_chances += prob
                        x.append(prob * 100)
                        y.append(k)
                        if k > 0 and (abs(mean - k) <= std or (k == 1 and mean < 1)):
                            likely_b += prob
                            if not first_likely_k:
                                first_likely_k = k
                            added = True
                        if added:
                            last_likely_k = max(last_likely_k, k)
                            added = False

                        if player_chances > 0.99:
                            break

                    if total_drops and my_tops:
                        if last_likely_k == 1:
                            drops_range = "1" if total_drops == 1 else "1+"
                        elif first_likely_k < last_likely_k:
                            drops_range = f"{first_likely_k}-{last_likely_k}"
                        else:
                            drops_range = str(first_likely_k)
                        final[player][quality] = [drops_range, f"{likely_b:.0%}"]
                        qualities.add(quality)
                    else:
                        final[player][quality] = [0, "100%"]

                    if nick and len(x) > 1:
                        await self.bot.loop.run_in_executor(None, lambda: ax.plot(y, x, marker='.', label=quality))

        if not nick:
            qualities = sorted(qualities, reverse=True)
            header = [[f"{x} Prediction Range", f"{x} chance"] for x in qualities]
            output = StringIO()
            csv_writer = writer(output)
            csv_writer.writerow(["Citizen Id", "Hits", "Top 1", "Top 3", "Top 10"] + [a for a in header for a in a])

        for player, chances in final.items():
            if not nick:
                row = [player, tops_per_player[player]["hits"]] + tops_per_player[player]["tops"]
                for quality in qualities:
                    amount, chance = chances[quality]
                    row.extend([f" {amount}" if amount else "", chance])
                csv_writer.writerow(row)
            else:
                def plot_drops() -> BytesIO:
                    ax.legend()
                    ax.set_title(f"Drop chances for {nick} ({server}, {battle_id})")
                    ax.set_ylabel('%')
                    ax.set_xlabel('Drops Amount')
                    ax.xaxis.get_major_locator().set_params(integer=True)
                    return utils.plt_to_bytes()

                output_buffer = await self.bot.loop.run_in_executor(None, plot_drops)
                file = File(fp=output_buffer, filename=f"{interaction.id}.png")
                embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
                embed.add_field(name="**Expected Drops: Chances**", value="\n".join(
                    [f"**{chances[Q][0]} : ** {chances[Q][1]}" for Q in drops_per_q.keys()]))
                embed.add_field(name="Top", value="\n".join(
                    [f"**{x}**" for x in ["BH", "Top 3", "Top 10", "Hits"]]))
                embed.add_field(name="Total Tops",
                                value="\n".join([str(x) for x in all_total_tops.values()] + [f"{hits:,}"]))
                embed.add_field(name="Your Tops",
                                value="\n".join([f"{x:,}" for x in tops_per_player[given_user_id]['tops']]
                                                + [f'{tops_per_player[given_user_id]["hits"]:,}']))
                await utils.custom_followup(interaction, file=file, embed=await utils.convert_embed(interaction, embed))

        if not nick:
            output.seek(0)
            await utils.custom_followup(interaction, "Chances of receiving **at least** x amount of drops", files=[
                File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
                File(fp=BytesIO(output.getvalue().encode()),
                     filename=f"Chances_{link.split('battle.html?id=')[1]}.csv")],
                                        embed=await utils.convert_embed(interaction, embed))

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @guild_only()
    @check(not_support)
    async def motivate(self, interaction: Interaction, server: Transform[str, Server]) -> None:
        """Checks every ~10 minutes if there is a new citizen to motivate in the given server."""

        base_url = f'https://{server}.e-sim.org/'
        await interaction.response.send_message("Ok")
        try:
            tree = await utils.get_content(f'{base_url}newCitizenStatistics.html')
            names = tree.xpath("//tr//td[1]/a/text()")
            citizen_ids = tree.xpath("//tr//td[1]/a/@href")
            countries = tree.xpath("//tr//td[2]/span/text()")
            registration_time = tree.xpath("//tr[position()>1]//td[3]/text()[1]")
            registration_time1 = tree.xpath("//tr//td[3]/text()[2]")
            xp = [int(x) for x in tree.xpath("//tr[position()>1]//td[4]/text()")]
            wep = tree.xpath("//tr[position()>1]//td[5]/i/@class")
            food = tree.xpath("//tr[position()>1]//td[6]/i/@class")
            gift = tree.xpath("//tr[position()>1]//td[5]/i/@class")
            row = []
            for name, citizen_id, country, registration_time, registration_time1, xp, wep, food, gift in zip(
                    names, citizen_ids, countries, registration_time, registration_time1, xp, wep, food, gift):
                row.append({"name": name.strip(), "citizen_id": int(citizen_id.split("?id=")[1]), "country": country,
                            "registration_time": registration_time.strip(), "registered": registration_time1[1:-1],
                            "xp": xp, "wep": "479" in wep, "food": "479" in food, "gift": "479" in gift})
            result = [[], [], []]
            for citizen_data in row:
                types = citizen_data["food"], citizen_data["gift"], citizen_data["wep"]
                if not all(types):
                    result[0].append(f"{utils.codes(citizen_data['country'])} ["
                                     f"{citizen_data['name']}]({base_url}profile.html?id={citizen_data['citizen_id']})")
                    result[1].append(" ".join("\U0001f534" if not x else "\U0001f7e2" for x in types))
                    result[2].append(citizen_data['registered'])

            if any(result):
                embed = Embed(colour=0x3D85C6, title="Source", url=f'{base_url}newCitizenStatistics.html')
                embed.add_field(name="Nick", value="\n".join(result[0]))
                embed.add_field(name="Motivate", value="\n".join(result[1]))
                embed.add_field(name="Registered", value="\n".join(result[2]))
                await interaction.edit_original_response(embed=await utils.convert_embed(interaction, embed))
        except Exception:
            print(datetime.now().astimezone(timezone('Europe/Berlin')))
            traceback.print_exc()
        db_dict = await utils.find_one("collection", "motivate")
        if server not in db_dict:
            db_dict[server] = [str(interaction.channel.id)]
            await utils.replace_one("collection", "motivate", db_dict)
            self.bot.loop.create_task(motivate_func(self.bot, server, db_dict))
        elif str(interaction.channel.id) not in db_dict[server]:
            db_dict[server].append(str(interaction.channel.id))
            await utils.replace_one("collection", "motivate", db_dict)
        await interaction.edit_original_response(content=f"I will check every 5 minutes if there is a new player at `{server}`")

    @command()
    @describe(servers="Default to all servers")
    async def got(self, interaction: Interaction, servers: str = "") -> None:
        """Stops motivate program."""
        if not servers or servers.lower() == "all":
            servers = " ".join(self.bot.all_servers)
        db_dict = await utils.find_one("collection", "motivate")
        changed_servers = []
        for server in servers.replace(",", " ").split():
            if not server.strip():
                continue
            try:
                server = utils.server_validation(server)
            except Exception:
                continue

            if server in db_dict:
                if str(interaction.channel.id) in db_dict[server]:
                    db_dict[server].remove(str(interaction.channel.id))
                    changed_servers.append(server)

                if not db_dict[server]:
                    del db_dict[server]

        if changed_servers:
            await utils.custom_followup(
                interaction, "Program `motivate` have been stopped for the following servers in this channel:\n" +
                             ", ".join(changed_servers))
            await utils.replace_one("collection", "motivate", db_dict)

        else:
            await utils.custom_followup(interaction, "I didn't had to change anything.")

    @command(name="motivate-scanner")
    @check(utils.is_premium_level_1)
    async def motivate_scanner(self, interaction: Interaction, server: Transform[str, Server]) -> None:
        """Scanning motivates."""
        await utils.custom_followup(interaction, "Scanning...")
        base_url = f'https://{server}.e-sim.org/'
        tree = await utils.get_content(f'{base_url}newCitizens.html?countryId=0')
        citizen_id = int(utils.get_ids_from_path(tree, "//tr[2]//td[1]/a")[0])
        today = 0
        embed = Embed(colour=0x3D85C6, title="Motivates", url=f'{base_url}newCitizenStatistics.html')
        embed.set_footer(text="\U0001f7e2, \U0001f534 = Already Sent / Available")
        results = []
        view = None
        for index in range(200):
            tree = await utils.get_locked_content(f'{base_url}profile.html?id={citizen_id}', index == 0)
            birthday = int(tree.xpath(
                '//*[@class="profile-row" and span = "Birthday"]/span/text()')[0].split()[-1])
            if not today:  # first citizen
                today = birthday
            if today - birthday <= 3:
                if not tree.xpath('//*[@id="motivateCitizenButton"]'):
                    continue
                nick = tree.xpath('//*[@class="big-login"]/text()')[0]
                citizenship = tree.xpath('//*[@class="countryNameTranslated"]/text()')[-1]
                await utils.custom_delay(interaction)
                tree = await utils.get_locked_content(f"{base_url}motivateCitizen.html?id={citizen_id}")

                types = tree.xpath('//td[2]//input/@value')
                if not types:
                    continue
                icons = ["\U0001f7e2"] * 3
                for motivate_type in types:
                    icons[int(motivate_type) - 1] = "\U0001f534"
                results.append([f'[{nick}]({base_url}motivateCitizen.html?id={citizen_id})',
                                f"{utils.codes(citizenship)} {citizenship}", " ".join(icons)])

            citizen_id -= 1
            if (index + 1) % 10 == 0 or today - birthday > 3:
                if results:
                    embed.clear_fields()
                    embed.add_field(name="Nick", value="\n".join([x[0] for x in results]))
                    embed.add_field(name="Citizenship", value="\n".join([x[1] for x in results]))
                    embed.add_field(name=":gun: :bread: :gift:", value="\n".join([x[2] for x in results]))
                    results.clear()
                    view = utils.StopNext(interaction)
                    await interaction.edit_original_response(content=f"I have scanned {index + 1} players so far.",
                                                             embed=await utils.convert_embed(interaction, embed),
                                                             view=view)
                    if today - birthday > 3:
                        break
                    await view.wait()
                    if not view.next_page or view.canceled:
                        break
                else:
                    await interaction.edit_original_response(content=f"Scanned {index + 1} players so far.")

        if view:
            view.clear_items()
        await interaction.edit_original_response(content=f"I have scanned total {index + 1} players.", view=view)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(country="Show country's battles (optional)")
    async def nexts(self, interaction: Interaction, server: Transform[str, Server],
                    country: Transform[str, Country] = "") -> None:
        """Displays the upcoming battles."""

        await interaction.response.defer()
        base_url = f'https://{server}.e-sim.org/'
        detailed_list = []
        ids = []
        for battle_filter in ("NORMAL", "RESISTANCE"):
            link = f'{base_url}battles.html?filter={battle_filter}&countryId={self.bot.countries_by_name.get(country.lower(), 0)}'
            for page in range(1, await utils.last_page(link)):
                tree = await utils.get_content(link + f'&page={page}')
                for battle_data in (await utils.battles_data(tree))["battles"]:
                    if battle_data["battle_id"] not in ids and battle_data["attacker"]["name"] in self.bot.countries.values():
                        detailed_list.append(battle_data)
                        ids.append(battle_data["battle_id"])

        if not detailed_list:
            await utils.custom_followup(interaction, "There are currently no active RWs or attacks.")
            return
        detailed_list = sorted(detailed_list, key=lambda k: k['time_reminding'])
        last = detailed_list[-1]["time_reminding"]
        headers = ["**Time remaining**", "**Defender | Attacker (Score)**", "**Bar**"]
        detailed_list = [
            [x["time_reminding"],
             f"[{utils.shorten_country(x['defender']['name'])} vs " + utils.shorten_country(x['attacker']['name']) +
             f"]({base_url}battle.html?id={x['battle_id']}) ({x['defender']['score']}:{x['attacker']['score']})",
             (await bar(x['defender']['bar'], x['attacker']['bar'], size=6)).splitlines()[0]] for x in detailed_list]
        embed = Embed(colour=0x3D85C6, title=server, url=f'{base_url}battles.html')
        await utils.send_long_embed(interaction, embed, headers, detailed_list)
        time_of_last = int(last.split(":")[0]) * 3600 + int(last.split(":")[1]) * 60 + int(last.split(":")[2])
        detailed_list.clear()

        update_seconds = 60
        while time_of_last > 0:
            await sleep(min(time_of_last, update_seconds))
            values = embed.fields[0].value.splitlines()
            for num, value in enumerate(values):
                if "round is over" in value:
                    continue
                value = value.split()[0]
                actual_time = int(value.split(":")[0]) * 3600 + int(value.split(":")[1]) * 60 + int(
                    value.split(":")[2]) - update_seconds
                values[num] = str(timedelta(seconds=actual_time)) if actual_time > 0 else "round is over"
            embed.set_field_at(0, name=embed.fields[0].name, value="\n".join(values))
            embed.timestamp = datetime.utcnow()
            try:
                await interaction.edit_original_response(embed=await utils.convert_embed(interaction, deepcopy(embed)))
            except Exception:
                return
            time_of_last -= update_seconds

    @checks.dynamic_cooldown(CoolDownModified(10))
    @command()
    @describe(country='buffs per country (optional)',
              extra_premium_info='get more info and wait a bit longer (premium)')
    async def online(self, interaction: Interaction, server: Optional[Transform[str, Server]],
                     battle_link: Optional[Transform[dict, BattleLink]],
                     country: Transform[str, Country] = "", military_unit_id: int = 0,
                     extra_premium_info: bool = False) -> None:
        """
        Displays citizens online & buffs info in a bonus location of a battle or in a country.

        Use `online+` to get more info (you will have to wait a bit longer).
        online+ output: http://prntscr.com/v8diez
        """

        if extra_premium_info and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(
                interaction, "`extra_premium_info` is a premium parameter! If you wish to use it, along with many other premium commands, please visit https://www.buymeacoffee.com/RipEsim"
                             "\n\nOtherwise, try again, but this time with `extra_premium_info=False`", ephemeral=True)
            return

        check_battle = False
        link = ""
        if battle_link:
            link = f"https://{battle_link['server']}.e-sim.org/battle.html?id={battle_link['id']}"
            server = battle_link['server']
            check_battle = True
        elif not server:
            await utils.custom_followup(interaction, "You must provide server or battle link", ephemeral=True)
            return

        await interaction.response.defer()

        members = []
        country = self.bot.countries_by_name.get(country.lower(), 0)

        if military_unit_id:
            members = await utils.get_content(
                f'https://{server}.e-sim.org/apiMilitaryUnitMembers.html?id={military_unit_id}')
            members = [row["login"] for row in members]

        base_url = f"https://{server}.e-sim.org/"
        api_map = await utils.get_content(f"{base_url}apiMap.html")
        occupant_id = {i['regionId']: i['occupantId'] for i in api_map}

        if check_battle:
            api_battles = await utils.get_content(link.replace("battle", "apiBattles").replace("id", "battleId"))
            try:
                neighbours_id = [z['neighbours'] for z in await utils.get_content(link.split("?")[0].replace(
                    "battle", "apiRegions")) if z["id"] == api_battles['regionId']][0]
            except IndexError:
                await utils.custom_followup(interaction, "Only attack and RW...")
                return
            defender = [i for z in api_map for i in neighbours_id if z['occupantId'] == api_battles['defenderId']] + [
                api_battles['regionId']]
            attacker = [i for z in api_map for i in neighbours_id if z['occupantId'] == api_battles['attackerId']]
            neighbours = defender if api_battles['type'] == "RESISTANCE" else \
                defender + attacker if api_battles['type'] == "ATTACK" else None
        else:
            neighbours = []
        api_map.clear()
        table1 = []
        find_buff = await utils.find_one("buffs", server)
        now = datetime.now().astimezone(timezone('Europe/Berlin')).strftime(self.bot.date_format)
        header = []
        for row in await utils.get_content(f"{base_url}apiOnlinePlayers.html?countryId={country}"):
            row = loads(row)
            name = row['login']
            location_id = row['localization']
            if (members and name not in members) or (check_battle and location_id not in neighbours):
                continue
            citizenship = row['citizenship']
            level = row['level']
            location = self.bot.countries[occupant_id[location_id]]
            if extra_premium_info:
                tree = await utils.get_content(f"{base_url}profile.html?id={row['id']}")
                try:
                    dmg = tree.xpath('//*[@class="profile-row" and span = "Damage"]/span/text()')[0]
                except IndexError:
                    continue
                buffs_debuffs = [camel_case_merge(x.split("/specialItems/")[-1].split(".png")[0]).replace("Elixir", "")
                                 for x in tree.xpath(
                                     '//*[@class="profile-row" and (strong="Debuffs" or strong="Buffs")]//img/@src') if
                                 "//cdn.e-sim.org//img/specialItems/" in x]
                buffs = ', '.join([x.split("_")[0].replace("Vacations", "Vac").replace("Resistance", "Sewer").replace(
                    "Pain Dealer", "PD ").replace("Bonus Damage", "") + ("% Bonus" if "Bonus Damage" in x.split(
                     "_")[0] else "") for x in buffs_debuffs if "Positive" in x.split("_")[1:]]).title()
                debuffs = ', '.join([x.split("_")[0].lower().replace("Vacation", "Vac").replace(
                    "Resistance", "Sewer") for x in buffs_debuffs if "Negative" in x.split("_")[1:]]).title()
                if check_battle and api_battles['type'] != "ATTACK":
                    header = "Nick", "Citizenship", "lvl", "Total DMG", "Buffs", "Debuffs"
                    row = [name, self.bot.countries[citizenship], level, dmg, buffs, debuffs]
                else:
                    if not country:
                        header = "Nick", "Citizenship", "lvl", "Total DMG", "Location", "Buffs", "Debuffs"
                        row = [name, self.bot.countries[citizenship], level, dmg, location, buffs, debuffs]
                    else:
                        header = "Nick", "lvl", "Total DMG", "Location", "Buffs", "Debuffs"
                        row = [name, level, dmg, location, buffs, debuffs]
            else:
                if name in find_buff and find_buff[name][5]:
                    buff = ":red_circle: " if not (datetime.strptime(now, self.bot.date_format) - datetime.strptime(
                        find_buff[name][5], self.bot.date_format)).total_seconds() < 86400 else ":green_circle: "
                    level = buff + str(level)
                    citizenship_name = find_buff[name][1]
                    name = f"{utils.codes(citizenship_name)} [{name}]({find_buff[name][0]})"

                else:
                    citizenship_name = self.bot.countries[citizenship]
                    name = f"{utils.codes(citizenship_name)} [{name}]({base_url}profile.html?id={row['id']})"
                    level = f":unlock: {level}"

                header = "CS, Nick", "Level", "Location"
                row = [name, level, f"{utils.codes(location)} {location}"]
            table1.append(row)
        if not table1:
            await utils.custom_followup(
                interaction, "I'm sorry, but I could not find anyone online " +
                             (f"at the bonus locations of <{link}>" if check_battle else "") +
                             "\nPerhaps you should read the help command again.\n"
                             f"If you do not believe me, you may see for yourself here: <{base_url}citizensOnline.html?countryId={country}>")
            return
        if len(header) == 3:
            embed = Embed(colour=0x3D85C6, title="More Info",
                          url=f"{base_url}citizensOnline.html?countryId={country}")
            embed.set_footer(text="\U0001f7e2, \U0001f534, \U0001f513 = Buff / Debuff / Neither")
            await utils.send_long_embed(interaction, embed, header, table1)

        else:
            new_lines = 0
            if server in self.bot.gids:
                find_buffs = await utils.find_one("buffs", server)
                for row in table1:
                    if row[0] not in find_buffs or not find_buffs[row[0]][5]:
                        continue

                    db_row = find_buffs[row[0]]
                    index = None
                    if (datetime.strptime(now, self.bot.date_format) - datetime.strptime(db_row[5],
                                                                                         self.bot.date_format)).total_seconds() < 86400:
                        index = -2
                    if not db_row[5]:
                        index = -1
                    if index and row[index]:
                        row[index] += f"\n(Time left: {db_row[7].strip()})"
                        new_lines += 1
            output_buffer = await self.bot.loop.run_in_executor(None, draw_pil_table, table1, header, new_lines)
            await utils.custom_followup(interaction, file=File(fp=output_buffer, filename=f'{server}.jpg'))

    @checks.dynamic_cooldown(CoolDownModified(10))
    @command()
    @describe(role="ping a specific role", t="minutes before round ends to ping at",
              country="filter battles by country")
    @guild_only()
    @check(not_support)
    async def ping(self, interaction: Interaction, server: Transform[str, Server], role: Optional[Role],
                   t: float = 5.0, country: Transform[str, Country] = "") -> None:
        """Informs the user about each round that comes to an end."""

        ping_id = randint(1000, 9999)
        await utils.custom_followup(
            interaction, f"I will write here at the last {t} minutes of every battle in "
                         f"{server if not country else country}.\nIf you want to stop it, type `/stop {ping_id}`")
        ping_id = f"{interaction.channel.id} {ping_id}"
        try:
            role = role.mention
        except Exception:
            role = role or ""
        find_ping = await utils.find_one("collection", "ping")
        find_ping[ping_id] = {"t": t, "server": server, "country": country, "role": role,
                              "author_id": str(interaction.user.id)}
        await utils.replace_one("collection", "ping", find_ping)
        await ping_func(interaction.channel, t, server, ping_id, country, role, interaction.user.id)

    @checks.dynamic_cooldown(utils.CoolDownModified(2))
    @command()
    @describe(ping_id="leave it empty if you wish to remove all ids in this channel")
    async def stop(self, interaction: Interaction, ping_id: Optional[int]) -> None:
        """Stopping `ping` program for a given id.
        If you meant to stop `motivate` program - use `got`"""
        find_ping = await utils.find_one("collection", "ping")
        if not ping_id:
            ping_id = [x.split()[1] for x in find_ping if str(interaction.channel.id) == x.split()[0]]
            if len(ping_id) == 1:
                if f"{interaction.channel.id} {ping_id[0]}" in find_ping:
                    del find_ping[f"{interaction.channel.id} {ping_id[0]}"]
                    await utils.replace_one("collection", "ping", find_ping)
                    await utils.custom_followup(interaction, "Program `ping` have been stopped. no more spam!")
            elif len(ping_id) > 1:
                await utils.custom_followup(interaction,
                                            f"Type `/stop <ID>` with at least one of those ID's: {', '.join(ping_id)}\nExample: `/stop {ping_id[0]}`",
                                            ephemeral=True)
            else:
                await utils.custom_followup(interaction, "There is nothing to stop", ephemeral=True)

        elif f"{interaction.channel.id} {ping_id}" in find_ping:
            del find_ping[f"{interaction.channel.id} {ping_id}"]
            await utils.replace_one("collection", "ping", find_ping)
            await utils.custom_followup(interaction, f"Program `ping` for ID {ping_id} have been stopped.")
        else:
            await utils.custom_followup(interaction, f"Id {ping_id} was not found in this channel", ephemeral=True)

    @command()
    @check(utils.is_premium_level_1)
    async def spectators(self, interaction: Interaction, battle_link: Transform[dict, BattleLink]) -> None:
        """Displays spectators count in a battle (plus some extra info)."""

        server, battle_id = battle_link["server"], battle_link["id"]
        link = f"https://{server}.e-sim.org/battle.html?id={battle_id}"
        tree = await utils.get_locked_content(link)
        try:
            hidden_id = tree.xpath("//*[@id='battleRoundId']")[0].value
        except IndexError:
            await utils.custom_followup(interaction, "This battle is probably over. If not, please report it as a bug.",
                                        ephemeral=True)
            return

        await interaction.response.defer()
        my_id = utils.get_ids_from_path(tree, '//*[@id="userName"]')[0]
        api = await utils.get_content(
            f"https://{server}.e-sim.org/battleScore.html?id={hidden_id}&at={my_id}&ci=1&premium=1", "json")
        spect = {"spectatorsByCountries": [], "defendersByCountries": [], "attackersByCountries": []}
        for key, spect_list in spect.items():
            for item in api[key].splitlines():
                if "-" in item:
                    count = int(item.split("-")[0].split(">")[-1].strip())
                    country = item.split("xflagsSmall-")[1].split('"')[0].replace("-", " ")
                    if key == "spectatorsByCountries" and country == "Poland":
                        count -= 1
                        if not count:
                            continue
                    spect_list.append(f"{count} {country.title()}")

        top = {}
        for key in ("recentDefenders", "recentAttackers", "topDefenders", "topAttackers"):
            top[key] = [f'**{x["playerName"]}:** {x["influence"]}' for x in api[key]]
        embed = Embed(colour=0x3D85C6, title=f'Time Reminding: {timedelta(seconds=api["remainingTimeInSeconds"])}',
                      description=f'**Defender**: {api["defenderScore"]} ({round(100 - api["percentAttackers"], 2)}%)\n'
                                  f'**Attacker**: {api["attackerScore"]} ({api["percentAttackers"]}%)', url=link)
        for key, value in spect.items():
            key = key.replace("ByCountries", "")
            if key == "spectators":
                api[key + 'Online'] -= 1
            embed.add_field(name=f"__{api[key + 'Online']} {key}__".title(), value=("\n".join(value) or "-"))

        for key, value in top.items():
            if key == "topDefenders":
                embed.add_field(name="\u200B", value="\u200B")
            key = key.replace("10", " 10 ").replace("A", " A").replace("D", " D").title()
            embed.add_field(name=f"__{key}__", value="\n".join(value) or "-")

        await utils.custom_followup(interaction, embed=await utils.custom_author(embed))

    @command()
    async def watch_list(self, interaction: Interaction) -> None:
        """Get the watch list for this channel"""
        data = []
        find_watch = await utils.find_one("collection", "watch") or {"watch": []}
        find_auction = await utils.find_one("collection", "auction") or {"auction": []}
        for watch_dict in find_watch["watch"] + find_auction["auction"]:
            if watch_dict["channel"] == str(interaction.channel.id):
                data.append(f"<{watch_dict['link']}> (at T{watch_dict['t']})")
        await interaction.response.send_message('\n'.join(["**Watch List:**"] + data + [
                "\nIf you want to remove any, write `/unwatch <link>`",
                f"Example: `/unwatch {data[0].split()[0]}`"]) if data else
            "Currently, I'm not watching any battle. Type `.help watch` if you want to watch one.")

    @checks.dynamic_cooldown(CoolDownModified(10))
    @command()
    @guild_only()
    @check(not_support)
    @describe(link="The battle or auction link you want to watch",
              t="How many minutes before the end should I ping you? (default: 5)",
              role="Which role should I mention? (default: @here)", custom_msg="Would you like to add a message to the ping?")
    async def watch(self, interaction: Interaction, link: str, t: float = 5.0,
                    role: Role = None, custom_msg: str = "") -> None:
        """Watching a given battle (or auction) and pinging at a specific time."""

        try:
            role = role.mention
        except Exception:
            role = role or "@here"

        try:
            link = await AuctionLink().transform(interaction, link)
            server, auction_id = link["server"], link["id"]
            link = f'https://{server}.e-sim.org/auction.html?id={auction_id}'
            find_auction = await utils.find_one("collection", "auction") or {"auction": []}
            find_auction["auction"].append(
                {"channel": str(interaction.channel.id), "link": link, "t": t, "custom": custom_msg,
                 "author_id": str(interaction.user.id)})
            await utils.replace_one("collection", "auction", find_auction)
            await watch_auction_func(self.bot, interaction.channel, link, t, custom_msg)

        except Exception:
            link = await BattleLink().transform(interaction, link)
            server, battle_id = link["server"], link["id"]
            link = f"https://{server}.e-sim.org/battle.html?id={battle_id}"
            api_battles = await utils.get_content(link.replace("battle", "apiBattles").replace("id", "battleId"))
            if 8 in (api_battles['defenderScore'], api_battles['attackerScore']):
                await utils.custom_followup(interaction, "This battle is over!", ephemeral=True)
                return
            embed = Embed(colour=0x3D85C6, title=link,
                          description=f"**__Parameters__:**\n**T**: {t}\n**Role**: {role}\n**Custom msg**: " + (
                              f"{custom_msg}" if custom_msg else "None"))
            embed.add_field(name="Time Remaining",
                            value=f'{api_battles["hoursRemaining"]:02d}:{api_battles["minutesRemaining"]:02d}:{api_battles["secondsRemaining"]:02d}')
            defender, attacker = self.bot.countries.get(api_battles["defenderId"], "defender"), self.bot.countries.get(
                api_battles["attackerId"], "attacker")
            embed.add_field(name="Sides", value=f"{utils.codes(defender)} {defender} vs "
                                                f"{utils.codes(attacker)} {attacker}")
            embed.add_field(name="Score", value=f'{api_battles["defenderScore"]}:{api_battles["attackerScore"]}')
            embed.set_footer(text="If you want me to stop watching this battle, use /unwatch")
            find_watch = await utils.find_one("collection", "watch") or {"watch": []}
            find_watch["watch"].append(
                {"channel": str(interaction.channel.id), "link": link, "t": t, "role": role, "custom": custom_msg,
                 "author_id": str(interaction.user.id)})
            await utils.replace_one("collection", "watch", find_watch)
            await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed))
            await watch_func(self.bot, interaction.channel, link, t, role, custom_msg)

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @hybrid_command()
    async def unwatch(self, ctx, link: str) -> None:
        """Stop watching a battle / auction"""

        find_watch = await utils.find_one("collection", "watch") or {"watch": []}
        find_auction = await utils.find_one("collection", "auction") or {"auction": []}
        channel_id = ctx.channel.id if isinstance(ctx, Context) else ctx.id

        removed = []
        for auction_dict in list(find_watch["watch"]):
            if auction_dict["channel"] == str(channel_id) and auction_dict["link"] == link:
                find_watch["watch"].remove(auction_dict)
                removed.append(f"<{link}>")
        for auction_dict in list(find_auction["auction"]):
            if auction_dict["channel"] == str(channel_id) and auction_dict["link"] == link:
                find_auction["auction"].remove(auction_dict)
                removed.append(f"<{link}>")
        if not removed:
            await ctx.send(f"I'm not watching {link} in this server")
        else:
            await ctx.send("Removed " + ", ".join(removed))
            await utils.replace_one("collection", "watch", find_watch)
            await utils.replace_one("collection", "auction", find_auction)

    @staticmethod
    def normal_pdf(x, mean, std) -> float:
        """Probability Density Function - a good binomial approximation for big numbers
        X ~ N(mu=mean=np, sigma=std=sqrt(np(1-p))
        PDF(X) = e^(-(x-np)^2/(2np(1-p))) / sqrt(2*PI*np(1-p))"""
        return math.exp(- math.pow((x - mean)/std, 2) / 2) / (math.sqrt(2 * math.pi) * std)

    async def cup_func(self, interaction, db_query, server, ids, new_cup) -> None:
        """cup func"""
        base_url = f'https://{server}.e-sim.org/'
        first, last = min(ids), max(ids)
        try:
            msg = await interaction.channel.send(content="Progress status: 1%.\n(I will update you after every 10%)",
                                                 file=File("files/typing.gif"))
            battle_type = ""
            my_dict = defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0})
            output = StringIO()
            csv_writer = writer(output)
            for index, battle_id in enumerate(ids):
                msg = await utils.update_percent(index, len(ids), msg)
                api_battles = await utils.get_content(f'{base_url}apiBattles.html?battleId={battle_id}')
                if not new_cup:
                    if api_battles['frozen']:
                        continue
                    if not battle_type:
                        battle_type = api_battles['type']
                        if battle_type not in ['TEAM_TOURNAMENT', "COUNTRY_TOURNAMENT", "LEAGUE", "CUP_EVENT_BATTLE",
                                               "MILITARY_UNIT_CUP_EVENT_BATTLE", "TEAM_NATIONAL_CUP_BATTLE"]:
                            await interaction.edit_original_response(content=f"First battle must be a cup (not `{battle_type}`)")
                            db_dict = await utils.find_one("collection", interaction.command.name)
                            del db_dict[db_query]
                            return await utils.replace_one("collection", interaction.command.name, db_dict)
                        await interaction.edit_original_response(content=f"\nChecking battles of type {battle_type} (id {first}) from id {first} to id {last}")
                if new_cup or api_battles['type'] == battle_type:
                    if api_battles['defenderScore'] == 8 or api_battles['attackerScore'] == 8:
                        last_round = api_battles['currentRound']
                    else:
                        last_round = api_battles['currentRound'] + 1
                    for round_id in range(1, last_round):
                        for hit in await utils.get_content(
                                f'{base_url}apiFights.html?battleId={battle_id}&roundId={round_id}'):
                            key = hit['citizenId']
                            my_dict[key]['weps'][hit['weapon']] += 5 if hit['berserk'] else 1
                            my_dict[key]['dmg'] += hit['damage']
                            csv_writer.writerow([key, hit["time"], hit['damage']])
                        await utils.custom_delay(interaction)

            my_dict = dict(sorted(my_dict.items(), key=lambda kv: kv[1]['dmg'], reverse=True))
            top_10 = list(my_dict.keys())[:10]
            hit_time = {k: {"dmg": [], "time": []} for k in top_10}
            output.seek(0)
            for hit in sorted(reader(output), key=lambda row: utils.get_time(row[1])):
                citizen, time_reminding, dmg = int(hit[0]), hit[1], int(hit[2])
                if citizen in top_10:
                    hit_time[citizen]["time"].append(utils.get_time(time_reminding))
                    if hit_time[citizen]["dmg"]:
                        hit_time[citizen]["dmg"].append(hit_time[citizen]["dmg"][-1] + dmg)
                    else:
                        hit_time[citizen]["dmg"].append(dmg)

            output = StringIO()
            csv_writer = writer(output)
            csv_writer.writerow(["#", "Citizen Id", "DMG", "Q0 wep", "Q1", "Q2", "Q3", "Q4", "Q5 wep"])
            final = defaultdict(lambda: {'hits': 0, 'dmg': 0})
            for index, (channel_id, data) in enumerate(my_dict.items(), 1):
                if index <= 10:
                    api_citizen_by_id = await utils.get_content(f'{base_url}apiCitizenById.html?id={channel_id}')
                    hyperlink = f"{utils.codes(api_citizen_by_id['citizenship'])}" \
                                f" [{api_citizen_by_id['login'][:25]}]({base_url}profile.html?id={channel_id})"
                    final[hyperlink]['dmg'] = data['dmg']
                    final[hyperlink]['hits'] = sum(data['weps'])
                    hit_time[api_citizen_by_id['login']] = hit_time.pop(channel_id)
                csv_writer.writerow([index, channel_id, data['dmg']] + data['weps'])
            hit_time = dict(sorted(hit_time.items(), key=lambda kv: kv[1]["dmg"][-1], reverse=True)[:5])
            output_buffer = await Battle.cup_trend(self.bot, hit_time)
            if not output_buffer:
                output_buffer = await dmg_trend(hit_time, server, f"{first} - {last}")
            hit_time.clear()

            embed = Embed(colour=0x3D85C6, title=f"{server}, {first}-{last}")
            embed.add_field(name="**#. CS, Nick**",
                            value="\n".join(f"{index}. {k}" for index, k in enumerate(final.keys(), 1)))
            embed.add_field(name="**Damage**", value="\n".join([f'{v["dmg"]:,}' for v in final.values()]))
            embed.add_field(name="**Hits**", value="\n".join([f'{v["hits"]:,}' for v in final.values()]))

            db_dict = await utils.find_one("collection", interaction.command.name) or {}
            for cup_dict in db_dict.get(db_query, {}):
                for channel_id, data in cup_dict.items():
                    output_buffer.seek(0)
                    output.seek(0)
                    graph = File(fp=output_buffer, filename=f"{interaction.id}.png")
                    embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
                    added_fields = False
                    if data["nick"] and data["nick"] != "-":
                        try:
                            api = await utils.get_content(f'{base_url}apiCitizenByName.html?name={data["nick"].lower()}')
                            key = f"{utils.codes(api['citizenship'])} [{api['login']}]({base_url}profile.html?id={api['id']})"
                            if key not in final:
                                embed.add_field(name="\u200B",
                                                value=f"{list(my_dict.keys()).index(api['id']) + 1}. __{key}__")
                                embed.add_field(name="\u200B", value=f'{my_dict[api["id"]]["dmg"]:,}')
                                embed.add_field(name="\u200B", value=f'{sum(my_dict[api["id"]]["weps"]):,}')
                                added_fields = True
                        except Exception:
                            pass

                    try:
                        channel = self.bot.get_channel(int(channel_id))
                        await channel.send(embed=await utils.convert_embed(int(data["author_id"]), embed),
                                           files=[File(fp=BytesIO(output.getvalue().encode()),
                                                       filename=f"Fighters_{server}_{first}-{last}.csv"), graph])
                    except Exception as error:
                        await utils.send_error(interaction, error)
                    if added_fields:
                        for _ in range(3):
                            embed.remove_field(-1)
                    await sleep(0.4)

        except Exception as error:
            await utils.send_error(interaction, error)
            db_dict = await utils.find_one("collection", interaction.command.name)
            if db_query in db_dict:
                for cup_dict in db_dict[db_query]:
                    for channel_id, _ in cup_dict.items():
                        try:
                            channel = self.bot.get_channel(int(channel_id))
                            await channel.send("I am sorry, but it looks like e-sim rejected this request.")
                            await sleep(0.4)
                        except Exception:
                            traceback.print_exc()

        db_dict = await utils.find_one("collection", interaction.command.name)
        if db_query in db_dict:
            del db_dict[db_query]
            await utils.replace_one("collection", interaction.command.name, db_dict)

    async def new_cup_func(self, interaction: Interaction, server: str, nick: str, ids: iter) -> None:
        """cup func"""
        base_url = f"https://{server}.e-sim.org/"
        first, last = min(ids), max(ids)
        api_battles_df = await utils.find_many_api_battles(interaction, server, ids)
        battle_type = api_battles_df[api_battles_df['battle_id'] == first]["type"].iloc[0]
        if battle_type not in ('TEAM_TOURNAMENT', "COUNTRY_TOURNAMENT", "LEAGUE", "CUP_EVENT_BATTLE",
                               "MILITARY_UNIT_CUP_EVENT_BATTLE", "TEAM_NATIONAL_CUP_BATTLE"):
            await utils.custom_followup(interaction, f"First battle must be a cup (not `{battle_type}`)")
            return
        api_battles_df = api_battles_df[api_battles_df["type"] == battle_type]
        hit_time_df = await utils.find_many_api_fights(interaction, server, api_battles_df)
        hit_time_df['hits'] = hit_time_df['berserk'].apply(lambda x: 5 if x else 1)
        for i in range(6):
            hit_time_df[f'Q{i} weps'] = hit_time_df.apply(lambda c: c['hits'] if c['weapon'] == i else 0, axis=1)

        output = StringIO()
        df = hit_time_df.groupby('citizenId', sort=False)[["damage", "hits"] + [f'Q{i} weps' for i in range(6)]].sum()
        df.sort_values("damage", ascending=False, inplace=True)
        df.to_csv(output)
        hit_time_df = hit_time_df[['citizenId', 'damage', 'time']]
        hit_time_df['citizenName'] = ""

        final = defaultdict(lambda: {'hits': 0, 'damage': 0})
        for i, (citizen_id, row) in enumerate(df.iterrows()):
            if i == 10:
                break
            api_citizen = await utils.get_content(f'{base_url}apiCitizenById.html?id={citizen_id}')
            hyperlink = f"{utils.codes(api_citizen['citizenship'])}" \
                        f" [{api_citizen['login'][:25]}]({base_url}profile.html?id={citizen_id})"
            final[hyperlink]['damage'] = row['damage']
            final[hyperlink]['hits'] = row['hits']
            if i < 5:
                hit_time_df.loc[(hit_time_df['citizenId'] == citizen_id), 'citizenName'] = api_citizen['login']
            await utils.custom_delay(interaction)

        hit_time_df = hit_time_df[hit_time_df['citizenName'] != ""]
        hit_time = defaultdict(lambda: {"dmg": [], "time": []})
        for i, row in hit_time_df.iterrows():
            if hit_time[row['citizenName']]["dmg"]:
                hit_time[row['citizenName']]["dmg"].append(hit_time[row['citizenName']]["dmg"][-1] + row['damage'])
            else:
                hit_time[row['citizenName']]["dmg"].append(row['damage'])
            hit_time[row['citizenName']]["time"].append(utils.get_time(row['time']))
        for v in hit_time.values():
            v["time"].sort()
        output_buffer = await Battle.cup_trend(self.bot, hit_time)
        if not output_buffer:
            output_buffer = await dmg_trend(hit_time, server, f"{first} - {last}")
        embed = Embed(colour=0x3D85C6, title=f"{server}, {first}-{last}")
        embed.add_field(name="**#. CS, Nick**",
                        value="\n".join(f"{index}. {k}" for index, k in enumerate(final.keys(), 1)))
        embed.add_field(name="**Damage**", value="\n".join([f'{v["damage"]:,}' for v in final.values()]))
        embed.add_field(name="**Hits**", value="\n".join([f'{v["hits"]:,}' for v in final.values()]))
        output_buffer.seek(0)
        output.seek(0)
        graph = File(fp=output_buffer, filename=f"{interaction.id}.png")
        embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
        if nick and nick != "-":
            api = await utils.get_content(f'{base_url}apiCitizenByName.html?name={nick.lower()}')
            key = f"{utils.codes(api['citizenship'])} [{api['login']}]({base_url}profile.html?id={api['id']})"
            if key not in final:
                i = df.index.get_loc(api['id'])
                embed.add_field(name="\u200B", value=f"{i}. __{key}__")
                embed.add_field(name="\u200B", value=f'{df.iloc[i]["damage"]:,}')
                embed.add_field(name="\u200B", value=f'{df.iloc[i]["hits"]:,}')

        await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed),
                               files=[File(fp=BytesIO(output.getvalue().encode()),
                                           filename=f"Fighters_{server}_{first}-{last}.csv"), graph])
    @staticmethod
    async def cup_trend(bot, hit_time: dict) -> Optional[BytesIO]:
        """cup trend"""
        hit_time1 = defaultdict(lambda: {"dmg": [], "time": []})
        hit_time2 = defaultdict(lambda: {"dmg": [], "time": []})
        for k in hit_time:
            for index in range(len(hit_time[k]["time"])):
                if hit_time2[k]["time"] or (index and (
                        hit_time[k]["time"][index] - hit_time[k]["time"][index - 1]).total_seconds() > 12 * 3600):
                    hit_time2[k]["time"].append(hit_time[k]["time"][index])
                    hit_time2[k]["dmg"].append(hit_time[k]["dmg"][index])
                else:
                    hit_time1[k]["time"].append(hit_time[k]["time"][index])
                    hit_time1[k]["dmg"].append(hit_time[k]["dmg"][index])
        hit_time2 = {k: v for k, v in hit_time2.items() if v["dmg"]}
        if hit_time2:
            def my_func() -> BytesIO:
                fig, (ax1, ax2) = plt.subplots(1, 2, sharey='all', tight_layout=True)
                fig.subplots_adjust(wspace=0.05)
                colors = {}
                for player, dmg_time in hit_time1.items():
                    lines = ax1.plot(dmg_time["time"], dmg_time["dmg"], label=player)
                    colors[player] = lines[-1].get_color()

                for player, dmg_time in hit_time2.items():
                    ax2.plot(dmg_time["time"], dmg_time["dmg"], label=player, color=colors.get(player))

                if hit_time1:
                    ax1.legend()
                else:
                    ax2.legend()
                max_dmg = max(x["dmg"][-1] for x in hit_time.values())
                ax1.set_ylim(0, max_dmg + max_dmg / 10)
                ax1.set_xlim(min(x["time"][0] for x in hit_time1.values()),
                            max(x["time"][-1] for x in hit_time1.values()))
                ax2.set_xlim(min(x["time"][0] for x in hit_time2.values()),
                             max(x["time"][-1] for x in hit_time2.values()))
                ax1.set_yticklabels([human_format(int(x)) for x in ax1.get_yticks().tolist()])

                ax1.xaxis.set_major_formatter(DateFormatter("%d-%m %H:%M"))
                ax2.xaxis.set_major_formatter(DateFormatter("%d-%m %H:%M"))
                fig.autofmt_xdate()

                ax1.spines['right'].set_visible(False)
                ax2.spines['left'].set_visible(False)
                ax2.yaxis.tick_right()
                return utils.plt_to_bytes()
            return await bot.loop.run_in_executor(None, my_func)


async def motivate_func(bot, server: str, data: dict) -> None:
    """motivate func"""
    base_url = f'https://{server}.e-sim.org/'
    old_citizen_id = 0
    while server in data:
        try:
            tree = await utils.get_content(f'{base_url}newCitizens.html?countryId=0')
            try:
                citizen_id = int(utils.get_ids_from_path(tree, "//tr[2]//td[1]/a")[0])
            except IndexError:
                await sleep(randint(500, 700))
                continue
            if old_citizen_id and citizen_id != old_citizen_id:
                embed = Embed(colour=0x3D85C6, title="Citizens Registered In The Last 5 Minutes",
                              url=f'{base_url}newCitizens.html?countryId=0')
                embed.add_field(name="Motivate Link", value="\n".join(
                    [f'{base_url}motivateCitizen.html?id={i}' for i in range(old_citizen_id + 1, citizen_id + 1)]))
                embed.set_footer(text=f"If you want to stop it, type .got {server}")
                for channel_id in list(data[server]):
                    try:
                        channel = bot.get_channel(int(channel_id))
                        await channel.send(embed=await utils.custom_author(embed))
                    except Exception:
                        data[server].remove(channel_id)
                    await sleep(0.4)
            old_citizen_id = citizen_id
            await utils.replace_one("collection", "motivate", data)
            del data, tree
        except Exception:
            print(datetime.now().astimezone(timezone('Europe/Berlin')))
            traceback.print_exc()
        await sleep(randint(500, 700))
        data = await utils.find_one("collection", "motivate")


async def ping_func(channel: TextChannel, t: float, server: str, ping_id: str, country: str,
                    role: str, author_id: int = 0) -> None:
    """ping func"""
    base_url = f'https://{server}.e-sim.org/'
    find_ping = await utils.find_one("collection", "ping")
    while ping_id in find_ping:
        detailed_list = []
        ids = []
        for battle_filter in ("NORMAL", "RESISTANCE"):
            link = f'{base_url}battles.html?filter={battle_filter}'
            for page in range(1, await utils.last_page(link)):
                tree = await utils.get_content(link + f'&page={page}')
                for battle_data in (await utils.battles_data(tree))["battles"]:
                    if battle_data["battle_id"] not in ids and country in (battle_data['defender']['name'], battle_data['attacker']['name'],):
                        detailed_list.append(battle_data)
                        ids.append(battle_data["battle_id"])
        if not detailed_list:
            await channel.send("The program has stopped, because there are currently no active RWs or attacks in this " +
                               (f"country (`{country}`)." if country else f"server (`{server}`)."))
            find_ping = await utils.find_one("collection", "ping")
            if ping_id in find_ping:
                del find_ping[ping_id]
                await utils.replace_one("collection", "ping", find_ping)
            break
        detailed_list = sorted(detailed_list, key=lambda k: k['time_reminding'])
        for battle_dict in detailed_list:
            api_battles = await utils.get_content(f'{base_url}apiBattles.html?battleId={battle_dict["battle_id"]}')
            if api_battles["frozen"]:
                continue
            sleep_time = api_battles["hoursRemaining"] * 3600 + api_battles["minutesRemaining"] * 60 + api_battles[
                "secondsRemaining"] - t * 60
            if sleep_time > 0:
                await sleep(sleep_time)
            find_ping = await utils.find_one("collection", "ping")
            if ping_id in find_ping:
                d_name, a_name = battle_dict['defender']['name'], battle_dict['attacker']['name']
                current_round = battle_dict['defender']['score'] + battle_dict['attacker']['score'] + 1
                api_fights = f'{base_url}apiFights.html?battleId={battle_dict["battle_id"]}&roundId={current_round}'
                my_dict, hit_time = await utils.save_dmg_time(api_fights, a_name, d_name)
                output_buffer = await dmg_trend(hit_time, server, f'{battle_dict["battle_id"]}-{current_round}')
                hit_time.clear()
                attacker_dmg = my_dict[a_name]
                defender_dmg = my_dict[d_name]
                embed = Embed(colour=0x3D85C6, title=f"{base_url}battle.html?id={battle_dict['battle_id']}",
                              description=f"**T{t}, Score:** {battle_dict['defender']['score']}:{battle_dict['attacker']['score']}\n"
                                          + (f"**Total Dmg:** {battle_dict['dmg']}" if 'dmg' in battle_dict else ''))
                embed.add_field(name=f"{utils.codes(d_name)} " + utils.shorten_country(d_name),
                                value=f"{defender_dmg:,}")
                embed.add_field(name=f"Battle type: {api_battles['type'].replace('_', ' ').title()}",
                                value=await bar(defender_dmg, attacker_dmg, d_name, a_name))
                embed.add_field(name=f"{utils.codes(a_name)} " + utils.shorten_country(d_name),
                                value=f"{attacker_dmg:,}")
                embed.set_footer(text="Type /stop if you wish to stop it.")
                embed.set_thumbnail(url=f"attachment://{channel.id}.png")
                try:
                    await channel.send(role, embed=await utils.convert_embed(int(author_id), embed),
                                       delete_after=t * 60,
                                       file=File(fp=output_buffer, filename=f"{channel.id}.png"))
                except Exception:
                    find_ping = await utils.find_one("collection", "ping")
                    if f"{channel.id} {ping_id}" in find_ping:
                        del find_ping[f"{channel.id} {ping_id}"]
                        await utils.replace_one("collection", "ping", find_ping)
                        await channel.send(f"There was an error. Program `ping` for ID {ping_id} has been stopped.")
                    return
        await sleep(t * 60 + 30)
        find_ping = await utils.find_one("collection", "ping")


async def watch_func(bot, channel: TextChannel, link: str, t: float, role: str, custom: str, author_id: int = 0) -> None:
    """watch func"""
    while any(DICT["channel"] == str(channel.id) and DICT["link"] == link for DICT in
              (await utils.find_one("collection", "watch"))["watch"]):
        api_battles = await utils.get_content(link.replace("battle", "apiBattles").replace("id", "battleId"))
        if 8 in (api_battles['defenderScore'], api_battles['attackerScore']):
            find_watch = await utils.find_one("collection", "watch") or {"watch": []}
            for watch_dict in list(find_watch["watch"]):
                if watch_dict["link"] == link:
                    find_watch["watch"].remove(watch_dict)
            return await utils.replace_one("collection", "watch", find_watch)
        sleep_time = api_battles["hoursRemaining"] * 3600 + api_battles["minutesRemaining"] * 60 + api_battles[
            "secondsRemaining"] - t * 60
        await sleep(sleep_time if sleep_time > 0 else 0)
        find_watch = await utils.find_one("collection", "watch") or {"watch": []}
        if not any(DICT["channel"] == str(channel.id) and DICT["link"] == link for DICT in find_watch["watch"]):
            break
        api_battles = await utils.get_content(link.replace("battle", "apiBattles").replace("id", "battleId"))
        sleep_time = api_battles["hoursRemaining"] * 3600 + api_battles["minutesRemaining"] * 60 + api_battles[
            "secondsRemaining"] - t * 60
        await sleep(sleep_time if sleep_time > 0 else 0)
        if api_battles['frozen']:
            continue
        attacker = api_battles["attackerId"]
        defender = api_battles["defenderId"]
        if attacker != defender and attacker in bot.countries and defender in bot.countries and \
                api_battles["type"] != "MILITARY_UNIT_CUP_EVENT_BATTLE":
            attacker = bot.countries[attacker]
            defender = bot.countries[defender]
        else:
            attacker, defender = "Attacker", "Defender"
        api_fights = link.replace("battle", "apiFights").replace("id", "battleId") + f"&roundId={api_battles['currentRound']}"
        my_dict, hit_time = await utils.save_dmg_time(api_fights, attacker, defender)
        output_buffer = await dmg_trend(hit_time, link.split("//")[1].split(".e-sim.org")[0],
                                        f'{link.split("=")[1].split("&")[0]}-{api_battles["currentRound"]}')
        hit_time.clear()
        msg = f"{role} {custom}"
        embed = Embed(colour=0x3D85C6,
                      title=f"T{t}, **Score:** {api_battles['defenderScore']}:{api_battles['attackerScore']}", url=link)
        embed.add_field(name=f"{utils.codes(defender)}" + utils.shorten_country(defender),
                        value=f"{my_dict[defender]:,}")
        embed.add_field(name=f'Battle type: {api_battles["type"].replace("_", " ").title()}',
                        value=await bar(my_dict[defender], my_dict[attacker], defender, attacker))
        embed.add_field(name=f"{utils.codes(attacker)} " + utils.shorten_country(attacker),
                        value=f"{my_dict[attacker]:,}")
        embed.set_thumbnail(url=f"attachment://{channel.id}.png")
        embed.set_footer(text="If you want to stop watching this battle, type /unwatch")
        delete_after = api_battles["hoursRemaining"] * 3600 + api_battles["minutesRemaining"] * 60 + api_battles[
            "secondsRemaining"]

        try:
            await channel.send(msg, embed=await utils.convert_embed(int(author_id), embed),
                               file=File(fp=output_buffer, filename=f"{channel.id}.png"), delete_after=delete_after)
        except Exception:
            return await bot.get_command("unwatch").__call__(channel, link)
        await sleep(t * 60 + 150)


async def watch_auction_func(bot, channel: TextChannel, link: str, t: float, custom_msg: str, author_id: int = 0) -> None:
    """Activate watch/auction function"""
    row = await utils.get_auction(link)

    if row["reminding_seconds"] < 0:
        return await remove_auction(bot, link, channel.id)

    await sleep(row["reminding_seconds"] - t * 60)
    row = await utils.get_auction(link)

    embed = Embed(colour=0x3D85C6, title=link,
                  description=f"**__Parameters__:**\n**T**: {t}\n\n**Custom msg**: " + (
                      f"{custom_msg}" if custom_msg else "None"))
    embed.add_field(name="Info", value="\n".join([f"**{k.title()}:** {v}" for k, v in row.items()]))

    embed = Embed(colour=0x3D85C6, title=link)
    embed.add_field(name="Info", value="\n".join([f"**{k.title()}:** {v}" for k, v in row.items()]))
    await channel.send(custom_msg, embed=await utils.convert_embed(author_id, embed))
    return await remove_auction(bot, link, channel.id)


async def remove_auction(bot, link: str, channel_id: int) -> None:
    """Removes auction"""
    find_auction = await utils.find_one("collection", "auction") or {"auction": []}
    for auction_dict in list(find_auction["auction"]):
        if auction_dict["link"] == link and auction_dict["channel"] == channel_id:
            find_auction["auction"].remove(auction_dict)
    await utils.replace_one("collection", "auction", find_auction)


async def setup(bot) -> None:
    """Setup"""
    await bot.add_cog(Battle(bot))
