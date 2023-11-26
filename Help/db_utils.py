from datetime import datetime

import asyncmy
import pandas as pd
from discord import Interaction

from bot.bot import bot

from .utils import custom_delay, get_content

api_battles_columns = ('battle_id', 'currentRound', 'attackerScore', 'regionId', 'defenderScore',
                       'frozen', 'type', 'defenderId', 'attackerId', 'totalSecondsRemaining')
api_fights_columns = ('battle_id', 'round_id', 'damage', 'weapon', 'berserk', 'defenderSide', 'citizenship',
                      'citizenId', 'time', 'militaryUnit')


async def execute_query(pool: asyncmy.Pool, query: str, params=None, many=False, fetch=False) -> list:
    async with pool.acquire() as connection:
        async with connection.cursor() as cursor:
            if many:
                await cursor.executemany(query, params)
            else:
                await cursor.execute(query, params)
            if fetch:
                return await cursor.fetchall()


async def cache_api_battles(interaction: Interaction, server: str, battle_ids: iter) -> None:
    """Verify all battles are in db, if not, insert them"""
    start_id, end_id = min(battle_ids), max(battle_ids)
    excluded_ids = ",".join(str(i) for i in range(start_id, end_id + 1) if i not in battle_ids)
    query = f"SELECT battle_id FROM {server}.apiBattles " \
            f"WHERE (battle_id BETWEEN {start_id} AND {end_id}) " + \
            (f"AND battle_id NOT IN ({excluded_ids})" if excluded_ids else "") + \
            " AND (defenderScore = 8 OR attackerScore = 8)"

    existing_battles = [x[0] for x in await execute_query(bot.pool, query, fetch=True)]  # x[0] = battle_id

    for battle_id in battle_ids:
        if battle_id not in existing_battles:
            await insert_into_api_battles(server, battle_id)
            await custom_delay(interaction)


async def insert_into_api_battles(server: str, battle_id: int) -> dict:
    """insert_into_api_battles"""
    api_battles = await get_content(f'https://{server}.e-sim.org/apiBattles.html?battleId={battle_id}')
    api_battles['totalSecondsRemaining'] = (api_battles["hoursRemaining"] * 3600 +
                                            api_battles["minutesRemaining"] * 60 + api_battles["secondsRemaining"])
    api_battles['battle_id'] = battle_id
    filtered_api_battles = {k: api_battles[k] for k in api_battles_columns}

    placeholders = ', '.join(['%s'] * len(filtered_api_battles))
    query = f"REPLACE INTO {server}.apiBattles VALUES ({placeholders})"
    await execute_query(bot.pool, query, tuple(filtered_api_battles.values()))

    return filtered_api_battles


async def select_many_api_battles(server: str, battle_ids: iter, columns: tuple = None,
                                  custom_condition: str = None) -> pd.DataFrame:
    columns = columns or api_battles_columns
    start_id, end_id = min(battle_ids), max(battle_ids)
    excluded_ids = ",".join(str(i) for i in range(start_id, end_id + 1) if i not in battle_ids)
    query = f"SELECT {', '.join(columns)} FROM {server}.apiBattles " \
            f"WHERE (battle_id BETWEEN {start_id} AND {end_id}) " + \
            (f"AND battle_id NOT IN ({excluded_ids}) " if excluded_ids else "") + \
            ("" if not custom_condition else f"AND {custom_condition}")

    api_battles = await execute_query(bot.pool, query, fetch=True)
    return pd.DataFrame(api_battles, columns=list(columns), index=[x[0] for x in api_battles])


async def select_one_api_battles(server: str, battle_id: int, columns: tuple = None) -> dict:
    columns = columns or api_battles_columns
    # TODO: ensure columns contains defenderScore and attackerScore or add them
    query = f"SELECT {', '.join(columns)} FROM {server}.apiBattles WHERE battle_id = {battle_id} LIMIT 1"
    r = await execute_query(bot.pool, query, fetch=True)
    r = dict(zip(columns, r[0])) if r else {}
    if not r or 8 not in (r['defenderScore'], r['attackerScore']):
        r = await insert_into_api_battles(server, battle_id)
    return r


async def insert_into_api_fights(server: str, battle_id: int, round_id: int) -> None:
    """insert_into_api_fights"""
    api_fights = await get_content(f'https://{server}.e-sim.org/apiFights.html?battleId={battle_id}&roundId={round_id}')
    if not api_fights:
        # insert dummy hit to avoid rechecking this round
        api_fights = [{'damage': 0, 'weapon': 0, 'berserk': False, 'defenderSide': False, 'citizenship': None,
                       'citizenId': 0, 'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[
                                               :-3]}]  # TODO: Will those values cause problems?
    # time can be %d-%m-%Y %H:%M:%S:%f or %Y-%m-%d %H:%M:%S:%f or %Y-%m-%d %H:%M:%S.%f or %Y-%m-%d %H:%M:%S
    # so we should replace last : with . if the count of : is 3
    api_fights = [(battle_id, round_id, hit['damage'], hit['weapon'], hit['berserk'], hit['defenderSide'],
                   hit['citizenship'], hit['citizenId'],
                   ".".join(hit["time"].strip().rsplit(":", 1)) if hit["time"].count(":") == 3 else hit["time"].strip(),
                   hit.get('militaryUnit')) for hit in reversed(api_fights)]

    placeholders = ', '.join(['%s'] * len(api_fights[0]))
    query = f"INSERT IGNORE INTO {server}.apiFights VALUES ({placeholders})"
    await execute_query(bot.pool, query, api_fights, many=True)


async def cache_api_fights(interaction: Interaction, server: str, api_battles_df: pd.DataFrame) -> None:
    """Verify all fights are in db, if not, insert them"""
    # get last inserted round per battle:
    start_id, end_id = min(api_battles_df["battle_id"].values), max(api_battles_df["battle_id"].values)
    excluded_ids = ",".join(str(i) for i in range(start_id, end_id + 1) if i not in api_battles_df["battle_id"].values)

    query = f"SELECT battle_id, MAX(round_id) FROM {server}.apiFights " + \
            f"WHERE (battle_id BETWEEN {start_id} AND {end_id}) " + \
            (f"AND battle_id NOT IN ({excluded_ids}) " if excluded_ids else "") + \
            f"GROUP BY battle_id"
    last_round_per_battle = {x[0]: x[1] for x in await execute_query(bot.pool, query, fetch=True)}

    for i, api in api_battles_df.iterrows():
        current_round = api["currentRound"]
        if 8 in (api['defenderScore'], api['attackerScore']):
            last_round = current_round
        else:
            last_round = current_round + 1
        for round_id in range(last_round_per_battle.get(api["battle_id"], 0) + 1, last_round):
            await insert_into_api_fights(server, int(api["battle_id"]), round_id)
            await custom_delay(interaction)


async def select_many_api_fights(server: str, battle_ids: iter, columns: tuple = None,
                                 custom_condition: str = None) -> pd.DataFrame:
    columns = columns or api_fights_columns
    start_id, end_id = min(battle_ids), max(battle_ids)
    excluded_ids = ",".join(str(i) for i in range(start_id, end_id + 1) if i not in battle_ids)

    query = f"SELECT {', '.join(columns)} FROM {server}.apiFights " \
            f"WHERE (battle_id BETWEEN {start_id} AND {end_id}) " + \
            (f"AND battle_id NOT IN ({excluded_ids}) " if excluded_ids else "") + \
            ("" if not custom_condition else f"AND {custom_condition}")

    api_fights = await execute_query(bot.pool, query, fetch=True)
    return pd.DataFrame(api_fights, columns=list(columns))


async def get_api_fights_sum(server: str, battle_ids: iter) -> pd.DataFrame:
    start_id, end_id = min(battle_ids), max(battle_ids)
    excluded_ids = ",".join(str(i) for i in range(start_id, end_id + 1) if i not in battle_ids)
    query = ("SELECT citizenId, SUM(damage) AS damage, "
             f"SUM(IF(weapon = 0, IF(berserk, 5, 1), 0)) AS Q0, "
             f"SUM(IF(weapon = 1, IF(berserk, 5, 1), 0)) AS Q1, "
             f"SUM(IF(weapon = 2, IF(berserk, 5, 1), 0)) AS Q2, "
             f"SUM(IF(weapon = 3, IF(berserk, 5, 1), 0)) AS Q3, "
             f"SUM(IF(weapon = 4, IF(berserk, 5, 1), 0)) AS Q4, "
             f"SUM(IF(weapon = 5, IF(berserk, 5, 1), 0)) AS Q5, "
             "SUM(IF(berserk, 5, 1)) AS hits "
             f"FROM {server}.apiFights WHERE (battle_id BETWEEN {start_id} AND {end_id}) " +
             (f"AND battle_id NOT IN ({excluded_ids}) " if excluded_ids else "") +
             "GROUP BY citizenId "
             "ORDER BY damage DESC "  # TODO: parameter
             )

    api_fights = await execute_query(bot.pool, query, fetch=True)
    columns = ["citizenId", "damage", "Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "hits"]
    return pd.DataFrame(api_fights, columns=columns, index=[x[0] for x in api_fights])


async def select_one_api_fights(server: str, api: dict, round_id: int = 0) -> pd.DataFrame:
    # TODO: rewrite
    columns = ['battle_id', 'round_id', 'damage', 'weapon', 'berserk', 'defenderSide', 'citizenship',
               'citizenId', 'time', 'militaryUnit']
    battle_id = api["battle_id"]
    query = f"SELECT * FROM {server}.apiFights WHERE battle_id = {battle_id}" + \
            (f" AND round_id = {round_id}" if round_id else "")
    values = await execute_query(bot.pool, query, fetch=True)
    dfs = []
    if values:
        dfs.append(pd.DataFrame(values, columns=["index"] + columns))

    current_round, first_round = api["currentRound"], api["last_round_in_db"] + 1
    if 8 in (api['defenderScore'], api['attackerScore']):
        last_round = current_round
    else:
        last_round = current_round + 1
    for round_id in range(first_round, last_round):
        api_fights = await get_content(
            f'https://{server}.e-sim.org/apiFights.html?battleId={battle_id}&roundId={round_id}')
        if not api_fights:
            continue
        api_fights = [(battle_id, round_id, hit['damage'], hit['weapon'], hit['berserk'], hit['defenderSide'],
                       hit['citizenship'], hit['citizenId'], hit['time'], hit.get('militaryUnit', 0))
                      for hit in reversed(api_fights)]
        if round_id != current_round:
            placeholders = ', '.join(['%s'] * len(api_fights[0]))
            query = f"INSERT IGNORE INTO {server}.apiFights {tuple(columns)} VALUES ({placeholders})"
            await execute_query(bot.pool, query, api_fights, many=True)
        dfs.append(pd.DataFrame(api_fights, columns=columns))
    return pd.concat(dfs, ignore_index=True, copy=False) if dfs else None
