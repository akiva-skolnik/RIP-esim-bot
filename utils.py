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

from constants import countries_per_id, countries_per_server

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

sessions = {}


async def get_session(locked: bool) -> ClientSession:
    """create session"""
    key = "locked" if locked else "regular"
    if key not in sessions:
        sessions[key] = ClientSession(headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0"})
    return sessions[key]


def get_creds():
    """get creds callback"""
    root = os.path.dirname(os.path.abspath(__file__))
    creds_path = os.path.join(root, "credentials.json")
    creds = Credentials.from_service_account_file(creds_path)
    return creds.with_scopes(["https://www.googleapis.com/auth/spreadsheets"])


agcm = gspread_asyncio.AsyncioGspreadClientManager(get_creds)


async def spreadsheets(spreadsheet_id: str, tab: str, columns: str = "A:Z",
                       values: list = None, delete: bool = False) -> None:
    """Update spreadsheets"""
    agc = await agcm.authorize()
    spreadsheet = await agc.open_by_key(key=spreadsheet_id)
    worksheet = await spreadsheet.worksheet(title=tab)
    if delete:
        await worksheet.clear()
        await asyncio.sleep(0.5)
    await worksheet.update(range_name=columns, values=values, raw=False)


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


async def get_content(link: str, return_type: str = "", data: dict = None, session=None):
    session = session or await get_session(locked=False)
    if not return_type:
        if "api" in link:
            return_type = "json"
        else:
            return_type = "html"
    b = None
    for _ in range(10):
        try:
            async with (session.get(link, ssl=False) if data is None else
            session.post(link, data=data, ssl=False)) as respond:
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
    link = link.split("#")[0].replace("http://", "https://")  # noqa
    server = link.split("https://", 1)[1].split(".e-sim.org", 1)[0]
    base_url = f"https://{server}.e-sim.org/"
    not_logged_in = False
    tree = None
    locked_session = await get_session(locked=True)
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
        payload = {'login': os.environ.get(server, os.environ.get("NICK")),
                   'password': os.environ.get("PASSWORD"), "submit": "Login"}
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
    root = os.path.dirname(os.path.abspath(__file__))
    filename = os.path.join(os.path.dirname(root), f"db/{collection}_{_id}.json")
    if os.path.exists(filename):
        with open(filename, "r", encoding='utf-8') as file:
            return json.load(file)
    else:
        return {}


async def replace_one(collection: str, _id: str, data: dict) -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    filename = os.path.join(os.path.dirname(root), f"db/{collection}_{_id}.json")
    with open(filename, "w", encoding='utf-8', errors='ignore') as file:
        json.dump(data, file)


def format_seconds(seconds):
    """Helper function to convert seconds to HH:MM:SS format."""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f'{int(h):02d}:{int(m):02d}:{int(s):02d}'


def extract_player_details(player_profile_link: str, tree: fromstring) -> dict:
    """Extract player details such as whether they are premium and their buffs."""
    try:
        premium = len(tree.xpath('//*[@class="premium-account"]')) == 1
        citizenship = tree.xpath('//*[@class="profile-row" and span = "Citizenship"]/span/span/text()')[0]
        damage = tree.xpath('//*[@class="profile-row" and span = "Damage"]/span/text()')[0]
        buffs_debuffs = [
            x.split("/specialItems/")[-1].split(".png")[0] for x in tree.xpath(
                '//*[@class="profile-row" and (strong="Debuffs" or strong="Buffs")]//img/@src') if
            "img/specialItems/" in x]
        buffs = [x.split("_")[0].lower() for x in buffs_debuffs if "positive" in x.split("_")[1:]]
        buffed = any(a in buffs for a in ('steroids', 'tank', 'bunker', 'sewer')) or any(
            "elixir" in x for x in buffs)
    except Exception as e:
        print(f"Error extracting player details for {player_profile_link}: {e}")
        return {}

    return {
        'premium': premium,
        'citizenship': citizenship,
        'damage': damage,
        'buffs': buffs,
        'buffed': buffed
    }
