"""bot.py"""
import asyncio
import json
import time
import traceback
import warnings
from datetime import datetime, timedelta
from random import randint

import pytz

from big_dicts import countries_per_id, countries_per_server
from utils import find_one, get_content, get_countries, get_eqs, replace_one, spreadsheets

warnings.filterwarnings("ignore")

PRODUCT_SHEET = "17y8qEU4aHQRTXKdnlM278z3SDzY16bmxMwrZ0RKWcEI"
servers: dict = {
    "azura": "1xy8Ssj91q6z8vqmtnpbviY1pK44ed3FQrOI3KyVq2cg",
    "sigma": "1SuHcJLqS-nSAzprs7kGsrrcuNLOdXsPRaDVQbkvpxZc",
    "unica": "1PvjB3E-7A4cYAUmczJ1HNDOUAQAUnFzjSkCu-dJuVL0",
    "luxia": "1mx_JkHVnTVikNdTSxhvfFh4Pzuepp9ZGakCAtxnGxyY",
    "suna": "1imlsoLdaEb45NnJGmo5T7mQxsjzzTGbrkvqfcR8pMlE",
    "alpha": "1KqxbZ9LqS191wRf1VGLNl-aw6UId9kmUE0k7NfKQdI4",
    "primera": "1laY2aYa5_TcaDPCZ4FrFjZnbvVkxRIrGdm7ZRaO41nY",
    "secura": "10en9SJVsIQz7uGhbXwb9GInnOdcDuE4p7L93un0q6xw"}


async def update_buffs(server: str) -> None:
    """update buffs db"""
    url = f'https://{server}.e-sim.org/'
    date_format = "%d-%m-%Y %H:%M:%S"
    sizes = {"mili": 15, "mini": 30, "standard": 60,
             "major": 2 * 60, "huge": 4 * 60, "exceptional": 8 * 60}
    elixirs = ["jinxed", "finese", "bloodymess", "lucky"]
    LINK, CITIZENSHIP, DMG, LAST_SEEN, PREMIUM, BUFFED_AT, DEBUFF_ENDS, TILL_CHANGE = range(8)

    while True:
        start = time.time()
        try:
            data: dict = await find_one("buffs", server)
            now = datetime.now().astimezone(pytz.timezone('Europe/Berlin')).replace(tzinfo=None)
            now_s = now.strftime(date_format)
            last_update = data.get("Last update:", [now_s])[0]
            if data:
                try:
                    del data["Nick"]
                    del data["Last update:"]
                except:
                    pass

            for player in await get_content(f"{url}apiOnlinePlayers.html"):
                row: dict = json.loads(player)
                nick = row['login']

                link = url + f"profile.html?id={row['id']}"
                await asyncio.sleep(0.37)
                tree = await get_content(link)
                try:
                    premium = len(tree.xpath('//*[@class="premium-account"]')) == 1
                    CS = tree.xpath('//*[@class="profile-row" and span = "Citizenship"]/span/span/text()')[0]
                    dmg = tree.xpath('//*[@class="profile-row" and span = "Damage"]/span/text()')[0]
                except:
                    continue

                buffs_debuffs = [x.split("/specialItems/")[-1].split(".png")[0] for x in tree.xpath(
                    '//*[@class="profile-row" and (strong="Debuffs" or strong="Buffs")]//img/@src') if
                                 "//cdn.e-sim.org//img/specialItems/" in x]
                buffs = [x.split("_")[0].lower() for x in buffs_debuffs if "positive" in x.split("_")[1:]]
                if any(a in buffs for a in ('steroids', 'tank', 'bunker', 'sewer')):
                    if nick not in data:
                        data[nick] = [link, CS, dmg, "", premium, "", "", "", "", "", "", "", "", "", "", ""]
                    if not data[nick][BUFFED_AT]:
                        data[nick][BUFFED_AT] = now_s

                elixir_bonus = 0
                for eq_type, parameters, values, eq_link in get_eqs(tree):
                    for val, p in zip(values, parameters):
                        if p == "elixir":
                            elixir_bonus += val

                for buff in buffs:
                    if "elixir" in buff:
                        size = buff.split("elixir")[1].split("_")[0]
                        elixir = buff.split("elixir")[0]
                        index = elixirs.index(elixir)
                        if nick not in data:
                            data[nick] = [link, CS, dmg, "", premium, "", "", "", "", "", "", "", "", "", "", ""]
                        if not data[nick][index + 8]:
                            data[nick][index + 8] = str(timedelta(minutes=(1 + elixir_bonus / 100) * sizes[size]))
                        if not data[nick][index + 12]:
                            data[nick][index + 12] = now_s
                if row["login"] in data:
                    data[row["login"]][LAST_SEEN] = now_s

            for nick in list(data):
                row: dict = data[nick]
                days = 2  # if row[PREMIUM] else 3
                day_seconds = 24 * 60 * 60
                if row[BUFFED_AT]:
                    buffed_seconds = (now - datetime.strptime(row[BUFFED_AT], date_format)).total_seconds()
                    row[DEBUFF_ENDS] = (timedelta(days=days) + datetime.strptime(row[BUFFED_AT], date_format)).strftime(
                        date_format)
                else:
                    buffed_seconds = 0

                if 0 < buffed_seconds < day_seconds:  # buff lasts 24h
                    seconds = day_seconds - buffed_seconds
                elif 0 < buffed_seconds < day_seconds * days:  # debuff ends
                    seconds = (datetime.strptime(row[DEBUFF_ENDS], date_format) - now).total_seconds()
                else:
                    seconds = 0

                m, s = divmod(seconds, 60)
                h, m = divmod(m, 60)
                if seconds > 0:
                    row[TILL_CHANGE] = f'{int(h):02d}:{int(m):02d}:{int(s):02d}'
                else:
                    row[BUFFED_AT] = row[DEBUFF_ENDS] = row[TILL_CHANGE] = ""

                for elixir in range(8, 12):
                    if not row[elixir]:
                        continue
                    time_from_update = now - datetime.strptime(last_update, date_format)
                    is_negative = "-" in row[elixir]
                    row[elixir] = row[elixir].replace("-", "")
                    try:
                        t = datetime.strptime(row[elixir], "%H:%M:%S")
                    except:
                        row[elixir] = ""
                        continue
                    till_elixir_db = timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
                    sec = (till_elixir_db - time_from_update).total_seconds()
                    if not is_negative:
                        is_negative = False
                        if sec < 0:
                            sec += 24 * 60 * 60 - (
                                        now - datetime.strptime(row[elixir + 4], date_format)).total_seconds()
                            is_negative = True

                    m, s = divmod(sec, 60)
                    h, m = divmod(m, 60)
                    row[elixir] = ((
                                       "-" if is_negative else "") + f'{int(h):0d}:{int(m):02d}:{int(s):02d}') if sec > 0 else ""

                if not any(row[i] for i in range(7, 12)):
                    del data[nick]

            values: dict = {"Last update:": [now_s, "(game time)."] + ([""] * 10),
                            "Nick": ["Link", "Citizenship", "Total Dmg", "Last Seen", "Premium", "Buffed At",
                                     "Debuff Ends", "Till Status Change"] + [x.title() for x in elixirs]}
            values.update(dict(sorted(data.items(), key=lambda x: (x[1][1], x[0]))))
            data.clear()
            if randint(1, 10) == 1:
                await spreadsheets(servers[server], "buffs", "!A1:M200",
                                   [([v[0], k] + v[1:12]) if k != "Last update:" else [k] + v for k, v in values.items()],
                                   delete=True)
            await replace_one("buffs", server, values)
            values.clear()
        except Exception as e:
            if len(str(e)) < 1000:
                traceback.print_exc()
            else:
                print("buffs long error")
        await asyncio.sleep(max(300 - time.time() + start, 1))


async def update_time(server: str) -> None:
    """update time db"""
    url = f'https://{server}.e-sim.org/'
    nick, cs, total_minutes, total_avg, month_minutes, month_avg = range(6)
    first_date = {
        "primera": ["Minutes online (since 10/12/20)", "09/12/2020", "10/12/2020"],
        "luxia": ["Minutes online (since day 1)", "10/02/2022", "11/02/2022"],
        "unica": ["Minutes online (since day 1)", "01/12/2022", "02/12/2022"],
        "sigma": ["Minutes online (since day 1)", "27/01/2023", "28/01/2023"],
        "azura": ["Minutes online (since day 1)", "16/03/2023", "17/03/2023"]}
    headers = ["Link", "Nick", "Citizenship",
               "Minutes online (since 19/05/2020)" if server not in first_date else first_date[server][0],
               "Avg. per day", "Minutes online (this month)", "Avg. per day"]
    while True:
        start = time.time()
        try:
            now = datetime.now().astimezone(pytz.timezone('Europe/Berlin'))
            data: dict = await find_one("time_online", server)
            if "_headers" in data:
                del data["_headers"]
            if now.strftime("%d %H:%M") in ("01 00:00", "01 00:01"):
                for k, v in data.items():
                    data[k][month_minutes] = 0

            for raw_player in await get_content(f"{url}apiOnlinePlayers.html"):
                row: dict = json.loads(raw_player)
                citizen_id = str(row['id'])
                if citizen_id in data:
                    data[citizen_id][total_minutes] += 1
                    data[citizen_id][month_minutes] += 1
                    data[citizen_id][cs] = get_countries(server, row['citizenship'])
                    data[citizen_id][nick] = row['login']
                else:
                    data[citizen_id] = [row['login'], get_countries(server, row['citizenship']), 1, "", 1, ""]

            date_1 = datetime.strptime("18/05/2020" if server not in first_date else first_date[server][1], "%d/%m/%Y")
            date_2 = datetime.strptime(f"01/{now.strftime('%m')}/{now.strftime('%Y')}", "%d/%m/%Y")
            today = datetime.strptime(now.strftime("%d/%m/%Y"), "%d/%m/%Y")
            end_date1 = (today - date_1).total_seconds() / 60
            end_date2 = (today - date_2 + (timedelta(days=1))).total_seconds() / 60
            for k, v in data.items():
                data[k][total_avg] = str(timedelta(minutes=int((v[total_minutes] / end_date1) * 24 * 60)))[:-3]
                data[k][month_avg] = str(timedelta(minutes=int((v[month_minutes] / end_date2) * 24 * 60)))[:-3]
            data = dict(sorted(data.items(), key=lambda x: (
                x[1][month_minutes], x[1][total_minutes]), reverse=True)[:3000 if len(data) < 3000 else 2900])
            data["_headers"] = headers[1:]
            await replace_one("time_online", server, data)
            del data["_headers"]
            if randint(1, 30) == 1:
                await spreadsheets(servers[server], "Time online", "!A1:G1000",
                                   [headers] + [[f"{url}profile.html?id={k}"] + v for k, v in data.items()][:999])
            data.clear()
        except Exception as e:
            tb = traceback.format_exc()
            if len(tb) < 1000:
                print(tb)
            else:
                print("time online long error")
        await asyncio.sleep(max(60 - time.time() + start, 1))


async def mm():
    date_format = "%d-%m-%Y %H:%M:%S"
    while True:
        mm_per_server: dict = {server: {} for server in servers}
        start = time.time()
        for server in reversed(list(servers)):
            url = f'https://{server}.e-sim.org/'
            # get data
            for country_id in countries_per_server[server]:
                try:
                    tree = await get_content(f'{url}monetaryMarketOffers?sellerCurrencyId=0&buyerCurrencyId={country_id}&page=1')
                    MM = float(tree.xpath("//*[@class='ratio']//b/text()")[0])

                except:
                    MM = 0
                mm_per_server[server][str(country_id)] = min(1.4, MM)
                await asyncio.sleep(0.35)

            # update history
            history: dict = await find_one("mm_history", server)
            today = datetime.now().astimezone(pytz.timezone('Europe/Berlin')).strftime("%d-%m-%Y")
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
            await replace_one("mm_history", server, history)
            history.clear()

            # update db
            await replace_one("mm", server, mm_per_server[server])

        now = datetime.now().astimezone(pytz.timezone('Europe/Berlin')).strftime(date_format)
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
                await spreadsheets(PRODUCT_SHEET, "Monetary Market", "!A1:K200", values, True)
            except Exception as e:
                if len(str(e)) < 1000:
                    traceback.print_exc()
                else:
                    print("MM long error")
        values.clear()
        await asyncio.sleep(max(3600 - time.time() + start, 1))


async def price(server: str) -> None:
    """Update price db"""
    url = f'https://{server}.e-sim.org/'
    while True:
        start = time.time()
        try:
            countries_cc: dict = {v: k for k, v in get_countries(server, index=2).items()}
            occupants: set = {i['occupantId'] for i in await get_content(f'{url}apiMap.html')}
            offers: dict = {}
            db_mm: dict = await find_one("mm", server)
            for page in range(1, 100):  # the last page is unknown
                tree = await get_content(f'{url}productMarket.html?countryId=-1&page={page}')
                raw_products = tree.xpath("//*[@class='productMarketOfferList']//*[@class='product']//div//img/@src") or \
                               tree.xpath("//*[@id='productMarketItems']//*[@class='product']//div//img/@src")
                products = []
                i = -1
                for product in raw_products:
                    product = product.replace("_", " ").split("/")[-1].split(".png")[0]
                    if product.startswith("q") and len(product) == 2:
                        products[i] = product.upper() + " " + products[i]
                    else:
                        products.append(product)
                        i += 1

                raw_prices = tree.xpath("//*[@class='productMarketOffer']//b/text()")
                cc = [x.strip() for x in tree.xpath("//*[@class='price']/div/text()") if x.strip()]
                stock = [int(x) for x in tree.xpath("//*[@class='quantity']//text()") if x.strip()]
                if len(cc) > len(stock): # old market view
                    raw_prices = tree.xpath("//*[@class='productMarketOffer']//b/text()")[::2]
                    cc = [x.strip() for x in tree.xpath("//*[@class='price']/div/text()") if x.strip()][::3]

                if len(raw_prices) < 15:  # last page
                    break
                for product, cc, price, stock in zip(products, cc, raw_prices, stock):
                    country = countries_cc[cc.lower()]
                    if country in occupants:
                        if product not in offers:
                            offers[product] = {}
                        if country not in offers[product]:
                            offers[product][country] = {"price": round(db_mm.get(str(country), 0) * float(price), 4),
                                                        "stock": stock}
                await asyncio.sleep(0.37)
            countries_cc.clear()
            occupants.clear()
            db_mm.clear()
            if server not in ('unica', 'sigma', 'azura'):
                this_month = "01-" + datetime.now().astimezone(pytz.timezone('Europe/Berlin')).strftime("%m-%Y")
            else:
                this_month = datetime.now().astimezone(pytz.timezone('Europe/Berlin')).strftime("%d-%m-%Y")
            now = datetime.now().astimezone(pytz.timezone('Europe/Berlin')).strftime("%d-%m-%Y %H:%M:%S")
            results: dict = {}
            for product, DICT in offers.items():
                if len(product.split()[0]) == 2:
                    quality = product.split()[0].replace("Q", "")
                    product_type = product.split()[1]
                else:
                    quality = 5
                    product_type = product.split()[0]

                # Delete 0 (no MM offers)
                DICT = sorted({k: v for k, v in DICT.items() if DICT[k]['price']}.items(), key=lambda x: x[1]["price"])[:5]
                FIND: dict = await find_one("prices_history", product)
                for count, (country, price_stock) in enumerate(DICT):
                    link = f"{url}productMarket.html?resource={product_type.upper()}&countryId={country}&quality={quality}"
                    MM = f"{url}monetaryMarket.html?buyerCurrencyId={country}"
                    p_price = str(price_stock["price"])
                    if not count:  # First loop
                        if server not in FIND:
                            FIND[server] = {}
                        if this_month not in FIND[server]:
                            FIND[server][this_month] = {}
                        if p_price not in FIND[server][this_month]:
                            FIND[server][this_month][p_price] = 0
                        FIND[server][this_month][p_price] += 1
                    if product not in results:
                        results[product] = []
                    results[product].append(
                        [price_stock["price"], price_stock["stock"], get_countries(server, country), link, MM])
                await replace_one("prices_history", product, FIND)
                FIND.clear()
            offers.clear()

            new_values: list = []
            headers: dict = {"Product": [
                ["Price", "Stock", "Country", "Link", "Monetary market", f"Last update: {now} (game time)."]]}
            headers.update(dict(sorted(results.items())))
            results = headers
            if len(results) > 1:
                await replace_one("price", server, results)
                for k, v in results.items():
                    for index, row in enumerate(v[:5]):
                        if index == 0:
                            new_values.append([k] + row)
                        else:
                            new_values.append([""] + row)
                    if len(new_values) > 1:
                        new_values.append(["", "-", "-", "-"])
                if randint(1, 3) == 1:
                    await spreadsheets(PRODUCT_SHEET, server, "!A1:G300", new_values, True)
            else:  # error
                continue
            results.clear()
            new_values.clear()
        except Exception as e:
            if len(str(e)) < 1000:
                traceback.print_exc()
            else:
                print("price long error")
        await asyncio.sleep(max(1000 - time.time() + start, 1))


loop = asyncio.get_event_loop()


async def start_time_buff() -> None:
    """start time and buff"""
    for server in servers:
        loop.create_task(update_time(server))
        loop.create_task(update_buffs(server))
        await asyncio.sleep(int(120 / len(servers)))


async def start_mm_price() -> None:
    """start mm and price"""
    loop.create_task(mm())
    await asyncio.sleep(30)
    for server in servers:
        loop.create_task(price(server))
        await asyncio.sleep(int(900 / len(servers)))


loop.create_task(start_time_buff())
loop.create_task(start_mm_price())
loop.run_forever()
