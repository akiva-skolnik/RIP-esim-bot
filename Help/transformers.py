"""transformers.py"""
from difflib import SequenceMatcher
from typing import List

from discord import Interaction
from discord.app_commands import (CheckFailure, Choice, Transformer,
                                  TransformerError)

from bot.bot import bot
from Help import utils


def fix_link(link: str) -> str:
    """fix link"""
    return link.split("#")[0].replace("http://", "https://").split("&actionStatus=")[0].replace("*", "")

def get_server(link: str) -> str:
    """get server"""
    return link.split("https://", 1)[1].split(".e-sim.org", 1)[0]


def get_id(link: str, parameter: str = "id") -> int:
    """get id"""
    return int(link.split(parameter + "=")[1].split("&")[0])

class Server(Transformer): # noqa
    """Server"""
    async def transform(self, interaction: Interaction, server: str) -> str:
        return server

    @property
    def choices(self) -> List[Choice]:
        return [Choice(name=x, value=x) for x in bot.all_servers]


class Country(Transformer):
    """Country"""
    async def transform(self, interaction: Interaction, country: str) -> str:
        if country.lower() in bot.countries_by_name:
            return bot.countries[bot.countries_by_name[country.lower()]]
        raise TransformerError(country, self.type, self)

    async def autocomplete(self, interaction: Interaction, value: str, /) -> list[Choice]:
        return [Choice(name=k, value=k) for k in sorted(
            bot.countries.values(), key=lambda x: SequenceMatcher(None, x.lower(), value.lower()).ratio(), reverse=True)][:10]


class Ids(Transformer):  # noqa
    """Ids"""
    async def transform(self, interaction: Interaction, ids: str) -> list:
        try:
            fixed_ids = ids.replace("_", "-").replace("\n", " ").replace(",", " ")
            ids_list = fixed_ids.split()
            if ".e-sim.org" in ids:
                ids = [get_id(ids)]
            elif "https://" in ids:
                if "https://docs.google.com/spreadsheets/d/" in ids:
                    ids = ids.split("/edit")[0] + "/export?format=csv"
                async with bot.session.get(ids, ssl=True) as respond:
                    ids = sorted({i.replace("\r", "").replace(",", "") for i in (await respond.text()).splitlines() if i})
            elif "-" in fixed_ids:
                ids_list = ids.split("-")
                ids = range(int(ids_list[0]), int(ids_list[-1]) + 1)
            elif len(ids_list) == 1:
                ids = range(int(ids_list[0]), int(ids_list[0]) + 1)
            else:
                ids = [int(x.strip()) for x in ids_list]

            if len(ids) > 500 and not await utils.is_premium_level_1(interaction, False, False):
                raise CheckFailure("It's too much... sorry. You can buy premium at https://www.buymeacoffee.com/RipEsim to remove this limit.")
            return ids
        except (ValueError, IndexError) as exc:
            raise TransformerError(ids, self.type, self) from exc


class AuctionLink(Transformer):  # noqa
    """AuctionLink"""
    async def transform(self, interaction: Interaction, link: str) -> dict:
        if link.startswith("http") and "auction" in link:
            link = fix_link(link)
            server = get_server(link)
            auction_id = get_id(link)
            return {"server": utils.server_validation(server), "id": auction_id, "base": "auction"}
        raise TransformerError(link, self.type, self)


class ProfileLink(Transformer):  # noqa
    """ProfileLink"""
    async def transform(self, interaction: Interaction, link: str) -> dict:
        result = {"base": "profile"}
        link = link.replace("_", "-")
        if link in bot.all_servers:
            link = link + "-" + await utils.default_nick(interaction, link)
        if link.startswith("http") and "profile" in link:
            link = fix_link(link)
            server = get_server(link)
            nick = get_id(link)  # id
            result["link"] = link
        elif "-" in link and not link.startswith("http"):
            server, nick = link.split("-")
            try:
                server = utils.server_validation(server)
                nick = nick.strip()
            except Exception:
                server, nick = nick.strip(), server.strip()
        else:
            try:
                server = utils.server_validation(link.split()[0])
                nick = " ".join(link.split()[1:])
            except Exception as exc:
                raise TransformerError(link, self.type, self) from exc

        result["server"] = utils.server_validation(server)
        result["nick_or_id"] = nick
        return result

class TournamentLink(Transformer):  # noqa
    """TournamentLink"""
    async def transform(self, interaction: Interaction, tournament_link: str) -> str:
        link = tournament_link.split("#")[0].replace("http://", "https://")
        if any(x in link for x in ("tournamentEvent.html?id=", "teamTournament.html?id=",
                                   "countryTournament.html?id=")):
            return link
        raise TransformerError(tournament_link, self.type, self)

class BattleLink(Transformer):  # noqa
    async def transform(self, interaction: Interaction, link: str) -> dict:
        round_id = 0
        last_battle = 0
        try:
            if link.startswith("http") and "battle" in link:
                link = fix_link(link.replace("Statistics", "").replace("Drops", ""))
                server = get_server(link)
                battle = get_id(link)
                if "&round=" in link:
                    round_id = get_id(link, "&round")
            elif "-" in link and not link.startswith("http"):
                server, battle = link.split("-")
                try:
                    battle = int(battle)
                except Exception:
                    server, battle = battle.strip(), server.strip()
            elif "_" in link:
                battle, last_battle = [int(x) for x in link.split("_")]
                server = ""
            else:
                raise TransformerError(link, self.type, self)

            if server:
                server = utils.server_validation(server)
            return {"server": server, "id": int(battle), "last": last_battle, "round": round_id, "base": "battle"}
        except (ValueError, IndexError) as exc:
            raise TransformerError(link, self.type, self) from exc


class Product(Transformer):  # noqa
    """Product"""
    def __init__(self, products_list: list = bot.products):
        self.products = products_list

    async def transform(self, interaction: Interaction, product: str) -> str:
        return product.upper()

    @property
    def choices(self) -> List[Choice]:
        return [Choice(name=x, value=x.upper()) for x in self.products]


class Slots(Transformer):  # noqa
    """Slots"""
    async def transform(self, interaction: Interaction, slot: str) -> str:
        return slot.title()

    @property
    def choices(self) -> List[Choice]:
        slots = ["helmet", "vision", "armor", "pants", "shoes", "lucky charm", "weapon upgrade", "offhand"]
        return [Choice(name=x.title(), value=x.title()) for x in slots]
