from collections import defaultdict
from copy import deepcopy
from csv import writer
from io import BytesIO, StringIO

from discord import Embed, File, Interaction
from discord.app_commands import Transform
from discord.utils import MISSING

from . import utils
from .constants import all_countries, all_countries_by_name
from .transformers import BattleLink, Country
from .utils import dmg_trend, draw_pil_table


# TODO: Shorten this function / break it down into smaller functions
async def dmg_func(bot, interaction: Interaction, battle_link: Transform[dict, BattleLink], nick: str = "",
                   country: Transform[str, Country] = "", mu_id: int = 0) -> None:
    """
    Displays wep used and dmg done (Per player, MU, country, or overall) in a given battle(s).

    **Notes:**
    - If your nick is the same string as some country (or close enough), add a dash before your nick. Example: `-Israel`
    - For range of battles, use `<first>_<last>` instead of `<link>` (`/dmg battle_link: alpha 1165_1167 country: Israel`)
    """  # noqa

    server, battle_id, round_id = battle_link["server"], battle_link["id"], battle_link["round"]
    last_battle = battle_link["last"] if battle_link["last"] else battle_id
    range_of_battles = battle_link["last"]
    if last_battle - battle_id > 1000 and not await utils.is_premium_level_1(interaction, False):
        await utils.custom_followup(
            interaction, "It's too much, sorry. You can buy premium and remove this limit.", ephemeral=True)
        return
    server = utils.server_validation(server or "")
    base_url = f"https://{server}.e-sim.org/"
    api_battles = await utils.get_content(f'{base_url}apiBattles.html?battleId={battle_id}')
    key = mu_name = mu_api = header = citizen = None
    if country:
        nick = country
        key_id = all_countries_by_name[country.lower()]
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
        if api_battles["type"] == "MILITARY_UNIT_CUP_EVENT_BATTLE" and not range_of_battles:
            header = ["Military unit", "Q0 wep", "Q1", "Q5", "DMG"]
            attacker_id = (await utils.get_content(
                f'{base_url}apiMilitaryUnitById.html?id={api_battles["attackerId"]}'))["name"]
            defender_id = (await utils.get_content(
                f'{base_url}apiMilitaryUnitById.html?id={api_battles["defenderId"]}'))["name"]
        else:
            attacker_id = api_battles["attackerId"]
            defender_id = api_battles["defenderId"]
            header = ["Side", "Q0 wep", "Q1", "Q5", "DMG"]
    else:
        attacker_id, defender_id = 0, 0

    attacker, defender = utils.get_sides(api_battles, attacker_id, defender_id)

    hit_time = defaultdict(lambda: {"dmg": [], "time": []})
    tops = False
    my_dict = defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0})
    if range_of_battles:
        msg = await utils.custom_followup(interaction,
                                          "Progress status: 1%.\n(I will update you after every 10%)" if
                                          last_battle - battle_id > 10 else "I'm on it, Sir. Be patient.",
                                          file=File(bot.typing_gif_path))
        empty_sides = {"Total": {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0}}
    else:
        msg = None
        empty_sides = {defender: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0},
                       attacker: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0},
                       "Total": {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0}}
    my_dict.update(empty_sides)

    if not round_id:
        for index, battle_id in enumerate(range(battle_id, last_battle + 1)):
            if range_of_battles:
                msg = await utils.update_percent(index, last_battle - battle_id, msg)

            if api_battles['defenderScore'] == 8 or api_battles['attackerScore'] == 8:
                last = api_battles['currentRound']
            else:
                last = api_battles['currentRound'] + 1
            for round_i in range(1, last):
                defender_details = defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0})
                attacker_details = defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0})
                for hit in reversed(
                        await utils.get_content(
                            f'{base_url}apiFights.html?battleId={battle_id}&roundId={round_i}')):
                    side_string = defender if hit['defenderSide'] else attacker
                    update_hit_dmg(hit, my_dict, range_of_battles, key, side_string)
                    update_hit_time(hit, hit_time, side_string)

                    if key == 'citizenId':
                        side = defender_details if hit['defenderSide'] else attacker_details
                        side[hit['citizenId']]['weps'][hit['weapon']] += 5 if hit['berserk'] else 1
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
                side_string = defender if hit['defenderSide'] else attacker
                update_hit_dmg(hit, my_dict, range_of_battles, key, side_string)
                if key in hit:
                    # TODO: I am not sure what this is doing
                    if (not range_of_battles) and (not key_id or hit[key] == key_id):
                        name = nick if key_id else side_string
                        update_hit_time(hit, hit_time, name)

            if not hit and not range_of_battles:
                await utils.custom_followup(
                    interaction,
                    f'Nothing found at <{base_url}apiFights.html?battleId={battle_id}&roundId={round_id}>')
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
        row = [name if key != "citizenship" else all_countries.get(name, name), value["dmg"]] + value["weps"]
        if "tops" in value:
            row.extend(value["tops"])
        if value["dmg"]:
            csv_writer.writerow([x or "" for x in row])
        if len(new_dict) < 10 and isinstance(name, int):
            if key == "citizenship":
                embed_name = "Country"
                filed = all_countries[name]
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
                        [name, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}",
                         f"{value['dmg']:,}"])
                else:
                    table.append(
                        [name, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}",
                         f"{value['dmg']:,}"])
        else:
            if name == key_id:
                if key == 'militaryUnit':
                    table.append(
                        [mu_name, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}",
                         f"{value['dmg']:,}"])
                elif round_id:
                    table.append([nick, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}",
                                  f"{value['dmg']:,}", f'x{value.get("tops", [0])[0]} times'] + value.get(
                        "tops", [0] * 4)[1:])
                elif key == 'citizenId':
                    table.append(
                        [nick, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}",
                         f"{value['dmg']:,}"])
                else:
                    table.append(
                        [nick, f"{value['weps'][0]:,}", f"{value['weps'][1]:,}", f"{value['weps'][-1]:,}",
                         f"{value['dmg']:,}"])
    output.seek(0)
    if not table:
        await utils.custom_followup(
            interaction,
            f"I did not find {key.replace('Id', '')} `{nick}` at <{base_url}battle.html?id={battle_id}>\n"
            "**Remember:** for __nick__ use `-nick`, for __MU__ use the MU id, "
            "and for __country__ - write the country name.")
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
    view = utils.Transform() if "Id" in embed_name else MISSING
    if len(table) == 1 and not range_of_battles:
        if key != 'citizenship':
            citizenship = all_countries[
                (citizen if embed_name == "Citizen Id" else mu_api)[keys[embed_name]['cs_key']]]
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
        embed.description = f'**Battle type: {api_battles["type"]}**'
        output_buffer1 = await bot.loop.run_in_executor(None, draw_pil_table, table, header)
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
                api_battles = await utils.get_content(f'{base_url}{keys[embed_name]["api_url"]}.html?id={value}')
                flag = utils.codes(all_countries[api_battles[keys[embed_name]['cs_key']]])
                values[num] = f"{flag} [{api_battles[keys[embed_name]['api_key'][:20]]}]" \
                              f"({base_url}{keys[embed_name]['final_link']}.html?id={value})"
                await utils.custom_delay(interaction)
            embed.set_field_at(index, name=field.name[:-5] + "**", value="\n".join(values))
    await msg.edit(embed=await utils.convert_embed(interaction, embed), view=view)


def update_hit_dmg(hit: dict, my_dict: dict, range_of_battles: bool, key: str, side_string: str) -> None:
    wep = 5 if hit['berserk'] else 1
    if not range_of_battles:
        my_dict[side_string]['weps'][hit['weapon']] += wep
        my_dict[side_string]['dmg'] += hit['damage']
    my_dict['Total']['weps'][hit['weapon']] += wep
    my_dict['Total']['dmg'] += hit['damage']
    if key in hit:
        my_dict[hit[key]]['weps'][hit['weapon']] += wep
        my_dict[hit[key]]['dmg'] += hit['damage']


def update_hit_time(hit: dict, hit_time: dict, side_string: str) -> None:
    hit_time[side_string]["time"].append(utils.get_time(hit["time"]))
    if hit_time[side_string]["dmg"]:
        hit_time[side_string]["dmg"].append(hit_time[side_string]["dmg"][-1] + hit['damage'])
    else:
        hit_time[side_string]["dmg"].append(hit['damage'])
