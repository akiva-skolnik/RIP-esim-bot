"""bot.py"""
import asyncio
import heapq
import json
import time
import traceback
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from random import randint

import pytz

import utils
from constants import countries_per_id, countries_per_server

warnings.filterwarnings("ignore")

TIMEZONE = 'Europe/Berlin'
DATETIME_FORMAT = "%d-%m-%Y %H:%M:%S"

PRODUCT_SHEET = "17y8qEU4aHQRTXKdnlM278z3SDzY16bmxMwrZ0RKWcEI"
servers = {
    "vega": "19fmlmxwWrzA2PgvzKvB-tNhiSUDTfVBtooLIOnc38vI",
    "nika": "141302UWgwAMoNO55NfWzeQkvCtq7IY_MAYSGnqfTy2I",
    "luxia": "1mx_JkHVnTVikNdTSxhvfFh4Pzuepp9ZGakCAtxnGxyY",
    "suna": "1imlsoLdaEb45NnJGmo5T7mQxsjzzTGbrkvqfcR8pMlE",
    "alpha": "1KqxbZ9LqS191wRf1VGLNl-aw6UId9kmUE0k7NfKQdI4",
    "primera": "1laY2aYa5_TcaDPCZ4FrFjZnbvVkxRIrGdm7ZRaO41nY",
    "secura": "10en9SJVsIQz7uGhbXwb9GInnOdcDuE4p7L93un0q6xw"}


# TODO: split into smaller functions.
async def update_buffs(server: str) -> None:
    """update buffs db"""
    base_url = f'https://{server}.e-sim.org/'
    BUFF_SIZES = {"mili": 15, "mini": 30, "standard": 60,
                  "major": 2 * 60, "huge": 4 * 60, "exceptional": 8 * 60}
    ELIXIRS = ["jinxed", "finese", "bloodymess", "lucky"]
    base_columns = 8
    LINK, CITIZENSHIP, DMG, LAST_SEEN, PREMIUM, BUFFED_AT, DEBUFF_ENDS, TILL_CHANGE = range(base_columns)
    is_first_update = True
    while True:
        loop_start_time = time.time()
        try:
            buffs_data = await utils.find_one("buffs", server) or {}
            now = datetime.now().astimezone(pytz.timezone(TIMEZONE)).replace(tzinfo=None)
            now_s = now.strftime(DATETIME_FORMAT)
            last_update = buffs_data.get("Last update:", [now_s])[0]
            buffs_data.pop("Nick", None)
            buffs_data.pop("Last update", None)

            for player_info in await utils.get_content(f"{base_url}apiOnlinePlayers.html"):
                player = json.loads(player_info)
                nick = player['login']
                player_profile_link = f"{base_url}profile.html?id={player['id']}"

                # Pause to comply with server request limits
                await asyncio.sleep(0.37)
                tree = await utils.get_content(player_profile_link)
                player_details = utils.extract_player_details(player_profile_link, tree)

                # Update the player data if they are buffed
                if player_details.get("buffed"):
                    if nick not in buffs_data:
                        buffs_data[nick] = [player_profile_link, player_details['citizenship'],
                                            player_details['damage'],
                                            now_s, player_details['premium']] + [""] * (
                                                   3 + len(ELIXIRS) * 2)  # 3 = buffed at, debuff ends, till change
                    if not buffs_data[nick][BUFFED_AT]:
                        buffs_data[nick][BUFFED_AT] = now_s

                # Calculate the elixir buff durations
                elixir_bonus = 0
                for eq_type, parameters, sorted_data, eq_link in utils.get_eqs(tree):
                    for val, p in zip(sorted_data, parameters):
                        if p == "elixir":
                            elixir_bonus += val

                # Update the times of the elixir buff
                for buff in player_details.get("buffs", []):
                    if "elixir" not in buff:
                        continue
                    size = buff.split("elixir")[1].split("_")[0]
                    elixir = buff.split("elixir")[0]
                    index = ELIXIRS.index(elixir)
                    if nick not in buffs_data:
                        buffs_data[nick] = [player_profile_link, player_details['citizenship'],
                                            player_details['damage'],
                                            now_s, player_details['premium']] + \
                                           [""] * (3 + len(ELIXIRS) * 2)  # 3 = buffed at, debuff ends, till change
                    if not buffs_data[nick][base_columns + index]:
                        buffs_data[nick][base_columns + index] = str(
                            timedelta(minutes=(1 + elixir_bonus / 100) * BUFF_SIZES[size]))
                        buffs_data[nick][base_columns + index + len(ELIXIRS)] = now_s

                if player["login"] in buffs_data:  # update last seen
                    buffs_data[player["login"]][LAST_SEEN] = now_s

            # Update the buffed and debuffed times
            day_seconds = 24 * 60 * 60  # seconds in a day
            for nick in list(buffs_data):  # Convert to list to avoid 'dictionary changed size during iteration' error
                player = buffs_data[nick]
                days = 2  # if row[PREMIUM] else 3  (non-premium debuff used to last for 3 days)

                # Calculate the seconds since the player was buffed
                if player[BUFFED_AT]:
                    buffed_at = datetime.strptime(player[BUFFED_AT], DATETIME_FORMAT)
                    buffed_seconds = (now - buffed_at).total_seconds()
                    player[DEBUFF_ENDS] = (timedelta(days=days) + buffed_at).strftime(DATETIME_FORMAT)
                else:
                    buffed_seconds = 0

                # Determine time remaining until buff/debuff status changes
                if 0 < buffed_seconds < day_seconds:  # If buffed within the last 24h
                    seconds_until_change = day_seconds - buffed_seconds
                elif day_seconds < buffed_seconds < day_seconds * days:  # If in debuff period
                    seconds_until_change = (
                            datetime.strptime(player[DEBUFF_ENDS], DATETIME_FORMAT) - now).total_seconds()
                else:  # If no buffs/debuffs are active
                    seconds_until_change = 0

                # Update the time remaining until buff/debuff status changes
                if seconds_until_change > 0:
                    player[TILL_CHANGE] = utils.format_seconds(seconds_until_change)
                else:  # Reset timers if no active buffs or debuffs
                    player[BUFFED_AT] = player[DEBUFF_ENDS] = player[TILL_CHANGE] = ""

                # Update elixir buff timers
                for elixir in range(base_columns, base_columns + len(ELIXIRS)):
                    if not player[elixir]:
                        try:
                            player[elixir + len(ELIXIRS)] = ""
                        except IndexError:
                            print(f"index error for {nick} at {server}")
                        continue
                    elapsed_since_update = now - datetime.strptime(last_update, DATETIME_FORMAT)
                    is_negative = "-" in player[elixir]
                    player[elixir] = player[elixir].replace("-", "")
                    try:
                        elixir_time = datetime.strptime(player[elixir], "%H:%M:%S")
                    except ValueError:
                        player[elixir] = ""
                        player[elixir + len(ELIXIRS)] = ""
                        continue

                    elixir_duration = timedelta(hours=elixir_time.hour, minutes=elixir_time.minute,
                                                seconds=elixir_time.second)
                    remaining_seconds = (elixir_duration - elapsed_since_update).total_seconds()
                    if not is_negative:  # TODO: is there a nicer way to replace this logic?
                        is_negative = False
                        if remaining_seconds < 0:  # If the timer is negative, calculate the actual remaining time
                            elixir_start = datetime.strptime(player[elixir + len(ELIXIRS)], DATETIME_FORMAT)
                            remaining_seconds += day_seconds - (now - elixir_start).total_seconds()
                            is_negative = True

                    player[elixir] = (("-" if is_negative else "") + utils.format_seconds(
                        remaining_seconds)) if remaining_seconds > 0 else ""

                # Remove the player if there are no active buffs or elixirs
                if not any(player[i] for i in range(7, 12)):
                    del buffs_data[nick]

            # Sort the data for presentation in the spreadsheet, and update the database
            sorted_data = {"Last update:": [now_s, "(game time)."] + [""] * (base_columns - 2 + len(ELIXIRS)),
                           "Nick": ["Link", "Citizenship", "Total Dmg", "Last Seen", "Premium", "Buffed At",
                                    "Debuff Ends", "Till Status Change"] +
                                   [x.title() for x in ELIXIRS] + [f"{x.title()} Buffed At" for x in ELIXIRS]
                           }
            # sort by citizenship then nick
            sorted_data.update(dict(sorted(buffs_data.items(), key=lambda x: (x[1][CITIZENSHIP], nick))))
            buffs_data.clear()  # Clear the data to free up memory
            if is_first_update or randint(1, 10) == 1:
                await utils.spreadsheets(
                    servers[server], "buffs", f"A1:Q{len(sorted_data) + 1}",
                    [([v[0], k] + v[1:]) if k != "Last update:" else [k] + v
                     for k, v in sorted_data.items()], delete=True)
                is_first_update = False
            await utils.replace_one("buffs", server, sorted_data)
            sorted_data.clear()
        except Exception as e:
            error_traceback = traceback.format_exc()
            print(error_traceback if len(error_traceback) < 1000 else "buffs long error")
        await asyncio.sleep(max(300 - time.time() + loop_start_time, 1))


async def update_time(server: str) -> None:
    """Asynchronously updates the online time statistics of players in the e-sim game."""
    # Constants for indexes in the player data array
    NICK, CITIZENSHIP, TOTAL_MINUTES, TOTAL_AVG, MONTH_MINUTES, MONTH_AVG = range(6)

    base_url = f'https://{server}.e-sim.org/'
    initial_date_info = {
        "primera": ["Minutes online (since 10/12/20)", "09/12/2020", "10/12/2020"],
        "luxia": ["Minutes online (since day 1)", "10/02/2022", "11/02/2022"],
        "nika": ["Minutes online (since day 1)", "07/09/2023", "08/09/2023"],
        "vega": ["Minutes online (since day 1)", "05/11/2023", "06/11/2023"]
    }

    # Define the headers for the data collection
    headers = ["Link", "Nick", "Citizenship",
               initial_date_info.get(server, ["Minutes online (since 19/05/2020)"])[0],
               "Avg. per day", "Minutes online (this month)", "Avg. per day"]

    is_first_update = True
    while True:
        loop_start_time = time.time()
        try:
            now = datetime.now().astimezone(pytz.timezone(TIMEZONE))
            player_data = await utils.find_one("time_online", server)  # Retrieve current player time online data
            player_data.pop("_headers", None)  # Remove headers if they are in the data already

            max_month_minutes = next(iter(player_data.values()))[MONTH_MINUTES]

            # Update player data from the API content
            for player_info in await utils.get_content(f"{base_url}apiOnlinePlayers.html"):
                player = json.loads(player_info)
                citizen_id = str(player['id'])
                player_stats = player_data.setdefault(
                    citizen_id, [player['login'], utils.get_countries(server, player['citizenship']), 0, "", 0, ""])
                player_stats[TOTAL_MINUTES] += 1
                player_stats[MONTH_MINUTES] += 1
                player_stats[CITIZENSHIP] = utils.get_countries(server, player['citizenship'])
                player_stats[NICK] = player['login']

            # Calculate averages and update data
            date_format = "%d/%m/%Y"
            start_date = datetime.strptime(initial_date_info.get(server, ["", "18/05/2020"])[1], date_format)
            start_of_month = max(start_date, datetime.strptime(f"01/{now.strftime('%m')}/{now.strftime('%Y')}", date_format))
            today_date = datetime.strptime(now.strftime(date_format), date_format)
            elapsed_since_start = (today_date - start_date).total_seconds() / 60
            elapsed_since_month_start = (today_date - start_of_month + timedelta(days=1)).total_seconds() / 60

            new_month = max_month_minutes > elapsed_since_month_start

            # Update averages for each player
            for player_stats in player_data.values():
                # [:-3] to remove the seconds from the string
                if new_month:
                    player_stats[MONTH_MINUTES] = 1
                player_stats[TOTAL_AVG] = str(timedelta(
                    minutes=int((player_stats[TOTAL_MINUTES] / elapsed_since_start) * 24 * 60)))[:-3]
                player_stats[MONTH_AVG] = str(timedelta(
                    minutes=int((player_stats[MONTH_MINUTES] / elapsed_since_month_start) * 24 * 60)))[:-3]

            # Sort and limit the data
            player_data = dict(sorted(player_data.items(),
                                      key=lambda item: (item[1][MONTH_MINUTES], item[1][TOTAL_MINUTES]),
                                      reverse=True)[:3000 if len(player_data) < 3000 else 2900])

            # Update the headers with the current time
            current_time = datetime.now().astimezone(pytz.timezone(TIMEZONE)).strftime(DATETIME_FORMAT)
            player_data["_headers"] = headers[1:] + [current_time]

            # Persist the updated data
            await utils.replace_one("time_online", server, player_data)

            # Update the spreadsheet
            if is_first_update or randint(1, 30) == 1:
                del player_data["_headers"]
                await utils.spreadsheets(servers[server], "Time online", f"A1:G{len(player_data) + 1}",
                                         [headers] + [[f"{base_url}profile.html?id={player_id}"] + stats for
                                                      player_id, stats in player_data.items()][:999])
                is_first_update = False

            player_data.clear()
        except Exception:
            error_traceback = traceback.format_exc()
            print(error_traceback if len(error_traceback) < 1000 else "time online long error")

        await asyncio.sleep(max(60 - time.time() + loop_start_time, 1))


async def update_monetary_market():
    while True:
        mm_per_server = {server: {} for server in servers}
        loop_start_time = time.time()

        for server in reversed(list(servers)):
            base_url = f'https://{server}.e-sim.org/'
            # get data
            for country_id in countries_per_server[server]:
                monetary_market_ration = 0
                try:
                    func = utils.get_locked_content if server == "primera" else utils.get_content
                    url = f'{base_url}monetaryMarketOffers?sellerCurrencyId=0&buyerCurrencyId={country_id}&page=1'
                    tree = await func(url)

                    ratios = tree.xpath("//*[@class='ratio']//b/text()")
                    amounts = tree.xpath("//*[@class='amount']//b/text()")

                    for ratio, amount in zip(ratios, amounts):
                        if float(amount) > 1:
                            monetary_market_ration = float(ratio)
                            break
                    if not monetary_market_ration and ratios:
                        monetary_market_ration = float(ratios[-1])
                except:
                    pass
                mm_per_server[server][str(country_id)] = min(1.4, monetary_market_ration)
                await asyncio.sleep(0.35)

            # update history
            history = await utils.find_one("mm_history", server)
            today = datetime.now().astimezone(pytz.timezone(TIMEZONE)).strftime(DATETIME_FORMAT.split()[0])
            for country_id, price in mm_per_server[server].items():
                country_id = str(country_id)  # MongoDB forcing keys to be str
                price = str(price)
                if country_id not in history:
                    history[country_id] = {}
                if today not in history[country_id]:
                    history[country_id][today] = {}
                if price not in history[country_id][today]:
                    history[country_id][today][price] = 0
                history[country_id][today][price] += 1
            await utils.replace_one("mm_history", server, history)
            history.clear()

            # update db
            now = datetime.now().astimezone(pytz.timezone(TIMEZONE)).strftime(DATETIME_FORMAT)
            mm_per_server[server]["last_update"] = now
            await utils.replace_one("mm", server, mm_per_server[server])

        now = datetime.now().astimezone(pytz.timezone(TIMEZONE)).strftime(DATETIME_FORMAT)
        values = [["Country Name", "Currency"] + list(servers) + [f"Last update: {now} (game time)."]]

        for country_id, country_details in countries_per_id.items():
            name, currency = country_details[0].title(), country_details[-1].upper()
            if any(str(country_id) in mm_per_server[server] for server in servers):
                values.append([name, currency] + [
                    f"=HYPERLINK(\"https://{server}.e-sim.org/monetaryMarket.html?buyerCurrencyId={country_id}\", {mm_per_server[server][str(country_id)]})"
                    if str(country_id) in mm_per_server[server] else "" for server in servers])
        mm_per_server.clear()
        values[1:] = sorted(values[1:])
        if len(values) > 1:
            try:
                await utils.spreadsheets(PRODUCT_SHEET, "Monetary Market", f"A1:K{len(values) + 1}", values, True)
            except Exception:
                error_traceback = traceback.format_exc()
                print(error_traceback if len(error_traceback) < 1000 else "monetary_market long error")

        values.clear()
        await asyncio.sleep(max(3600 - time.time() + loop_start_time, 1))


async def update_prices(server: str) -> None:
    """Continuously updates the product prices database from the e-sim game for a given server."""
    base_url = f'https://{server}.e-sim.org/'
    is_first_update = True
    raw_products = ["Iron", "Diamonds", "Grain", "Oil", "Stone", "Wood"]
    while True:
        loop_start_time = time.time()
        try:
            offers = defaultdict(list)
            total_stock_per_product = defaultdict(int)
            db_mm = await utils.find_one("mm", server)
            for index, offer in enumerate(await utils.get_content(f"{base_url}apiProductMarket.html?id=-1")):
                country_id = offer["countryId"]
                product_type = offer["resource"].title()
                product_key = f"Q{offer['quality']} {product_type}" if product_type not in raw_products else product_type
                price = db_mm.get(str(country_id), 0) * float(offer["price"])
                if not price:
                    continue
                total_stock_per_product[product_key] += offer["quantity"]

                # keep only the 5 cheapest offers
                offer = {"country_id": country_id, "price": round(price, 4), "stock": offer["quantity"]}
                price = -offer["price"]
                heap = offers[product_key]
                if len(heap) < 5:
                    heapq.heappush(heap, (price, index, offer))
                elif price > heap[0][0]:
                    heapq.heapreplace(heap, (price, index, offer))
                # else ignore the offer

            db_mm.clear()

            # sort offers by price
            for product_key, product_offers in offers.items():
                offers[product_key] = sorted([x[-1] for x in product_offers], key=lambda x: x["price"])

            # Update the history
            now = datetime.now().astimezone(pytz.timezone(TIMEZONE))
            if server not in ('nika', 'vega'):
                this_month = "01-" + now.strftime("%m-%Y")
            else:
                this_month = now.strftime("%d-%m-%Y")
            now = now.strftime(DATETIME_FORMAT)

            results = defaultdict(list)
            for product_key, product_offers in offers.items():
                quality, product_type = product_key[1:].split() if product_key[0] == "Q" else (1, product_key)
                n = 0
                avg_price = 0
                for offer in product_offers:
                    country_id = offer["country_id"]
                    link = f"{base_url}productMarket.html?resource={product_type.upper()}&countryId={country_id}&quality={quality}"
                    monetary_market_link = f"{base_url}monetaryMarket.html?buyerCurrencyId={country_id}"
                    results[product_key].append(
                        [offer["price"], offer["stock"], utils.get_countries(server, country_id), link,
                         monetary_market_link])

                    # Calculate the average price of the top 1% of total offers
                    stock_left = int(total_stock_per_product[product_key] * 0.01 - n) + 1  # +1 to avoid division by 0 for <100 offers
                    if stock_left > 0:
                        stock = min(stock_left, offer["stock"])  # stock left to reach 1% of total stock
                        avg_price += stock * offer["price"]
                        n += stock

                # Update history  TODO: use SQL
                history_key = product_key.replace(" ", "_")
                avg_price = str(round(avg_price / n if n else 0, 4))
                history_entry = await utils.find_one("prices_history", history_key)
                if server not in history_entry:
                    history_entry[server] = {}
                if this_month not in history_entry[server]:
                    history_entry[server][this_month] = {}
                if avg_price not in history_entry[server][this_month]:
                    history_entry[server][this_month][avg_price] = 0
                history_entry[server][this_month][avg_price] += 1
                await utils.replace_one("prices_history", history_key, history_entry)
                history_entry.clear()

            offers.clear()
            total_stock_per_product.clear()

            # Update the spreadsheet with processed data
            new_values = []
            headers = {"Product": [
                ["Price", "Stock", "Country", "Link", "Monetary market", f"Last update: {now} (game time)."]]}
            headers.update(dict(sorted(results.items())))
            results = headers
            if len(results) > 1:
                await utils.replace_one("price", server, results)

                # format results
                for product, offers in results.items():
                    for index, offer in enumerate(offers[:5]):
                        row = ([product] if index == 0 else [""]) + offer
                        new_values.append(row)
                    if len(new_values) > 1:
                        new_values.append(["", "-", "-", "-"])

                if is_first_update or randint(1, 3) == 1:
                    await utils.spreadsheets(PRODUCT_SHEET, server, f"A1:G{len(new_values) + 1}", new_values, True)
                    is_first_update = False
            results.clear()
            new_values.clear()
        except Exception:
            error_traceback = traceback.format_exc()
            print(error_traceback if len(error_traceback) < 1000 else "price long error")

        await asyncio.sleep(max(1000 - time.time() + loop_start_time, 1))


loop = asyncio.get_event_loop()


async def start_time_buff() -> None:
    """start time and buff"""
    for server in servers:
        loop.create_task(update_time(server))
        loop.create_task(update_buffs(server))
        await asyncio.sleep(int(120 / len(servers)))


async def start_mm_price() -> None:
    """start mm and price"""
    loop.create_task(update_monetary_market())
    await asyncio.sleep(30)
    for server in servers:
        loop.create_task(update_prices(server))
        await asyncio.sleep(int(900 / len(servers)))


loop.create_task(start_time_buff())
loop.create_task(start_mm_price())
loop.run_forever()
