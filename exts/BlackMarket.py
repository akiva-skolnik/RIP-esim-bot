"""BlackMarket.py"""
from collections import defaultdict
from datetime import date
from random import randint
from typing import Literal, Optional

from discord import Embed, Interaction, User
from discord.app_commands import Range, Transform, checks, command, describe
from discord.ext.commands import GroupCog

from Utils import utils
from Utils.constants import all_products, all_servers
from Utils.transformers import Product, ProfileLink, Server, Slots


class BlackMarket(GroupCog, name="black-market"):
    """Black Market Commands"""

    def __init__(self, bot) -> None:
        self.bot = bot
        super().__init__()

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @command()
    @describe(server="Ignore if you wish to see all offers from all servers.",
              product="you should provide product or eq link (but not both). Ignore both if you wish to see all offers",
              equipment="you should provide product or eq link (but not both). Ignore both if you wish to see all offers")
    async def list(self, interaction: Interaction, server: Optional[Transform[str, Server]],
                   item_quality: Range[int, 0, 8] = 5, product: Transform[str, Product] = "",
                   equipment: Transform[str, Slots] = "") -> None:
        """Display a list of offers for specific products or equipment per server."""
        data = await utils.find_one("collection", __name__)
        if not product and not equipment:
            by_servers = defaultdict(list)
            for offer_dict in sorted(data.values(), key=lambda y: y["server"]):
                if (server and server != offer_dict["server"]) or (
                        offer_dict.get("buy") or offer_dict["server"] not in all_servers):
                    continue
                if offer_dict["item"] not in (y["item"] for y in by_servers[offer_dict["server"]]):
                    by_servers[offer_dict["server"]].append(offer_dict)
            if not by_servers:
                await utils.custom_followup(interaction, f"No offers found for {server or 'all servers'}!", ephemeral=True)
                return
            embed = Embed(colour=0x3D85C6, title="Current selling offers")
            for server, offers in by_servers.items():
                embed.add_field(name="\u200B", value=f"__**{server}:**__", inline=False)
                embed.add_field(name="Item", value="\n".join(x["item"].title() for x in offers))
                embed.add_field(name="Best Offer", value="\n".join(str(x["price"]) for x in offers))
                embed.add_field(name="Created At", value="\n".join(x["created_at"] for x in offers))
            embed.set_footer(text="For more details, you should specify an item.")

        else:
            item = product or equipment
            full_item = f"Q{item_quality} {item}" if item.lower() not in all_products[:6] else item
            rates_db = await utils.find_one("collection", "rates")
            rates = {}
            offers = []
            for offer_id, offer_dict in data.items():
                if full_item.lower() == offer_dict["item"].lower() and server == offer_dict["server"]:
                    offer_dict["id"] = offer_id
                    offers.append(offer_dict)

                    rate = rates_db.get(offer_dict['discord_id'])
                    rates[offer_dict['discord_id']] = str(
                        round(sum(x['rate'] for x in rate) / len(rate),
                              2)) + f"/10 by {len(rate)} users" if rate else "-"

            if not offers:
                await utils.custom_followup(interaction, f"No offers found for {full_item.title()} in {server}!",
                                            ephemeral=True)
                return
            offers = sorted(offers, key=lambda x: x["price"])
            embed = Embed(colour=0x3D85C6, title=full_item.title() + f", {server}")
            if not product:
                embed.add_field(name="Price :moneybag:",
                                value="\n".join(
                                    f"[{x['price']}]({x['stock_or_eq_link']}) ({'buy' if x.get('buy') else 'sell'})" for
                                    x in offers))
            else:
                embed.add_field(name="Price | Stock :moneybag:",
                                value="\n".join(
                                    f"{x['price']} | {int(x['stock_or_eq_link']):,} ({'buy' if x.get('buy') else 'sell'})"
                                    for x in offers))
            embed.add_field(name="User Rate", value="\n".join(rates[x['discord_id']] for x in offers))
            embed.add_field(name=":money_mouth: Seller, Discord",
                            value="\n".join(f"[{x['nick']}]({x['link']}), {x['discord']}" for x in offers))

        await utils.custom_followup(interaction, embed=await utils.custom_author(embed))

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @command()
    @describe(product="you should provide product or eq link (but not both). Ignore both if you wish to see all offers",
              equipment="you should provide product or eq link (but not both). Ignore both if you wish to see all offers",
              stock_or_eq_link="if you provided a product, you must provide the stock, "
                               "and if an eq, you must provide its link.")
    async def add(self, interaction: Interaction, action: Literal["buy", "sell"],
                  your_profile_link: Transform[dict, ProfileLink], item_quality: Optional[Range[int, 0, 8]],
                  product: Optional[Transform[str, Product]], equipment: Optional[Transform[str, Slots]],
                  price: float, stock_or_eq_link: str) -> None:
        """Add a buy/sell offer to the black market."""

        if not product and not equipment:
            await utils.custom_followup(interaction, "You must provide product or eq", ephemeral=True)
            return
        item = (product or equipment).lower()
        if item not in all_products[:6] and not item_quality:
            await utils.custom_followup(interaction, "You must provide the item's quality", ephemeral=True)
            return
        server = your_profile_link["server"]
        if equipment and f"https://{server}.e-sim.org/showEquipment.html?id=" not in stock_or_eq_link:
            await utils.custom_followup(interaction, "You must provide an eq link", ephemeral=True)
            return
        if product and not stock_or_eq_link.isdigit():
            await utils.custom_followup(interaction, "You must provide the stock", ephemeral=True)
            return

        nick = your_profile_link["nick_or_id"]
        if isinstance(nick, int):
            api = await utils.get_content(your_profile_link["link"].replace("profile", "apiCitizenById"))
        else:
            api = await utils.get_content(f'https://{server}.e-sim.org/apiCitizenByName.html?name={nick.lower()}')
        link = f'https://{server}.e-sim.org/profile.html?id={api["id"]}'
        nick = api["login"]

        data = await utils.find_one("collection", __name__)
        offer_id = str(randint(10000, 99999))
        while offer_id in data:
            offer_id = str(randint(10000, 99999))
        data[offer_id] = {"server": server, "price": round(price, 4), "buy": action == "buy",
                          "item": (f"Q{item_quality or 5} {item}" if item.lower() not in all_products[:6]
                                   else item).lower(),
                          "stock_or_eq_link": stock_or_eq_link, "discord": str(interaction.user),
                          "discord_id": str(interaction.user.id), "nick": nick, "link": link,
                          "created_at": str(date.today())}
        data = dict(sorted(data.items(), key=lambda x: x[1]["price"]))
        await utils.replace_one("collection", __name__, data)
        await utils.custom_followup(interaction,
                                    f"Your offer id is #`{offer_id}`. You can remove your offer later using this number.")

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @command()
    async def update(self, interaction: Interaction, offer_id: int, price: float, stock: Optional[int]) -> None:
        """Updates an offer in the black market."""
        offer_id = str(offer_id)
        data = await utils.find_one("collection", __name__)
        if offer_id not in data:
            await utils.custom_followup(interaction, "Offer not found.", ephemeral=True)
        elif data[offer_id]["discord_id"] != str(interaction.user.id):
            await utils.custom_followup(interaction, "This offer is not yours.", ephemeral=True)
        else:
            if stock:
                data[offer_id]["stock_or_eq_link"] = stock
            data[offer_id]["price"] = price
            data[offer_id]["created_at"] = str(date.today())

            await utils.replace_one("collection", __name__, data)
            await utils.custom_followup(interaction, "Done.", ephemeral=True)

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @command()
    @describe(offer_id="IMPORTANT: if not given, it will delete all your offers")
    async def remove(self, interaction: Interaction, offer_id: Optional[int]) -> None:
        """
        Remove your offer from the black market.
        Type `/black-market list` to get all your offers ids.
        """
        data = await utils.find_one("collection", __name__)
        if not offer_id:
            for offer_id in list(data):
                if str(interaction.user.id) == data[offer_id]["discord_id"]:
                    del data[offer_id]
            await utils.replace_one("collection", __name__, data)
            await utils.custom_followup(interaction, "I just removed all your offers.", ephemeral=True)
            return

        offer_id = str(offer_id)
        if offer_id not in data:
            await utils.custom_followup(interaction, "Offer was not found.", ephemeral=True)
        elif data[offer_id]["discord_id"] != str(interaction.user.id):
            await utils.custom_followup(interaction, "This offer is not yours.", ephemeral=True)
        else:
            del data[offer_id]
            await utils.replace_one("collection", __name__, data)
            await utils.custom_followup(interaction, "Done.", ephemeral=True)

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @command()
    @describe(server="Ignore if you want to see offers from all servers",
              user="Tag the user you want the data on, or ignore if you want to see your offers")
    async def list_per_user(self, interaction: Interaction, server: Optional[Transform[str, Server]],
                            user: Optional[User]) -> None:
        """Displays a list of items for a given user in the black market."""
        user = user or interaction.user
        data = await utils.find_one("collection", __name__)
        rates = (await utils.find_one("collection", "rates")).get(str(user.id))

        results = {}
        for offer_id, offer_dict in data.items():
            if str(user.id) == offer_dict["discord_id"] and (not server or server == offer_dict["server"]) and (
                    offer_dict["server"] in all_servers):
                results[offer_id] = offer_dict
        results = sorted(results.items(), key=lambda x: x[1]['server'])
        embed = Embed(colour=0x3D85C6, title=f"{user}'s offers")
        if results:
            embed.add_field(name="Offer Id | Nick",
                            value="\n".join(f"# {k} | [{v['nick']}]({v['link']})" for k, v in results))
            embed.add_field(name="Offer Details", value="\n".join(
                ("" if server else f"**{v['server']}: **") + (
                    f"{v['stock_or_eq_link']} {v['item']} at {v['price']}" if "http" not in v['stock_or_eq_link']
                    else f"[{v['item']}]({v['stock_or_eq_link']}) at {v['price']}") + f" ({'buy' if v.get('buy') else 'sell'})"
                for k, v in results))
            embed.add_field(name="Time Created", value="\n".join(v['created_at'] for k, v in results))

        if rates:
            embed.add_field(name="__**Your Rates:**__", value="\u200B", inline=False)
            embed.add_field(name="User", value="\n".join(rate['user'] for rate in rates))
            embed.add_field(name="Rate", value="\n".join(rate['rate'] for rate in rates))
            embed.add_field(name="Reason", value="\n".join(rate['reason'] for rate in rates))
            embed.set_footer(
                text=f"\nYour average rate is {round(sum(rate['rate'] for rate in rates) / len(rates), 2)} from 10")

        if not results and not rates:
            await utils.custom_followup(interaction, "You do not have any offer yet. You can use `/black-market add`",
                                        ephemeral=True)
        else:
            await utils.custom_followup(interaction, embed=await utils.custom_author(embed))

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @command()
    async def rate(self, interaction: Interaction, user: User, rate: Range[float, 0.0, 10.0], reason: str = "") -> None:
        """Give feedback about a user, and help other players to know if he's reliable."""
        if user == interaction.user:
            await utils.custom_followup(interaction, "You can't rate yourself, obviously.", ephemeral=True)
            return
        rates_db = await utils.find_one("collection", "rates")
        rate_dict = {"user": str(interaction.user), "id": str(interaction.user.id), "rate": rate, "reason": reason}
        user_id = str(user.id)
        if user_id not in rates_db:
            rates_db[user_id] = [rate_dict]
        else:
            for rate in rates_db[user_id]:
                if str(interaction.user.id) == str(rate["id"]):
                    rate["rate"] = rate
                    rate["reason"] = reason
                    await utils.replace_one("collection", "rates", rates_db)
                    await utils.custom_followup(interaction, "Rate updated.", ephemeral=True)
                    return
            rates_db[user_id].append(rate_dict)
        await utils.replace_one("collection", "rates", rates_db)
        await utils.custom_followup(interaction, "Done.", ephemeral=True)


async def setup(bot) -> None:
    """Setup"""
    await bot.add_cog(BlackMarket(bot))
