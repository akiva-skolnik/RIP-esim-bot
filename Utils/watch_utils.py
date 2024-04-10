import math
import traceback
from asyncio import sleep
from collections import defaultdict
from datetime import datetime
from io import BytesIO
from random import randint
from typing import Optional

import pandas as pd
from discord import Embed, File, Interaction, TextChannel
from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
from matplotlib.gridspec import GridSpec
from matplotlib.ticker import FixedLocator
from pytz import timezone

from . import db_utils, utils


def normal_pdf(x, mean, std) -> float:
    """Probability Density Function - a good binomial approximation for big numbers
    X ~ N(mu=mean=np, sigma=std=sqrt(np(1-p))
    PDF(X) = e^(-(x-np)^2/(2np(1-p))) / sqrt(2*PI*np(1-p))"""
    return math.exp(- math.pow((x - mean) / std, 2) / 2) / (math.sqrt(2 * math.pi) * std)

    # async def old_cup_func(self, interaction: Interaction, db_key: str, server: str, ids: iter, new_cup: bool) -> None:
    #     """cup func"""
    #     base_url = f'https://{server}.e-sim.org/'
    #     first, last = min(ids), max(ids)
    #     try:
    #         msg = await interaction.channel.send(content="Progress status: 1%.\n(I will update you after every 10%)",
    #                                              file=File(self.bot.typing_gif))
    #         battle_type = ""
    #         my_dict = defaultdict(lambda: {'weps': [0, 0, 0, 0, 0, 0], 'dmg': 0})
    #         output = StringIO()
    #         csv_writer = writer(output)
    #         for index, battle_id in enumerate(ids):
    #             msg = await utils.update_percent(index, len(ids), msg)
    #             api_battles = await utils.get_content(f'{base_url}apiBattles.html?battleId={battle_id}')
    #             if not new_cup:
    #                 if api_battles['frozen']:
    #                     continue
    #                 if not battle_type:
    #                     battle_type = api_battles['type']
    #                     if battle_type not in ['TEAM_TOURNAMENT', "COUNTRY_TOURNAMENT", "LEAGUE", "CUP_EVENT_BATTLE",
    #                                            "MILITARY_UNIT_CUP_EVENT_BATTLE", "TEAM_NATIONAL_CUP_BATTLE"]:
    #                         await interaction.edit_original_response(
    #                             content=f"First battle must be a cup (not `{battle_type}`)")
    #                         db_dict = await utils.find_one("collection", interaction.command.name)
    #                         del db_dict[db_key]
    #                         return await utils.replace_one("collection", interaction.command.name, db_dict)
    #                     await interaction.edit_original_response(
    #                         content=f"\nChecking battles of type {battle_type} (id {first}) from id {first} to id {last}")
    #             if new_cup or api_battles['type'] == battle_type:
    #                 if api_battles['defenderScore'] == 8 or api_battles['attackerScore'] == 8:
    #                     last_round = api_battles['currentRound']
    #                 else:
    #                     last_round = api_battles['currentRound'] + 1
    #                 for round_id in range(1, last_round):
    #                     for hit in await utils.get_content(
    #                             f'{base_url}apiFights.html?battleId={battle_id}&roundId={round_id}'):
    #                         key = hit['citizenId']
    #                         my_dict[key]['weps'][hit['weapon']] += 5 if hit['berserk'] else 1
    #                         my_dict[key]['dmg'] += hit['damage']
    #                         csv_writer.writerow([key, hit["time"], hit['damage']])
    #                     await utils.custom_delay(interaction)
    #
    #         my_dict = dict(sorted(my_dict.items(), key=lambda kv: kv[1]['dmg'], reverse=True))
    #         top_10 = list(my_dict.keys())[:10]
    #         hit_time = {k: {"dmg": [], "time": []} for k in top_10}
    #         output.seek(0)
    #         for hit in sorted(reader(output), key=lambda row: utils.get_time(row[1])):
    #             citizen, time_remaining, dmg = int(hit[0]), hit[1], int(hit[2])
    #             if citizen in top_10:
    #                 hit_time[citizen]["time"].append(utils.get_time(time_remaining))
    #                 if hit_time[citizen]["dmg"]:
    #                     hit_time[citizen]["dmg"].append(hit_time[citizen]["dmg"][-1] + dmg)
    #                 else:
    #                     hit_time[citizen]["dmg"].append(dmg)
    #
    #         output = StringIO()
    #         csv_writer = writer(output)
    #         csv_writer.writerow(["#", "Citizen Id", "DMG", "Q0 wep", "Q1", "Q2", "Q3", "Q4", "Q5 wep"])
    #         final = defaultdict(lambda: {'hits': 0, 'dmg': 0})
    #         for index, (channel_id, data) in enumerate(my_dict.items(), 1):
    #             if index <= 10:
    #                 api_citizen_by_id = await utils.get_content(f'{base_url}apiCitizenById.html?id={channel_id}')
    #                 hyperlink = f"{utils.codes(api_citizen_by_id['citizenship'])}" \
    #                             f" [{api_citizen_by_id['login'][:25]}]({base_url}profile.html?id={channel_id})"
    #                 final[hyperlink]['dmg'] = data['dmg']
    #                 final[hyperlink]['hits'] = sum(data['weps'])
    #                 hit_time[api_citizen_by_id['login']] = hit_time.pop(channel_id)
    #             csv_writer.writerow([index, channel_id, data['dmg']] + data['weps'])
    #         hit_time = dict(sorted(hit_time.items(), key=lambda kv: kv[1]["dmg"][-1], reverse=True)[:5])
    #         output_buffer = await Battle.cup_trend(self.bot, hit_time)
    #         if not output_buffer:
    #             output_buffer = await utils.dmg_trend(hit_time, server, f"{first} - {last}")
    #         hit_time.clear()
    #
    #         embed = Embed(colour=0x3D85C6, title=f"{server}, {first}-{last}")
    #         embed.add_field(name="**CS, Nick**", value="\n".join(final.keys()))
    #         embed.add_field(name="**Damage**", value="\n".join([f'{v["dmg"]:,}' for v in final.values()]))
    #         embed.add_field(name="**Hits**", value="\n".join([f'{v["hits"]:,}' for v in final.values()]))
    #
    #         db_dict = await utils.find_one("collection", interaction.command.name) or {}
    #         for cup_dict in db_dict.get(db_key, {}):
    #             for channel_id, data in cup_dict.items():
    #                 output_buffer.seek(0)
    #                 output.seek(0)
    #                 graph = File(fp=output_buffer, filename=f"{interaction.id}.png")
    #                 embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
    #                 added_fields = False
    #                 if data["nick"] and data["nick"] != "-":
    #                     try:
    #                         api = await utils.get_content(
    #                             f'{base_url}apiCitizenByName.html?name={data["nick"].lower()}')
    #                         key = f"{utils.codes(api['citizenship'])} [{api['login']}]({base_url}profile.html?id={api['id']})"
    #                         if key not in final:
    #                             embed.add_field(name="\u200B",
    #                                             value=f"{list(my_dict.keys()).index(api['id']) + 1}. __{key}__")
    #                             embed.add_field(name="\u200B", value=f'{my_dict[api["id"]]["dmg"]:,}')
    #                             embed.add_field(name="\u200B", value=f'{sum(my_dict[api["id"]]["weps"]):,}')
    #                             added_fields = True
    #                     except Exception:
    #                         pass
    #
    #                 try:
    #                     channel = self.bot.get_channel(int(channel_id))
    #                     await channel.send(embed=await utils.convert_embed(int(data["author_id"]), embed),
    #                                        files=[File(fp=BytesIO(output.getvalue().encode()),
    #                                                    filename=f"Fighters_{server}_{first}-{last}.csv"), graph])
    #                 except Exception as error:
    #                     await utils.send_error(interaction, error)
    #                 if added_fields:
    #                     for _ in range(3):
    #                         embed.remove_field(-1)
    #                 await sleep(0.4)
    #
    #     except Exception as error:
    #         await utils.send_error(interaction, error)
    #         db_dict = await utils.find_one("collection", interaction.command.name)
    #         if db_key in db_dict:
    #             for cup_dict in db_dict[db_key]:
    #                 for channel_id, _ in cup_dict.items():
    #                     try:
    #                         channel = self.bot.get_channel(int(channel_id))
    #                         await channel.send("I am sorry, but it looks like e-sim rejected this request.")
    #                         await sleep(0.4)
    #                     except Exception:
    #                         traceback.print_exc()
    #
    #     db_dict = await utils.find_one("collection", interaction.command.name)
    #     if db_key in db_dict:
    #         del db_dict[db_key]
    #         await utils.replace_one("collection", interaction.command.name, db_dict)


async def cup_func(bot, interaction: Interaction, db_key: str, server: str, battle_ids: iter) -> None:
    """cup func"""
    try:
        base_url = f"https://{server}.e-sim.org/"
        start_id, end_id = min(battle_ids), max(battle_ids)
        battle_type = (await db_utils.select_one_api_battles(server, start_id))['type']
        if battle_type not in ('TEAM_TOURNAMENT', "COUNTRY_TOURNAMENT", "LEAGUE", "CUP_EVENT_BATTLE",
                               "MILITARY_UNIT_CUP_EVENT_BATTLE", "TEAM_NATIONAL_CUP_BATTLE"):
            await utils.custom_followup(interaction, f"First battle must be a cup (not `{battle_type}`)")
            db_dict = await utils.find_one("collection", interaction.command.name)
            del db_dict[db_key]
            return await utils.replace_one("collection", interaction.command.name, db_dict)
        await db_utils.cache_api_battles(interaction, server, battle_ids)
        api_battles_df = await db_utils.select_many_api_battles(server, battle_ids,
                                                                custom_condition=f"type = '{battle_type}'")
        await db_utils.cache_api_fights(interaction, server, api_battles_df)

        api_fights_df = await db_utils.get_api_fights_sum(server, battle_ids)
        del api_battles_df  # free memory

        output = BytesIO()
        api_fights_df.to_csv(output, index=False)

        final = defaultdict(lambda: {'hits': 0, 'damage': 0})
        top5 = {}
        for i, (citizen_id, row) in enumerate(api_fights_df.iterrows()):
            if i == 10:
                break
            api_citizen = await utils.get_content(
                f'{base_url}apiCitizenById.html?id={citizen_id}')  # TODO: cache to db
            hyperlink = f"{utils.codes(api_citizen['citizenship'])}" \
                        f" [{api_citizen['login'][:25]}]({base_url}profile.html?id={citizen_id})"
            final[hyperlink]['damage'] = row['damage']
            final[hyperlink]['hits'] = row['hits']
            if i < 5:
                top5[citizen_id] = api_citizen['login']
            await utils.custom_delay(interaction)

        hit_time_df = await db_utils.select_many_api_fights(server, battle_ids,
                                                            columns=("citizenId", "time", "damage"),
                                                            custom_condition=f"citizenId in {tuple(top5)}")
        output_buffer = generate_cup_plot(hit_time_df, top5)
        embed = Embed(colour=0x3D85C6, title=f"{server}, {start_id}-{end_id}")
        embed.add_field(name="**CS, Nick**", value="\n".join(final.keys()))
        embed.add_field(name="**Damage**", value="\n".join([f'{v["damage"]:,}' for v in final.values()]))
        embed.add_field(name="**Hits**", value="\n".join([f'{v["hits"]:,}' for v in final.values()]))
        db_dict = await utils.find_one("collection", interaction.command.name) or {}
        for cup_dict in db_dict.get(db_key, {}):
            for channel_id, data in cup_dict.items():
                output_buffer.seek(0)
                output.seek(0)
                graph = File(fp=output_buffer, filename=f"{interaction.id}.png")
                embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
                added_fields = False
                if data["nick"] and data["nick"] != "-":
                    try:
                        api = await utils.get_content(
                            f'{base_url}apiCitizenByName.html?name={data["nick"].lower()}')
                        key = f"{utils.codes(api['citizenship'])} [{api['login']}]({base_url}profile.html?id={api['id']})"
                        if key not in final:
                            i = api_fights_df.index.get_loc(api['id'])
                            embed.add_field(name="\u200B", value=f"{i}. __{key}__")
                            embed.add_field(name="\u200B", value=f'{api_fights_df.iloc[i]["damage"]:,}')
                            embed.add_field(name="\u200B", value=f'{api_fights_df.iloc[i]["hits"]:,}')
                            added_fields = True
                    except Exception:
                        pass

                try:
                    channel = bot.get_channel(int(channel_id))
                    await channel.send(embed=await utils.convert_embed(int(data["author_id"]), embed),
                                       files=[File(fp=BytesIO(output.getvalue()),
                                                   filename=f"Fighters_{server}_{start_id}-{end_id}.csv"), graph])
                except Exception as error:
                    await utils.send_error(interaction, error)
                if added_fields:
                    for _ in range(3):
                        embed.remove_field(-1)
                await sleep(0.4)

    except Exception as error:
        await utils.send_error(interaction, error)

    db_dict = await utils.find_one("collection", interaction.command.name)
    if db_key in db_dict:
        del db_dict[db_key]
        await utils.replace_one("collection", interaction.command.name, db_dict)


def generate_cup_plot(df: pd.DataFrame, names: dict) -> Optional[BytesIO]:
    names = {k: v.replace("_", "") for k, v in names.items()}  # matplotlib ignores names that starts with _
    # Calculate total_damage for each row
    df['total_damage'] = df.groupby('citizenId')['damage'].cumsum()

    # Identify the day changes (more than 12h) and plot them directly
    fig, (ax0, ax1) = plt.subplots(1, 2, sharey='all', tight_layout=True)

    has_second_day = False

    colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'gray', 'olive', 'cyan']

    for i, (citizen_id, group) in enumerate(df.groupby('citizenId')):
        color = colors[i]

        # Filter and plot points corresponding to day changes
        second_day_points = group[group['time'] - group['time'].shift() > pd.Timedelta(hours=12)]

        # Plot the first subplot (before the day change)
        if not second_day_points.empty:
            ax0.plot(group['time'][group['time'] < second_day_points.iloc[0]['time']],
                     group['total_damage'][group['time'] < second_day_points.iloc[0]['time']],
                     label=names[citizen_id], color=color)
        else:
            ax0.plot(group['time'], group['total_damage'], label=names[citizen_id], color=color)

        # Plot the second subplot (after the day change)
        if not second_day_points.empty:
            has_second_day = True
            ax1.plot(group['time'][group['time'] >= second_day_points.iloc[0]['time']],
                     group['total_damage'][group['time'] >= second_day_points.iloc[0]['time']],
                     label=names[citizen_id], color=color)

    # Use FixedFormatter with existing tick positions
    ax0.yaxis.set_major_locator(FixedLocator(ax0.get_yticks()))
    ax0.set_yticklabels([utils.human_format(x) for x in ax0.get_yticks().tolist()])

    ax0.xaxis.set_major_formatter(DateFormatter("%d-%m %H:%M"))
    ax1.xaxis.set_major_formatter(DateFormatter("%d-%m %H:%M"))

    if has_second_day:
        ax0.spines['right'].set_visible(False)
        ax1.spines['left'].set_visible(False)
        ax1.yaxis.tick_right()
    else:
        # remove ax1 and expand ax0
        fig.delaxes(ax1)
        ax0.set_subplotspec(GridSpec(1, 1)[0])

    fig.suptitle('Total Damage vs Time')
    ax0.set_ylabel('Total Damage')
    ax0.set_xlabel('Time')

    # sort legends based on tops
    lines, labels = ax0.get_legend_handles_labels()
    lines = [lines[labels.index(label)] for label in names.values()]
    labels = [labels[labels.index(label)] for label in names.values()]
    ax0.legend(lines, labels)

    fig.autofmt_xdate()

    return utils.plt_to_bytes(fig)


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
        battles = await utils.get_battles(base_url)
        if country:
            battles = [x for x in battles if
                       country.lower() in (x['defender']['name'].lower(), x['attacker']['name'].lower())]

        if not battles:
            await channel.send(
                "The program has stopped, because there are currently no active RWs or attacks in this " +
                (f"country (`{country}`)." if country else f"server (`{server}`)."))
            find_ping = await utils.find_one("collection", "ping")
            if ping_id in find_ping:
                del find_ping[ping_id]
                await utils.replace_one("collection", "ping", find_ping)
            break
        battles = sorted(battles, key=lambda k: k['time_remaining'])
        for battle_dict in battles:
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
                output_buffer = await utils.dmg_trend(hit_time, server, f'{battle_dict["battle_id"]}-{current_round}')
                hit_time.clear()
                attacker_dmg = my_dict[a_name]
                defender_dmg = my_dict[d_name]
                embed = Embed(colour=0x3D85C6, title=f"{base_url}battle.html?id={battle_dict['battle_id']}",
                              description=f"**T{t}, Score:** "
                                          f"{battle_dict['defender']['score']}:{battle_dict['attacker']['score']}\n"
                                          + (f"**Total Dmg:** {battle_dict['dmg']}" if 'dmg' in battle_dict else ''))
                embed.add_field(name=f"{utils.codes(d_name)} " + utils.shorten_country(d_name),
                                value=f"{defender_dmg:,}")
                embed.add_field(name=f"Battle type: {api_battles['type'].replace('_', ' ').title()}",
                                value=await utils.bar(defender_dmg, attacker_dmg, d_name, a_name))
                embed.add_field(name=f"{utils.codes(a_name)} " + utils.shorten_country(a_name),
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


async def watch_should_break(link: str, api_battles: dict) -> bool:
    """Returns True if link should be removed from watch dict:
        1. if battle is over
        2. if battle is frozen
        3. if battle is not in watch dict
    also updates the watch dict with the current score and sides"""

    attacker, defender = utils.get_sides(api_battles)
    should_break = True
    find_watch = await utils.find_one("collection", "watch") or {"watch": []}
    for watch_dict in list(find_watch["watch"]):
        if watch_dict["link"] != link:
            continue
        if (8 in (api_battles['defenderScore'], api_battles['attackerScore'])
                or find_watch.get("removed")
                or api_battles['frozen']):
            find_watch["watch"].remove(watch_dict)
        else:
            watch_dict["sides"] = f"{defender} vs {attacker}"
            watch_dict["score"] = f"{api_battles['defenderScore']}:{api_battles['attackerScore']}"
            should_break = False  # If not all battles are over, don't break

    await utils.replace_one("collection", "watch", find_watch)
    return should_break


async def watch_func(bot, channel: TextChannel, link: str, t: float, role: str, custom: str,
                     author_id: int = 0) -> None:
    """watch func"""
    for _ in range(20):  # Max rounds: 15, plus option for some freeze/delay
        api_battles = await utils.get_content(link.replace("battle", "apiBattles").replace("id", "battleId"))
        if await watch_should_break(link, api_battles):
            break

        for _ in range(5):  # allow 5 delays from e-sim
            h, m, s = api_battles["hoursRemaining"], api_battles["minutesRemaining"], api_battles["secondsRemaining"]
            sleep_time = h * 3600 + m * 60 + s - t * 60
            if sleep_time < 30:
                break  # If less than 30 seconds left, don't sleep again
            await sleep(max(0, sleep_time))

            # check again, in case e-sim froze the battle / delayed it
            api_battles = await utils.get_content(
                link.replace("battle", "apiBattles").replace("id", "battleId"))

        attacker, defender = utils.get_sides(api_battles)
        api_fights_link = link.replace("battle", "apiFights").replace(
            "id", "battleId") + f"&roundId={api_battles['currentRound']}"
        my_dict, hit_time = await utils.save_dmg_time(api_fights_link, attacker, defender)
        output_buffer = await utils.dmg_trend(hit_time, link.split("//")[1].split(".e-sim.org")[0],
                                              f'{link.split("=")[1].split("&")[0]}-{api_battles["currentRound"]}')
        hit_time.clear()
        msg = f"{role} {custom}"
        embed = Embed(colour=0x3D85C6,
                      title=f"T{t}, **Score:** {api_battles['defenderScore']}:{api_battles['attackerScore']}", url=link)
        embed.add_field(name=f"{utils.codes(defender)}" + utils.shorten_country(defender),
                        value=f"{my_dict[defender]:,}")
        embed.add_field(name=f'Battle type: {api_battles["type"].replace("_", " ").title()}',
                        value=await utils.bar(my_dict[defender], my_dict[attacker], defender, attacker))
        embed.add_field(name=f"{utils.codes(attacker)} " + utils.shorten_country(attacker),
                        value=f"{my_dict[attacker]:,}")
        embed.set_thumbnail(url=f"attachment://{channel.id}.png")
        embed.set_footer(text="If you want to stop watching this battle, type /unwatch")
        delete_after = api_battles["hoursRemaining"] * 3600 + api_battles["minutesRemaining"] * 60 + api_battles[
            "secondsRemaining"]

        try:
            await channel.send(msg, embed=await utils.convert_embed(author_id, embed),
                               file=File(fp=output_buffer, filename=f"{channel.id}.png"), delete_after=delete_after)
        except Exception:
            return await bot.get_command("unwatch").__call__(channel, link)
        await sleep(t * 60 + 150)


async def watch_auction_func(channel: TextChannel, link: str, t: float, custom_msg: str,
                             author_id: int = 0) -> None:
    """Activate watch/auction function"""
    row = await utils.get_auction(link)

    if row["remaining_seconds"] < 0:
        return await remove_auction(link, channel.id)

    await sleep(row["remaining_seconds"] - t * 60)
    if not row.get("removed"):
        row = await utils.get_auction(link)

        embed = Embed(colour=0x3D85C6, title=link,
                      description=f"**__Parameters__:**\n**T**: {t}\n\n**Custom msg**: " + (
                          f"{custom_msg}" if custom_msg else "None"))
        embed.add_field(name="Info", value="\n".join([f"**{k.title()}:** {v}" for k, v in row.items()]))

        embed = Embed(colour=0x3D85C6, title=link)
        embed.add_field(name="Info", value="\n".join([f"**{k.title()}:** {v}" for k, v in row.items()]))
        await channel.send(custom_msg, embed=await utils.convert_embed(author_id, embed))
    return await remove_auction(link, channel.id)


async def remove_auction(link: str, channel_id: int) -> None:
    """Removes auction"""
    find_auctions = await utils.find_one("collection", "auctions") or {"auctions": []}
    for auction_dict in list(find_auctions["auctions"]):
        if auction_dict["link"] == link and auction_dict["channel_id"] == channel_id:
            find_auctions["auctions"].remove(auction_dict)
    await utils.replace_one("collection", "auctions", find_auctions)
