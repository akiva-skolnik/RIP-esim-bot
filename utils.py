import asyncio
import json
import os
import traceback
from random import randint
from typing import Union

import gspread_asyncio
from aiohttp import ClientSession
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from lxml.html import fromstring

from big_dicts import countries_per_id, countries_per_server

load_dotenv()

all_parameters: dict = {
    "avoid": "Chance to avoid damage",
    "max": "Increased maximum damage",
    "crit": "Increased critical hit chance",
    "damage": "Increased damage", "dmg": "Increased damage",
    "miss": "Miss chance reduction",
    "flight": "Chance for free flight",
    "consume": "Save ammunition",
    "eco": "Increased economy skill",
    "str": "Increased strength",
    "hit": "Increased hit",
    "less": "Less weapons for Berserk",
    "find": "Find a weapon",
    "split": "Improved split",
    "production": "Bonus * production",
    "merging": "Merge bonus",
    "merge": "Reduced equipment merge price",
    "restore": "Restoration",
    "increase": "Increase other parameters",
    "elixir": "Elixir time increased"
}

session = ClientSession(
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0"})
locked_session = ClientSession(
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0"})


def get_creds():
    """get creds callback"""
    creds = Credentials.from_service_account_file("credentials.json")
    return creds.with_scopes(["https://www.googleapis.com/auth/spreadsheets"])


agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)


async def spreadsheets(SPREADSHEET_ID: str, RANGE_NAME: str, columns: str = "!A:Z",
                       values: list = None, delete: bool = False) -> None:
    """Update spreadsheets"""
    agc = await agcm.authorize()
    ss = await agc.open_by_key(SPREADSHEET_ID)
    if delete:
        await ss.values_clear(RANGE_NAME + '!A:Z')
        await asyncio.sleep(0.5)
    await ss.values_update(RANGE_NAME + columns, params={'valueInputOption': 'USER_ENTERED'}, body={'values': values})


def get_countries(server: str, country: int = 0, index: int = -1) -> Union[str, dict]:
    """get countries"""
    if country:
        return countries_per_id.get(country, 'unknown')[0].title()
    per_id = {}
    for country_id in countries_per_server.get(server, []):
        if index < 0:
            per_id[country_id] = countries_per_id.get(country_id, ('no one', 'no one', 'no one'))
        else:
            per_id[country_id] = countries_per_id.get(country_id, ('unknown', 'unknown', 'unknown'))[index]
    return per_id


async def get_content(link: str, return_type: str = "", data: dict = None, session=session):
    if not return_type:
        if "api" in link:
            return_type = "json"
        else:
            return_type = "html"
    b = None
    for _ in range(10):
        try:
            async with (
                    session.get(link, ssl=False) if data is None else session.post(link, data=data,
                                                                                   ssl=False)) as respond:
                if "google.com" in str(respond.url) or respond.status == 403:
                    await asyncio.sleep(randint(3, 10))
                    continue
                if respond.status == 200:
                    if return_type == "json":
                        try:
                            api = await respond.json(content_type=None)
                        except:
                            await asyncio.sleep(randint(3, 10))
                            continue
                        return api
                    if return_type == "html":
                        try:
                            return fromstring(await respond.text())
                        except:
                            await asyncio.sleep(randint(3, 10))
                else:
                    await asyncio.sleep(randint(3, 10))
        except Exception as e:
            b = e
            await asyncio.sleep(randint(3, 10))
    if b:
        traceback.print_exception(b)
    raise ConnectionError(link)


async def get_locked_content(link: str, test_login: bool = False):
    """get locked content"""
    link = link.split("#")[0].replace("http://", "https://")
    server = link.split("https://", 1)[1].split(".e-sim.org", 1)[0]
    base_url = f"https://{server}.e-sim.org/"
    not_logged_in = False
    tree = None
    try:
        if not test_login:
            tree = await get_content(link, session=locked_session)
        else:
            tree = await get_content(base_url + "storage.html", session=locked_session)
        logged = tree.xpath('//*[@id="command"]')
        if any("login.html" in x.action for x in logged):
            not_logged_in = True
    except:
        not_logged_in = True
    if not_logged_in:
        payload = {'login': os.environ.get("NICK"), 'password': os.environ.get("PASSWORD"), "submit": "Login"}
        async with locked_session.get(base_url, ssl=False) as _:
            async with locked_session.post(base_url + "login.html", data=payload, ssl=False) as r:
                if "index.html?act=login" not in str(r.url):
                    print("failed to login " + server)
        tree = await get_content(link, session=locked_session)
    if test_login and not not_logged_in:
        tree = await get_content(link, session=locked_session)
    return tree


def get_id(string: str) -> str:
    return "".join(x for x in string.split("=")[-1].split("&")[0] if x.isdigit())


def get_ids_from_path(tree, path: str) -> list:
    ids = tree.xpath(path + "/@href")
    if ids and all("#" == x for x in ids):
        ids = [get_id(x.values()[-1]) for x in tree.xpath(path)]
    else:
        ids = [x.split("=")[-1].split("&")[0].strip() for x in ids]
    return ids


def get_eqs(tree) -> iter:
    for slot_path in tree.xpath('//*[@id="profileEquipmentNew"]//div//div//div//@title'):
        tree = fromstring(slot_path)
        try:
            slot = tree.xpath('//b/text()')[0].lower().replace("personal", "").replace("charm", "").replace(
                "weapon upgrade", "WU").replace("  ", " ").title().strip()
        except IndexError:
            continue
        eq_link = get_ids_from_path(tree, "//a")[0]
        parameters = []
        values = []
        for parameter_string in tree.xpath('//p/text()'):
            for x in all_parameters:
                if x in parameter_string.lower():
                    parameters.append(x)
                    try:
                        values.append(float(parameter_string.split(" ")[-1].replace("%", "").strip()))
                        break
                    except:
                        pass
        yield slot, parameters, values, eq_link


async def find_one(collection: str, _id: str) -> dict:
    filename = f"../db/{collection}_{_id}.json"
    if os.path.exists(filename):
        with open(filename, "r", encoding='utf-8') as file:
            return json.load(file)
    else:
        return {}


async def replace_one(collection: str, _id: str, data: dict) -> None:
    filename = f"../db/{collection}_{_id}.json"
    with open(filename, "w", encoding='utf-8', errors='ignore') as file:
        json.dump(data, file)
