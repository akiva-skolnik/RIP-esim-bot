import logging
from datetime import datetime

import asyncmy
import pandas as pd
from asyncmy.cursors import logger as asyncmy_logger
from discord import Interaction, File

from bot.bot import bot
from .utils import custom_delay, get_content, custom_followup, update_percent

asyncmy_logger.setLevel("ERROR")  # I INSERT IGNORE, so I don't care about duplicate key warnings
logger = logging.getLogger()

api_battles_columns = ('battle_id', 'currentRound', 'lastVerifiedRound', 'attackerScore', 'regionId',
                       'defenderScore', 'frozen', 'type', 'defenderId', 'attackerId', 'totalSecondsRemaining')
api_fights_columns = ('battle_id', 'round_id', 'damage', 'weapon', 'berserk', 'defenderSide', 'citizenship',
                      'citizenId', 'time', 'militaryUnit')


async def execute_query(pool: asyncmy.Pool, query: str, params: iter = None,
                        many: bool = False, fetch: bool = False) -> list:
    logger.info(f"Executing query: {query} (many={many}, fetch={fetch})")
    logger.debug(f"Params: {params}")
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
    logger.info(f"cache_api_battles: {server=}, {start_id=}, {end_id=}, {len(battle_ids)=}")
    excluded_ids = ",".join(str(i) for i in range(start_id, end_id + 1) if i not in battle_ids)

    # Select battles that are in the db and have finished, to be excluded from reinserting
    query = f"SELECT battle_id FROM {server}.apiBattles " \
            f"WHERE (battle_id BETWEEN {start_id} AND {end_id}) " + \
            (f"AND battle_id NOT IN ({excluded_ids})" if excluded_ids else "") + \
            " AND (defenderScore = 8 OR attackerScore = 8)"

    existing_battles = [x[0] for x in await execute_query(bot.pool, query, fetch=True)]  # x[0] = battle_id

    for battle_id in battle_ids:
        if await bot.should_cancel(interaction):
            break
        if battle_id not in existing_battles:
            await insert_into_api_battles(server, battle_id)
            await custom_delay(interaction)
    logger.info(f"cache_api_battles: Done caching {len(battle_ids)} battles from {server=}")


async def insert_into_api_battles(server: str, battle_id: int) -> dict:
    """insert_into_api_battles"""
    api_battles = await get_content(f'https://{server}.e-sim.org/apiBattles.html?battleId={battle_id}')
    api_battles['totalSecondsRemaining'] = (api_battles["hoursRemaining"] * 3600 +
                                            api_battles["minutesRemaining"] * 60 + api_battles["secondsRemaining"])
    api_battles['battle_id'] = battle_id
    api_battles['lastVerifiedRound'] = -1
    filtered_api_battles = {k: api_battles[k] for k in api_battles_columns}

    placeholders = ', '.join(['%s'] * len(filtered_api_battles))
    query = f"REPLACE INTO {server}.apiBattles VALUES ({placeholders})"
    await execute_query(bot.pool, query, tuple(filtered_api_battles.values()))

    return filtered_api_battles


async def select_many_api_battles(server: str, battle_ids: iter, columns: tuple = None,
                                  custom_condition: str = None) -> pd.DataFrame:
    columns = columns or api_battles_columns
    start_id, end_id = min(battle_ids), max(battle_ids)
    logger.info(f"select_many_api_battles: {server=}, {start_id=}, {end_id=}, {len(battle_ids)=}, {custom_condition=}")
    excluded_ids = ",".join(str(i) for i in range(start_id, end_id + 1) if i not in battle_ids)
    query = f"SELECT {', '.join(columns)} FROM {server}.apiBattles " \
            f"WHERE (battle_id BETWEEN {start_id} AND {end_id}) " + \
            (f"AND battle_id NOT IN ({excluded_ids}) " if excluded_ids else "") + \
            ("" if not custom_condition else f"AND {custom_condition}")

    api_battles = await execute_query(bot.pool, query, fetch=True)
    df = pd.DataFrame(api_battles, columns=list(columns), index=[x[0] for x in api_battles])
    logger.info(f"select_many_api_battles: Done selecting {len(df)} battles from {server=}")
    return df


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
                       'citizenId': 0, 'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}]
    # time can be one of: (%d-%m-%Y %H:%M:%S:%f, %Y-%m-%d %H:%M:%S:%f, %Y-%m-%d %H:%M:%S.%f, %Y-%m-%d %H:%M:%S)
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
    total_rounds_to_be_scanned = (api_battles_df["currentRound"].sum() -
                                  api_battles_df["lastVerifiedRound"].sum() -
                                  len(api_battles_df))
    logger.info(f"cache_api_fights: {server=}, {len(api_battles_df)=}, {total_rounds_to_be_scanned=}")
    msg = await custom_followup(interaction,
                                "Progress status: 1%.\n(I will update you after every 10%)\n"
                                if total_rounds_to_be_scanned > 10 else "Alright, Sir. Just a moment.",
                                file=File(bot.typing_gif_path))

    scanned_rounds = 0
    for api_battles in api_battles_df.to_dict(orient="index").values():
        if await bot.should_cancel(interaction, msg):
            break

        battle_is_over = 8 in (api_battles['defenderScore'], api_battles['attackerScore'])
        if battle_is_over:
            current_round = api_battles["currentRound"]  # this can be 9...16 included
        else:
            current_round = api_battles["currentRound"] + 1  # insert the ongoing round too
        last_verified_round = max(api_battles["lastVerifiedRound"], 0)
        for round_id in range(last_verified_round + 1, current_round):
            # Using int because battle_id is np.int64
            await insert_into_api_fights(server, int(api_battles["battle_id"]), round_id)
            await custom_delay(interaction)
        scanned_rounds += current_round

        await update_last_verified_round(server, api_battles)
        msg = await update_percent(scanned_rounds, total_rounds_to_be_scanned, msg)

    try:
        await msg.delete()
    except Exception:
        pass
    logger.info(f"cache_api_fights: Done caching {total_rounds_to_be_scanned} rounds from {server=}")


async def update_last_verified_round(server: str, api_battles: pd.Series) -> None:
    """Update lastVerifiedRound in apiBattles
    We attempt to insert every closed last round twice, because sometimes the api takes a while to update.
    For example, when the current round is 15, there's no point in inserting rounds 1-13 twice, because they surely updated.
    But round 14 might not have updated yet, so we insert it twice: once with lastVerifiedRound = 13, and once with 14.
    Same with finished battles: if the battle is finished, we insert the last round twice:
        once with lastVerifiedRound = current-2, and once with lastVerifiedRound = last_round (current-1)

    Edge cases: in the first round, we don't change lastVerifiedRound, because there's no previous round to verify.
    The second round, we insert lastVerifiedRound=0, because the first round is not verified yet but next time it will be.
    """
    current_round = api_battles["currentRound"]
    previous_round = current_round - 1
    if current_round == 1:  # first round
        last_verified_round = -1  # no previous round to verify
    elif api_battles["lastVerifiedRound"] < 0:  # first time (new battle)
        last_verified_round = current_round - 2
    elif api_battles["lastVerifiedRound"] != previous_round:
        last_verified_round = previous_round
    else:  # lastVerifiedRound is present and equal to previous_round
        last_verified_round = -1

    if last_verified_round >= 0:
        query = f"UPDATE {server}.apiBattles SET lastVerifiedRound = {last_verified_round} " \
                f"WHERE battle_id = {api_battles['battle_id']}"
        await execute_query(bot.pool, query)


async def select_many_api_fights(server: str, battle_ids: iter, columns: tuple = None,
                                 custom_condition: str = None) -> pd.DataFrame:
    """Select all fight records in the given battles (can be a lot)"""
    columns = columns or api_fights_columns
    start_id, end_id = min(battle_ids), max(battle_ids)
    logger.info(f"select_many_api_fights: {server=}, {start_id=}, {end_id=}, {len(battle_ids)=}, {custom_condition=}")
    excluded_ids = ",".join(str(i) for i in range(start_id, end_id + 1) if i not in battle_ids)

    query = f"SELECT {', '.join(columns)} FROM {server}.apiFights " \
            f"WHERE (battle_id BETWEEN {start_id} AND {end_id}) AND citizenId <> 0 " + \
            (f"AND battle_id NOT IN ({excluded_ids}) " if excluded_ids else "") + \
            ("" if not custom_condition else f"AND {custom_condition}")

    api_fights = await execute_query(bot.pool, query, fetch=True)
    df = pd.DataFrame(api_fights, columns=list(columns))
    logger.info(f"select_many_api_fights: Done selecting {len(df)} hits from {server=}, {start_id=}, {end_id=}")
    return df


async def get_api_fights_sum(server: str, battle_ids: iter, group_by: str = "citizenId") -> pd.DataFrame:
    """Get the sum of damage, hits, and quality for each citizen in the given battles.
    Returns a DataFrame with columns: citizenId, damage, Q0, Q1, Q2, Q3, Q4, Q5, hits"""
    start_id, end_id = min(battle_ids), max(battle_ids)
    logger.info(f"get_api_fights_sum: {server=}, {start_id=}, {end_id=}, {len(battle_ids)=}, {group_by=}")
    excluded_ids = ",".join(str(i) for i in range(start_id, end_id + 1) if i not in battle_ids)
    query = (f"SELECT {group_by}, SUM(damage) AS damage, "
             "SUM(IF(weapon = 0, IF(berserk, 5, 1), 0)) AS Q0, "
             "SUM(IF(weapon = 1, IF(berserk, 5, 1), 0)) AS Q1, "
             "SUM(IF(weapon = 2, IF(berserk, 5, 1), 0)) AS Q2, "
             "SUM(IF(weapon = 3, IF(berserk, 5, 1), 0)) AS Q3, "
             "SUM(IF(weapon = 4, IF(berserk, 5, 1), 0)) AS Q4, "
             "SUM(IF(weapon = 5, IF(berserk, 5, 1), 0)) AS Q5, "
             "SUM(IF(berserk, 5, 1)) AS hits "
             f"FROM {server}.apiFights "
             f"WHERE (battle_id BETWEEN {start_id} AND {end_id}) AND {group_by} <> 0 " +
             (f"AND battle_id NOT IN ({excluded_ids}) " if excluded_ids else "") +
             f"GROUP BY {group_by} "
             "ORDER BY damage DESC "  # TODO: parameter
             )

    api_fights = await execute_query(bot.pool, query, fetch=True)
    columns = [group_by, "damage", "Q0", "Q1", "Q2", "Q3", "Q4", "Q5", "hits"]
    df = pd.DataFrame(api_fights, columns=columns, index=[x[0] for x in api_fights])
    logger.info(f"get_api_fights_sum: Done selecting {len(df)} citizens from {server=}, {start_id=}, {end_id=}")
    return df


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

    current_round, first_round = api["currentRound"], api["lastVerifiedRound"] + 1
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
