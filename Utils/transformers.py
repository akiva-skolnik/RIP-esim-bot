"""transformers.py"""
from difflib import SequenceMatcher

from discord import Interaction
from discord.app_commands import (CheckFailure, Choice, Transformer,
                                  TransformerError)

from Utils import utils
from bot.bot import bot
from .constants import (all_countries, all_countries_by_name, all_products,
                        all_servers)


def fix_link(link: str) -> str:
    """fix link"""
    return link.split("#")[0].replace("http://", "https://").split(  # noqa WPS221
        "&actionStatus=")[0].replace("*", "")


def get_server(link: str) -> str:
    """get server"""
    return link.split("https://", 1)[1].split(".e-sim.org", 1)[0]


def get_id(link: str, parameter: str = "id") -> int:
    """get id"""
    return int(link.split(parameter + "=")[1].split("&")[0])


class Period(Transformer):
    """Period"""

    async def transform(self, interaction: Interaction, period: str) -> str:
        lookup_split = period.split()
        if not any(x in period.lower() for x in ("hour", "day", "month", "year")) or \
                len(lookup_split) > 2 or (len(lookup_split) == 2 and not lookup_split[0].isdigit()):
            error_msg = f"`period` can be `X hours/days/months/years`, example: 1 month (not {period})"
            raise CheckFailure(error_msg)
        return period.replace("s", "")  # remove trailing s


class Server(Transformer):
    """Server"""

    async def transform(self, interaction: Interaction, server: str) -> str:
        return server

    @property
    def choices(self) -> list[Choice]:
        return [Choice(name=x, value=x) for x in all_servers]


class Country(Transformer):
    """Country"""

    async def transform(self, interaction: Interaction, country: str) -> str:
        if country.lower() in all_countries_by_name:
            return all_countries[all_countries_by_name[country.lower()]]
        raise TransformerError(country, self.type, self)

    async def autocomplete(self, interaction: Interaction, value: str, /) -> list:
        return [Choice(name=k, value=k) for k in sorted(
            all_countries.values(), key=lambda x: SequenceMatcher(None, x.lower(), value.lower()).ratio(),
            reverse=True)][:10]


class BattleTypes(Transformer):
    """BattleTypes"""

    async def transform(self, interaction: Interaction, battles_types: str) -> tuple[str, ...]:
        correct_battle_types = ('ATTACK', 'CIVIL_WAR', 'COUNTRY_TOURNAMENT', 'CUP_EVENT_BATTLE', 'LEAGUE',
                                'MILITARY_UNIT_CUP_EVENT_BATTLE', 'PRACTICE_BATTLE', 'RESISTANCE', 'DUEL_TOURNAMENT',
                                'TEAM_NATIONAL_CUP_BATTLE', 'TEAM_TOURNAMENT', 'WORLD_WAR_EVENT_BATTLE')
        battle_mapping = {
            'ww': 'WORLD_WAR_EVENT_BATTLE',
            'world war': 'WORLD_WAR_EVENT_BATTLE',
            'tournament': 'COUNTRY_TOURNAMENT',
            'country tournament': 'COUNTRY_TOURNAMENT',
            'country': 'COUNTRY_TOURNAMENT',
            'cw': 'CIVIL_WAR',
            'civil war': 'CIVIL_WAR',
            'rw': 'RESISTANCE',
            'resistance war': 'RESISTANCE',
            'cup': 'CUP_EVENT_BATTLE',
            'mu cup': 'MILITARY_UNIT_CUP_EVENT_BATTLE',
            'duel': 'DUEL_TOURNAMENT'
        }
        battle_types = tuple(battle_mapping.get(formal_battle_type.lower().strip(), formal_battle_type.strip().upper())
                             for formal_battle_type in
                             battles_types.replace("and", ",").replace("\n", ",").split(","))

        for x in battle_types:
            if x not in correct_battle_types:
                raise CheckFailure(f"No such type (`{x}`). Pls choose from this list:\n" + ", ".join(
                    [f"`{i}`" for i in correct_battle_types]))
        return battle_types or ('ATTACK', 'RESISTANCE')


class Ids(Transformer):
    """Ids"""

    async def transform(self, interaction: Interaction, ids: str) -> tuple:
        try:
            fixed_ids = ids.replace("_", "-").replace("\n", " ").replace(",", " ")
            ids_list = fixed_ids.split()
            if ".e-sim.org" in ids:
                ids = (get_id(ids),)
            elif ids.startswith("https://"):
                if ids.startswith("https://docs.google.com/spreadsheets/d/"):
                    ids = ids.split("/edit")[0] + "/export?format=csv"
                async with bot.session.get(ids, ssl=True) as respond:
                    ids = sorted(
                        {i.replace("\r", "").replace(",", "") for i in (await respond.text()).splitlines() if i})
            elif "-" in fixed_ids:
                ids_list = ids.split("-")
                ids = range(int(ids_list[0]), int(ids_list[-1]) + 1)
            elif len(ids_list) == 1:
                ids = range(int(ids_list[0]), int(ids_list[0]) + 1)
            else:
                ids = utils.strip(ids_list, apply_function=int)

            if len(ids) > 500 and not await utils.is_premium_level_1(interaction, False, False):
                raise CheckFailure("It's too much... sorry. "
                                   "You can buy premium at https://www.buymeacoffee.com/RipEsim to remove this limit.")
            return ids
        except (ValueError, IndexError) as exc:
            raise TransformerError(ids, self.type, self) from exc


class AuctionLink(Transformer):
    """AuctionLink"""

    async def transform(self, interaction: Interaction, link: str) -> dict:
        if link.startswith("http") and "auction" in link:
            link = fix_link(link)
            server = get_server(link)
            auction_id = get_id(link)
            return {"server": utils.server_validation(server), "id": auction_id, "base": "auction"}
        raise TransformerError(link, self.type, self)


class ProfileLink(Transformer):
    """ProfileLink"""

    async def transform(self, interaction: Interaction, link: str) -> dict:
        result = {"base": "profile"}
        link = link.replace("_", "-")
        if link in all_servers:
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


class TournamentLink(Transformer):
    """TournamentLink"""

    async def transform(self, interaction: Interaction, tournament_link: str) -> str:
        link = tournament_link.split("#")[0].replace("http://", "https://")  # noqa WPS221
        if any(x in link for x in ("tournamentEvent.html?id=", "teamTournament.html?id=",
                                   "countryTournament.html?id=")):
            return link
        raise TransformerError(tournament_link, self.type, self)


class BattleLink(Transformer):
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
                battle, last_battle = (int(x) for x in link.split("_"))
                server = ""
            else:
                raise TransformerError(link, self.type, self)

            if server:
                server = utils.server_validation(server)
            return {"server": server, "id": int(battle), "last": last_battle, "round": round_id, "base": "battle"}
        except (ValueError, IndexError) as exc:
            raise TransformerError(link, self.type, self) from exc


class Product(Transformer):
    """Product"""

    def __init__(self, products_list: tuple = all_products):
        self.products = products_list

    async def transform(self, interaction: Interaction, product: str) -> str:
        return product.upper()

    @property
    def choices(self) -> list[Choice]:
        return [Choice(name=x, value=x.upper()) for x in all_products]


class Slots(Transformer):
    """Slots"""

    async def transform(self, interaction: Interaction, slot: str) -> str:
        return slot.title()

    @property
    def choices(self) -> list[Choice]:
        slots = ("helmet", "vision", "armor", "pants", "shoes", "lucky charm", "weapon upgrade", "offhand")
        # TODO: can we return tuple?
        return [Choice(name=x.title(), value=x.title()) for x in slots]
