"""utils.py"""
import json
import random
from asyncio import sleep
from collections import defaultdict
from copy import deepcopy
from csv import reader
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO
from os import path
from re import findall, finditer
from traceback import format_exception
from typing import List, Optional, Union
from warnings import filterwarnings

import pandas as pd
from discord import ButtonStyle, Embed, File, Interaction, Message, ui
from discord.app_commands import CheckFailure
from discord.ext import tasks
from discord.ext.commands import BadArgument, Cooldown
from discord.utils import MISSING
from lxml.html import fromstring
from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
from PIL import Image, ImageDraw, ImageFont
from pytz import timezone
from tabulate import tabulate

from bot.bot import bot

from .paginator import FieldPageSource, Pages


class CoolDownModified:
    """CoolDownModified"""
    def __init__(self, per, rate=1) -> None:
        self.rate = rate
        self.per = per

    async def __call__(self, message) -> Optional[Cooldown]:
        if is_premium_level_0(message):
            return None
        return Cooldown(self.rate, self.per)


hidden_guild = int(bot.config_ids["commands_server"])
font = path.join(path.dirname(__file__), "DejaVuSansMono.ttf")
filterwarnings("ignore")


def server_validation(server: str) -> str:
    """server validation"""
    server = server.lower().strip()
    if server in bot.all_servers:
        return server
    raise CheckFailure(f"`{server} ` is not a valid server.\nValid servers: " + ", ".join(bot.all_servers))


def human_format(num: int, precision: int = 1) -> str:
    """Number to human format"""
    suffixes = ['', 'K', 'M', 'B', 'T']
    m = sum(abs(num / 1000.0 ** x) >= 1 for x in range(1, len(suffixes)))
    return f'{num / 1000.0 ** m:.{precision}f}{suffixes[m]}'


async def extract_url(string: str) -> list:
    """extract url"""
    regex = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    return [x[0] for x in findall(regex, string.replace("*", ""))]


async def split_list(alist: list, wanted_parts: int) -> list:
    """split list into parts"""
    length = len(alist)
    small_lists = [alist[i * length // wanted_parts: (i + 1) * length // wanted_parts]
                   for i in range(wanted_parts)]
    return [x for x in small_lists if x]


async def chunker(seq: list, size: int) -> iter:
    """list to sub lists"""
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


def draw_pil_table(my_table: list, header: list, new_lines: int = 0) -> BytesIO:
    """draw table"""
    tabulate_table = tabulate(my_table, headers=header, tablefmt='grid', numalign="center", stralign="center")
    table_len = len(tabulate_table) / (len(my_table) * 2 + 3 + new_lines)
    img = Image.new('RGB', (int(60 * table_len), 300 + new_lines * 100 + len(my_table) * 200), color=(44, 47, 51))
    d = ImageDraw.Draw(img)
    d.text((10, 10), tabulate_table, font=ImageFont.truetype(font, 100))
    output_buffer = BytesIO()
    img.save(output_buffer, format='JPEG', subsampling=0, quality=95)
    output_buffer.seek(0)
    return output_buffer


async def bar(defender_dmg: int, attacker_dmg: int, defender: str = "", attacker: str = "", size: int = -1) -> str:
    """bar"""
    if size < 0:
        def_len = max(len(f"{defender_dmg:,}"), len(defender), len("defender"))
        att_len = max(len(f"{attacker_dmg:,}"), len(attacker), len("attacker"))
        size = 20 - (def_len + att_len) / 2
    if not defender_dmg + attacker_dmg:
        defender_dmg, attacker_dmg = 0.5, 0.5
    total = attacker_dmg + defender_dmg
    pct_1, pct_2 = f'{100 * defender_dmg / total:.1f}%', f'{100 * attacker_dmg / total:.1f}%'
    bar_n = round(size * defender_dmg / total)
    bar_1, bar_2 = '▓' * bar_n, '░' * int(size - bar_n)
    value = f'{pct_1} {bar_1}{bar_2} {pct_2}'
    if defender_dmg - attacker_dmg:
        diff = max([defender_dmg, attacker_dmg]) - min([defender_dmg, attacker_dmg])
        bigger = ("<" if attacker_dmg > defender_dmg else ">") * 3
        spaces = int((len(value) - (len(f"{diff:,}") + 4)) / 2) * " "
        code_block = f"\n`{spaces}{bigger} {diff:,} {bigger}{spaces}`"
        value += code_block
    return value


async def dmg_trend(hit_time: dict, server: str, battle_id: str) -> BytesIO:
    """dmg trend"""
    fig, ax = plt.subplots()
    for side, DICT in hit_time.items():
        ax.plot(DICT["time"], DICT["dmg"], label=side)
    ax.legend()
    ax.xaxis.set_major_formatter(DateFormatter("%d-%m %H:%M"))
    fig.autofmt_xdate()
    ax.set_title(f"Dmg Trend ({server}, {battle_id})")
    ax.set_ylabel('DMG')
    ax.set_xlabel('Time')
    ax.set_yticklabels([human_format(int(x)) for x in ax.get_yticks().tolist()])
    ax.grid()
    return plt_to_bytes()

async def get_auction(link: str) -> dict:
    """get auction"""
    tree = await get_content(link)
    seller = tree.xpath("//div[1]//table[1]//tr[2]//td[1]//a/text()")[0]
    buyer = tree.xpath("//div[1]//table[1]//tr[2]//td[2]//a/text()") or ["None"]
    item = tree.xpath("//*[@id='esim-layout']//div[1]//tr[2]//td[3]/b/text()")
    if not item:
        item = [x.strip() for x in tree.xpath("//*[@id='esim-layout']//div[1]//tr[2]//td[3]/text()") if
                x.strip()]
    price = tree.xpath("//div[1]//table[1]//tr[2]//td[4]//b//text()")[0]
    bidders = int(tree.xpath('//*[@id="esim-layout"]//div[1]//table//tr[2]//td[5]/b')[0].text)
    time1 = tree.xpath('//*[@id="esim-layout"]//div[1]//table//tr[2]//td[6]/span/text()')
    if not time1:
        time1 = [x.strip() for x in tree.xpath('//*[@id="esim-layout"]//div[1]//table//tr[2]//td[6]/text()') if
                 x.strip()]
        remaining_seconds = -1
    else:
        time1 = [int(x) for x in time1[0].split(":")]
        remaining_seconds = time1[0] * 60 * 60 + time1[1] * 60 + time1[2]
        time1 = [f'{time1[0]:02d}:{time1[1]:02d}:{time1[2]:02d}']
    return {"seller": seller.strip(), "buyer": buyer[0].strip(), "item": item[0],
            "price": price, "time": time1[0], "bidders": bidders, "remaining_seconds": remaining_seconds}


async def save_dmg_time(api_fights: str, attacker:str, defender: str) -> (dict, dict):
    """save dmg time"""
    my_dict = {defender: 0, attacker: 0}
    hit_time = {defender: {"dmg": [], "time": []}, attacker: {"dmg": [], "time": []}}
    for hit in reversed(await get_content(api_fights)):
        side = defender if hit['defenderSide'] else attacker
        my_dict[side] += hit['damage']
        hit_time[side]["time"].append(get_time(hit["time"]))
        if hit_time[side]["dmg"]:
            hit_time[side]["dmg"].append(hit_time[side]["dmg"][-1] + hit['damage'])
        else:
            hit_time[side]["dmg"].append(hit['damage'])
    return my_dict, hit_time

def plt_to_bytes() -> BytesIO:
    """plt to bytes"""
    output_buffer = BytesIO()
    plt.savefig(output_buffer)
    output_buffer.seek(0)
    plt.close()
    return output_buffer


async def _stop_alert(channel_id: str) -> None:
    await sleep(30)
    db_dict = await find_one("collection", "alert")
    for name_for_db in list(db_dict):
        for x in db_dict[name_for_db]:
            if channel_id in x:
                db_dict[name_for_db].remove(x)
            if not db_dict[name_for_db]:
                del db_dict[name_for_db]
    await replace_one("collection", "alert", db_dict)


"""
@tasks.loop(seconds=900)
async def update_donors():
    now = datetime.utcnow()
    guild = bot.get_guild(int(bot.config_ids["support_server"]))
    patreon = bot.get_user(216303189073461248)
    async for entry in guild.audit_logs(user=patreon):
        if entry.user.name == 'Patreon' and (now-entry.created_at).total_seconds() < 5*24*3600:  # 5 days
            bot.premium_users.update({str(entry.target.id): {"level": 0, "reason": "auto",
                                                     "nick": entry.target.name, "added_at": str(now)}})
"""


@tasks.loop(seconds=1000)
async def alert() -> None:
    """alert"""
    try:
        for name_for_db, list_of_requests in (await find_one("collection", "alert")).items():
            name_for_db = name_for_db.split()
            server, product_name = name_for_db[0], " ".join(name_for_db[1:])
            prices = await find_one("price", server)
            try:
                row = prices[product_name][0]
            except (KeyError, IndexError):
                continue
            for string in list_of_requests:
                channel_id, price = string.split()[-2:]
                try:
                    channel = bot.get_channel(int(channel_id))
                    if row[0] < float(price):
                        await channel.send(f"The price of {product_name} at {server} is {row[0]} (below {price})\n"
                                           f"For more info, type /price")
                        await _stop_alert(channel_id)
                        continue
                except Exception:
                    await _stop_alert(channel_id)
                await sleep(1)
    except Exception as error:
        await send_error(None, error, cmd="alert")


async def not_support(interaction: Interaction) -> bool:
    """not support channel"""
    if interaction.guild and str(interaction.guild.id) == bot.config_ids["support_server"]:
        await custom_followup(interaction, "You can't use this command on support channel. Go spam somewhere else!")
        return False
    return True


ranks = {'Rookie': 1, 'Private': 1.1, 'Private First Class': 1.2, 'Corporal': 1.3, 'Sergeant': 1.4,
         'Staff Sergeant': 1.5, 'Sergeant First Class': 1.6, 'Master Sergeant': 1.65, 'First Sergeant': 1.7,
         'Sergeant Major': 1.75, 'Command Sergeant Major': 1.8, 'Sergeant Major of the Army': 1.85,
         'Second Lieutenant': 1.9, 'First Lieutenant': 1.93, 'Captain': 1.96, 'Major': 2, 'Lieutenant Colonel': 2.03,
         'Colonel': 2.06, 'Brigadier General': 2.1, 'Major General': 2.13, 'Lieutenant General': 2.16, 'General': 2.19,
         'General of the Army': 2.21, 'Marshall': 2.24, 'Field Marshall': 2.27, 'Supreme Marshall': 2.3,
         'Generalissimus': 2.33, 'Supreme Generalissimuss': 2.36, 'Imperial Generalissimus': 2.4,
         'Legendary Generalissimuss': 2.42, 'Imperator': 2.44, 'Imperator Caesar': 2.46, 'Deus Dimidiam': 2.48,
         'Deus': 2.5, 'Summi Deus': 2.52, 'Deus Imperialis': 2.54, 'Deus Fabuloso': 2.56, 'Deus Ultimum': 2.58,
         'Destroyer': 2.6, 'Annihilator': 2.62, 'Executioner': 2.64, 'Slaughterer': 2.66, 'Exterminator': 2.68,
         'Almighty': 2.7, 'Demigod': 2.72, 'Divinity': 2.74, 'Angelus censura': 2.77, 'Angelus crudelis': 2.8,
         'Angelus destructo': 2.83, 'Angelus dux ducis': 2.86, 'Angelus eximietate': 2.9, 'Angelus exitiabilis': 2.95,
         'Angelus extremus': 3, 'Angelus caelestis': 3.05, 'Angelus infinitus': 3.1, 'Angelus invictus': 3.15,
         'Angelus legatarius': 3.2, 'Angelus mortifera': 3.25}


async def dmg_calculator(api: dict, bonuses: str = "new") -> dict:
    """
    Damage formula:

    ED = AD * H * W * DS * L * MU * Buff * (1+C-M)

    [H = BH * (1+A)]

        ED = Estimated total damage.
        AD = Average damage (min hit + max hit)/2.
        W = Weapon quality.
        H = Estimated number of hits.
        DS = Defense System quality (1.0 if no DS, 1.05~1.25 if there is Q1~Q5 DS). [Q0/5 in this function]
        L = Location bonus (1.2 if you're located in the battlefield as a defender or in resistance wars,
            or next to the battlefield as an attacker, 1.0 if not, 0.8 if no route to core regions)
        MU = Military unit order bonus (1.0 if no order, 1.05-1.20 if fight in order depending on MU type) [no MU / elite MU in this function]
        Buff = special item bonus (1.2 if tank is on * 1.2 if steroid is on * 1.25 if bunker or sewer guide is on, 0.8 if debuffed)
        C = Critical chance (0.125-0.4)
        M = Miss chance (0-0.125)

        BH = basic number of hits (depends on the quality and quantity of food and gifts you want to use (10 q5 food = 50))
        A = Avoid chance (0.05-0.4)
    """

    counted_bonuses = {"stats": {}, "bonuses": {}}

    bonuses = bonuses.replace(",", " ").lower().split()
    bonuses = [x.strip() for x in bonuses]  # Delete spaces.

    if "new" in bonuses:
        # Change strength from eqs, according to the change in total strength.
        api['eqIncreaseStrength'] = 300 * api['eqIncreaseStrength'] / api['strength']
        api['rank'] = 'Rookie'
        api['strength'] = 300
        counted_bonuses["stats"]["as new player"] = "300 strength, first rank"

    limits = [x.replace("x", "") for x in bonuses if x.startswith("x")]
    limits = 1 if not limits else int(limits[0])

    military_rank = ranks[api['rank']]
    strength = api['strength'] + api['eqIncreaseStrength']
    min_damage = 0.01 * api['eqIncreaseDamage']
    max_damage = 0.01 * api['eqIncreaseMaxDamage']

    AD = (military_rank * strength * 0.8 * (1 + min_damage) +
          (military_rank * strength * 1.2 * (1 + min_damage + max_damage))
          ) / 2  # (min hit + max hit)/2
    BH = limits * 5
    A = api['eqAvoidDamage'] * 0.01
    C = api['eqCriticalHit'] * (2 if "pd" in bonuses else 1) * 0.01
    M = api['eqReduceMiss'] * 0.01
    H = BH / (1 - A)

    qualities = [x for x in bonuses if x.startswith("q")]
    quality = 5 if not qualities else int(qualities[0].split("q")[1])
    W = (1 + 0.2 * quality) if quality else 0.5

    DS = 1.25 if "ds" in bonuses else 1
    L = 1
    if "location" in bonuses:
        L = 1.2
        counted_bonuses["bonuses"]["location"] = "20%"
    elif "-location" in bonuses:
        L = 0.8
        counted_bonuses["bonuses"]["debuff location"] = "-20%"
    MU = 1.2 if "mu" in bonuses else 1

    tank = 1
    if "tank" in bonuses and quality == 5:
        tank = 1.2
        counted_bonuses["bonuses"]["tank"] = "20%"
    elif "-tank" in bonuses:
        W = 0.5
        counted_bonuses["bonuses"]["debuff tank"] = "-20%"

    steroids = 1
    if "steroids" in bonuses:
        steroids = 1.2
        counted_bonuses["bonuses"]["steroids"] = "20%"
    elif "-steroids" in bonuses:
        steroids = 0.8
        counted_bonuses["bonuses"]["debuff steroids"] = "-20%"

    core = 1
    if "bunker" in bonuses or "sewer" in bonuses:
        core = 1.25
        counted_bonuses["bonuses"]["core"] = "25%"
    elif "-bunker" in bonuses or "-sewer" in bonuses:
        core = 0.8
        counted_bonuses["bonuses"]["debuff core"] = "-20%"

    buff = tank * steroids * core

    bonus_dmg = [x.replace("%", "") for x in bonuses if x.endswith("%")]
    bonus_dmg = 1 if not bonus_dmg else (1 + int(bonus_dmg[0]) * 0.01)

    ED = AD * H * W * DS * L * MU * buff * bonus_dmg * (1 + C - M)

    if MU > 1:
        counted_bonuses["bonuses"]["MU"] = "20%"
    if DS > 1:
        counted_bonuses["bonuses"]["Q5 DS"] = "25%"
    if bonus_dmg:
        counted_bonuses["bonuses"]["bonus dmg"] = f"{(bonus_dmg - 1) * 100}%"
    counted_bonuses["bonuses"].update({"limits": limits, "weps": f"Q{quality}"})
    counted_bonuses["stats"].update({"rank": f"{api['rank']} ({military_rank})", "strength": round(strength),
                                     "Increase dmg": api['eqIncreaseDamage'], "max": api['eqIncreaseMaxDamage'],
                                     "avoid": api['eqAvoidDamage'], "crit": C * 100,
                                     "miss": api['eqReduceMiss']})
    return {"avoid": round(ED), "clutch": round(ED / H * BH), "hits": round(H), "bonuses": counted_bonuses["bonuses"],
            "stats": counted_bonuses["stats"]}


def csv_to_txt(content: bytes) -> BytesIO:
    """csv to text file"""
    text = "[table]"
    indexes = defaultdict(lambda: [])
    num = -1
    for row in reader(StringIO(content.decode()), delimiter=","):
        row_len = len(row)
        if all(x == "-" for x in row) or all(not x for x in row):
            indexes = defaultdict(lambda: [])
            num = -1
            text += "[/table]\n[table]"
            continue
        num += 1
        for column_index, column in enumerate(row):
            column = column.replace("\n", "\\n")
            if not num:
                if column.lower() in ["nick", "shareholders", "login", "seller", "buyer", "cp", "citizenid",
                                      "citizen id"]:
                    indexes["citizen"].append(column_index)
                elif column.lower() in ["cs", "citizenship", "country", "side", "defender", "attacker"]:
                    indexes["flag"].append(column_index)
                elif column.lower() in ["sc", "stock company", "sc id"]:
                    indexes["stockcompany"].append(column_index)

            if column_index + 1 != row_len and column == "0":
                column = ""
            if num:
                for k, v in indexes.items():
                    if column_index in v:
                        column = f"[{k}]{column}[/{k}]"
                        break

            try:
                column = int(float(column))
                column = f"{column:,}".replace(",", ".")
            except ValueError:
                pass
            text += f"{column},"

            if column_index + 1 == row_len:
                text = text[:-1]

        text += "|"
    text = text[:-1] + "[/table]"
    output = BytesIO()
    output.write(text.encode())
    output.seek(0)
    return output


def camel_case_merge(identifier: str) -> str:
    """camel case merge"""
    matches = finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)', identifier)
    return " ".join([m.group(0) for m in matches]).title()


async def get_content(link: str, return_type: str = "", method: str = "get", session = None, throw: bool = False):
    """get content"""
    if not return_type:
        if "api" in link or link.startswith(bot.api):
            return_type = "json"
        else:
            return_type = "html"
    server = link.split("#")[0].replace("http://", "https://").split("https://")[1].split(".e-sim.org")[0]
    if not session:
        session = bot.session
    for _ in range(5):
        try:
            async with session.get(link, ssl=False) if method == "get" else session.post(
                    link, ssl=False) as respond:
                if "google.com" in str(respond.url) or respond.status == 403:
                    await sleep(2)
                    continue
                if "NO_PRIVILEGES" in str(respond.url):
                    raise IOError("NO_PRIVILEGES")
                if any(t in str(respond.url) for t in ("notLoggedIn", "error")):
                    raise BadArgument(f"This page is locked for bots.\n"
                                      f"(Try open this page after logging out or in a private tab {link.replace(' ', '+')} )\n\n"
                                      f"If you want this command to work again, you should ask `Liberty Games Interactive#3073` to reopen this page.")
                if respond.status == 500:
                    raise OSError(500)
                if respond.status == 200:
                    if return_type == "json":
                        try:
                            api = await respond.json(content_type=None)
                        except Exception as error:
                            if throw:
                                raise error
                            await sleep(2)
                            continue
                        if "error" in api:
                            error_msg = str(respond.url).replace(" ", "+") + "\n**Error:** " + api["error"]
                            if api["error"] == "No citizen with such a name":
                                error_msg += f"\n\n**Did you mean...**\nhttps://{server}.e-sim.org/search.html?search=" \
                                             f"{link.split('=')[-1].replace(' ', '+')}&searchInactive=true"
                            raise BadArgument(error_msg)
                        return api if "apiBattles" not in link else api[0]
                    if return_type == "html":
                        try:
                            return fromstring(await respond.text())
                        except Exception:
                            await sleep(2)
                else:
                    await sleep(2)
        except Exception as error:
            if isinstance(error, (BadArgument, OSError)) or throw:
                raise error
            await sleep(2)

    raise OSError(link)


async def get_locked_content(link: str, test_login: bool = False, method: str = "get", org: bool = False):
    """get locked content"""
    link = link.split("#")[0].replace("http://", "https://")
    server = link.split("https://", 1)[1].split(".e-sim.org", 1)[0]
    if not org:
        nick, password = bot.config.get(server, bot.config['nick']), bot.config.get(server+"_password", bot.config['password'])
        session = bot.locked_session
    else:
        nick = bot.orgs[server][0]
        password = bot.orgs[server][1]
        session = bot.org_session
    base_url = f"https://{server}.e-sim.org/"
    not_logged_in = False
    tree = None
    try:
        if not test_login:
            tree = await get_content(link, method=method, session=session)
        else:
            tree = await get_content(base_url + "storage.html", method=method, session=session)
        logged = tree.xpath('//*[@id="command"]')
        if any("login.html" in x.action for x in logged):
            not_logged_in = True
    except Exception as error:
        if "This page is locked for bots." not in str(error):
            raise error
        not_logged_in = True
    if not_logged_in:
        payload = {'login': nick, 'password': password, "submit": "Login"}
        async with session.get(base_url, ssl=False) as _:
            async with session.post(base_url + "login.html", data=payload, ssl=False) as r:
                if "index.html?act=login" not in str(r.url):
                    raise BadArgument("This command is currently unavailable")
        tree = await get_content(link, method=method, session=session)
    if test_login and not not_logged_in:
        tree = await get_content(link, method=method, session=session)
    return tree


async def update_percent(current_id: int, ids_length: int, msg: Message) -> Message:
    """update percent"""
    current_id += 1
    edit_at = [int(ids_length / 10 * x) for x in range(1, 11)]
    try:
        if current_id >= ids_length - 3:
            try:
                await msg.edit(content="Progress status: 100%", attachments=[])
                return msg
            except Exception:
                pass
        elif current_id in edit_at:
            return await msg.edit(content=f"Progress status: {(edit_at.index(current_id) + 1) * 10}%."
                                          "\n(I will update this message every 10%)")
    except Exception:
        pass
    return msg


async def is_premium_level_0(interaction: Interaction) -> bool:  # reset cooldown
    """for cooldown reset"""
    return bot.premium_users.get(str(interaction.user.id), {}).get("level", -1) >= 0


async def is_premium_level_1(interaction: Interaction, send_error_msg: bool = True, allow_trial: bool = True) -> bool:
    """is premium"""
    # remove expired users
    expire_at = bot.premium_users.get(str(interaction.user.id), {}).get("expire_at", "")
    if expire_at and datetime.strptime(expire_at, "%d/%m/%Y") < datetime.now():
        del bot.premium_users[str(interaction.user.id)]

    today = str(date.today())
    if bot.premium_users.get(str(interaction.user.id), {}).get("level", -1) >= 1 or (
            interaction.guild and str(interaction.guild.id) in bot.premium_servers):
        return True
    if allow_trial and bot.premium_users.get(str(interaction.user.id), {}).get("added_at", "") != today:
        bot.premium_users[str(interaction.user.id)] = {"added_at": today}
        await replace_one("collection", "donors", bot.premium_users)
        return True
    if send_error_msg:
        raise CheckFailure("You have used your premium limit for today.\n"
                           "You can try again tomorrow, or visit https://www.buymeacoffee.com/RipEsim")
    return False


async def default_nick(interaction: Interaction, server: str, nick: str = "-") -> str:
    """default nick"""
    if nick == "-":
        return ""
    if nick:
        return nick
    if str(interaction.user.id) in bot.default_nick_dict:
        nick = bot.default_nick_dict[str(interaction.user.id)].get(server)
    if nick == "-":
        return ""
    return nick or interaction.user.name


async def custom_delay(interaction: Interaction) -> None:
    """custom delay"""
    if str(interaction.user.id) not in bot.custom_delay_dict:
        await sleep(0.4)
    else:
        await sleep(bot.custom_delay_dict[str(interaction.user.id)])


async def send_error(interaction: Optional[Interaction], error: Exception, cmd: str = "") -> None:
    """send error"""
    if interaction:
        data = interaction.data["name"] + " " + "  ".join(
            f"**{x['name']}**: {x.get('value')}" for x in interaction.data.get('options', []))
    else:
        data = cmd
    msg = f"[{datetime.now().astimezone(timezone('Europe/Berlin')).strftime(bot.date_format)}] : {data}"
    error_channel = bot.get_channel(int(bot.config_ids["error_channel"]))
    try:
        await error_channel.send(
            f"{msg}\n```{''.join(format_exception(type(error), error, error.__traceback__))}```")
    except Exception:  # Big msg
        await error_channel.send(f"{msg}\n{error}"[:1900])
    if interaction is None:
        return
    custom_error = f"```{str(error).strip() or 'Timeout!'}\n```\n `The program {cmd if cmd else interaction.command.name} has halted.`"
    await custom_followup(interaction, custom_error if not cmd else
                            custom_error + f"The following results do not include ID {cmd} onwards")


class Confirm(ui.View):
    """Confirm"""
    def __init__(self) -> None:
        super().__init__()
        self.value = None

    @ui.button(label='Confirm', style=ButtonStyle.green)
    async def confirm(self, interaction: Interaction, button: ui.Button) -> None:
        """confirm"""
        self.value = True
        self.clear_items()
        self.stop()

    @ui.button(label='Cancel', style=ButtonStyle.grey)
    async def cancel(self, interaction: Interaction, button: ui.Button) -> None:
        """cancel"""
        self.value = False
        self.clear_items()
        self.stop()


class StopNext(ui.View):
    """Stop and next"""
    def __init__(self, interaction: Interaction) -> None:
        super().__init__()
        self.canceled = None
        self.next_page = None
        self.interaction = interaction
        self.next.disabled = False

    @ui.button(label='Next Page', style=ButtonStyle.blurple)
    async def next(self, interaction: Interaction, button: ui.Button) -> None:
        """Next Page"""
        self.next_page = True
        button.disabled = True
        await self.interaction.edit_original_response(view=self)
        await custom_followup(interaction, "Scanning more players...", ephemeral=True)
        self.stop()

    @ui.button(label='Stop', style=ButtonStyle.red)
    async def cancel(self, interaction: Interaction, button: ui.Button) -> None:
        """cancel"""
        self.canceled = True
        self.clear_items()
        self.stop()


class WaitForNext(ui.View):
    """Wait for next button"""
    def __init__(self) -> None:
        super().__init__()
        self.value = None

    @ui.button(label='Convert Ids', style=ButtonStyle.blurple)
    async def convert(self, interaction: Interaction, button: ui.Button) -> None:
        """Convert Ids"""
        await custom_followup(interaction, "Just a few moments...", ephemeral=True)
        self.value = True
        self.clear_items()
        self.stop()


async def custom_author(embed: Embed) -> Embed:
    """Add link for donations"""
    if random.randint(1, 100) > 80:
        return embed
    if not embed.title and not embed.url:
        embed.title = "Would you like to buy me a coffee? ☕"
        embed.url = "https://www.buymeacoffee.com/RipEsim"
    elif not embed.description:
        embed.description = "[Would you like to buy me a coffee?](https://www.buymeacoffee.com/RipEsim)"
    else:
        embed.set_author(name="Buy me a coffee ☕", url="https://www.buymeacoffee.com/RipEsim",
                         icon_url="https://c.tenor.com/N0NBKhTbAcMAAAAC/good-morning.gif")
    return embed


async def convert_embed(interaction_or_author: Union[Interaction, int], embed: Embed, is_columns: bool = True) -> Embed:
    """convert embed to phone format + add fix and donate link"""
    embed = await custom_author(embed)
    if not is_columns:
        return embed
    interaction = interaction_or_author
    author_id = str(interaction.user.id) if not isinstance(interaction, int) else str(interaction)
    embed_fields = embed.fields
    my_range = iter(range(len(embed_fields)))

    def is_ascii(s: str) -> bool:
        return all(ord(c) < 128 for c in s)

    if author_id not in bot.phone_users:
        for index in my_range:
            if not isinstance(interaction, int) and not interaction.channel.permissions_for(interaction.user).external_emojis:
                break
            try:
                first_item = embed_fields[index].value.splitlines()[0]
            except IndexError:
                continue
            if "fix" not in first_item and (
                    is_ascii(first_item) or "%" in first_item) and embed_fields[index].value.count("\n") > 3:
                embed.set_field_at(index, name=embed_fields[index].name,
                                   value=embed_fields[index].value.replace("\n", " <:fix:824351642103185408>\n"),
                                   inline=embed_fields[index].inline)
        if is_columns and not embed.footer and len(embed_fields) > 1 and any("\n" in f.value for f in embed_fields):
            embed.set_footer(text="type `!phone` if it looks ugly")
        return embed

    indexes = {}
    for index in my_range:
        length = len(embed_fields[index].value.splitlines())
        if length == 1:
            continue
        try:
            for i in range(1, 3):
                if embed_fields[index].name == embed_fields[index + 1].name:
                    continue
                if length == len(embed_fields[index + i].value.splitlines()):
                    if index not in indexes:
                        indexes[index] = 1
                    else:
                        indexes[index] += 1
            for _ in range(indexes.get(index, 0)):
                next(my_range, None)
        except (IndexError, StopIteration):
            break

    if not indexes:
        return embed

    for first, columns in reversed(indexes.items()):
        columns += 1
        for index in reversed(range(first, first + columns)):
            embed.remove_field(index)
        embed.insert_field_at(first, name="\n".join([field.name for field in embed_fields[first:first + columns]]),
                              value="\u200B",
                              inline=False)
        my_list = []
        for LIST in [[embed_fields[x + first].value.splitlines()[i] for x in range(columns)] for i in
                     range(len(embed_fields[0 + first].value.splitlines()))]:
            my_list.append(LIST)
        for index, LIST in enumerate(await split_list(my_list, 3)):
            embed.insert_field_at(index + first + 1, name="\u200B", value="\n".join(["\n".join(x) for x in LIST]))

    if not embed.footer:
        embed.set_footer(text="That is an auto phone format. Type `/phone` to change this preference")

    return embed


async def send_long_embed(interaction: Interaction, embed: Embed, headers: list, result: list, files: List[File] = MISSING) -> None:
    """send long embed"""
    for index, header in enumerate(headers):
        embed.add_field(name=header, value="\n".join([str(x[index]) for x in result]))
    embed1 = await convert_embed(interaction, deepcopy(embed))
    result = [(embed if str(interaction.user.id) in bot.phone_users else embed1).fields[index].value.splitlines() for
              index in range(3)]
    result = list(zip(*result))
    pages = max(sum(len(str(x[index])) for x in result) for index in range(3)) // 950 + 1
    chunks = await split_list(result, pages)
    chunks = [(headers[i], "\n".join([str(x[i]) for x in c])) for c in chunks for i in range(3)]
    source = FieldPageSource(chunks, inline=True, per_page=3, clear_description=False, embed=embed)
    pages = Pages(source, interaction=interaction, embed=embed)
    await pages.start(files=files)
    return


async def csv_to_image(output: StringIO, columns: int = 10):
    """Convert csv file to image"""
    headers = []
    table = []
    for index, row in enumerate(reader(output)):
        if not index:
            headers = row[:columns]
        elif index <= 10:
            table.append(row[:columns])
        else:
            break
    output.seek(0)
    return await bot.loop.run_in_executor(None, draw_pil_table, table, headers)


async def last_page(link: str, func=get_content, **kwargs) -> int:
    """Get last page"""
    tree = await func(link, **kwargs)
    last = get_ids_from_path(tree, "//ul[@id='pagination-digg']//li[last()-1]/a") or ['1']
    last = int(last[0])
    if last > 1000000:
        tree = await func(link + f"&page={last}", **kwargs)
        last = int(tree.xpath('//*[@id="pagingInput"]')[0].value)
    return last + 1


flags_codes = {
    'defender': '\u2694', 'attacker': '\u2620', 'poland': '\U0001f1f5\U0001f1f1', 'russia': '\U0001f1f7\U0001f1fa',
    'germany': '\U0001f1e9\U0001f1ea', 'france': '\U0001f1eb\U0001f1f7', 'spain': '\U0001f1ea\U0001f1f8',
    'united kingdom': '\U0001f1ec\U0001f1e7', 'italy': '\U0001f1ee\U0001f1f9',
    'hungary': '\U0001f1ed\U0001f1fa', 'romania': '\U0001f1f7\U0001f1f4', 'bulgaria': '\U0001f1e7\U0001f1ec',
    'serbia': '\U0001f1f7\U0001f1f8', 'croatia': '\U0001f1ed\U0001f1f7',
    'bosnia and herzegovina': '\U0001f1e7\U0001f1e6', 'greece': '\U0001f1ec\U0001f1f7',
    'republic of macedonia': '\U0001f1f2\U0001f1f0', 'ukraine': '\U0001f1fa\U0001f1e6',
    'sweden': '\U0001f1f8\U0001f1ea', 'portugal': '\U0001f1f5\U0001f1f9', 'lithuania': '\U0001f1f1\U0001f1f9',
    'latvia': '\U0001f1f1\U0001f1fb', 'slovenia': '\U0001f1f8\U0001f1ee', 'turkey': '\U0001f1f9\U0001f1f7',
    'brazil': '\U0001f1e7\U0001f1f7', 'argentina': '\U0001f1e6\U0001f1f7', 'mexico': '\U0001f1f2\U0001f1fd',
    'usa': '\U0001f1fa\U0001f1f8', 'canada': '\U0001f1e8\U0001f1e6', 'china': '\U0001f1e8\U0001f1f3',
    'indonesia': '\U0001f1ee\U0001f1e9', 'iran': '\U0001f1ee\U0001f1f7', 'south korea': '\U0001f1f0\U0001f1f7',
    'taiwan': '\U0001f1f9\U0001f1fc', 'israel': '\U0001f1ee\U0001f1f1', 'india': '\U0001f1ee\U0001f1f3',
    'australia': '\U0001f1e6\U0001f1fa', 'netherlands': '\U0001f1f3\U0001f1f1',
    'finland': '\U0001f1eb\U0001f1ee', 'ireland': '\U0001f1ee\U0001f1ea',
    'switzerland': '\U0001f1e8\U0001f1ed', 'belgium': '\U0001f1e7\U0001f1ea',
    'pakistan': '\U0001f1f5\U0001f1f0', 'malaysia': '\U0001f1f2\U0001f1fe', 'norway': '\U0001f1f3\U0001f1f4',
    'peru': '\U0001f1f5\U0001f1ea', 'chile': '\U0001f1e8\U0001f1f1', 'colombia': '\U0001f1e8\U0001f1f4',
    'montenegro': '\U0001f1f2\U0001f1ea', 'austria': '\U0001f1e6\U0001f1f9',
    'slovakia': '\U0001f1f8\U0001f1f0', 'denmark': '\U0001f1e9\U0001f1f0',
    'czech republic': '\U0001f1e8\U0001f1ff', 'belarus': '\U0001f1e7\U0001f1fe',
    'estonia': '\U0001f1ea\U0001f1ea', 'philippines': '\U0001f1f5\U0001f1ed',
    'albania': '\U0001f1e6\U0001f1f1', 'venezuela': '\U0001f1fb\U0001f1ea', 'egypt': '\U0001f1ea\U0001f1ec',
    'japan': '\U0001f1ef\U0001f1f5', 'bangladesh': '\U0001f1e7\U0001f1e9', 'vietnam': '\U0001f1fb\U0001f1f3',
    'yemen': '\U0001f1fe\U0001f1ea', 'saudi arabia': '\U0001f1f8\U0001f1e6',
    'thailand': '\U0001f1f9\U0001f1ed', 'algeria': '\U0001f1e9\U0001f1ff', 'angola': '\U0001f1e6\U0001f1f4',
    'cameroon': '\U0001f1e8\U0001f1f2', 'ivory coast': '\U0001f1e8\U0001f1ee',
    'ethiopia': '\U0001f1ea\U0001f1f9', 'ghana': '\U0001f1ec\U0001f1ed', 'kenya': '\U0001f1f0\U0001f1ea',
    'libya': '\U0001f1f1\U0001f1fe', 'morocco': '\U0001f1f2\U0001f1e6', 'mozambique': '\U0001f1f2\U0001f1ff',
    'nigeria': '\U0001f1f3\U0001f1ec', 'senegal': '\U0001f1f8\U0001f1f3',
    'south africa': '\U0001f1ff\U0001f1e6', 'sudan': '\U0001f1f8\U0001f1e9',
    'tanzania': '\U0001f1f9\U0001f1ff', 'togo': '\U0001f1f9\U0001f1ec', 'tunisia': '\U0001f1f9\U0001f1f3',
    'uganda': '\U0001f1fa\U0001f1ec', 'zambia': '\U0001f1ff\U0001f1f2', 'zimbabwe': '\U0001f1ff\U0001f1fc',
    'botswana': '\U0001f1e7\U0001f1fc', 'benin': '\U0001f1e7\U0001f1ef',
    'burkina faso': '\U0001f1e7\U0001f1eb', 'congo': '\U0001f1e8\U0001f1ec',
    'central african republic': '\U0001f1e8\U0001f1eb', 'dr of the congo': '\U0001f1e8\U0001f1e9',
    'eritrea': '\U0001f1ea\U0001f1f7', 'gabon': '\U0001f1ec\U0001f1e6', 'chad': '\U0001f1f9\U0001f1e9',
    'niger': '\U0001f1f3\U0001f1ea', 'mali': '\U0001f1f2\U0001f1f1', 'mauritania': '\U0001f1f2\U0001f1f7',
    'guinea': '\U0001f1ec\U0001f1f3', 'guinea bissau': '\U0001f1ec\U0001f1fc',
    'sierra leone': '\U0001f1f8\U0001f1f1', 'liberia': '\U0001f1f1\U0001f1f7',
    'equatorial guinea': '\U0001f1ec\U0001f1f6', 'namibia': '\U0001f1f3\U0001f1e6',
    'lesotho': '\U0001f1f1\U0001f1f8', 'swaziland': '\U0001f1f8\U0001f1ff',
    'madagascar': '\U0001f1f2\U0001f1ec', 'malawi': '\U0001f1f2\U0001f1fc', 'somalia': '\U0001f1f8\U0001f1f4',
    'djibouti': '\U0001f1e9\U0001f1ef', 'rwanda': '\U0001f1f7\U0001f1fc', 'burundi': '\U0001f1e7\U0001f1ee',
    'united arab emirates': '\U0001f1e6\U0001f1ea', 'syria': '\U0001f1f8\U0001f1fe',
    'iraq': '\U0001f1ee\U0001f1f6', 'oman': '\U0001f1f4\U0001f1f2', 'qatar': '\U0001f1f6\U0001f1e6',
    'jordan': '\U0001f1ef\U0001f1f4', 'western sahara': '\U0001f1ea\U0001f1ed',
    'the gambia': '\U0001f1ec\U0001f1f2', 'south sudan': '\U0001f1f8\U0001f1f8',
    'cambodia': '\U0001f1f0\U0001f1ed', 'nepal': '\U0001f1f3\U0001f1f5', 'bolivia': '\U0001f1e7\U0001f1f4',
    'ecuador': '\U0001f1ea\U0001f1e8', 'paraguay': '\U0001f1f5\U0001f1fe', 'uruguay': '\U0001f1fa\U0001f1fe',
    'honduras': '\U0001f1ed\U0001f1f3', 'dominican republic': '\U0001f1e9\U0001f1f4',
    'guatemala': '\U0001f1ec\U0001f1f9', 'kazakhstan': '\U0001f1f0\U0001f1ff',
    'sri lanka': '\U0001f1f1\U0001f1f0', 'afghanistan': '\U0001f1e6\U0001f1eb',
    'armenia': '\U0001f1e6\U0001f1f2', 'azerbaijan': '\U0001f1e6\U0001f1ff', 'georgia': '\U0001f1ec\U0001f1ea',
    'kyrgyzstan': '\U0001f1f0\U0001f1ec', 'laos': '\U0001f1f1\U0001f1e6', 'tajikistan': '\U0001f1f9\U0001f1ef',
    'turkmenistan': '\U0001f1f9\U0001f1f2', 'uzbekistan': '\U0001f1fa\U0001f1ff',
    'new zealand': '\U0001f1f3\U0001f1ff', 'guyana': '\U0001f1ec\U0001f1fe',
    'suriname': '\U0001f1f8\U0001f1f7', 'nicaragua': '\U0001f1f3\U0001f1ee', 'panama': '\U0001f1f5\U0001f1e6',
    'costa rica': '\U0001f1e8\U0001f1f7', 'mongolia': '\U0001f1f2\U0001f1f3',
    'papua new guinea': '\U0001f1f5\U0001f1ec', 'cuba': '\U0001f1e8\U0001f1fa',
    'lebanon': '\U0001f1f1\U0001f1e7', 'puerto rico': '\U0001f1f5\U0001f1f7',
    'moldova': '\U0001f1f2\U0001f1e9', 'jamaica': '\U0001f1ef\U0001f1f2',
    'el salvador': '\U0001f1f8\U0001f1fb', 'haiti': '\U0001f1ed\U0001f1f9', 'bahrain': '\U0001f1e7\U0001f1ed',
    'kuwait': '\U0001f1f0\U0001f1fc', 'cyprus': '\U0001f1e8\U0001f1fe', 'belize': '\U0001f1e7\U0001f1ff',
    'kosovo': '\U0001f1fd\U0001f1f0', 'east timor': '\U0001f1f9\U0001f1f1', 'bahamas': '\U0001f1e7\U0001f1f8',
    'solomon islands': '\U0001f1f8\U0001f1e7', 'myanmar': '\U0001f1f2\U0001f1f2',
    'north korea': '\U0001f1f0\U0001f1f5', 'bhutan': '\U0001f1e7\U0001f1f9', 'iceland': '\U0001f1ee\U0001f1f8',
    'vanuatu': '\U0001f1fb\U0001f1fa', 'san marino': '\U0001f1f8\U0001f1f2', 'palestine': '\U0001f1f5\U0001f1f8',
    'republic of china': '\U0001f1e8\U0001f1f3', 'yugoslavia': '\U0001f1f8\U0001f1f0',
    'czechoslovakia': '\U0001f1e8\U0001f1ff', 'persia': '\U0001f1ee\U0001f1f7',
    'weimar republic': '\U0001f1e9\U0001f1ea', 'soviet union': '\U0001f1f7\U0001f1fa'}


def codes(country: str) -> str:
    """flags codes"""
    return flags_codes.get(country.lower(), '\u2620')


countries_per_id = {1: ('poland', 'pl', 'pln'), 2: ('russia', 'ru', 'rub'), 3: ('germany', 'ger', 'dem'),
                    4: ('france', 'fr', 'frf'), 5: ('spain', 'es', 'esp'), 6: ('united kingdom', 'gb', 'gbp'),
                    7: ('italy', 'it', 'itl'), 8: ('hungary', 'hu', 'huf'), 9: ('romania', 'ro', 'ron'),
                    10: ('bulgaria', 'bg', 'bgn'), 11: ('serbia', 'rs', 'rsd'), 12: ('croatia', 'hr', 'hrk'),
                    13: ('bosnia and herzegovina', 'ba', 'bam'), 14: ('greece', 'gr', 'grd'),
                    15: ('republic of macedonia', 'mk', 'mkd'), 16: ('ukraine', 'ua', 'uah'),
                    17: ('sweden', 'se', 'sek'), 18: ('portugal', 'pt', 'pte'), 19: ('lithuania', 'lt', 'ltl'),
                    20: ('latvia', 'lv', 'lvl'), 21: ('slovenia', 'si', 'sit'), 22: ('turkey', 'tr', 'try'),
                    23: ('brazil', 'br', 'brl'), 24: ('argentina', 'ar', 'ars'), 25: ('mexico', 'mx', 'mxn'),
                    26: ('usa', 'us', 'usd'), 27: ('canada', 'ca', 'cad'), 28: ('china', 'cn', 'cny'),
                    29: ('indonesia', 'id', 'idr'), 30: ('iran', 'ir', 'irr'), 31: ('south korea', 'kr', 'krw'),
                    32: ('taiwan', 'tw', 'twd'), 33: ('israel', 'il', 'nis'), 34: ('india', 'in', 'inr'),
                    35: ('australia', 'au', 'aud'), 36: ('netherlands', 'nl', 'nlg'), 37: ('finland', 'fi', 'fim'),
                    38: ('ireland', 'i', 'iep'), 39: ('switzerland', 'ch', 'chf'), 40: ('belgium', 'be', 'bef'),
                    41: ('pakistan', 'pk', 'pkr'), 42: ('malaysia', 'my', 'myr'), 43: ('norway', 'no', 'nok'),
                    44: ('peru', 'pe', 'pen'), 45: ('chile', 'cl', 'clp'), 46: ('colombia', 'co', 'cop'),
                    47: ('montenegro', 'me', 'mep'), 48: ('austria', 'a', 'ats'), 49: ('slovakia', 'sk', 'skk'),
                    50: ('denmark', 'dk', 'dkk'), 51: ('czech republic', 'cz', 'czk', 'czech'),
                    52: ('belarus', 'by', 'byr'), 53: ('estonia', 'ee', 'eek'), 54: ('philippines', 'ph', 'php'),
                    55: ('albania', 'al', 'all'), 56: ('venezuela', 've', 'vef'), 57: ('egypt', 'eg', 'egp'),
                    58: ('japan', 'jp', 'jpy'), 59: ('bangladesh', 'bd', 'bdt'), 60: ('vietnam', 'vn', 'vnd'),
                    61: ('yemen', 'ye', 'yer'), 62: ('saudi arabia', 'sa', 'sar'), 63: ('thailand', 'th', 'thb'),
                    64: ('algeria', 'dz', 'dzd'), 65: ('angola', 'ao', 'aoa'), 66: ('cameroon', 'cm', 'cm'),
                    67: ('ivory coast', 'ci', 'ci'), 68: ('ethiopia', 'et', 'etb'), 69: ('ghana', 'gh', 'ghs'),
                    70: ('kenya', 'ke', 'kes'), 71: ('libya', 'ly', 'lyd'), 72: ('morocco', 'ma', 'mad'),
                    73: ('mozambique', 'mz', 'mzn'), 74: ('nigeria', 'ng', 'ngn'), 75: ('senegal', 'sn', 'sn'),
                    76: ('south africa', 'za', 'zar'), 77: ('sudan', 'sd', 'sdg'), 78: ('tanzania', 'tz', 'tzs'),
                    79: ('togo', 'tg', 'tg'), 80: ('tunisia', 'tn', 'tnd'), 81: ('uganda', 'ug', 'ugx'),
                    82: ('zambia', 'zm', 'zmw'), 83: ('zimbabwe', 'zw', 'zwl'), 84: ('botswana', 'bw', 'bwp'),
                    85: ('benin', 'bj', 'bj'), 86: ('burkina faso', 'bf', 'bf'), 87: ('congo', 'cg', 'cg'),
                    88: ('central african republic', 'cf', 'cf'), 89: ('dr of the congo', 'cd', 'cdf'),
                    90: ('eritrea', 'er', 'ern'), 91: ('gabon', 'ga', 'ga'), 92: ('chad', 'td', 'td'),
                    93: ('niger', 'ne', 'ne'), 94: ('mali', 'ml', 'ml'), 95: ('mauritania', 'mr', 'mro'),
                    96: ('guinea', 'gn', 'gnf'), 97: ('guinea bissau', 'gw', 'gw'), 98: ('sierra leone', 'sl', 'sll'),
                    99: ('liberia', 'lr', 'lrd'), 100: ('equatorial guinea', 'gq', 'gq'), 101: ('namibia', 'na', 'nad'),
                    102: ('lesotho', 'ls', 'lsl'), 103: ('swaziland', 'sz', 'szl'), 104: ('madagascar', 'mg', 'mga'),
                    105: ('malawi', 'mw', 'mwk'), 106: ('somalia', 'so', 'sos'), 107: ('djibouti', 'dj', 'djf'),
                    108: ('rwanda', 'rw', 'rwf'), 109: ('burundi', 'bi', 'bif'),
                    110: ('united arab emirates', 'ae', 'aed'), 111: ('syria', 'sy', 'syp'), 112: ('iraq', 'iq', 'iqd'),
                    113: ('oman', 'om', 'omr'), 114: ('qatar', 'qa', 'qar'), 115: ('jordan', 'jo', 'jod'),
                    116: ('western sahara', 'eh', 'eh'), 117: ('the gambia', 'gm', 'gmd'),
                    118: ('south sudan', 'ss', 'ssp'), 119: ('cambodia', 'kh', 'khr'), 120: ('nepal', 'np', 'npr'),
                    121: ('bolivia', 'bo', 'bob'), 122: ('ecuador', 'ec', 'ecd'), 123: ('paraguay', 'py', 'pyg'),
                    124: ('uruguay', 'uy', 'uyu'), 125: ('honduras', 'hn', 'hnl'),
                    126: ('dominican republic', 'do', 'dop'), 127: ('guatemala', 'gt', 'gtq'),
                    128: ('kazakhstan', 'kz', 'kzt'), 129: ('sri lanka', 'lk', 'lkr'),
                    130: ('afghanistan', 'af', 'afn'), 131: ('armenia', 'am', 'amd'), 132: ('azerbaijan', 'az', 'azn'),
                    133: ('georgia', 'ge', 'gel'), 134: ('kyrgyzstan', 'kg', 'kgs'), 135: ('laos', 'la', 'lak'),
                    136: ('tajikistan', 'tj', 'tjs'), 137: ('turkmenistan', 'tm', 'tmt'),
                    138: ('uzbekistan', 'uz', 'uzs'), 139: ('new zealand', 'nz', 'nzd'), 140: ('guyana', 'gy', 'gyt'),
                    141: ('suriname', 'sr', 'srd'), 142: ('nicaragua', 'ni', 'nio'), 143: ('panama', 'pa', 'pab'),
                    144: ('costa rica', 'cr', 'crc'), 145: ('mongolia', 'mn', 'mnt'),
                    146: ('papua new guinea', 'pg', 'pgk'), 147: ('cuba', 'cu', 'cuc'), 148: ('lebanon', 'lb', 'lbp'),
                    149: ('puerto rico', 'pr', 'prd'), 150: ('moldova', 'md', 'mdl'), 151: ('jamaica', 'jm', 'jmd'),
                    152: ('el salvador', 'sv', 'svd'), 153: ('haiti', 'ht', 'htg'), 154: ('bahrain', 'bh', 'bhd'),
                    155: ('kuwait', 'kw', 'kwd'), 156: ('cyprus', 'cy', 'cy'), 157: ('belize', 'bz', 'bzd'),
                    158: ('kosovo', 'xk', 'xkd'), 159: ('east timor', 'tl', 'tld'), 160: ('bahamas', 'bs', 'bsd'),
                    161: ('solomon islands', 'sb', 'sbd'), 162: ('myanmar', 'mm', 'mmk'),
                    163: ('north korea', 'kp', 'kpw'), 164: ('bhutan', 'bt', 'btn'), 165: ('iceland', 'is', 'isk'),
                    166: ('vanuatu', 'vu', 'vut'), 167: ('san marino', 'sm', 'rsm'), 168: ('palestine', 'ps', 'psd'),
                    169: ('soviet union', 'su', 'sur'), 170: ('czechoslovakia', 'cshh', 'cs'),
                    171: ('yugoslavia', 'yug', 'yug'), 172: ('weimar republic', 'wer', 'wer'),
                    173: ('republic of china', 'cn', 'cn'), 174: ('persia', 'prs', 'prs')}

countries_per_server = {
    'luxia': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
              30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
              56, 57, 58, 59, 60, 61, 62, 63, 64, 68, 71, 72, 80, 104, 106, 110, 111, 112, 113, 114, 115, 119, 120, 121,
              122, 123, 124, 125, 126, 127, 128, 130, 131, 132, 133, 134, 135, 136, 137, 138, 140, 141, 142, 143, 144,
              145, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 158, 159, 162, 164, 165],
    'alpha': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
              29, 30, 31, 32, 33, 34, 36, 37, 39, 40, 41, 43, 44, 45, 46, 47, 48, 49, 50, 51, 53, 54, 55, 56, 57, 58,
              60, 64, 71, 72, 80, 121, 131, 132, 133],
    'primera': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
                28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53,
                54, 55, 56, 57, 58, 59, 60, 63, 119, 121, 122, 123, 124, 125, 126, 127, 139, 140, 141, 142, 143, 144,
                147, 149, 150, 151, 152, 153, 156, 157, 158, 160, 165, 167, 168],
    'secura': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
               29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 54, 55, 56,
               57, 58, 60, 63, 119, 120, 121, 122, 123, 124, 125, 126, 127, 130, 135, 140, 141, 142, 143, 144, 145, 146,
               147, 149, 150, 151, 152, 153, 156, 157, 158, 159, 160, 161, 162, 163, 164, 166, 167, 168],
    'suna': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28,
             29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
             56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82,
             83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107,
             108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128,
             129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149,
             150, 151, 152, 153, 154, 155, 167, 168],
    'testura': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27,
                28, 29, 30, 31, 32, 33, 34, 36, 37, 40, 41, 43, 44, 45, 46, 47, 48, 49, 50, 51, 53, 55, 56, 57, 58, 64,
                71, 72, 80, 121, 131, 132, 133],
    'nika': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
             30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56,
             57, 58, 59, 60, 62, 63, 64, 71, 72, 80, 110, 111, 112, 115, 119, 120, 121, 122, 123, 124, 125, 126, 127,
             128, 130, 131, 132, 133, 134, 135, 136, 138, 142, 143, 144, 145, 147, 148, 149, 150, 152, 155, 156, 162,
             165],
    'vega': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
             30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56,
             57, 58, 59, 60, 62, 63, 64, 71, 72, 80, 110, 111, 112, 115, 119, 120, 121, 122, 123, 124, 125, 126, 127,
             128, 130, 131, 132, 133, 134, 135, 136, 138, 142, 143, 144, 145, 147, 148, 149, 150, 152, 155, 156, 162,
             165]
}


def get_countries(server: str, country: int = 0, index: int = -1) -> Union[dict, str]:
    """get countries"""
    if country:
        return countries_per_id.get(country, 'unknown')[0]
    per_id = {}
    for country_id in countries_per_server.get(server, []):
        if index < 0:
            per_id[country_id] = countries_per_id.get(country_id, ('no one', 'no one', 'no one'))
        else:
            per_id[country_id] = countries_per_id.get(country_id, ('unknown',))[index]
    return per_id


def get_time(string: str, floor_to_10: bool = False) -> datetime:
    """get time"""
    try:
        try:
            dt = datetime.strptime(string.strip(), '%d-%m-%Y %H:%M:%S:%f')
        except ValueError:
            dt = datetime.strptime(string.strip(), '%Y-%m-%d %H:%M:%S:%f')
    except ValueError:
        try:
            dt = datetime.strptime(string.strip(), '%Y-%m-%d %H:%M:%S')
        except ValueError:
            dt = datetime.strptime(string.strip(), '%Y-%m-%d %H:%M:%S.%f')
    if floor_to_10:
        dt = dt - timedelta(minutes=dt.minute % 10, seconds=dt.second, microseconds=dt.microsecond)
    return dt


def shorten_country(country: str) -> str:
    country = country.lower()
    d = {"united kingdom": "UK", "bosnia and herzegovina": "bosnia", "republic of macedonia": "Macedonia",
         "czech republic": "Czech", "central african republic": "Africa",
         "dr of the Congo": "congo", "united arab emirates": "Emirates", "dominican republic": "Dominican",
         "papua new guinea": "papua", "republic of china": "China R."}

    country = d.get(country, country)
    return country.replace("south ", "s. ").title()


def get_eqs(tree) -> iter:
    """get eqs"""
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
            for x in bot.all_parameters:
                if x in parameter_string.lower():
                    parameters.append(x)
                    try:
                        values.append(float(parameter_string.split(" ")[-1].replace("%", "").strip()))
                        break
                    except Exception:
                        pass
        yield slot, parameters, values, eq_link


def get_id(string: str) -> str:
    """get id"""
    return "".join(x for x in string.split("=")[-1].split("&")[0] if x.isdigit())


def get_ids_from_path(tree, xpath: str) -> list:
    """get ids from path"""
    ids = tree.xpath(xpath + "/@href")
    if ids and all("#" == x for x in ids):
        ids = [get_id(x.values()[-1]) for x in tree.xpath(xpath)]
    else:
        ids = [x.split("=")[-1].split("&")[0].strip() for x in ids]
    return ids


def camel_case(s: str) -> str:
    output = ''.join(x for x in s.title() if x.isalnum())
    return output[0].lower() + output[1:]


async def custom_followup(interaction: Interaction, content: str = None, **kwargs) -> Message:
    """custom_followup"""
    if not interaction.response.is_done():
        msg = await interaction.response.send_message(content, **kwargs)
    else:
        if "mention_author" in kwargs:
            del kwargs["mention_author"]
        try:
            msg = await interaction.followup.send(content, **kwargs)
        except Exception as error:
            if "Invalid Webhook Token" not in str(error):
                return await interaction.followup.send(error)
            if "ephemeral" in kwargs:
                del kwargs["ephemeral"]
            msg = await interaction.channel.send(content, **kwargs)
    return msg


async def get_battles(base_url: str, country_id: int = 0, filtering: iter = ('Normal battle', 'Resistance war')) -> list:
    """Get battles data"""
    battles = []
    link = f'{base_url}battles.html?countryId={country_id}'
    for page in range(1, await last_page(link)):
        tree = await get_content(link + f'&page={page}')
        total_dmg = tree.xpath('//*[@class="battleTotalDamage"]/text()')
        progress_attackers = [float(x.replace("%", "")) for x in tree.xpath('//*[@id="attackerScoreInPercent"]/text()')]
        attackers_dmg = tree.xpath('//*[@id="attackerDamage"]/text()')
        defenders_dmg = tree.xpath('//*[@id="defenderDamage"]/text()')
        counters = [i.split(");\n")[0] for i in tree.xpath('//*[@id="battlesTable"]//div//div//script/text()') for i in
                    i.split("() + ")[1:]]
        counters = [f'{int(x[0]):02d}:{int(x[1]):02d}:{int(x[2]):02d}' for x in await chunker(counters, 3)]
        sides = tree.xpath('//*[@class="battleHeader"]//em/text()')
        battle_ids = tree.xpath('//*[@class="battleHeader"]//a/@href')
        battle_regions = tree.xpath('//*[@class="battleHeader"]//a/text()')
        scores = tree.xpath('//*[@class="battleFooterScore hoverText"]/text()')

        types = tree.xpath('//*[@class="battleHeader"]//i/@data-hover')
        for i, (dmg, progress_attacker, counter, sides, battle_id, battle_region, score, battle_type) in enumerate(zip(
                total_dmg, progress_attackers, counters, sides, battle_ids, battle_regions, scores, types)):
            if battle_type not in filtering:
                continue
            defender, attacker = sides.split(" vs ")
            battles.append(
                {"total_dmg": dmg, "time_remaining": counter,
                 "battle_id": int(battle_id.split("=")[-1]), "region": battle_region,
                 "defender": {"name": defender, "score": int(score.strip().split(":")[0]),
                              "bar": round(100 - progress_attacker, 2)},
                 "attacker": {"name": attacker, "score": int(score.strip().split(":")[1]),
                              "bar": progress_attacker}})
            if attackers_dmg:  # some servers do not show current dmg
                try:
                    battles[-1]["defender"]["dmg"] = int(defenders_dmg[i].replace(",", ""))
                    battles[-1]["attacker"]["dmg"] = int(attackers_dmg[i].replace(",", ""))
                except Exception:
                    pass
    return battles


async def find_one(collection: str, _id: str) -> dict:
    """find one"""
    filename = f"../db/{collection}_{_id}.json"
    if path.exists(filename):
        with open(filename, "r", encoding='utf-8') as file:
            return json.load(file)
    else:
        return {}


async def replace_one(collection: str, _id: str, data: dict) -> None:
    """replace one"""
    filename = f"../db/{collection}_{_id}.json"
    with open(filename, "w", encoding='utf-8', errors='ignore') as file:
        json.dump(data, file)


inserted_api_fights = {server: {} for server in bot.all_servers}

async def insert_api_battles(server: str, battle_id: int, columns: iter) -> dict:
    r = await get_content(f'https://{server}.e-sim.org/apiBattles.html?battleId={battle_id}')
    r['totalSecondsRemaining'] = r["hoursRemaining"] * 3600 + r["minutesRemaining"] * 60 + r["secondsRemaining"]
    r['battle_id'] = battle_id
    r = {k: r[k] for k in columns}
    await bot.dbs[server].execute(f"INSERT OR REPLACE INTO apiBattles VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  tuple(r[k] for k in columns))
    await bot.dbs[server].commit()
    return r


async def find_many_api_battles(interaction: Interaction, server: str, ids: iter) -> pd.DataFrame:
    """find_many_api_battles"""
    columns = ['battle_id', 'currentRound', 'attackerScore', 'regionId', 'defenderScore',
               'frozen', 'type', 'defenderId', 'attackerId', 'totalSecondsRemaining']
    first, last = min(ids), max(ids)
    get_range = len(ids) / (last - first + 1) > 0.5 # get_range=True when ids~=range(min(ids), max(ids))
    cursor = await bot.dbs[server].execute(f"SELECT * FROM apiBattles WHERE battle_id " + (
        f"BETWEEN {first} AND {last}" if get_range else f"IN {tuple(ids)}"))
    values = [x for x in await cursor.fetchall() if x[0] in ids] if get_range else await cursor.fetchall()  # x[0] = battle_id
    df = pd.DataFrame(values, columns=columns)
    df['last_round_in_db'] = df['currentRound']
    values = []
    for battle_id in ids:
        row = df.loc[df['battle_id'] == battle_id]
        if row.empty or 8 not in (row['defenderScore'].iloc[0], row['attackerScore'].iloc[0]):
            r = await insert_api_battles(server, battle_id, columns)
            r['last_round_in_db'] = 0
            if row.empty:
                values.append(r)
            else:
                df.iloc[row.index[0]] = pd.Series(r)
            await custom_delay(interaction)
    return pd.concat([df, pd.DataFrame(values)], ignore_index=True, copy=False)


async def find_many_api_fights(interaction: Interaction, server: str, api_battles_df: pd.DataFrame) -> pd.DataFrame:
    columns = ['battle_id', 'round_id', 'damage', 'weapon', 'berserk', 'defenderSide', 'citizenship',
               'citizenId', 'time', 'militaryUnit']
    ids = api_battles_df["battle_id"].values
    first, last = min(ids), max(ids)
    get_range = len(ids) / (last - first + 1) > 0.5 # get_range=True when ids~=range(min(ids), max(ids))
    cursor = await bot.dbs[server].execute(f"SELECT * FROM apiFights WHERE battle_id " + (
        f"BETWEEN {first} AND {last}" if get_range else f"IN {tuple(ids)}"))
    values = [x for x in await cursor.fetchall() if x[1] in ids] if get_range else await cursor.fetchall()  # x[1] = battle_id
    dfs = []
    if values:
        dfs.append(pd.DataFrame(values, columns=["index"] + columns))
        dfs[0].drop('index', axis=1, inplace=True)
    for i, api in api_battles_df.iterrows():
        current_round = api["currentRound"]
        if 8 in (api['defenderScore'], api['attackerScore']):
            last_round = current_round
        else:
            last_round = current_round + 1
        for round_id in range(api["last_round_in_db"] + 1, last_round):
            r = await get_content(f'https://{server}.e-sim.org/apiFights.html?battleId={api["battle_id"]}&roundId={round_id}')
            if not r:
                continue
            r = [(api["battle_id"], round_id, hit['damage'], hit['weapon'], hit['berserk'], hit['defenderSide'], hit['citizenship'],
                  hit['citizenId'], hit['time'], hit.get('militaryUnit', 0)) for hit in reversed(r)]
            if api["battle_id"] not in inserted_api_fights[server]:
                inserted_api_fights[server][api["battle_id"]] = []
            if round_id != current_round and round_id not in inserted_api_fights[server][api["battle_id"]]:
                await bot.dbs[server].executemany(f"INSERT INTO apiFights {tuple(columns)} VALUES (?,?,?,?,?,?,?,?,?,?)", r)
                await bot.dbs[server].commit()
                inserted_api_fights[server][api["battle_id"]].append(round_id)
            dfs.append(pd.DataFrame(r, columns=columns))
            await custom_delay(interaction)

    return pd.concat(dfs, ignore_index=True, copy=False)


async def find_one_api_battles(server: str, battle_id: int) -> dict:
    columns = ['battle_id', 'currentRound', 'attackerScore', 'regionId', 'defenderScore',
               'frozen', 'type', 'defenderId', 'attackerId', 'totalSecondsRemaining']
    cursor = await bot.dbs[server].execute(f"SELECT * FROM apiBattles WHERE battle_id = {battle_id}")
    r = await cursor.fetchone()
    r = dict(zip(columns, r)) if r else {}
    last_round_in_db = r.get('currentRound', 0)

    if not r or 8 not in (r['defenderScore'], r['attackerScore']):
        r = await insert_api_battles(server, battle_id, columns)
    r["last_round_in_db"] = last_round_in_db
    return r


async def find_one_api_fights(server: str, api: dict, round_id:int = 0) -> pd.DataFrame:
    columns = ['battle_id', 'round_id', 'damage', 'weapon', 'berserk', 'defenderSide', 'citizenship',
               'citizenId', 'time', 'militaryUnit']
    battle_id = api["battle_id"]
    cursor = await bot.dbs[server].execute(f"SELECT * FROM apiFights WHERE battle_id = {battle_id}" +
                                           (f" AND round_id = {round_id}" if round_id else ""))
    dfs = []
    values = await cursor.fetchall()
    if values:
        dfs.append(pd.DataFrame(values, columns=["index"] + columns))

    current_round, first_round = api["currentRound"], api["last_round_in_db"] + 1
    if 8 in (api['defenderScore'], api['attackerScore']):
        last_round = current_round
    else:
        last_round = current_round + 1
    for round_id in range(first_round, last_round):
        r = await get_content(f'https://{server}.e-sim.org/apiFights.html?battleId={battle_id}&roundId={round_id}')
        if not r:
            continue
        r = [(battle_id, round_id, hit['damage'], hit['weapon'], hit['berserk'], hit['defenderSide'], hit['citizenship'],
              hit['citizenId'], hit['time'], hit.get('militaryUnit', 0)) for hit in reversed(r)]
        if battle_id not in inserted_api_fights[server]:
            inserted_api_fights[server][battle_id] = []
        if round_id != current_round and round_id not in inserted_api_fights[server][battle_id]:
            await bot.dbs[server].executemany(f"INSERT INTO apiFights {tuple(columns)} VALUES (?,?,?,?,?,?,?,?,?,?)", r)
            await bot.dbs[server].commit()
            inserted_api_fights[server][battle_id].append(round_id)
        dfs.append(pd.DataFrame(r, columns=columns))
    return pd.concat(dfs, ignore_index=True, copy=False) if dfs else None
