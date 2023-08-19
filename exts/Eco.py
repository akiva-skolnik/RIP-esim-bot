"""Eco.py"""
import statistics
from collections import defaultdict
from csv import writer
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from typing import Optional

import pandas as pd
from discord import Embed, File, Interaction
from discord.app_commands import Range, Transform, check, checks, command, describe, rename
from discord.ext.commands import BadArgument, Cog
from lxml import html
from matplotlib import pyplot as plt
from matplotlib.ticker import MultipleLocator
from pytz import timezone

from Help import utils
from Help.transformers import Country, Product, ProfileLink, Server
from Help.utils import CoolDownModified, draw_pil_table, split_list

options = ["iron", "grain", "oil", "stone", "wood", "diamonds"]
product_gids = {"primera": 6602346, "secura": 1142213909, "suna": 1317638633, "alpha": 1073258602,
                'luxia': 1542255867, "azura": 2005137513, "zeta": 755107492, "delta": 1948556513}


class Eco(Cog, command_attrs={"cooldown_after_parsing": True, "ignore_extra": False}):
    """Economy Commands"""

    def __init__(self, bot) -> None:
        self.bot = bot

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(workers="workers * eco skill (example: 1 x 2.5 + 3 x 4.6)")
    async def company(self, interaction: Interaction, quality: Optional[Range[int, 0, 5]],
                      company_type: Transform[str, Product],
                      country_control_capital: bool, high_resource: bool, speed_server: bool, workers: str) -> None:
        """Company production calculator."""

        if not quality:
            quality = 5
        workers = workers.replace("`", "").replace("*", "x").replace(",", "+").lower().split("+")
        workers_dict = {}
        for x in workers:
            if "x" not in x:
                x = "1x" + x
            n_workers, skill = x.split("x")
            workers_dict[float(skill)] = int(n_workers)
        workers_count = workers_dict.values()
        ecos = [[k] * v for k, v in workers_dict.items()]
        ecos = [j for i in ecos for j in i]

        raw = company_type.lower() in self.bot.products[:6]
        high_raw = high_product = False
        if high_resource:
            if raw:
                high_raw = True
            else:
                high_product = True
        worker = []
        for worker_count, ES in zip(range(1, sum(workers_count) + 1), ecos):
            E = float(ES)  # Economy skill level
            # N = Number of employees already worked that day in the company.
            if worker_count < 10:
                N = 15 - (worker_count - 1) / 2
            elif worker_count < 20:
                N = 13 - (3 * worker_count) / 10
            elif worker_count < 30:
                N = 11 - worker_count / 5
            else:
                N = 5
            R = 4 * (quality / 20 + 1 / 5) if high_raw else 3 * (quality / 20 + 1 / 5) if raw else 1  # Raw effects
            M = 1.25 if high_product else 1  # Manufactured effects
            C = 0.75 if not country_control_capital else 1  # Capital malus
            S = 3 if speed_server else 1  # Speed server bonus production
            P = (4 + E) * N * C * R * M * S
            worker.append(P)
        high = ("high", True) if high_product or high_raw else ("high", False)
        parameters = [("capital", country_control_capital), high, ("speed", speed_server)]
        parameters = [i[0] for i in parameters if i[1]]

        embed = Embed(colour=0x3D85C6, title=f"Q{quality} {company_type.title()}, {', '.join(parameters)}".title())
        if not raw:
            mined = {"food": 1, "ticket": 4, "estate": 600, **{k: 2 for k in ("gift", "weapon")},
                     **{k: 300 for k in ("defense_system", "hospital", "house")}}.get(company_type.lower())
            embed.add_field(name=f"**Productivity:** {round(int(sum(worker)) / (int(quality) * mined), 2)}",
                            value=f"**Raw materials consumed:** {round(sum(worker), 2)}", inline=False)
        else:
            embed.add_field(name=f"**Productivity:** {round(sum(worker), 2)}", value="\u200B", inline=False)
        embed.add_field(name="**Number of workers:**", value="\n".join([str(v) for v in workers_dict.values()]))
        embed.add_field(name="**Eco skill (each):**", value="\n".join([str(k) for k in workers_dict]))
        await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed))

    @checks.dynamic_cooldown(CoolDownModified(30))
    @command()
    async def job(self, interaction: Interaction, server: Transform[str, Server], skill: float) -> None:
        """Job finder."""

        await interaction.response.defer()
        base_url = f"https://{server}.e-sim.org/"
        skill = int(skill)
        data = {}
        api_countries = utils.get_countries(server)
        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File("files/typing.gif"))
        for index, (k, v) in enumerate(api_countries.items()):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(index, len(api_countries), msg)
            tree = await utils.get_content(f"{base_url}getJobOffers.html?countryId={k}&minimalSkill={skill}&regionId=0")
            salary = tree.xpath('//*[@class="currency"]/b/text()')
            if salary:
                try:
                    func = utils.get_locked_content if server == "primera" else utils.get_content
                    tree = await func(f"{base_url}monetaryMarketOffers?sellerCurrencyId=0&buyerCurrencyId={k}&page=1")
                    mm_ratio = tree.xpath("//*[@class='ratio']//b/text()")[0]
                except Exception:
                    continue
                gold = round(float(mm_ratio) * float(salary[0]), 4)
                data[f"{base_url}jobMarket.html?countryId={k}&minimalSkill={skill}"] = (gold, v[0], mm_ratio)
                await utils.custom_delay(interaction)

        embed = Embed(colour=0x3D85C6, title=f"Job offers at {server}, skill {skill}")
        data = sorted(data.items(), key=lambda item: item[1], reverse=True)[:10]
        embed.add_field(name="Link", value="\n".join(
            f"{utils.codes(v[1])} [{v[1].title()}]({k})" for k, v in data))
        embed.add_field(name="Gold", value="\n".join(f"{v[0]}g" for k, v in data))
        embed.add_field(name="MM rate", value="\n".join(v[2] for k, v in data))
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text="* The results do not include taxes")
        await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed))

    @command()
    async def npc_help(self, interaction: Interaction):
        hint = """**General info about NPC:**
(might be outdated)
            
- NPC is an automated worker who takes the highest-paying job available.
    > If you have premium, you can see their stats at https://<server>.e-sim.org/npcStatistics.html

- To hire an unemployed NPC, offer a salary equal to 2x + 0.01 (where x is their skill level).

- To hire an employed NPC, offer a salary equal to their current salary / 0.9 + 0.01.
    > Hence, to keep your employed NPC - make sure the offer in the market, minus 10% (`X*0.9`), is lower or equal to the current salary.

- You cannot hire NPC through organizations or military units, but:
- Governments can profit a lot from NPC through currency printing, taxes, and NPC donations to their treasury.

- The best way to hurt your enemy is to find out what is the maximum salary they are willing to pay for an NPC, and force them to pay it every single day.
    This means you may have to sacrifice some gold for a few days, but it will show your opponent that you are serious.


- Another method is to place high salary offers, This will force your enemy to raise the salaries or risk losing the NPC.
    The NPC may leave its job and try to apply again later, which is when you can create a small offer to employ it.
    It's best to create multiple offers, one for each NPC, to force each of them to leave.

- A company can only be relocated once every 24 hours.

        Good Luck :)
        """

        await interaction.response.send_message(hint)

    # TODO: auto find region and hour
    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(hour="when an NPC worked (example: 14:43 or 00:25:35)",
              region_id="the region in which the NPC worked",
              seconds_per_region="NPC's work delay between regions")
    async def npc(self, interaction: Interaction, server: Transform[str, Server],
                  hour: str, region_id: int, seconds_per_region: float = 105.0) -> None:
        """If you know when a NPC worked, I can help you to know when the rest of them will."""

        try:
            hours, minutes, seconds = (int(x) for x in (hour if hour.count(":") == 2 else hour + ":00").split(":"))
            seconds += hours * 3600 + minutes * 60 - seconds_per_region
        except Exception:
            await utils.custom_followup(interaction, f"Hour format should be like 14:43 or 00:25:35 (not {hour})",
                                        ephemeral=True)
            return

        await interaction.response.defer()
        base_url = f"https://{server}.e-sim.org/"
        regions = sorted(await utils.get_content(f'{base_url}apiRegions.html'), key=lambda x: x["id"])

        countries = utils.get_countries(server, index=0)
        regions_country = {}
        for region in regions:
            if region["homeCountry"] not in regions_country:
                regions_country[region["homeCountry"]] = []
            regions_country[region["homeCountry"]].append(region["id"])

        for k, v in regions_country.items():
            v = sorted(v)
            regions_country[k] = v[0] if v[0] == v[1] - 1 else v[1]
        regions_country = {v: k for k, v in regions_country.items()}

        regions = [k for k in regions if k['id'] >= region_id] + [k for k in regions if k['id'] < region_id]
        result = []
        output = StringIO()
        csv_writer = writer(output)
        csv_writer.writerow(["Estimate Time", "Region Id", "Region Name", "Country Id",
                             "Country Name", "Raw Richness", "Resource"])
        count = 1
        for row in regions:
            seconds += seconds_per_region
            region = row["id"]
            country_name = countries[row["homeCountry"]].title()
            estimate_time = str(timedelta(seconds=int(seconds))).replace("1 day, ", "")
            csv_writer.writerow([estimate_time, region, row["name"], row["homeCountry"], country_name,
                                 row["rawRichness"].title().replace("None", ""),
                                 row.get("resource", "").title()])
            if region in regions_country:
                result.append((count, f"{utils.codes(country_name)} " + country_name, estimate_time))
                count += 1

        embed = Embed(colour=0x3D85C6, title="NPC Estimate work time per country",
                      description=f"**ASSUMING npc have worked at region {region_id} at {hour}**")
        embed.set_footer(text="NPCs will probably work around the estimated hours unless there is lag from e-sim")
        headers = ["#", "Country", "Estimate Work Time"]
        output.seek(0)
        await utils.send_long_embed(interaction, embed, headers, result,
                                    files=[File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
                                           File(fp=BytesIO(output.getvalue().encode()),
                                                filename=f"NPC_estimate_time_{server}.csv")])

    @check(utils.is_premium_level_1)
    @command(name="npc-stats")
    async def npc_stats(self, interaction: Interaction, server: Transform[str, Server]) -> None:
        """Displays npc stats."""

        if server not in self.bot.orgs:
            await utils.custom_followup(
                interaction, f"This command is unavailable at the moment.\n"
                             "If you want it to work, DM the author (@34444#8649) with org password (for premium)",
                ephemeral=True)
            return
        await interaction.response.defer()
        base_url = f"https://{server}.e-sim.org/"
        mm_dict = {}
        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File("files/typing.gif"))
        countries = utils.get_countries(server, index=2)
        length = len(countries) * 7
        for index, (country_id, mm_name) in enumerate(countries.items()):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(index, length, msg)
            try:
                func = utils.get_locked_content if server == "primera" else utils.get_content
                tree = await func(f"{base_url}monetaryMarketOffers?sellerCurrencyId=0&buyerCurrencyId={country_id}&page=1")
                ratio = float(tree.xpath("//*[@class='ratio']//b/text()")[0])
            except Exception:
                ratio = 0
            mm_dict[mm_name] = ratio
            await utils.custom_delay(interaction)

        output = StringIO()
        csv_writer = writer(output)
        csv_writer.writerow(["NPC name", "Skill", "Salary", "CC", "Salary In Gold", "Company", "Company Link",
                             "Resource", "Raw Richness", "Region", "Region Id", "Country"])
        for index, row in enumerate(
                sorted(await utils.get_content(f"{base_url}apiRegions.html"), key=lambda x: x["id"])):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(index + length // 7, length, msg)
            tree = await utils.get_locked_content(f"{base_url}npcStatistics.html?regionId={row['id']}", org=True)
            for tr in range(2, len(tree.xpath('//table[@class="myTable"][1]//tr/td[1]/a/text()')) + 2):
                name = tree.xpath(f'//table[@class="myTable"][1]//tr[{tr}]/td[1]/a/text()')[0]
                skill = tree.xpath(f'//table[@class="myTable"][1]//tr[{tr}]/td[2]/text()')[0]
                company = (tree.xpath(f'//table[@class="myTable"][1]//tr[{tr}]//td[3]/a/text()') or [""])[0]
                company_id = utils.get_ids_from_path(tree, f'//table[@class="myTable"][1]//tr[{tr}]//td[3]/a')
                company_link = f"{base_url}company.html?id={company_id[0]}" if company_id else ""
                salary = float(tree.xpath(f'//table[@class="myTable"][1]//tr[{tr}]/td[4]/b/text()')[0])
                cc = tree.xpath(f'//table[@class="myTable"][1]//tr[{tr}]/td[4]/text()')[1].strip()
                csv_writer.writerow(
                    [name, skill, salary, cc, mm_dict.get(cc.lower(), 0) * salary, company, company_link,
                     row.get("resource", "").title(), row["rawRichness"].title().replace("None", ""),
                     row["name"], row['id'], (utils.get_countries(server, row["homeCountry"])).title()])
        output.seek(0)
        await utils.custom_followup(interaction, mention_author=True, files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename="NPC_stats.csv")])

    @checks.dynamic_cooldown(CoolDownModified(25))
    @command()
    async def penalty(self, interaction: Interaction, server: Transform[str, Server],
                      raw: Transform[str, Product(options)], country: Transform[str, Country] = "") -> None:
        """Shows list of region penalties for the given raw product"""

        if server in ("secura", "primera", "suna"):
            await utils.custom_followup(
                interaction, "As far as I know, there is no regions penalty in this server", ephemeral=True)
            return

        await interaction.response.defer()
        country_name, country = country, self.bot.countries_by_name.get(country.lower())

        data = []
        for i in await utils.get_content(f'https://{server}.e-sim.org/apiMap.html'):
            if i['rawRichness'] != "HIGH":
                continue
            try:
                if not country:
                    if i['raw'] == raw.upper():
                        data.append(i['regionId'])
                else:
                    if i['occupantId'] == country:
                        if i['raw'] == raw.upper():
                            data.append(i['regionId'])
            except KeyError:
                continue
        msg = await utils.custom_followup(
            interaction, "Progress status: 1%.\n(I will update you after every 10%)" if len(data) > 10 else
            "I'm on it, Sir. Be patient.", file=File("files/typing.gif"))
        data1 = {}
        for index, region_id in enumerate(data):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(index, len(data), msg)
            link = f'https://{server}.e-sim.org/region.html?id={region_id}'
            tree = await utils.get_content(link)
            region = tree.xpath("//tr[2]//td[1]//span")[0].text
            penalties = [x.replace("%", "") for x in
                         tree.xpath('//*[@id="esim-layout"]//table[2]//tr[position()>1]//td[4]/text()')]
            companies_type = [x.split()[1].lower() for x in
                              tree.xpath('//*[@id="esim-layout"]//table[2]//td[1]/b/text()')]
            penalty_in_region = 100
            for company_type, penalties in zip(companies_type, penalties):
                if company_type == raw.lower():
                    penalty_in_region = penalties
                    break
            data1[link, region] = int(penalty_in_region)
            await utils.custom_delay(interaction)

        embed = Embed(colour=0x3D85C6, title=f"{raw}, {server}".title())
        data1 = sorted(data1.items(), key=lambda x: x[0][1])
        result = [f"**{num + 1}.** {value}% {utils.codes(key[1])} [{key[1][:15]}]({key[0]})" for
                  num, [key, value] in enumerate(sorted(data1, key=lambda x: x[1], reverse=True))][:30]
        if not result:
            await utils.custom_followup(interaction,
                                        f"I couldn't find {raw} regions in {country_name if country else server}")
            return

        for column in await split_list(result, 3 if len(result) > 10 else 2):
            if column:
                embed.add_field(name="\u200B", value="\n".join(column))
        if len(data) > 30:
            embed.set_footer(text="30 out of " + str(len(data)))
        await utils.custom_followup(interaction, embed=await utils.custom_author(embed))

    @command()
    async def price_list(self, interaction: Interaction, server: Transform[str, Server]) -> None:
        """Displays a list of the cheapest prices in the given server"""
        await interaction.response.defer()
        db_dict = await utils.find_one("price", server)
        embed = Embed(colour=0x3D85C6, title=server,
                      description=f"[All products](https://docs.google.com/spreadsheets/d/17y8qEU4aHQRTXKdnlM278z3SDzY16bmxMwrZ0RKWcEI/edit#gid={product_gids.get(server, '')}),"
                                  f" [API For developers]({self.bot.api}/https:/{server}.e-sim.org/prices.html)")
        headers = ["Cheapest Item", "Price", "Stock"]
        results = []
        for item, row in db_dict.items():
            if item != "Product":
                results.append([f"**{item.replace('Defense_System', 'DS')}**: {utils.codes(row[0][2])} {row[0][2]}",
                               f"{row[0][0]}g", f"{row[0][1]:,}"])
        embed.set_footer(text=db_dict["Product"][0][-1])
        await utils.send_long_embed(interaction, embed, headers, results)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(optimal_price="I will let you know once there's an offer below that price",
              real_time="get the most updated data (premium)", quality="Default: Q5")
    async def price(self, interaction: Interaction, server: Transform[str, Server], quality: Optional[Range[int, 0, 5]],
                    item: Transform[str, Product], optimal_price: float = 0.0, real_time: bool = False) -> None:
        """Displays the cheapest prices in the market for a given product / for all products"""
        if real_time and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(
                interaction, "`real_time` is a premium parameter! If you wish to use it, along with many other premium commands, please visit https://www.buymeacoffee.com/RipEsim"
                             "\n\nOtherwise, try again, but this time with `real_time=False`")
            return
        await interaction.response.defer()
        if not quality:
            quality = 5
        base_url = f'https://{server}.e-sim.org/'
        product_name = f"Q{quality} {item.title()}" if item.lower() not in self.bot.products[:6] else item.title()
        best_price = 0
        if not real_time:
            db_dict = await utils.find_one("price", server)
            if product_name in db_dict:
                results = db_dict[product_name][:5]
            else:
                results = None
                if await utils.is_premium_level_1(interaction, False):
                    tree = await utils.get_locked_content(
                        f'{base_url}productMarketOffers?type={item}&countryId=-1&quality={quality}&page=1')
                    market_is_not_empty = tree.xpath("//*[@class='productMarketOffer']//b/text()")
                    if market_is_not_empty:
                        real_time = True

            if not real_time:
                embed = Embed(colour=0x3D85C6, title=f"{product_name}, {server}",
                              description=f"[All products](https://docs.google.com/spreadsheets/d/17y8qEU4aHQRTXKdnlM278z3SDzY16bmxMwrZ0RKWcEI/edit#gid={product_gids.get(server, '')}),"
                                          f" [API For developers]({self.bot.api}/https:/{server}.e-sim.org/prices.html)")
                embed.set_footer(text=db_dict["Product"][0][-1])
                if results:
                    embed.add_field(name="**Link**", value="\n".join(
                            [f"{utils.codes(row[2])} [{row[2]}]({row[3]}) ([MM]({row[4]}))" for row in results]))
                    embed.add_field(name="**Price**", value="\n".join([f"{row[0]}g" for row in results]))
                    embed.add_field(name="**Stock**", value="\n".join([f"{row[1]:,}" for row in results]))
                    best_price = results[0][0]
                else:
                    embed.add_field(name="Error", value="No offers found in the market.")
                last = db_dict["Product"][0][-1].replace("Last update: ", "").replace(" (game time).", "")
                now = datetime.now().astimezone(timezone('Europe/Berlin')).strftime(self.bot.date_format)
                seconds_from_update = (datetime.strptime(now, self.bot.date_format) -
                                       datetime.strptime(last, self.bot.date_format)).total_seconds()
                if seconds_from_update > 3600:
                    channel = self.bot.get_channel(int(self.bot.config_ids["warnings_channel"]))
                    await channel.send(f'Prices for {server} updated {seconds_from_update} seconds ago.')
                    if await utils.is_premium_level_1(interaction, False):
                        real_time = True

        if real_time:
            currency_names = {v: k for k, v in utils.get_countries(server, index=2).items()}
            final = {}
            for page in range(1, 10):  # the last page is unknown
                tree = await utils.get_content(
                    f'{base_url}productMarketOffers?type={item}&countryId=-1&quality={quality}&page={page}')
                raw_prices = tree.xpath("//*[@class='productMarketOffer']//b/text()")
                cc = [x.strip() for x in tree.xpath("//*[@class='price']/div/text()") if x.strip()]
                stock = [int(x) for x in tree.xpath("//*[@class='quantity']//text()") if x.strip()]
                for cc, raw_price, stock in zip(cc, raw_prices, stock):
                    country_id = currency_names[cc.lower()]
                    if country_id not in final:
                        mm_ratio = 0
                        try:
                            func = utils.get_locked_content if server == "primera" else utils.get_content
                            tree = await func(f"{base_url}monetaryMarketOffers?sellerCurrencyId=0&buyerCurrencyId={country_id}&page=1")
                            ratios = tree.xpath("//*[@class='ratio']//b/text()")
                            amounts = tree.xpath("//*[@class='amount']//b/text()")
                            for ratio, amount in zip(ratios, amounts):
                                if float(amount) > 1:
                                    mm_ratio = ratio
                                    break
                            if not mm_ratio and ratios:
                                mm_ratio = ratios[-1]
                        except Exception:
                            pass
                        price = round(float(mm_ratio) * float(raw_price), 4)
                        final[country_id] = {"price": price, "stock": stock,
                                             "country": self.bot.countries[country_id]}
                if len(raw_prices) < 20:  # last page
                    break
                await utils.custom_delay(interaction)

            embed = Embed(colour=0x3D85C6, title=f"{product_name}, {server}")
            final = dict(sorted(final.items(), key=lambda x: x[1]["price"]))
            if final:
                results = []
                for country_id, db_dict in final.items():
                    product_market = f'{base_url}productMarket.html?resource={item}&countryId={country_id}&quality={quality}'
                    monetary_market = f'{base_url}monetaryMarket.html?buyerCurrencyId={country_id}'
                    results.append(
                        [db_dict['price'], db_dict["stock"], db_dict["country"], product_market, monetary_market])
                db_dict = await utils.find_one("price", server)
                db_dict[product_name] = results
                await utils.replace_one("price", server, db_dict)

                embed.add_field(name="**Link**", value="\n".join([
                    f"{utils.codes(DICT['country'])} [{DICT['country']}]({base_url}productMarket.html?"
                    f"resource={item}&countryId={country_id}&quality={quality}) "
                    f"([MM]({base_url}monetaryMarket.html?buyerCurrencyId={country_id}))"
                    for country_id, DICT in final.items()][:5]))
                embed.add_field(name="**Price**", value="\n".join([f"{DICT['price']}g" for DICT in final.values()][:5]))
                embed.add_field(name="**Stock**", value="\n".join([str(DICT["stock"]) for DICT in final.values()][:5]))
                best_price = list(final.values())[0]['price']
                if len(final.keys()) > 5:
                    embed.set_footer(text="(Top 5 offers)")
            else:
                embed.add_field(name="Error", value="No offers found in the market.")

        if optimal_price > 0:
            name_for_db = f"{server} {product_name}"
            db_dict = await utils.find_one("collection", "alert")
            val = f"{interaction.channel.id} {optimal_price}"
            if name_for_db not in db_dict:
                db_dict[name_for_db] = [val]
            else:
                db_dict[name_for_db].append(val)
            await utils.replace_one("collection", "alert", db_dict)
            message = f"I will let you know once there is an offer below that price ({optimal_price})"
        elif optimal_price < 0:
            message = "This embed has been sent because you wrote a specific price at the message I replied, and the price now is lower than that.\n"
            message += "I deleted your request to avoid spam, but feel free to make a new one."
        else:
            message = "You can add optimal price and i will let you know once the price in market is below that price\n"

        db_dict = await utils.find_one("prices_history", product_name.replace(" ", "_"))
        db_dict = db_dict[server] if server in db_dict else {}
        if len(db_dict.keys()) > 2:
            def x(db_dict: dict) -> BytesIO:
                d = []
                d1 = []
                length = 0
                for k, v in db_dict.items():
                    length += 1
                    d.append(datetime.strptime(k, "%d-%m-%Y"))
                    d1.append(sum(float(key) * val for key, val in v.items()) / sum(v.values()))

                if best_price:
                    d.append(datetime.now().astimezone(timezone('Europe/Berlin')))
                    d1.append(best_price)

                temp_server = server in ('azura', 'zeta', 'delta')
                med = statistics.median(d1)
                std = statistics.stdev(d1)
                window = 12 if not temp_server else 7
                average_y = []
                for i, item in enumerate(d1):
                    d1[i] = min(item, med + 2 * std)
                    if i + window // 2 <= len(d1) and i >= window // 2:
                        average_y.append(statistics.median(d1[i - window // 2: i + window // 2]))
                    else:
                        average_y.append(None)
                fig, ax = plt.subplots()
                ax.set_title(f"{product_name}, {server}")
                ax.set_ylabel('Price')
                ax.set_xlabel('Date')
                ax.plot(d, d1, label="Daily Average" if temp_server else "Monthly Average")
                if any(average_y):
                    ax.plot(d, average_y, '.-', label="Moving Average")
                ax.legend()
                fig.autofmt_xdate()
                ax.grid()
                return utils.plt_to_bytes()

            output_buffer = await self.bot.loop.run_in_executor(None, x, db_dict)
            file = File(fp=output_buffer, filename=f"{interaction.id}.png")
            embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
            await utils.custom_followup(interaction, message, file=file, embed=await utils.convert_embed(interaction, embed))
        else:
            await utils.custom_followup(interaction, message, embed=await utils.convert_embed(interaction, embed))

    @command()
    @check(utils.is_premium_level_1)
    @describe(link="profile, military unit or stock company link")
    async def productivity(self, interaction: Interaction, link: str) -> None:
        """Companies productivity results (per player / MU / SC)."""
        await interaction.response.defer()
        link = link.split("#")[0].replace("http://", "https://")
        server = link.split("https://", 1)[1].split(".e-sim.org", 1)[0]
        base_url = f"https://{server}.e-sim.org/"
        used = defaultdict(lambda: [0] * 10)
        produced = defaultdict(lambda: [0] * 10)
        headers1 = []
        link = link.replace("militaryUnit.html", "militaryUnitCompanies.html").replace("profile", "companies")

        if "/stockCompany.html" in link:
            tree = await utils.get_locked_content(link)

            types = [x.strip() for x in tree.xpath('//tr//td[1]//div[4]//tr[position()>1]//td[2]/text()')]
            companies = utils.get_ids_from_path(tree, '//tr//td[1]//div[4]//tr[position()>1]//td[1]/a')

        elif "/militaryUnitCompanies.html" in link or "/companies.html" in link:
            tree = await utils.get_locked_content(link)
            companies = utils.get_ids_from_path(tree, '//*[@id="myCompaniesToSortTable"]//tr//td[1]/a')
            types = [x.split("productIcons/")[1].split(".")[0].replace("Rewards/", "") for x in
                     tree.xpath('//*[@id="myCompaniesToSortTable"]//tr//td[2]//img[1]/@src')]
            qualities = [x.split("productIcons/")[1].split(".")[0].upper() for x in
                         tree.xpath('//*[@id="myCompaniesToSortTable"]//tr//td[2]//img[2]/@src')]
            types = [Type if Type in ["Iron", "Diamonds", "Grain", "Oil", "Stone", "Wood"] else f"{Q} {Type}" for
                     Q, Type in zip(qualities, types)]
        else:
            await utils.custom_followup(interaction, "`link` must be SC / MU / profile link!", ephemeral=True)
            return
        try:
            name = link if "/companies.html" in link else tree.xpath("//span[@class='big-login']")[0].text
        except IndexError:
            name = link
        if not companies:
            await utils.custom_followup(interaction, "No companies found", ephemeral=True)
            return

        msg = await utils.custom_followup(
            interaction, "Progress status: 1%.\n(I will update you after every 10%)" if len(companies) > 10 else
            "I'm on it, Sir. Be patient.", file=File("files/typing.gif"))
        product_raw = {"Weapon": "Iron", "House": "Wood", "Gift": "Diamonds",
                       "Food": "Grain",
                       "Ticket": "Oil", "Defense System": "Stone", "Hospital": "Stone",
                       "Estate": "Stone"}
        for index, (company, company_type) in enumerate(zip(companies, types)):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(index, len(companies), msg)
            await utils.custom_delay(interaction)
            try:
                tree = await utils.get_locked_content(base_url + 'companyWorkResults.html?id=' + str(company))
            except Exception:
                await utils.custom_followup(interaction, f"Skipped company {company}")
                continue
            if not headers1:
                headers1 = tree.xpath('//*[@id="productivityTable"]//tr[1]//td[position()>2]//text()')
            df = pd.read_html(html.tostring(tree))[0]
            raw = " ".join([x for x in company_type.split() if "Q" not in x])
            not_raw = raw not in ("Iron", "Diamonds", "Grain", "Oil", "Stone", "Wood")
            for i, row in df.iloc[1:, 2:].iterrows():
                for key, value in row.items():
                    if not isinstance(value, str):
                        continue
                    produced[company_type][key - 2] += sum(float(unit[1:-1]) for unit in value.split()[1::2])
                    if not_raw:
                        used[product_raw[raw]][key - 2] += sum(float(unit) for unit in value.split()[0::2])

        db_dict = await utils.find_one("price", server)
        output = StringIO()
        csv_writer = writer(output)
        total_cost = 0
        total_profit = 0
        per_day = defaultdict(lambda: {"cost": 0, "worth": 0})
        csv_writer.writerow(
            ["Raw Used", "Cost (gold)"] + headers1 + ["Sum (units)", "Daily Average (units)", "Sum (gold)",
                                                      "Daily Average (gold)"])
        for k, v in used.items():
            val = db_dict.get(k, [[0]])[0][0]
            s = round(sum(v), 2)
            total_cost += val * s
            csv_writer.writerow([k, val] + [round(x, 2) for x in v] + [s, round(s / len(v), 2), round(val * s, 2),
                                                                       round(val * s / len(v), 2)])
            for index, x in enumerate(v):
                per_day[headers1[index]]["cost"] += val * x

        csv_writer.writerow([""])

        csv_writer.writerow(
            ["Produced", "Worth (gold)"] + headers1 + ["Sum (units)", "Daily Average (units)", "Sum (gold)",
                                                       "Daily Average (gold)"])
        for k, v in produced.items():
            val = db_dict.get(k.replace("Defense System", "Defense_System"), [[0]])[0][0]
            s = round(sum(v), 2)
            total_profit += val * s
            csv_writer.writerow([k, val] + [round(x, 3) for x in v] + [s, round(s / len(v), 2), round(val * s, 2),
                                                                       round(val * s / len(v), 2)])
            for index, x in enumerate(v):
                per_day[headers1[index]]["worth"] += val * x

        csv_writer.writerow([""])
        csv_writer.writerow(["Cost per day (gold)", ""] + [str(round(val["cost"], 2)) for val in per_day.values()])
        csv_writer.writerow(["Worth per day (gold)", ""] + [str(round(val["worth"], 2)) for val in per_day.values()])
        csv_writer.writerow(
            ["Profit per day (gold)", ""] + [str(round(val["worth"] - val["cost"], 2)) for val in per_day.values()])
        csv_writer.writerow([""])
        csv_writer.writerow(["Total Cost:", round(total_cost, 2)])
        csv_writer.writerow(["Total Worth (gold):", "", round(total_profit, 2)])
        csv_writer.writerow(
            ["Net Profit (gold):", "", round(total_profit - total_cost, 2), "", "* SALARIES ARE NOT INCLUDED!"])
        output.seek(0)

        embed = Embed(colour=0x3D85C6, title=name, url=link,
                      description='Net profit per day, based on market prices\nSalaries are not included!')
        embed.add_field(name="Day", value="\n".join(per_day.keys()))
        embed.add_field(name="Theoretical Estimated Profit",
                        value="\n".join(f"{round(val['worth'] - val['cost']):,}g" for val in per_day.values()))
        embed.add_field(name="\u200B", value="\u200B")

        embed.add_field(name="Average", value=f"{round((total_profit - total_cost) / len(per_day)):,}g")
        embed.add_field(name="Median",
                        value=f"{round(statistics.median([val['worth'] - val['cost'] for val in per_day.values()])):,}g")
        embed.add_field(name="Sum", value=f"{round(total_profit - total_cost):,}g")

        fig, ax = plt.subplots()
        ax.set_title("Theoretical Estimated Profit Per Day")
        ax.set_ylabel('Gold')
        ax.set_xlabel('Day')
        ax.plot(list(per_day.keys())[:-1],
                [val['worth'] - val['cost'] for val in per_day.values()][:-1])
        ax.grid()
        output_buffer = utils.plt_to_bytes()
        file = File(fp=output_buffer, filename=f"{interaction.id}.png")
        embed.set_thumbnail(url=f"attachment://{interaction.id}.png")

        await utils.custom_followup(
            interaction, mention_author=index > 50, embed=await utils.convert_embed(interaction, embed), files=[
                file, File(fp=BytesIO(output.getvalue().encode()), filename='Productivity.csv'),
                File(fp=await utils.csv_to_image(output, columns=14), filename=f"Preview_{server}.png")])

    @command()
    @check(utils.is_premium_level_1)
    async def sc_profit(self, interaction: Interaction, server: Transform[str, Server], stock_company_id: int) -> None:
        """Displays the profit of each shareholder in a given stock company."""

        base_url = f'https://{server}.e-sim.org/'
        await interaction.response.defer()
        balance = defaultdict(
            lambda: {"profit": 0, "dividends": 0, "shares sold": 0, "shares purchased": 0, "owned shares": 0})
        link = f'{base_url}stockCompanyLogs.html?stockCompanyId={stock_company_id}&type=DIVIDEND_TRANSACTION&importance=TRIVIAL&initiatorId=0'
        try:
            last_page = await utils.last_page(link)
        except Exception:
            await utils.custom_followup(interaction, "No such company! (otherwise - please use `/bug`)")
            return

        link2 = f'{base_url}stockCompanyTransactions.html?id={stock_company_id}'
        last_page2 = await utils.last_page(link2)

        msg = await utils.custom_followup(interaction,
                                          "Progress status: 1%.\n(I will update you after every 10%)" if last_page + last_page2 > 10 else "I'm on it, Sir. Be patient.",
                                          file=File("files/typing.gif"))
        for page in range(1, last_page):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(page, last_page + last_page2, msg)
            tree = await utils.get_content(link + f'&page={page}')
            gold = [float(x) for x in tree.xpath("//tr[position()>1]//td[2]//b[1]//text()")]
            player = [x.strip() for x in tree.xpath("//tr[position()>1]//td[2]//a[@class='profileLink']/text()")]
            for gold, player in zip(gold, player):
                balance[player]["dividends"] += gold
            await utils.custom_delay(interaction)

        for page in range(1, last_page2):
            msg = await utils.update_percent(last_page + page, last_page + last_page2, msg)
            tree = await utils.get_content(link2 + f'&page={page}')
            sellers = [x.strip() for x in tree.xpath("//tr[position()>1]//td[4]//a/text()")]
            buyers = [x.strip() for x in tree.xpath("//tr[position()>1]//td[5]//a/text()")]
            golds = [float(x) for x in tree.xpath("//tr[position()>1]//td[3]//b//text()")]
            amounts = [int(x) for x in tree.xpath("//tr[position()>1]//td[2]//b//text()")]
            for seller, buyer, gold, amount in zip(sellers, buyers, golds, amounts):
                balance[seller]["shares sold"] += amount * gold
                balance[buyer]["shares purchased"] += amount * gold
            await utils.custom_delay(interaction)

        tree = await utils.get_content(f'{base_url}stockCompany.html?id={stock_company_id}')

        per_share = float(tree.xpath('//*[@class="muColEl"]//b/text()')[2])
        shares = [int(x) for x in tree.xpath("//td[2]//div[2]//table[1]//tr[position()>1]//td[1]//b//text()")]
        # Remove "Show" row. It won't work if there's only 1 minor share, but it's really rare.
        shares = [shares[0]] + [shares[x] for x in range(len(shares)) if shares[x] <= shares[x - 1]]
        holders = [x.strip() for x in
                   tree.xpath("//td[2]//div[2]//table[1]//tr[position()>1]//td[2]//a[@class='profileLink']/text()")]
        for share, holder in zip(shares, holders):
            balance[holder]["owned shares"] += share * per_share

        output = StringIO()
        csv_writer = writer(output)
        for v in balance.values():
            v.update({"profit": v["dividends"] + v["shares sold"] + v["owned shares"] - v["shares purchased"]})

        for index, (k, v) in enumerate(sorted(balance.items(), key=lambda x: x[1]["profit"], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Nick"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1, k] + list(v.values()))

        output.seek(0)
        await utils.custom_followup(interaction, mention_author=(last_page + last_page2) > 50, files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"SC_profit_{server}_{stock_company_id}.csv")])

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    async def mm(self, interaction: Interaction, server: Transform[str, Server], country: Transform[str, Country] = "") -> None:
        """Shows monetary market stats per server/country."""
        await interaction.response.defer()
        country_id = self.bot.countries_by_name.get(country.lower(), 0)
        link = f"https://{server}.e-sim.org/monetaryMarket.html?buyerCurrencyId={country_id}"
        get_url = self.bot.api + link.replace("https://", "https:/")
        embed = Embed(colour=0x3D85C6, title=link, description=f"[source]({get_url})")
        if not country:
            mm_db = await utils.find_one("mm", server)
            embed.set_footer(text="Last update: " + mm_db['last_update'])
            del mm_db['last_update']
            headers = ["Id", "Country", "Price"]
            data = [[f"[{k}](https://{server}.e-sim.org/monetaryMarket.html?buyerCurrencyId={k})",
                     utils.get_countries(server, int(k)).title(), v] for k, v in
                    sorted(mm_db.items(), key=lambda item: float(item[1]))]
            return await utils.send_long_embed(interaction, embed, headers, data)
        mm_history = (await utils.find_one("mm_history", server))[str(country_id)]
        d = []
        d1 = []
        length = 0
        for k, v in mm_history.items():
            length += 1
            d.append(datetime.strptime(k, "%d-%m-%Y"))
            d1.append(sum(float(key) * val for key, val in v.items()) / sum(v.values()))
        med = statistics.median(d1)
        std = statistics.stdev(d1)
        for i, item in enumerate(d1):
            d1[i] = min(item, med + 2 * std)
        fig, ax = plt.subplots()
        ax.set_title(f"{utils.get_countries(server, country_id).title()}, {server}")
        ax.set_ylabel('Price')
        ax.set_xlabel('Date')
        ax.plot(d, d1)
        fig.autofmt_xdate()
        ax.grid()
        output_buffer = utils.plt_to_bytes()
        file = File(fp=output_buffer, filename=f"{interaction.id}.png")
        embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
        try:
            func = utils.get_locked_content if server == "primera" else utils.get_content
            tree = await func(f"https://{server}.e-sim.org/monetaryMarketOffers?sellerCurrencyId=0&buyerCurrencyId={country_id}&page=1")
            sellers = tree.xpath("//*[@class='seller']/a/text()")
            buy = tree.xpath("//*[@class='buy']/button")[0].attrib['data-buy-currency-name']
            seller_ids = [int(x.split("?id=")[1]) for x in tree.xpath("//*[@class='seller']/a/@href")]
            amounts = tree.xpath("//*[@class='amount']//b/text()")
            ratios = tree.xpath("//*[@class='ratio']//b/text()")
            row = []
            for seller, seller_id, amount, ratio in zip(sellers, seller_ids, amounts, ratios):
                row.append({"seller": seller.strip(), "seller_id": seller_id, "amount": amount, "ratio": ratio})
            embed.add_field(name="Seller", value="\n".join(
                [f'[{x["seller"]}](https://{server}.e-sim.org/profile.html?id={x["seller_id"]})' for x in row[:5]]))
            embed.add_field(name="Stock", value="\n".join([x["amount"] for x in row[:5]]))
            embed.add_field(name="Price", value="\n".join([x["ratio"] for x in row[:5]]))
            embed.set_footer(text=buy)
        except Exception:
            pass
        await utils.custom_followup(interaction, file=file, embed=await utils.convert_embed(interaction, embed))

    @checks.dynamic_cooldown(CoolDownModified(10))
    @command()
    @describe(value="The eq parameter value (in case you didn't provide a link)",
              parameter="profile link / eq link / eq parameter (Avoid, Max, Crit, Damage, Miss, Flight, Eco, "
                        "Str, Hit, Less, Find, Split, Production, Consume, Merging, Restore, Increase, Evening/Noon...)")
    @rename(parameter="link_or_parameter")
    async def upgrade(self, interaction: Interaction, parameter: str, value: float = -1.0) -> None:
        """Displays estimated parameter value after upgrade, and how many needed until the maximum (90%)"""
        total = {}

        embed = Embed(colour=0x3D85C6)
        files = []
        _, ax = plt.subplots()
        func = interaction.response.send_message
        if "/profile.html?id=" in parameter:
            await interaction.response.defer()
            func = interaction.followup.send
            server_nick = await ProfileLink().transform(interaction, parameter)
            server = server_nick['server']
            base_link = "apiCitizenByName.html?name=" if isinstance(server_nick["nick_or_id"],
                                                                    str) else "apiCitizenById.html?id="
            api = await utils.get_content(
                f"https://{server_nick['server']}.e-sim.org/{base_link}{str(server_nick['nick_or_id']).lower()}")

            embed.title = f"{utils.codes(api['citizenship'])} " + api['login'] + ", " + server
            embed.url = f"https://{server_nick['server']}.e-sim.org/profile.html?id={api['id']}"
            tree = await utils.get_content(embed.url)

            # update values precision from the api (bad format)
            api_items = []
            api_values = []
            for item in api["gearInfo"]:
                if "slot" in item:
                    api_items.append(item["slot"].lower().replace("personal", "").replace("charm", "").replace(
                        "weapon upgrade", "WU").title().strip())
                else:
                    for p in item["parameters"]:
                        api_values.append(p["value"])

            profile_items = {eq_type.split()[1]: {"type": eq_type, "parameters": [list(x) for x in zip(parameters, values)]} for
                             eq_type, parameters, values, eq_link in utils.get_eqs(tree)}
            api_count = 0
            for item in api_items:
                for profile_count in range(len(profile_items[item]["parameters"])):
                    profile_items[item]["parameters"][profile_count][1] = api_values[api_count]
                    api_count += 1
            # end update

            array = []
            for profile_items_values in profile_items.values():
                eq_type = profile_items_values["type"]
                parameters = [x[0] for x in profile_items_values["parameters"]]
                values = [x[1] for x in profile_items_values["parameters"]]
                increase = 1
                if "increase" in parameters:
                    inc_index = parameters.index("increase")
                    increase = values[inc_index] / 100 + 1
                    values[inc_index] *= values[inc_index] / 100 + 1  # Will be fixed later when dividing back
                for parameter, value in zip(parameters, values):
                    data, _, _ = await calc_upgrades(self.bot, parameter, value / increase, total, ax, eq_type)
                    if data:
                        array.append([eq_type, parameter.title()] + data)

            if total:
                biggest_column = max(len(x) for x in array)
                header = ["Slot", "Parameter"] + [f"Upgrade {x + 1}:" for x in range(biggest_column)]
                for row in array:
                    row.extend((biggest_column - len(row)) * [""])
                embed.add_field(name="\n**Upgrades per stat**", value="\n".join(
                    f"**{k.title()}:** {v}" for k, v in sorted(total.items())), inline=False)
                embed.set_footer(text=f"{sum(total.values())} total upgrades")
                files.append(File(fp=await self.bot.loop.run_in_executor(None, draw_pil_table, array, header),
                                  filename=f'{server_nick["nick_or_id"]}.jpg'))

        elif "/showEquipment.html?id=" in parameter:
            api = await utils.get_content(parameter.replace("showEquipment", "apiEquipmentById"))
            embed.title = f"__**Q{api['EqInfo'][0]['quality']} {api['EqInfo'][0]['slot'].title()}**__"
            embed.url = parameter
            if "ownerId" in api['EqInfo'][0]:
                owner_link = f"{parameter.replace('showEquipment', 'profile').split('=')[0]}={api['EqInfo'][0]['ownerId']}"
                embed.description = f"[Owner Profile]({owner_link})"
            embed.set_footer(text="Try also /upgrade <Profile Link>")

            parameters = [p["Name"] for p in api["Parameters"]]
            values = [p["Value"] for p in api["Parameters"]]
            increase = 1
            if "Increase other parameters" in parameters:
                inc_index = parameters.index("Increase other parameters")
                increase = values[inc_index] / 100 + 1
                values[inc_index] *= values[inc_index] / 100 + 1  # Will be fixed later when dividing back

            all_parameters1 = {v: k for k, v in self.bot.all_parameters.items()}
            for name, value in zip(parameters, values):
                parameter = all_parameters1.get(name, "production")
                data, percentages, quality = await calc_upgrades(self.bot, parameter, value / increase, total, ax)
                if data:
                    embed.add_field(name="\u200B", value=f"**{parameter.title()}**", inline=False)
                    embed.add_field(name="Upgrades Count",
                                    value="\n".join([f"**Upgrade {num + 1}:**" for num in range(len(data))]))
                    embed.add_field(name="Expected Value", value="\n".join(data))
                    embed.add_field(name="Percentages", value="\n".join([f'{item * 100:.2f}%' for item in percentages]))
                else:
                    embed.add_field(name="\u200B", value=f"**{parameter.title()}**\nThere's nothing to upgrade!")

        else:
            if parameter.lower() not in self.bot.all_parameters:
                await utils.custom_followup(
                    interaction, f"Possible parameters: {', '.join(self.bot.all_parameters.keys()).title()}.\n"
                                 f"You can also use `<profile link>` or `<eq link>`", ephemeral=True)
                return
            data, percentages, quality = await calc_upgrades(self.bot, parameter.lower(), value, total, ax)
            if data:
                embed.title = f"__**Q{quality} {parameter.title()}**__"
                embed.add_field(name="Upgrades Count",
                                value="\n".join([f"**Upgrade {num + 1}:**" for num in range(len(data))]))
                embed.add_field(name="Expected Value", value="\n".join(data))
                embed.add_field(name="Percentages", value="\n".join([f'{item * 100:.2f}%' for item in percentages]))
                embed.set_footer(text="Try also /upgrade <Profile Link>")

        if not total:
            return await func("There is nothing to upgrade")

        ax.xaxis.set_major_locator(MultipleLocator(1))
        ax.set_yticklabels([f'{x * 100:.0f}%' for x in ax.get_yticks()])
        ax.legend()
        ax.set_xlabel('Upgrades Count')
        output_buffer = utils.plt_to_bytes()
        files.append(File(fp=output_buffer, filename=f"{interaction.id}.png"))
        embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
        await func(files=files, embed=await utils.convert_embed(interaction, embed))


async def calc_upgrades(bot, parameter: str, value: float, total: dict, ax, slot="") -> (list, list, int):
    """calculate upgrades"""
    ranges = {"max": [0, 2, 4, 6, 8, 12, 16, 20],
              "core": [0, 0, 0, 0, 0, 0, 7, 8],  # must be before "damage"
              "bonus damage": [0, 0, 0, 0, 0, 0, 3, 10],
              "damage": [0, 1, 2, 3, 4, 6, 8, 8.5],
              "miss": [0, 1.5, 3, 4.5, 6, 7.5, 9, 9.5],
              "flight": [0.5, 1, 1.5, 2, 3, 4, 5.5, 6],
              "eco": [0.1, 0.2, 0.4, 0.6, 0.8, 1.1, 1.4, 1.6],
              "str": [10, 16, 20, 24, 28, 40, 60, 80],
              "hit": [20, 40, 50, 60, 70, 90, 130, 150],
              "less": [3, 4, 5, 6, 7, 8, 10, 10.5],
              "find": [2, 2.5, 3, 3.5, 4, 4.5, 5, 6],
              "production": [0, 0, 0, 0, 0, 0, 2.5, 3],
              "split": [0, 0, 0, 0, 0, 0, 4, 5],
              "increase": [0, 0, 0, 0, 0, 0, 10, 15],
              "elixir": [0, 0, 0, 0, 0, 0, 6, 10],
              }

    if parameter in ("avoid", "crit", "dmg"):
        ranges = ranges["damage"]
    elif parameter in ("morning", "noon", "evening", "night"):
        ranges = ranges["bonus damage"]
    elif parameter in ("consume", "merge", "merging", "restore", "ammunition"):
        ranges = ranges["production"]
    else:
        ranges = ranges[parameter]

    if value < 0:
        value = ranges[-2]
    if slot:
        lowest, biggest = ranges[int(slot[1]) - 1], ranges[int(slot[1])]
    else:
        try:
            if value == ranges[-1]:
                value -= 0.01
            lowest, biggest = [[x for x in ranges if x <= value][-1], [x for x in ranges if x > value][0]]
        except IndexError as exc:
            raise BadArgument(f"`{parameter.title()}` can be between {ranges[0]} and {ranges[-1]} only!") from exc

    quality = ranges.index(biggest)
    max_value = biggest - (biggest - lowest) / 10
    data = []
    while value < max_value:
        if f"Q{quality} {parameter}" not in total:
            total[f"Q{quality} {parameter}"] = 0
        total[f"Q{quality} {parameter}"] += 1
        upgrade = round((biggest - value) / (3 if not ranges[-1] == biggest else (10 / 3)), 10)
        value += upgrade
        data.append(str(round(value, 2)))

    percentages = [(float(value) - lowest) / (biggest - lowest) for value in data]
    if data:
        await bot.loop.run_in_executor(None, lambda: ax.plot([
            x + 1 for x in range(len(data))], percentages, marker='o', linestyle='--',
            label=f"{slot} ({parameter})" if slot else parameter))
    return data, percentages, quality


async def setup(bot) -> None:
    """Setup"""
    await bot.add_cog(Eco(bot))
