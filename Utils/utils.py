"""Utils.py."""
import json
import logging
import random
from asyncio import sleep
from collections import defaultdict
from copy import deepcopy
from csv import reader
from datetime import date, datetime, timedelta, UTC
from io import BytesIO, StringIO
from itertools import islice
from os import path
from re import finditer
from traceback import format_exception

from PIL import Image, ImageDraw, ImageFont
from aiohttp import ClientSession, ClientTimeout
from discord import Embed, File, Interaction, Message
from discord.app_commands import CheckFailure
from discord.ext import tasks
from discord.ext.commands import BadArgument, Cooldown
from discord.utils import MISSING
from lxml.html import fromstring, HtmlElement
from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
from matplotlib.ticker import FixedLocator
from pytz import timezone
from tabulate import tabulate

from bot.bot import bot
from .constants import (all_countries, all_parameters, all_servers, api_url,
                        config_ids, countries_per_id, countries_per_server,
                        date_format, flags_codes)
from .paginator import FieldPageSource, Pages

hidden_guild = config_ids["commands_server_id"]
font = ImageFont.truetype(path.join(path.dirname(path.dirname(__file__)), "files", "DejaVuSansMono.ttf"), 100)
logger = logging.getLogger()


class CoolDownModified:
    """CoolDownModified."""

    def __init__(self, per, rate=1) -> None:
        self.rate = rate
        self.per = per

    async def __call__(self, message) -> Cooldown | None:
        if await is_premium_level_0(message):
            return None  # remove cooldown
        return Cooldown(self.rate, self.per)


def remove_decimal(x: float or int) -> int or float:
    """5 -> 5, 5.0 -> 5, 5.1 -> 5.1."""
    return int(x) if isinstance(x, float) and x.is_integer() else x


def get_sides(api_battles: dict, attacker_id: int = None, defender_id: int = None) -> tuple[str, str]:
    attacker_id = attacker_id or api_battles["attackerId"]
    defender_id = defender_id or api_battles["defenderId"]
    if attacker_id != defender_id and api_battles["type"] != "MILITARY_UNIT_CUP_EVENT_BATTLE":
        attacker = all_countries.get(attacker_id, "Attacker")
        defender = all_countries.get(defender_id, "Defender")
    else:
        attacker, defender = "Attacker", "Defender"
    return attacker, defender


def server_validation(server: str) -> str:
    """Server validation."""
    server = server.lower().strip()
    if server in all_servers:
        return server
    raise CheckFailure(f"`{server}` is not a valid server.\nValid servers: " + ", ".join(all_servers))


def human_format(num: float) -> str:
    """Number to human format."""
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000

    if num < 10:
        precision = 2
    elif num < 100:
        precision = 1
    else:
        precision = 0
    return f'{num:.{precision}f}' + ['', 'K', 'M', 'B', 'T', 'P'][magnitude]


def split_list(alist: list or tuple, wanted_parts: int) -> tuple:
    """Split list into parts."""
    length = len(alist)
    small_lists = tuple(alist[i * length // wanted_parts: (i + 1) * length // wanted_parts]
                        for i in range(wanted_parts))
    return tuple(x for x in small_lists if x)


def chunker(seq: list or tuple, size: int) -> iter:
    """List to sub lists."""
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


def draw_pil_table(my_table: list or tuple, header: list or tuple, new_lines: int = 0) -> BytesIO:
    """Draw table."""
    tabulate_table = tabulate(my_table, headers=header, tablefmt='grid', numalign="center", stralign="center")
    table_len = len(tabulate_table) / (len(my_table) * 2 + 3 + new_lines)
    img = Image.new('RGB', (int(60 * table_len), 300 + new_lines * 100 + len(my_table) * 200), color=(44, 47, 51))
    ImageDraw.Draw(img).text((10, 10), tabulate_table, font=font)
    output_buffer = BytesIO()
    img.save(output_buffer, format='JPEG', subsampling=0, quality=95)
    output_buffer.seek(0)
    return output_buffer


def bar(defender_dmg: int, attacker_dmg: int, defender: str = "", attacker: str = "", size: int = -1) -> str:
    """Bar."""
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
    """Dmg trend."""
    fig, ax = plt.subplots()
    for side, DICT in hit_time.items():
        ax.plot(DICT["time"], DICT["dmg"], label=side)
    ax.legend()
    ax.xaxis.set_major_formatter(DateFormatter("%d-%m %H:%M"))
    fig.autofmt_xdate()
    ax.set_title(f"Dmg Trend ({server}, {battle_id})")
    ax.set_ylabel('DMG')
    ax.set_xlabel('Time')
    ax.yaxis.set_major_locator(FixedLocator(ax.get_yticks()))
    ax.set_yticklabels([human_format(x) for x in ax.get_yticks().tolist()])
    ax.grid()
    return plt_to_bytes(fig)


async def get_auction(link: str) -> dict:
    """Get auction."""
    tree = await get_content(link)
    info = tree.xpath('//button[@class="btn-buy btn-yellow"]')[0]
    seller = info.get('data-seller')
    buyer = info.get('data-top-bidder')
    item = " ".join(info.get('data-auction-item').split()[:2]).replace("_", " ")
    price = info.get('data-current-price')
    time_remaining = tree.xpath('//*[@class="auctionTime"]//span/text()')
    if not time_remaining:  # finished
        time_remaining = strip(tree.xpath('//*[@class="auctionTime"]/text()'))[0]
        remaining_seconds = -1
    else:
        time_remaining = tuple(int(x) for x in time_remaining[0].split(":"))
        remaining_seconds = time_remaining[0] * 60 * 60 + time_remaining[1] * 60 + time_remaining[2]
        time_remaining = f'{time_remaining[0]:02d}:{time_remaining[1]:02d}:{time_remaining[2]:02d}'
    return {"seller": seller.strip(), "buyer": buyer.strip(), "item": item,
            "price": price, "time": time_remaining, "remaining_seconds": remaining_seconds}


async def save_dmg_time(api_fights: str, attacker: str, defender: str) -> (dict, dict):
    """Save dmg time."""
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


def plt_to_bytes(fig: plt.Figure) -> BytesIO:
    output_buffer = BytesIO()
    fig.tight_layout()
    fig.savefig(output_buffer)
    plt.close(fig)
    output_buffer.seek(0)
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
    guild = bot.get_guild(config_ids["support_server_id"])
    patreon = bot.get_user(216303189073461248)
    async for entry in guild.audit_logs(user=patreon):
        if entry.user.name == 'Patreon' and (now-entry.created_at).total_seconds() < 5*24*3600:  # 5 days
            bot.premium_users.update({str(entry.target.id): {"level": 0, "reason": "auto",
                                                     "nick": entry.target.name, "added_at": str(now)}})
"""


@tasks.loop(seconds=1000)
async def alert() -> None:
    """Alert."""
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
    """Not support channel."""
    if interaction.guild and interaction.guild.id == config_ids["support_server_id"]:
        await custom_followup(interaction, "You can't use this command on support channel. Go spam somewhere else!")
        return False
    return True


def csv_to_txt(content: bytes) -> BytesIO:
    """Csv to text file."""
    text = "[table]"
    indexes = defaultdict(list)
    num = -1
    for row in reader(StringIO(content.decode()), delimiter=","):
        row_len = len(row)
        if all(x == "-" for x in row) or all(not x for x in row):
            indexes = defaultdict(list)
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
                column = f"{int(float(column)):,}".replace(",", ".")
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
    """Camel case merge."""
    matches = finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)', identifier)
    return " ".join(m.group(0) for m in matches).title()


async def get_content(link: str, return_type: str = "", method: str = "get", session: ClientSession = None,
                      throw: bool = False) -> list[dict] | dict | HtmlElement:
    """Get content."""
    if not return_type:
        if "api" in link or link.startswith(api_url):
            return_type = "json"
        else:
            return_type = "html"
    server = link.split("#")[0].replace("http://", "https://").split(  # noqa WPS221
        "https://")[1].split(".e-sim.org")[0]
    if not session:
        session = bot.session
    for _ in range(3):
        try:
            async with session.get(link, ssl=False) if method == "get" else session.post(
                    link, ssl=False) as respond:
                if "google.com" in str(respond.url) or respond.status == 403:
                    await sleep(2)
                    continue
                if "NO_PRIVILEGES" in str(respond.url):
                    raise IOError("NO_PRIVILEGES")
                if any(t in str(respond.url) for t in ("notLoggedIn", "error")):
                    raise BadArgument(
                        f"This page is locked for bots.\n"
                        f"(Try open this page after logging out or in a private tab {link.replace(' ', '+')} )\n\n"
                        f"If you want this command to work again, "
                        f"you should ask `Liberty Games Interactive#3073` to reopen this page.")
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


async def create_session(server: str = None) -> ClientSession:
    """Create session."""
    headers = {"User-Agent": bot.config["headers"]}
    if server:
        headers["Host"] = server + ".e-sim.org"
    return ClientSession(timeout=ClientTimeout(total=15), headers=headers)


async def get_session(server: str) -> ClientSession:
    """Get session."""
    if server not in bot.locked_sessions or bot.locked_sessions[server].closed:
        bot.locked_sessions[server] = await create_session(server)
    return bot.locked_sessions[server]


async def get_locked_content(link: str, test_login: bool = False, method: str = "get"):
    """Get locked content."""
    link = link.split("#")[0].replace("http://", "https://")  # noqa WPS221
    server = link.split("https://", 1)[1].split(".e-sim.org", 1)[0]
    nick = bot.config.get(server, bot.config['nick'])
    password = bot.config.get(server + "_password", bot.config['password'])
    session = await get_session(server)
    base_url = f"https://{server}.e-sim.org/"
    not_logged_in = False
    tree = None
    try:
        if not test_login:
            tree = await get_content(link, method=method, session=session)
        else:
            tree = await get_content(base_url + "storage.html", method=method, session=session)
        logged = tree.xpath('//*[@id="command"]')
        if any("login.html" in x.action or "Iogin.html" in x.action for x in logged):
            not_logged_in = True
    except Exception as error:
        if "This page is locked for bots." not in str(error):
            raise error
        not_logged_in = True
    if not_logged_in:
        payload = {'login': nick, 'password': password, "submit": "Login"}
        async with session.get(base_url, ssl=False) as main_page:
            tree = fromstring(await main_page.text(encoding='utf-8'))
            login_path = "login.html" if any("login.html" in x.action for x in tree.xpath('//*[@id="command"]')
                                             ) else "Iogin.html"
            async with session.post(base_url + login_path, data=payload, ssl=False) as respond:
                tree = fromstring(await respond.text(encoding='utf-8'))
                logged = tree.xpath('//*[@id="command"]')
                logger.info(f"Logged in to {server}")
                if any("login.html" in x.action or "Iogin.html" in x.action for x in logged):
                    raise BadArgument("This command is currently unavailable")
        tree = await get_content(link, method=method, session=session)
    if test_login and not not_logged_in:
        tree = await get_content(link, method=method, session=session)
    return tree


async def edit_message(msg: Message, content: str, attachments: list = MISSING) -> Message:
    if msg.content == content:
        return msg
    try:
        logger.debug(f"Editing message `{msg.content}` to `{content}`")
        return await msg.edit(content=content, attachments=attachments)
    except Exception:
        logger.warning(f"Failed to edit message {msg}")
        return msg


async def update_percent(current_id: int, ids_length: int, msg: Message) -> Message:
    """Update percent."""
    if ids_length < 10:
        return msg
    current_id += 1
    edit_at = [int(ids_length / 10 * x) for x in range(1, 11)]
    if current_id >= ids_length - 3:
        msg = await edit_message(msg, content="Progress status: 99%", attachments=[])
    elif current_id in edit_at:
        content = f"Progress status: {(edit_at.index(current_id) + 1) * 10}%." \
                  "\n(I will update this message every 10%)"
        msg = await edit_message(msg, content=content)

    return msg


async def reset_cooldown(interaction: Interaction) -> None:
    """Reset cooldown."""
    interaction.command.reset_cooldown(interaction)


async def is_premium_guild(interaction: Interaction) -> bool:
    """Is premium guild."""
    return interaction.guild and interaction.guild.id in bot.premium_servers


async def is_premium_level_0(interaction: Interaction) -> bool:  # reset cooldown
    """For cooldown reset."""
    return (bot.premium_users.get(str(interaction.user.id), {}).get("level", -1) >= 0 or
            await is_premium_guild(interaction))


async def is_premium_level_1(interaction: Interaction, send_error_msg: bool = True, allow_trial: bool = True) -> bool:
    """Is premium."""
    # remove expired users
    expire_at = bot.premium_users.get(str(interaction.user.id), {}).get("expire_at", "")
    if expire_at and datetime.strptime(expire_at, "%d/%m/%Y") < datetime.now():
        del bot.premium_users[str(interaction.user.id)]

    today = str(date.today())
    if (bot.premium_users.get(str(interaction.user.id), {}).get("level", -1) >= 1 or
            await is_premium_guild(interaction)):
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
    """Default nick."""
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
    """Custom delay."""
    # TODO: remove this and instead add a dynamic delay based on server load
    await sleep(bot.custom_delay_dict.get(str(interaction.user.id), 0.4))


def get_formatted_interaction(interaction: Interaction | None, bold: bool = True) -> str | None:
    if interaction and getattr(interaction, "data", None):
        return interaction.data.get("name", "") + " " + "  ".join(
            (f"**{x.get('name')}**" if bold else x.get('name')) +
            f": {x.get('value')}" for x in interaction.data.get('options', []))


async def log_error(interaction: Interaction | None, error: Exception, cmd: str = "") -> None:
    logger.error(f"Error in {cmd}", exc_info=error)
    msg = f"[{get_current_time_str()}] : {get_formatted_interaction(interaction) or cmd}"
    error_channel = bot.get_channel(config_ids["error_channel_id"])
    error_msg = f"{msg}\n```{''.join(format_exception(type(error), error, error.__traceback__))}```"
    if len(error_msg) >= 2000:
        error_msg = error_msg[:990] + "\n...\n" + error_msg[-990:]
    try:
        await error_channel.send(error_msg)
    except Exception:  # Big msg
        await error_channel.send(f"{msg}\n{error}"[:1900])

    query = """INSERT INTO collections.commands_logs (interaction_id, is_success, time, error)
               VALUES (%s, %s, %s, %s)"""
    params = (interaction.id, False, datetime.now(UTC), str(error))
    await bot.db_utils.execute_query(bot.pool, query, params)


async def send_error(interaction: Interaction | None, error: Exception, cmd: str = "") -> None:
    """Send error."""
    await log_error(interaction, error, cmd)
    if interaction is None:
        return
    user_error = f"An error occurred. Please report this at the support server: {config_ids['support_invite']}" \
                 f"\n `The program {cmd if cmd else interaction.command.name} has halted.`"
    if cmd and (isinstance(cmd, int) or cmd.isdigit()):
        user_error += f"The following results do not include ID {cmd} onwards"
    await custom_followup(interaction, user_error)


async def custom_author(embed: Embed) -> Embed:
    """Add link for donations."""
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


async def convert_embed(interaction_or_author: Interaction | int, embed: Embed, is_columns: bool = True) -> Embed:
    """Convert embed to phone format + add fix and donate link."""
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
            if not isinstance(interaction, int) and not interaction.channel.permissions_for(
                    interaction.user).external_emojis:
                break
            try:
                first_item = embed_fields[index].value.splitlines()[0]
            except IndexError:
                continue
            # TODO: it shouldn't add fix if no emojis (example: drops, upgrades)
            if "fix" not in first_item and (
                    is_ascii(first_item) or "%" in first_item) and embed_fields[index].value.count("\n") > 3:
                embed.set_field_at(index, name=embed_fields[index].name,
                                   value=embed_fields[index].value.replace("\n", " <:fix:1367880792121802762>\n"),
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
        embed.insert_field_at(first, name="\n".join(field.name for field in embed_fields[first:first + columns]),
                              value="\u200B", inline=False)
        my_list = tuple(tuple(embed_fields[x + first].value.splitlines()[i] for x in range(columns)) for i in
                        range(len(embed_fields[0 + first].value.splitlines())))
        for index, a_tuple in enumerate(split_list(my_list, 3)):
            embed.insert_field_at(index + first + 1, name="\u200B", value="\n".join("\n".join(x) for x in a_tuple))

    if not embed.footer:
        embed.set_footer(text="That is an auto phone format. Type `/phone` to change this preference")

    return embed


async def send_long_embed(interaction: Interaction, embed: Embed, headers: list or tuple, data: list or tuple,
                          files: list[File] = MISSING) -> None:
    """Send long embed."""
    for index, header in enumerate(headers):
        embed.add_field(name=header, value="\n".join(str(x[index]) for x in data))
    converted_embed = await convert_embed(interaction, deepcopy(embed))
    result = list(zip(*tuple(
        (embed if str(interaction.user.id) in bot.phone_users else converted_embed).fields[index].value.splitlines()
        for index in range(len(embed.fields)))))
    pages = max(sum(len(str(x[index])) for x in result) for index in range(3)) // 950 + 1
    chunks = split_list(result, pages)
    chunks = tuple((headers[i], "\n".join(str(x[i]) for x in chunk)) for chunk in chunks for i in range(3))
    source = FieldPageSource(chunks, inline=True, per_page=3, clear_description=False, embed=embed)
    pages = Pages(source, interaction=interaction, embed=embed)
    await pages.start(files=files)


async def csv_to_image(output: StringIO, columns: int = 10, rows: int = 10):
    """Convert csv file to image."""
    file_iter = reader(output)
    headers = tuple(next(file_iter))
    table = tuple(row[:columns] for row in islice(file_iter, rows))
    output.seek(0)
    return await bot.loop.run_in_executor(None, draw_pil_table, table, headers)


async def last_page(link: str, func=get_content, **kwargs) -> int:
    """Get last page."""
    tree = await func(link, **kwargs)
    last = get_ids_from_path(tree, "//ul[@id='pagination-digg']//li[last()-1]/a") or ['1']
    last = int(last[0])
    if last > 1000000:
        tree = await func(link + f"&page={last}", **kwargs)
        last = int(tree.xpath('//*[@id="pagingInput"]')[0].value)
    return last + 1


def get_flag_code(country: str) -> str:
    """Flags codes."""
    return flags_codes.get(country.lower(), '\u2620')


def get_countries(server: str, country: int = 0, index: int = -1) -> dict[int, str | tuple] | str:
    """Get countries."""
    if country:
        return countries_per_id.get(country, 'unknown')[0]
    per_id = {}
    for country_id in countries_per_server.get(server, []):
        if index < 0:
            per_id[country_id] = countries_per_id.get(country_id, ('no one', 'no one', 'no one'))
        else:
            per_id[country_id] = countries_per_id.get(country_id, ('unknown',))[index]
    return per_id


def get_time(string: str or datetime, floor_to_10: bool = False) -> datetime:
    """Get time."""
    if isinstance(string, datetime):
        dt = string
    else:
        string = string.strip()
        try:
            try:
                dt = datetime.strptime(string, '%d-%m-%Y %H:%M:%S:%f')
            except ValueError:
                dt = datetime.strptime(string, '%Y-%m-%d %H:%M:%S:%f')
        except ValueError:
            try:
                dt = datetime.strptime(string, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(string, '%Y-%m-%d %H:%M:%S.%f')
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


def normalize_slot(slot: str) -> str:
    return slot.lower().replace("personal", "").replace("charm", "").replace(
        "weapon upgrade", "WU").replace("  ", " ").title().strip()


def get_eqs(tree: HtmlElement) -> iter:
    """Get eqs."""
    for slot_path in tree.xpath('//*[@id="profileEquipmentNew"]//div//div//div//@title'):
        tree = fromstring(slot_path)
        try:
            slot = normalize_slot(tree.xpath('//b/text()')[0])
        except IndexError:
            continue
        eq_link = get_ids_from_path(tree, "//a")[0]
        parameters = []
        values = []
        for full_parameter_string in tree.xpath('//p/text()'):
            # full_parameter_string = "Increased damage by  8.71%", or "Merged by"
            parameter = normalize_parameter_string(full_parameter_string)
            if parameter:
                parameters.append(parameter)
                try:
                    values.append(float(full_parameter_string.split(" ")[-1].replace("%", "").strip()))
                except ValueError:
                    break  # end of valid parameters for this eq
            else:
                logger.warning(f"Unknown parameter: {full_parameter_string}")
        yield slot, parameters, values, eq_link


def normalize_parameter_string(parameter_string: str) -> str | None:
    return next((parameter for parameter in all_parameters if parameter in parameter_string.lower()), None)


def get_id(string: str) -> str:
    """Get id."""
    return "".join(x for x in string.split("=")[-1].split("&")[0] if x.isdigit())


def get_ids_from_path(tree: HtmlElement, xpath: str) -> list:
    """Get battle_ids from path."""
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
    """Custom_followup."""
    if not interaction.response.is_done():  # type: ignore
        msg = await interaction.response.send_message(content, **kwargs)  # type: ignore
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


async def get_battles(base_url: str, country_id: int = 0,
                      filtering: iter = ('Normal battle', 'Resistance war')) -> list[dict]:
    """Get battles data."""
    battles = []
    link = f'{base_url}battles.html?countryId={country_id}'
    for page in range(1, await last_page(link)):
        tree = await get_content(link + f'&page={page}')
        total_dmg = tree.xpath('//*[@class="battleTotalDamage"]/text()')
        progress_attackers = (float(x.replace("%", "")) for x in tree.xpath('//*[@id="attackerScoreInPercent"]/text()'))
        attackers_dmg = tree.xpath('//*[@id="attackerDamage"]/text()')
        defenders_dmg = tree.xpath('//*[@id="defenderDamage"]/text()')
        counters = tuple(i.split(");\n")[0] for i in tree.xpath('//*[@id="battlesTable"]//div//div//script/text()')
                         for i in i.split("() + ")[1:])
        counters = (f'{int(x[0]):02d}:{int(x[1]):02d}:{int(x[2]):02d}' for x in chunker(counters, 3))
        sides = tree.xpath('//*[@class="battleHeader"]//em/text()')
        battle_ids = tree.xpath('//*[@class="battleHeader"]//a/@href')
        battle_regions = tree.xpath('//*[@class="battleHeader"]//a/text()')
        scores = (tree.xpath('//*[@class="battleFooterScore hovertext"]/text()') or
                  tree.xpath('//*[@class="battleFooterScore hoverText"]/text()'))

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
    """Find one."""  # TODO: use msgpack
    filename = path.join(path.dirname(bot.root), f"db/{collection}_{_id}.json")
    if path.exists(filename):
        with open(filename, encoding='utf-8') as file:
            return json.load(file)
    else:
        return {}


async def replace_one(collection: str, _id: str, data: dict) -> None:
    """Replace one."""
    filename = path.join(path.dirname(bot.root), f"db/{collection}_{_id}.json")
    with open(filename, "w", encoding='utf-8', errors='ignore') as file:
        json.dump(data, file)


async def remove_old_donors():
    bot.premium_users = {k: v for k, v in bot.premium_users.items() if "level" in v}
    await replace_one("collection", "donors", bot.premium_users)


def get_buffs_debuffs(tree: HtmlElement) -> (str, str):
    buffs_debuffs = [camel_case_merge(x.split("/specialItems/")[-1].split(".png")[0]).replace("Elixir", "")
                     for x in tree.xpath(
            '//*[@class="profile-row" and (strong="Debuffs" or strong="Buffs")]//img/@src') if "img/specialItems/" in x]
    buffs = ', '.join(x.split("_")[0].replace("Vacations", "Vac").replace(
        "Resistance", "Sewer").replace("Pain Dealer", "PD ").replace(
        "Bonus Damage", "") + ("% Bonus" if "Bonus Damage" in x.split("_")[0] else "")
                      for x in buffs_debuffs if "Positive" in x.split("_")[1:]).title()
    debuffs = ', '.join(x.split("_")[0].lower().replace("Vacation", "Vac").replace(
        "Resistance", "Sewer") for x in buffs_debuffs if "Negative" in x.split("_")[1:]).title()
    return buffs, debuffs


def parse_product_icon(icon: str) -> str:
    """An icon may be in one of the following format:

    - //cdn.e-sim.org//img/productIcons/Gift.png
    - //cdn.e-sim.org//img/productIcons/q5.png
    """
    return icon.split("img/productIcons/")[1].split(".png")[0].replace("Rewards/", "")


def strip(data: tuple or list, apply_function: callable = None) -> tuple:
    # same as tuple(func(x.strip()) for x in data if x.strip()), but faster
    if apply_function:
        return tuple(map(apply_function, filter(None, map(str.strip, data))))
    else:
        return tuple(filter(None, map(str.strip, data)))


def get_profile_medals(tree: HtmlElement) -> list[str]:
    profile_medals = []
    for i in range(1, 11):
        medals_list = tree.xpath(f"//*[@id='medals']//ul//li[{i}]//div//text()")
        if medals_list:
            profile_medals.extend([x.replace("x", "") for x in medals_list])
        elif "emptyMedal" not in tree.xpath(f"//*[@id='medals']//ul//li[{i}]/img/@src")[0]:
            profile_medals.append("1")
        else:
            profile_medals.append("0")
    return profile_medals


def get_current_time_str(timezone_aware: bool = True, _format: str = date_format) -> str:
    return get_current_time(timezone_aware=timezone_aware).strftime(_format)


def get_current_time(timezone_aware: bool = True) -> datetime:
    now = datetime.now().astimezone(timezone('Europe/Berlin'))
    if not timezone_aware:
        now = now.replace(tzinfo=None)
    return now


def get_bonus_regions(api_map: list[dict], api_battles: dict, region_neighbour_ids: set[int]) -> (set[int], set[int]):
    """defender_regions are the regions that are neighbours of the regionId
        and have the same occupantId as the defenderId"""
    assert api_battles['type'] in ("RESISTANCE", "ATTACK")
    is_attack = api_battles['type'] == "ATTACK"
    defender_regions = {api_battles['regionId']}
    attacker_regions = set() if is_attack else {api_battles['regionId']}
    for region_entry in api_map:
        if region_entry["regionId"] in region_neighbour_ids:
            if is_attack and region_entry['occupantId'] == api_battles['defenderId']:
                defender_regions.add(region_entry["regionId"])
            elif region_entry['occupantId'] == api_battles['attackerId']:
                attacker_regions.add(region_entry["regionId"])
    return defender_regions, attacker_regions
