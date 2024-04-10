"""Stats.py"""
import os
from collections import defaultdict
from csv import reader, writer
from datetime import date, timedelta
from io import BytesIO, StringIO
from json import loads
from time import time
from typing import Literal, Optional

import numpy as np
import pandas as pd
from discord import Attachment, File, Interaction
from discord.app_commands import Transform, check, checks, command, describe
from discord.ext.commands import Cog

from Utils import utils, db_utils
from Utils.constants import all_countries, all_countries_by_name, api_url
from Utils.transformers import BattleTypes, Ids, Server
from Utils.utils import CoolDownModified, dmg_calculator


class Stats(Cog, command_attrs={"cooldown_after_parsing": True, "ignore_extra": False}):
    """Commands That Last Forever"""

    def __init__(self, bot) -> None:
        self.bot = bot

    @staticmethod
    async def __get_achievements_link_and_last_page(regular_achievement_type: str, premium_achievement_type: str,
                                                    is_premium: bool, server: str) -> tuple[str, int]:
        """__get_achievements_link_and_last_page"""
        achievements_url = f'https://{server}.e-sim.org/achievement.html?type='
        link = f'{achievements_url}{premium_achievement_type}' if is_premium \
            else f'{achievements_url}{regular_achievement_type}'
        last_page = await utils.last_page(link)
        if last_page == 1:
            link = f'{achievements_url}{premium_achievement_type}'
            last_page = await utils.last_page(link)
        return link, last_page

    @checks.dynamic_cooldown(CoolDownModified(60))
    @command()
    @describe(at_least_10_medals="Scan all active players with at least 10 medals, instead of 100 (premium)")
    async def bhs(self, interaction: Interaction, server: Transform[str, Server],
                  at_least_10_medals: bool = False) -> None:
        """Displays top bh medals per player in a given server."""

        if at_least_10_medals and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(
                interaction, "`at_least_10_medals` is a premium parameter! If you wish to use it, along with many other"
                             " premium commands, please visit https://www.buymeacoffee.com/RipEsim"
                             "\n\nOtherwise, try again, but this time with `at_least_10_medals=False`",
                ephemeral=True)
            return
        base_url = f'https://{server}.e-sim.org/'
        link, last_page = await self.__get_achievements_link_and_last_page(
            "BH_COLLECTOR_II", "BH_COLLECTOR_I", at_least_10_medals, server)

        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File(self.bot.typing_gif_path))
        count = 0
        output = StringIO()
        csv_writer = writer(output)
        break_main = False
        for page in range(1, last_page):
            tree = await utils.get_content(f'{link}&page={page}')
            ids = utils.get_ids_from_path(tree, '//*[@id="esim-layout"]//div[3]//div/a')
            nicks = tree.xpath('//*[@id="esim-layout"]//div[3]//div/a/text()')
            for nick, user_id in zip(nicks, ids):
                if await self.bot.should_cancel(interaction, msg):
                    break_main = True
                    break
                count += 1
                msg = await utils.update_percent(count, (last_page - 2) * 24 + len(ids), msg)
                tree1 = await utils.get_content(f"{base_url}profile.html?id={user_id}")
                bh_medals = tree1.xpath("//*[@id='medals']//ul//li[7]//div")[0].text.replace("x", "")
                cs = tree1.xpath("//div[@class='profile-data']//div[8]//span[1]//span[1]")
                csv_writer.writerow([nick.strip(), cs[0].text if cs else "Unknown", bh_medals])
                await utils.custom_delay(interaction)
            if break_main:
                break

        headers = ["#", "Nick", "Citizenship", "BHs"]
        await self.__send_csv_file_and_preview(interaction, output, headers, server, link, -1)

    @staticmethod
    async def __send_csv_file_and_preview(interaction: Interaction, output: StringIO, headers: list,
                                          server: str, link: str, sort_by: int) -> None:
        """__send_csv_file_and_preview"""
        output.seek(0)
        sorted_list = sorted(reader(output), key=lambda row: int(row[sort_by]), reverse=True)
        output = StringIO()
        csv_writer = writer(output)
        csv_writer.writerow(headers)
        csv_writer.writerows([[index + 1] + row for index, row in enumerate(sorted_list)])
        output.seek(0)
        await utils.custom_followup(interaction, f'All players listed here: <{link}>', files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"{server}.csv")], mention_author=True)

    @checks.dynamic_cooldown(CoolDownModified(10))
    @command()
    @describe(ids_in_file="csv file at cells A1, A2, A3...",
              ids="separated by a comma (,)",
              extra_premium_info="True (premium) will take twice as long but will return much more data")
    async def convert(self, interaction: Interaction, server: Transform[str, Server], ids_in_file: Optional[Attachment],
                      ids: Optional[str],
                      your_input_is: Literal["citizen ids", "citizen names", "military unit ids", "citizenship ids",
                      "single MU id (get info about all MU members)"],
                      extra_premium_info: bool = False) -> None:
        """Convert ids to names and vice versa"""
        if extra_premium_info and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(
                interaction, "`extra_premium_info` is a premium parameter! If you wish to use it, "
                             "along with many other premium commands, please visit https://www.buymeacoffee.com/RipEsim"
                             "\n\nOtherwise, try again, but this time with `extra_premium_info=False`")
            return

        if not ids and not ids_in_file:
            await utils.custom_followup(
                interaction, "You must provide list/range of ids or attach a file containing the list of ids "
                             "(if there are too many)",
                ephemeral=True)
            return
        if ids is None:
            ids = []
        else:
            ids = [x.strip() for x in ids.split(",")]
        if ids_in_file:
            ids.extend([i.decode("utf-8").split(",")[0] for i in (await ids_in_file.read()).splitlines() if i])
        key = your_input_is

        if "members" in key:
            mu_embers = await utils.get_content(f'https://{server}.e-sim.org/apiMilitaryUnitMembers.html?id={ids[0]}')
            ids = [str(row["id"]) for row in mu_embers]
            link = "apiCitizenById.html?id"
            name = "login"
            header = ["Id", "Nick", "citizenship", "MU id"]

        elif "citizenship" in key:
            header = ["Citizenship"]
            name = link = ""

        elif "military unit" in key:
            link = "apiMilitaryUnitById.html?id"
            name = "name"
            header = ["Id", "Name", "Total damage", "Max members", "Gold value", "Country", "Type"]

        elif key == "citizen ids":
            link = "apiCitizenById.html?id"
            name = "login"
            header = ["Id", "Nick", "citizenship", "MU id"]

        elif key == "citizen names":
            link = "apiCitizenByName.html?name"
            name = "id"
            header = ["Nick", "ID", "citizenship", "MU id"]

        else:
            await utils.custom_followup(interaction, "Key Error", ephemeral=True)
            return

        output = StringIO()
        csv_writer = writer(output)
        if extra_premium_info:
            csv_writer.writerow(["Id", "Link", "Nick", "Citizenship", "MU Id", "Inactive Since", "ES", "XP", "Strength",
                                 "Per limit", "Per Berserk", "Crit", "Avoid", "Miss", "Dmg", "Max", "Total Dmg",
                                 "Today's dmg", "Premium till", "", "Vision", "Helmet", "Armor", "Pants", "Shoes", "LC",
                                 "WU", "Offhand", "", "Congress medal", "CP", "Train", "Inviter", "Subs", "work", "BHs",
                                 "RW", "Tester", "Tournament"])
        else:
            csv_writer.writerow(header)
        msg = await utils.custom_followup(
            interaction, "Progress status: 1%.\n(I will update you after every 10%)" if len(ids) > 10 else
            "I'm on it, Sir. Be patient.", file=File(self.bot.typing_gif_path))
        errors = []
        index = 0
        for index, current_id in enumerate(ids):
            if await self.bot.should_cancel(interaction, msg):
                break
            if "citizenship" in key:
                csv_writer.writerow([all_countries[int(current_id)]])
                continue
            if current_id == "0" or not current_id.strip():
                continue
            msg = await utils.update_percent(index, len(ids), msg)
            try:
                api = await utils.get_content(f'https://{server}.e-sim.org/{link}={current_id.lower().strip()}')
            except Exception:
                errors.append(current_id)
                continue
            if not extra_premium_info:
                if name == "name":
                    csv_writer.writerow(
                        [current_id, api[name], api["totalDamage"], api["maxMembers"], api["goldValue"],
                         all_countries[api["countryId"]],
                         api["militaryUnitType"]])
                else:
                    csv_writer.writerow(
                        [current_id, api[name], api["citizenship"], api["militaryUnitId"]])

            elif api.get('id'):
                profile_link = f'https://{server}.e-sim.org/profile.html?id={api["id"]}'
                tree = await utils.get_content(profile_link)

                if api['status'] == "inactive":
                    days_number = [x.split()[-2] for x in tree.xpath('//*[@class="profile-data red"]/text()') if
                                   "This citizen has been inactive for" in x][0]
                    status = str(date.today() - timedelta(days=int(days_number)))
                elif api['status'] == "active":
                    status = ""
                else:
                    status = api['status']
                if api['premiumDays'] > 0:
                    premium = date.today() + timedelta(days=int(api['premiumDays']))
                else:
                    premium = ""
                eqs = []
                for quality in tree.xpath("//div[1]//div[2]//div[5]//tr//td[2]//div[1]//div[1]//@class"):
                    if "equipmentBack" in quality:
                        quality = quality.replace("equipmentBack q", "")
                        eqs.append(quality)
                medals1 = []
                for i in range(1, 11):
                    a = tree.xpath(f"//*[@id='medals']//ul//li[{i}]//div//text()")
                    if a:
                        medals1.append(*[x.replace("x", "") for x in a])
                    elif "emptyMedal" not in tree.xpath(f"//*[@id='medals']//ul//li[{i}]/img/@src")[0]:
                        medals1.append("1")
                    else:
                        medals1.append(0)
                strength = api['strength']
                dmg = await dmg_calculator(api=api)
                stats = {"crit": 12.5, "avoid": 5, "miss": 12.5, "damage": 0, "max": 0}
                for eq_type, parameters, values, _ in utils.get_eqs(tree):
                    for val, p in zip(values, parameters):
                        if p in stats:
                            stats[p] += (val if p != "miss" else -val)
                stats = [round(v, 2) for v in stats.values()]
                row = [api['id'], profile_link, api['login'], api['citizenship'], api['militaryUnitId'] or "", status,
                       round(api['economySkill'], 2), api['xp'], strength, dmg["avoid"], dmg["clutch"]] + stats + [
                          api['totalDamage'] - api['damageToday'], api['damageToday'], premium, ""] + eqs + [
                          ""] + medals1
                csv_writer.writerow(row)
            await utils.custom_delay(interaction)
        output.seek(0)
        if errors:
            await utils.custom_followup(interaction, f"Couldn't convert the following: {', '.join(errors)}")
        msg = "For duplicated values, use the following excel formula: `=FILTER(A:G, COUNTIF(I2, A:A))`, where `A:G`" \
              " is the range of values in the file bellow, `I2` is the cell containing the id, and `A:A`" \
              " is the column with all ids.\nExample: <https://prnt.sc/12w4p3m> Result: <https://prnt.sc/12w4qgs>"
        await utils.custom_followup(interaction, msg, mention_author=index > 30, files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"Converted_{key}_{server}.csv")])

    @checks.dynamic_cooldown(CoolDownModified(20))
    @command(name="dmg-stats")
    @describe(battle_ids="first-last or id1, id2, id3...",
              included_countries="Example: 'Norway, Israel VS Egypt' - "
                                 "all battles of norway plus all battles of (Israel VS Egypt)",
              battles_types="Check those types only (default: RWs and attacks)",
              fast_server="used for medkits estimation")
    #         extra_premium_info="True (premium) will give more data, but it will take much longer")
    # @check(utils.is_premium_level_1)
    async def dmg_stats(self, interaction: Interaction, server: Transform[str, Server],
                        battle_ids: Transform[list, Ids],
                        included_countries: Optional[str], battles_types: Optional[Transform[list, BattleTypes]],
                        fast_server: bool = None) -> None:
        """Displays a lot of data about the given battles"""
        # Calculated stats:
        # - For each player: dmg, medkits used, Clutches, BHs, Q0-Q5 weps, Best dmg in 1 battle, Best dmg in 1 round, Best hit
        # - For each date, country, MU, side and battle: total dmg, Q0-Q5 weps
        # - For each country: battles won, battles lost
        # - For each player and day: restores used, average per day, median, max

        if not await utils.is_premium_level_1(interaction, False) and len(battle_ids) > 500:
            await utils.custom_followup(
                interaction, "It's too much.. sorry. You can buy premium and remove this limit.", ephemeral=True)
            return

        base_url = f'https://{server}.e-sim.org/'

        def get_where_dmg_stats() -> str:
            exact_sides = []  # list of tuples
            any_side = []  # list of ids (ints)
            for battles_to_include in (included_countries or "").split(","):
                if "vs" in battles_to_include:
                    # append tuple of the 2 sides around "vs":
                    exact_sides.append(tuple(all_countries_by_name[country.strip().lower()] for country in
                                             battles_to_include.split("vs")))
                elif battles_to_include:
                    any_side.append(all_countries_by_name[battles_to_include.strip().lower()])

            # (defenderId, attacker_id) IN ((sides[0], sides[1]), (sides[1], sides[0]))
            reversed_sides: list[tuple] = [tuple(reversed(side)) for side in exact_sides]
            str_exact_sides = f"{','.join(map(str, exact_sides))},{','.join(map(str, reversed_sides))}"
            exact_side_condition = f"((defenderId, attackerId) IN ({str_exact_sides}))"
            any_side_condition = f"(defenderId IN {','.join(any_side)} OR attackerId IN {','.join(any_side)})"
            if exact_sides and any_side:
                where = f"({exact_side_condition} OR {any_side_condition})"
            elif exact_sides:
                where = exact_side_condition
            elif any_side:
                where = any_side_condition
            else:
                where = "TRUE"

            if battles_types:
                where += f" AND (type IN {battles_types})"
            return where

        await db_utils.cache_api_battles(interaction, server, battle_ids)
        where = get_where_dmg_stats()
        api_battles_df = await db_utils.select_many_api_battles(server, battle_ids, custom_condition=where)
        restore_battles_types = ('COUNTRY_TOURNAMENT', 'CUP_EVENT_BATTLE',
                                 'MILITARY_UNIT_CUP_EVENT_BATTLE', 'TEAM_TOURNAMENT')
        api_battles_df["is_restore_battle"] = api_battles_df["type"].isin(restore_battles_types)
        await db_utils.cache_api_fights(interaction, server, api_battles_df)
        api_fights_df = await db_utils.select_many_api_fights(server, battle_ids)

        side_dmg = api_fights_df.groupby(['battle_id', 'round_id', 'defenderSide'])['damage'].sum().unstack().fillna(
            0).rename_axis(None, axis=1)

        # Group by the specified columns and sum the damage for each player
        player_damage_per_round = api_fights_df.groupby(['citizenId', 'battle_id', 'round_id', 'defenderSide'])[
            'damage'].sum()

        # Calculate how many times the player was the best damage dealer in a round for each side
        bhs_count = player_damage_per_round.groupby(['battle_id', 'round_id', 'defenderSide']).idxmax().apply(
            lambda x: x[0]).value_counts().fillna(0)

        # Calculate how many times the round would have been lost without the player.
        #  (side_dmg > other_side_dmg AND (side_dmg - player_dmg_in_that_round) < other_side_dmg ?)
        unstacked_player = player_damage_per_round.unstack().fillna(0).rename_axis(None, axis=1)
        clutches_defender = (side_dmg[0] > side_dmg[1]) & (((side_dmg[0] - unstacked_player[0]) - side_dmg[1]) < 0)
        clutches_attacker = (side_dmg[1] > side_dmg[0]) & (((side_dmg[1] - unstacked_player[1]) - side_dmg[0]) < 0)
        # TODO: remove events?
        # Sum per citizen (clutches is a series with index (battle_id, round_id, citizenId) and value True/False)
        clutches_count = clutches_defender.groupby('citizenId').sum() + clutches_attacker.groupby('citizenId').sum()

        def get_sum_df(df: pd.DataFrame, column: str):
            """Returns df with the following columns:
            index, `column`, 'damage', 'Q0 weps', 'Q1 weps', 'Q2 weps', 'Q3 weps', 'Q4 weps', 'Q5 weps'
            """
            if 'hits' not in df.columns:
                df['hits'] = df['berserk'].apply(lambda x: 5 if x else 1)

            weps_count = df.groupby([column, 'weapon'])['hits'].sum().unstack(fill_value=0)
            result_df = df.groupby(column)['damage'].sum().to_frame().sort_values('damage', ascending=False)
            for wep_q in range(6):
                if wep_q in weps_count.columns:
                    result_df[f'Q{wep_q} weps'] = weps_count[wep_q]
            return result_df

        player_sum_df = get_sum_df(api_fights_df, 'citizenId')

        best_damage_battle = api_fights_df.groupby(['citizenId', 'battle_id'])['damage'].sum().groupby(
            'citizenId').max()
        best_damage_round = api_fights_df.groupby(['citizenId', 'battle_id', 'round_id'])['damage'].sum().groupby(
            'citizenId').max()
        best_single_hit = api_fights_df.groupby('citizenId')['damage'].max().groupby('citizenId').max()

        player_stats = pd.DataFrame({
            'Clutches': clutches_count,
            'BHs': bhs_count,
            'Damage record in single battle': best_damage_battle,
            'Damage record in single round': best_damage_round,
            'Single hit record': best_single_hit
        }).join(player_sum_df).sort_values(by='damage', ascending=False)

        battle_stats = api_fights_df.merge(api_battles_df, on='battle_id', how='left')
        battle_stats['date'] = battle_stats['time'].dt.date

        date_df = get_sum_df(battle_stats, 'date')
        country_df = get_sum_df(battle_stats, 'citizenship')
        mu_df = get_sum_df(battle_stats, 'militaryUnit')
        defender_df = get_sum_df(battle_stats, 'defenderId')
        attacker_df = get_sum_df(battle_stats, 'attackerId')
        side_df = defender_df.add(attacker_df, fill_value=0)
        side_df.index.name = 'Side'

        battle_df = get_sum_df(battle_stats, 'battle_id')
        battle_df['defenderId'] = api_battles_df.set_index('battle_id').loc[battle_df.index]['defenderId'].values
        battle_df['attackerId'] = api_battles_df.set_index('battle_id').loc[battle_df.index]['attackerId'].values
        # reorder cols, so that defenderId and attackerId are next to battle_id
        cols = battle_df.columns.tolist()
        battle_df = battle_df[cols[:1] + cols[-2:] + cols[1:-2]]
        battle_df.index = battle_df.index.map(lambda x: f"{base_url}battleStatistics.html?id={x}")
        battle_df.index.name = 'Battle Link'


        # get number of battles won and lost by each country
        # (country in defenderId and defenderScore == 8) or (country in attackerId and attackerScore == 8)
        # TODO: skip events?
        scores_df = api_battles_df[['defenderId', 'attackerId', 'defenderScore', 'attackerScore']]
        country_ids = pd.concat([scores_df['attackerId'], scores_df['defenderId']]).unique()
        countries_df = pd.DataFrame(index=country_ids, columns=['won', 'lost'], data=0)
        countries_df.index.name = 'Country'
        for idx, row in scores_df.iterrows():
            if row['attackerScore'] == 8:
                countries_df.at[row['attackerId'], 'won'] += 1
                countries_df.at[row['defenderId'], 'lost'] += 1
            elif row['defenderScore'] == 8:
                countries_df.at[row['defenderId'], 'won'] += 1
                countries_df.at[row['attackerId'], 'lost'] += 1

        # Each player has 32 daily limit. With each limit he can hit 1 berserk, or 5 non berserks. He has 40% chance to not lose a limit while hitting.
        # Every 10 minutes (or every day in some servers), the player get 2 limits, up to 32. This is called a restore.
        # In restore_battle, the player gets extra 22 limits per round, but only if he dealt 30 hits before that round.
        # If the player used all his limits plus some more, it means he opened a medkit, which gives him 20 limits.
        #
        # The goal is to calculate total medkits used per player, and total restores the player participated in every day
        #   (i.e. number of times per day that he hit at least 1 hit in 10 minutes windows [00:00-00:10, 00:10-00:20, ...])
        # TODO: rewrite this
        player_dict = defaultdict(lambda: {'limits': 0, 'medkits': 0,
                                           'last_hit': pd.Timestamp("2000-01-01"),
                                           'restores': {}})
        battles = api_battles_df[['battle_id', 'type', 'is_restore_battle']]
        days = []
        seconds_in_10_minutes = 10 * 60
        health_limits = limits_per_restore = 2
        full_limits = 15 + 15 + health_limits
        medkit_limits = 10 + 10
        avoid = 0.4
        hits_per_limit = 5
        threshold = -10
        slow_servers = ("primera", "secura", "suna")
        for battle_id, battle_type, is_restore_battle in battles.itertuples(index=False, name=None):
            # Extract relevant data for the current battle
            battle_data = api_fights_df[api_fights_df['battle_id'] == battle_id]
            for hit in battle_data.itertuples(index=False):
                key = hit.citizenId
                user = player_dict[key]
                seconds_from_last = (utils.get_time(hit.time, floor_to_10=True) -
                                     utils.get_time(user['last_hit'], floor_to_10=True)).total_seconds()

                day_month_year = hit.time.strftime("%d-%m-%Y")
                if user['last_hit'].strftime("%d-%m-%Y") != day_month_year:  # day change
                    user['limits'] = full_limits
                    if day_month_year not in days:
                        days.append(day_month_year)
                if seconds_from_last > 0:
                    if day_month_year not in user['restores']:
                        user['restores'][day_month_year] = 0
                    user['restores'][day_month_year] += 1
                    # fast server has limits restore, but sometimes also slow servers have it.
                    if fast_server or (fast_server is None and server not in slow_servers):
                        user['limits'] = min(user['limits'] + np.floor(seconds_from_last / seconds_in_10_minutes)
                                             * limits_per_restore + health_limits, full_limits)
                if is_restore_battle and user.get("has_restore"):
                    user['limits'] = medkit_limits + health_limits
                    user["has_restore"] = False
                user['limits'] -= hit.hits / (1 - avoid) / hits_per_limit
                if user['limits'] < threshold:
                    user['medkits'] += 1
                    user['limits'] += medkit_limits
                user['last_hit'] = hit.time

            # Calculate for each player if he participated in a restore battle with at least 30 hits
            restores = battle_data.groupby('citizenId').apply(
                lambda x: is_restore_battle & (x['hits'].sum() >= 30), include_groups=False).reset_index(
                name='has_restore')

            # Update player_dict with restores
            for row in restores.itertuples(index=False):
                player_dict[row.citizenId]['has_restore'] = row.has_restore

        # Write the data to csv

        player_stats_buffer = StringIO()
        player_stats = player_stats.reset_index().rename(columns={'index': 'citizenId'})
        player_stats = player_stats.merge(pd.DataFrame(player_dict).T, left_on='citizenId', right_index=True,
                                          how='left')
        columns_to_drop = ['limits', 'last_hit', 'restores', 'has_restore']
        player_stats.rename(columns={'medkits': 'Medkits used (rough estimation)'}).drop(
            columns=columns_to_drop).to_csv(player_stats_buffer, index=False, lineterminator='\n')

        battle_stats_buffer = StringIO()

        # Convert country ids to country names
        countries_columns = ('citizenship', 'Side', 'Country', 'defenderId', 'attackerId')
        for df in (country_df, side_df, defender_df, attacker_df):
            if df.index.name in countries_columns:
                df.index = df.index.map(all_countries)
            for col in df.columns:
                if col in countries_columns:
                    df[col] = df[col].map(all_countries)

        date_df.to_csv(battle_stats_buffer, lineterminator='\n')
        battle_stats_buffer.write("\n\n")
        country_df.to_csv(battle_stats_buffer, mode='a', lineterminator='\n')
        battle_stats_buffer.write("\n\n")
        mu_df.to_csv(battle_stats_buffer, mode='a', lineterminator='\n')
        battle_stats_buffer.write("\n\n")
        side_df.to_csv(battle_stats_buffer, mode='a', lineterminator='\n')
        battle_stats_buffer.write("\n\n")
        battle_df.to_csv(battle_stats_buffer, mode='a', lineterminator='\n')
        battle_stats_buffer.write("\n\n")

        countries_df["won %"] = round(countries_df["won"] / (countries_df["won"] + countries_df["lost"]) * 100, 2)
        countries_df["lost %"] = round(countries_df["lost"] / (countries_df["won"] + countries_df["lost"]) * 100, 2)
        countries_df.sort_values("won", ascending=False).to_csv(battle_stats_buffer, mode='a', lineterminator='\n')

        restores_per_day_buffer = StringIO()
        restores_per_day = player_stats[['citizenId', 'restores']].set_index('citizenId')['restores'].apply(pd.Series)
        restores_per_day["Average Per Day"] = restores_per_day.mean(axis=1)
        restores_per_day["Median"] = restores_per_day.median(axis=1)
        restores_per_day["Max"] = restores_per_day.max(axis=1)
        restores_per_day.to_csv(restores_per_day_buffer, lineterminator='\n')

        player_stats_buffer.seek(0)
        battle_stats_buffer.seek(0)
        restores_per_day_buffer.seek(0)

        battles_range = f"{battle_ids[0]}_{battle_ids[-1]}" if len(battle_ids) > 1 else battle_ids[0]
        await utils.custom_followup(interaction, mention_author=len(battle_ids) > 50, files=[
            File(fp=await utils.csv_to_image(player_stats_buffer), filename=f"Preview_{server}.png"),
            File(fp=await utils.csv_to_image(battle_stats_buffer), filename=f"Preview1_{server}.png"),
            File(fp=await utils.csv_to_image(restores_per_day_buffer), filename=f"Preview2_{server}.png"),
            File(fp=BytesIO(player_stats_buffer.getvalue().encode()),
                 filename=f"PlayersStats_{battles_range}_{server}.csv"),
            File(fp=BytesIO(battle_stats_buffer.getvalue().encode()),
                 filename=f"BattleStats_{battles_range}_{server}.csv"),
            File(fp=BytesIO(restores_per_day_buffer.getvalue().encode()),
                 filename=f"RestoresStats_{battles_range}_{server}.csv")])

    @command(name="drops-stats")
    @check(utils.is_premium_level_1)
    @describe(battles="first-last or id1, id2, id3...")
    async def drops_stats(self, interaction: Interaction, server: Transform[str, Server],
                          battles: Transform[list, Ids]) -> None:
        """Shows drops distribution per player in the given battles."""

        msg = await utils.custom_followup(interaction,
                                          "Progress status: 1%.\n(I will update you after every 10%)" if len(
                                              battles) > 10 else "I'm on it, Sir. Be patient.",
                                          file=File(self.bot.typing_gif_path))

        base_url = f'https://{server}.e-sim.org/'
        lucky = False
        index = current_id = 0
        filename = os.path.join(self.bot.root, f"temp_files/{time()}.csv")
        f = open(filename, "w", newline="")
        csv_writer = writer(f)
        for index, current_id in enumerate(battles):
            my_dict = defaultdict(lambda: {"Q": [0, 0, 0, 0, 0, 0]})
            try:
                if await self.bot.should_cancel(interaction, msg):
                    break
                msg = await utils.update_percent(index, len(battles), msg)
                battle_link = f'{base_url}battleDrops.html?id={current_id}'
                last_page = await utils.last_page(battle_link)
                for page in range(1, last_page):
                    tree = await utils.get_content(battle_link + f'&page={page}')
                    qualities = tree.xpath("//tr[position()>1]//td[2]/text()")
                    items = [x.strip() for x in tree.xpath("//tr[position()>1]//td[3]/text()")]
                    nicks = [x.strip() for x in tree.xpath("//tr[position()>1]//td[4]//a/text()")]
                    links = [f"{base_url}battle.html?id={x}" for x in
                             utils.get_ids_from_path(tree, "//tr[position()>1]//td[4]//a")]
                    for nick, link, quality, item in zip(nicks, links, qualities, items):
                        my_dict[(nick, link)]["Q"][int(quality.replace("Q", "")) - 1] += 1
                        if item == "Lucky charm":
                            lucky = True
                            if "LC" not in my_dict[(nick, link)]:
                                my_dict[(nick, link)]["LC"] = [0, 0, 0, 0, 0, 0]
                            my_dict[(nick, link)]["LC"][int(quality.replace("Q", "")) - 1] += 1
                for si_type in ("EQUIPMENT_PARAMETER_UPGRADE", "EQUIPMENT_PARAMETER_RESHUFFLE"):
                    battle_link = f'{base_url}battleDrops.html?id={current_id}&showSpecialItems=yes&siType={si_type}'
                    last_page = await utils.last_page(battle_link)
                    for page in range(1, last_page):
                        tree = await utils.get_content(battle_link + f'&page={page}')
                        nicks = [x.strip() for x in tree.xpath("//tr[position()>1]//td[2]//a/text()")]
                        links = [f"{base_url}battle.html?id={x}" for x in
                                 utils.get_ids_from_path(tree, "//tr[position()>1]//td[2]//a")]
                        items = [x.strip() for x in tree.xpath("//tr[position()>1]//td[1]//text()") if x.strip()]
                        for nick, link, item in zip(nicks, links, items):
                            key = item.replace("Equipment parameter ", "")
                            if key not in my_dict[(nick, link)]:
                                my_dict[(nick, link)][key] = 0  # noqa E226
                            my_dict[(nick, link)][key] += 1
            except Exception as error:
                await utils.send_error(interaction, error, current_id)
                break
            for k, v in my_dict.items():
                row = list(k) + [x or "0" for x in v["Q"]] + [
                    v.get("upgrade", "0"), v.get("reshuffle", "0")] + v.get("LC", [])
                csv_writer.writerow(row)
            await utils.custom_delay(interaction)
        f.close()
        headers = ["Nick", "Link", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Upgrade", "Reshuffle"]
        if lucky:
            headers += ["Q1 LC", "Q2 LC", "Q3 LC", "Q4 LC", "Q5 LC", "Q6 LC"]
        my_dict = {}
        with open(filename, 'r') as csvfile:
            for row in reader(csvfile):
                nick = (row[0], row[1])
                if nick not in my_dict:
                    my_dict[nick] = [0] * (len(headers) - 2)
                for i in range(len(headers) - 2):
                    try:
                        if row[i + 2]:
                            my_dict[nick][i] += int(row[i + 2])
                    except IndexError:
                        pass

        with open(filename, 'w', newline='') as csvfile:
            csv_writer = writer(csvfile)
            csv_writer.writerow(headers)
            for nick, row in my_dict.items():
                csv_writer.writerow(list(nick) + [str(x) if x else "" for x in row])
        if my_dict:
            await utils.custom_followup(interaction, mention_author=index > 100, file=File(
                filename, filename=f"Drops_{battles[0]}_{current_id}_{server}.csv"))
        else:
            await utils.custom_followup(interaction, "No drops were found")
        os.remove(filename)

    @checks.dynamic_cooldown(CoolDownModified(60))
    @command()
    @describe(server="You can see you score using /calc with bonuses=as new player",
              scan_more_players="True (premium) - all players with EQUIPPED_V achievement, otherwise - LEGENDARY_EQUIPMENT")
    async def sets(self, interaction: Interaction, server: Transform[str, Server],
                   scan_more_players: bool = False) -> None:
        """Displays top avoid and clutch sets per player in a given server."""

        if scan_more_players and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(
                interaction, "`scan_more_players` is a premium parameter! If you wish to use it, "
                             "along with many other premium commands, please visit https://www.buymeacoffee.com/RipEsim"
                             "\n\nOtherwise, try again, but this time with `scan_more_players=False`", ephemeral=True)
            return

        base_url = f'https://{server}.e-sim.org/'
        output = StringIO()
        csv_writer = writer(output)
        link, last_page = await self.__get_achievements_link_and_last_page(
            "LEGENDARY_EQUIPMENT", "EQUIPPED_V", scan_more_players, server)
        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File(self.bot.typing_gif_path))
        count = 0
        for page in range(1, last_page):
            tree = await utils.get_content(f'{link}&page={page}')
            links = utils.get_ids_from_path(tree, '//*[@id="esim-layout"]//div[3]//div/a')
            for user_id in links:
                count += 1
                msg = await utils.update_percent(count, (last_page - 2) * 24 + len(links), msg)
                api = await utils.get_content(f"{base_url}apiCitizenById.html?id={user_id}")
                dmg = await dmg_calculator(api)
                csv_writer.writerow([api["login"], api['citizenship'], api['eqCriticalHit'], api['eqReduceMiss'],
                                     api['eqAvoidDamage'], api['eqIncreaseMaxDamage'], api['eqIncreaseDamage'],
                                     dmg["avoid"], dmg["clutch"], api['eqIncreaseEcoSkill']])
                await utils.custom_delay(interaction)

        headers = ["#", "Nick", "Citizenship", "Crit", "Miss", "Avoid", "Max", "Dmg", "Per limit", "Per berserk", "Eco"]
        await self.__send_csv_file_and_preview(interaction, output, headers, server, link, -3)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(custom_api="API containing simple json (single dictionary or single list)")
    async def table(self, interaction: Interaction, server: Transform[str, Server], custom_api: str = "") -> None:
        """Converts simple json to csv table."""
        if custom_api and "http" not in custom_api:
            await utils.custom_followup(interaction, f"{custom_api} is not a valid link", ephemeral=True)
            return
        if ".e-sim.org/battle.html?id=" in custom_api:
            if "round" in custom_api:
                custom_api = custom_api.replace("battle", "apiFights").replace("id", "battleId").replace("round",
                                                                                                         "roundId")
            else:
                custom_api = custom_api.replace("battle", "apiBattles").replace("id", "battleId")
        if ".e-sim.org/" in custom_api and not custom_api.startswith(api_url) and "api" not in custom_api:
            custom_api = api_url + custom_api.replace("//", "/")
        files = []
        base_url = f"https://{server}.e-sim.org/"
        links = ["apiRegions", "apiMap", "apiRanks", "apiCountries", "apiOnlinePlayers"]
        for link in links if not custom_api else [custom_api]:
            api: list[str or dict] or dict = await utils.get_content(
                (base_url + link + ".html") if not custom_api else custom_api, return_type="json", throw=True)
            if link == "apiOnlinePlayers":
                api = [loads(row) for row in api]
            if not api:
                await utils.custom_followup(interaction, "Nothing found.")
                return
            if not isinstance(api, list):
                api = [api]
            lists_headers = [k for k, v in api[0].items() if isinstance(v, list)]
            headers = [k for k, v in api[0].items() if not isinstance(v, list)]
            headers = await update_missing_keys(link, headers)
            output = StringIO()
            csv_writer = writer(output)
            csv_writer.writerow(headers)
            for row in api:
                csv_writer.writerow([row.get(header, "") for header in headers])

                for header in lists_headers:
                    value = row.get(header)
                    if not value:
                        continue
                    if not isinstance(value[0], dict):
                        csv_writer.writerow([header])
                        csv_writer.writerow(value)
                        continue

                    inner_headers = list(value[0].keys())
                    csv_writer.writerow([])
                    csv_writer.writerow([header])
                    if len(inner_headers) < 10:
                        csv_writer.writerow(inner_headers)
                        for inner_row in value:
                            csv_writer.writerow([inner_row.get(inner_header, "") for inner_header in inner_headers])
                    else:
                        for inner_row in value:
                            csv_writer.writerows(
                                [(inner_header, inner_row.get(inner_header, "")) for inner_header in inner_headers])
                    csv_writer.writerow([])

            output.seek(0)
            files.append(File(fp=BytesIO(output.getvalue().encode()), filename=f"{link}_{server}.csv"))
            await utils.custom_delay(interaction)

        await utils.custom_followup(interaction, files=files)


async def update_missing_keys(link: str, headers: list) -> list:
    """update missing keys"""
    missing = {'apiRegions': ['resource'], 'apiMap': ['battleId', 'raw'], 'apiCountries': ['president'],
               'apiMilitaryUnitMembers': ['companyId'],
               'apiFights': ['dsQuality', 'militaryUnitBonus', 'localizationBonus', 'militaryUnit']}
    for k, v in missing.items():
        if k in link:
            for key in v:
                if key not in headers:
                    headers.append(key)
    return headers


async def setup(bot) -> None:
    """Setup"""
    await bot.add_cog(Stats(bot))
