"""Premium.py."""
from collections import defaultdict
from csv import reader, writer
from io import BytesIO, StringIO

from discord import File, Interaction, errors
from discord.app_commands import Transform, check, command, describe
from discord.ext.commands import Cog
from lxml.html import fromstring

from Utils import utils
from Utils.transformers import Ids, Server, Period


class Premium(Cog):
    """Premium Stats Commands.

    Get access at https://www.buymeacoffee.com/RipEsim or https://www.patreon.com/ripEsim
    """

    def __init__(self, bot) -> None:
        self.bot = bot

    @command()
    @check(utils.is_premium_level_1)
    @describe(include_comments="true is slower and false gives more data",
              period="should be similar to e-sim format (<x> hours/days/months/years)")
    async def articles(self, interaction: Interaction, server: Transform[str, Server], include_comments: bool | None,
                       period: Period) -> None:
        """Displays articles stats."""
        my_dict = {"articles": 0, "replies (by author)": 0, "votes": 0, "replies (to author)": 0}
        if not include_comments:
            del my_dict["replies (by author)"], my_dict["replies (to author)"]
        authors_per_month = defaultdict(lambda: my_dict.copy())
        preview_articles = 0
        deleted = 0
        msg = await utils.custom_followup(interaction,
                                          "I'm on it, Sir. Be patient. (I have no idea how long it will take, "
                                          "but i will update this msg every 50 articles)",
                                          file=File(self.bot.typing_gif_path))
        base_url = f"https://{server}.e-sim.org/"
        tree = await utils.get_content(f"{base_url}news.html?newsType=LATEST_ARTICLES")
        article_id = int(utils.get_ids_from_path(tree, "//*[@class='articleTitle']")[0]) + 1
        first = article_id
        logged_out = True
        max_articles = 1000
        for i in range(max_articles + 1):
            if await self.bot.should_cancel(interaction):
                break
            article_id -= 1
            if i % 50 == 0:
                try:
                    msg = await msg.edit(content=f"Checked {first - article_id} articles")
                except errors.NotFound:
                    pass
            if i == max_articles:
                await utils.custom_followup(interaction, f"Checked first {first - article_id} articles")
                break
            try:
                if include_comments:
                    tree = await utils.get_locked_content(f"{base_url}article.html?id={article_id}", logged_out)
                    logged_out = len(tree.xpath('//*[@id="tutorial1"]')) == 1
                else:
                    tree = await utils.get_content(f"{base_url}article.html?id={article_id}")
            except Exception:
                deleted += 1
                continue
            try:
                posted = " ".join(
                    tree.xpath('//*[@class="mobile_article_preview_width_fix"]/text()')[0].split()[1:-1]).lower()
                votes = int(tree.xpath('//*[@class="bigArticleTab"]/text()')[-1].strip())
                author_name = tree.xpath('//*[@class="mobileNewspaperStatus"]/a/text()')[0].strip()
                citizenship = tree.xpath("//*[@class='mobileNewspaperStatus']//div/@class")[0].replace(
                    "xflagsSmall xflagsSmall-", "").replace("-", " ")
            except Exception as error:
                await utils.send_error(interaction, error, str(article_id))
                break
            preview = any(x for x in tree.xpath("//b/text()") if
                          "This article is in preview mode and is not visible in the news section" in x)
            if preview:
                preview_articles += 1
                continue

            if period.lower() in posted:
                break
            authors_per_month[author_name, citizenship, posted]["articles"] += 1
            authors_per_month[author_name, citizenship, posted]["votes"] += votes
            if not include_comments:
                continue

            link = f"{base_url}article.html?id={article_id}"
            last_page = await utils.last_page(link, utils.get_locked_content)
            for page in range(1, last_page):
                await utils.custom_delay(interaction)
                tree = await utils.get_locked_content(link + f"&page={page}")
                authors = (x.replace("\xa0", "") for x in tree.xpath("//*[@id='comments']//div//div[1]//a/text()"))
                citizenships = (x.replace("xflagsSmall xflagsSmall-", "").replace("-", " ") for x in tree.xpath(
                    "//*[@id='comments']//div//div[1]/@class"))
                posted_comment = (x[1:-1] for x in tree.xpath("//*[@id='comments']//div//div[2]//div[1]/text()[2]") if
                                  x != "\n")
                for author, citizenship, posted_comment in zip(authors, citizenships, posted_comment):
                    if "month" not in posted_comment and "year" not in posted_comment:
                        posted_comment = "0 months ago"
                    authors_per_month[author_name, citizenship, posted]["replies (to author)"] += 1
                    authors_per_month[author, citizenship, posted_comment]["replies (by author)"] += 1
            await utils.custom_delay(interaction)

        await msg.delete()
        output = StringIO()
        csv_writer = writer(output)
        countries_per_month = defaultdict(lambda: my_dict.copy())
        authors = defaultdict(lambda: my_dict.copy())
        countries = defaultdict(lambda: my_dict.copy())
        months = defaultdict(lambda: my_dict.copy())
        sum_dict = defaultdict(int)
        for index, (k, v) in enumerate(sorted(authors_per_month.items(), key=lambda x: x[1]['articles'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Nick", "Citizenship", "Time"] + [x.title() for x in v.keys()])
            k = list(k)
            csv_writer.writerow([index + 1] + k + list(v.values()))
            for key, val in v.items():
                countries_per_month[k[1], k[2]][key] += val
                authors[k[0], k[1]][key] += val
                countries[k[1]][key] += val
                months[k[2]][key] += val
                sum_dict[key] += val
        authors_per_month.clear()
        csv_writer.writerow(["Sum", len(authors), len(countries), len(months)] + list(sum_dict.values()))
        output.seek(0)
        files = [File(fp=BytesIO(output.getvalue().encode()),
                      filename=f"articles_per_player_per_month_{article_id}_{first}_{server}.csv")]

        output = StringIO()
        csv_writer = writer(output)
        for index, (k, v) in enumerate(
                sorted(countries_per_month.items(), key=lambda x: x[1]['articles'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Country", "Time"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1] + list(k) + list(v.values()))
        countries_per_month.clear()
        csv_writer.writerow(["Sum", len(countries), len(months)] + list(sum_dict.values()))
        output.seek(0)
        files.append(File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"))
        files.append(
            File(fp=BytesIO(output.getvalue().encode()), filename=f"articles_per_country_per_month_{server}.csv"))

        output = StringIO()
        csv_writer = writer(output)
        for index, (k, v) in enumerate(sorted(authors.items(), key=lambda x: x[1]['articles'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Nick", "Citizenship"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1] + list(k) + list(v.values()))

        csv_writer.writerow(["Sum", len(authors), len(countries)] + list(sum_dict.values()))
        authors.clear()
        output.seek(0)
        files.append(File(fp=BytesIO(output.getvalue().encode()), filename=f"articles_per_player_{server}.csv"))

        output = StringIO()
        csv_writer = writer(output)
        for index, (k, v) in enumerate(sorted(months.items(), key=lambda x: int(x[0].split()[0]))):
            if not index:
                csv_writer.writerow(["#", "Month"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1, k] + list(v.values()))
        csv_writer.writerow(["Sum", len(months)] + list(sum_dict.values()))

        csv_writer.writerow([""])
        for index, (k, v) in enumerate(sorted(countries.items(), key=lambda x: x[1]['articles'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Country"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1, k] + list(v.values()))
        csv_writer.writerow(["Sum", len(countries)] + list(sum_dict.values()))
        output.seek(0)
        files.append(
            File(fp=BytesIO(output.getvalue().encode()), filename=f"articles_per_month_and_country_{server}.csv"))

        await utils.custom_followup(interaction,
                                    f"{deleted} articles deleted in this period.\n"
                                    f"{preview_articles} articles in preview mode.\n"
                                    f"You can calculate more stats in Excel, such as avg votes per article etc.",
                                    files=files,
                                    mention_author=first - article_id > 100)

    @command()
    @check(utils.is_premium_level_1)
    @describe(auctions_ids="first-last or id1, id2, id3...")
    async def auctions(self, interaction: Interaction, server: Transform[str, Server],
                       auctions_ids: Transform[list, Ids]) -> None:
        """Displays data about range of auctions."""
        msg = await utils.custom_followup(interaction,
                                          "Progress status: 1%.\n(I will update you after every 10%)" if len(
                                              auctions_ids) > 10 else "I'm on it, Sir. Be patient.",
                                          file=File(self.bot.typing_gif_path))
        output = StringIO()
        csv_writer = writer(output)
        csv_writer.writerow(["Id", "Seller", "Buyer", "Item", "Price"])
        first, last = auctions_ids[0], auctions_ids[-1]
        auction = index = 0
        for index, auction in enumerate(auctions_ids):
            try:
                if await self.bot.should_cancel(interaction, msg):
                    break
                msg = await utils.update_percent(index, len(auctions_ids), msg)
                data = await utils.get_auction(f'https://{server}.e-sim.org/auction.html?id={auction}')
                csv_writer.writerow([str(auction), data["seller"], data["buyer"], data["item"], data["price"]])
                await utils.custom_delay(interaction)
            except Exception as error:
                await utils.send_error(interaction, error, auction)
                break

        output.seek(0)
        sellers = defaultdict(lambda: {'money': 0, 'count': 0})
        buyers = defaultdict(lambda: {'money': 0, 'count': 0})
        items = defaultdict(lambda: {'money': 0, 'count': 0})
        for index, row in enumerate(reader(output)):
            if index:  # Ignore headers
                _, seller, buyer, item, price = row
                if buyer != "None":
                    price = float(price)
                    sellers[seller]["money"] += price
                    sellers[seller]["count"] += 1
                    buyers[buyer]["money"] += price
                    buyers[buyer]["count"] += 1
                    items[item]["money"] += price
                    items[item]["count"] += 1

        output1 = StringIO()
        csv_writer = writer(output1)
        csv_writer.writerow(["#", "Seller", "Money received", "Auctions sold"])
        for index, (k, v) in enumerate(sorted(sellers.items(), key=lambda x: x[1]['money'], reverse=True)):
            csv_writer.writerow([str(index + 1), k, v["money"], v["count"]])

        output2 = StringIO()
        csv_writer = writer(output2)
        csv_writer.writerow(["#", "Buyer", "Money spend", "Auctions bought"])
        for index, (k, v) in enumerate(sorted(buyers.items(), key=lambda x: x[1]['money'], reverse=True)):
            csv_writer.writerow([str(index + 1), k, v["money"], v["count"]])

        output3 = StringIO()
        csv_writer = writer(output3)
        csv_writer.writerow(["#", "Item", "average price", "Pieces"])
        for index, (k, v) in enumerate(sorted(items.items(), key=lambda x: x[1]['money'], reverse=True)):
            csv_writer.writerow([str(index + 1), k, v["money"] / v["count"], v["count"]])

        output.seek(0)
        output1.seek(0)
        output2.seek(0)
        output3.seek(0)
        last = auction
        await utils.custom_followup(interaction, mention_author=index > 200, files=[
            File(fp=BytesIO(output.getvalue().encode()), filename=f"Raw_data_{first}_{last}_{server}.csv"),
            File(fp=BytesIO(output1.getvalue().encode()), filename=f"Sellers_{first}_{last}_{server}.csv"),
            File(fp=BytesIO(output2.getvalue().encode()), filename=f"Buyers_{first}_{last}_{server}.csv"),
            File(fp=await utils.csv_to_image(output3), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output3.getvalue().encode()), filename=f"Items_{first}_{last}_{server}.csv")])

    # Admin blocked access
    # @command()
    # @check(utils.is_premium_level_1)
    # @describe(fund_raising_link="if you have a working link, pls provide it (faster result), otherwise I will do my best.")
    async def bb(self, interaction: Interaction, server: Transform[str, Server],
                 fund_raising_link: str | None) -> None:
        """Displays baby boom (fund-raising) stats for a given server."""
        if fund_raising_link and "fundRaising" not in fund_raising_link:
            await utils.custom_followup(interaction, "This is not a fundRaising link.", ephemeral=True)
            return
        servers = {"primera": {"day": 3401, "funds": 440},
                   "secura": {"day": 3046, "funds": 369},
                   "suna": {"day": 3197, "funds": 508},
                   "alpha": {"day": 795, "funds": 229}}

        if not fund_raising_link:
            base_url = f"https://{server}.e-sim.org/"
            tree = await utils.get_locked_content(base_url, True)
            fund_link = next((x for x in tree.xpath('//*[@id="slideWrap"]//li//div//div//a/@href')
                              if "fundRaising" in x), None)
            if fund_link:
                tree = await utils.get_locked_content(base_url + fund_link)
            else:
                age = int(tree.xpath('//*[@class="sidebar-clock"]//b/text()')[-1].split()[-1])
                if server not in servers:
                    servers[server] = {"day": 1, "funds": 1}
                low = servers[server]["funds"]
                # new fund every ~4.5 days.
                high = (age - servers[server]["day"]) // 4 + servers[server]["funds"]
                for _ in range(10):
                    average = (high + low) // 2
                    try:
                        tree = await utils.get_locked_content(f"{base_url}fundRaising.html?id={average}")
                        break
                    except IOError as e:
                        if e == "NO_PRIVILEGES":
                            low = average
                        elif e == 500:
                            high = average
                        if high - low == 1:
                            break

        elif fund_raising_link.isdigit():
            base_url = f"https://{server}.e-sim.org/"
            tree = await utils.get_locked_content(f"{base_url}fundRaising.html?id={fund_raising_link}")
        else:
            fund_raising_link = fund_raising_link.split("#")[0].replace("http://", "https://")  # noqa WPS221
            server = fund_raising_link.split("https://", 1)[1].split(".e-sim.org", 1)[0]
            base_url = f"https://{server}.e-sim.org/"
            tree = await utils.get_locked_content(fund_raising_link)

        ids = {int(x) for x in tree.xpath('//form[@action="fundRaising.html"]//select//option/@value')}
        if not ids:
            await utils.custom_followup(interaction, "Sorry, but I couldn't find anything")
            return
        bb_id = max(ids)
        citizens_dict = defaultdict(
            lambda: {"euro": 0, 'medkits': 0, 'Q5 LC': 0, 'Q6 item': 0, "gold": 0, "donations": 0, "citizenship": ""})
        countries_dict = defaultdict(
            lambda: {"euro": 0, 'medkits': 0, 'Q5 LC': 0, 'Q6 item': 0, "gold": 0, "donations": 0, "donors count": 0})
        last = bb_id
        msg = await utils.custom_followup(interaction, "I'm on it, Sir. Be patient.",
                                          file=File(self.bot.typing_gif_path))
        for index in range(500):
            if await self.bot.should_cancel(interaction, msg):
                break
            if bb_id == 0:
                break
            if bb_id not in ids:
                bb_id -= 1
                continue
            try:
                tree = await utils.get_locked_content(f"{base_url}fundRaising.html?id={bb_id}")
            except Exception:
                break
            bb_id -= 1
            nicks = utils.strip(tree.xpath('//*[@class="testDivblue fund-table"]//*[@class="profileLink"]/text()'))
            amounts = (float(x.replace("-", "").replace("€", "").strip()) for x in
                       tree.xpath('//*[@class="testDivblue fund-table"]//ul//li//text()') if "€" in x)
            for nick, amount in zip(nicks, amounts):
                citizens_dict[nick]["euro"] += amount
                citizens_dict[nick]["donations"] += 1
                citizens_dict[nick]["gold"] += amount * 5

                if amount >= 20:
                    citizens_dict[nick]["medkits"] += 3
                if amount >= 50:
                    citizens_dict[nick]["Q6 item"] += 1
                if amount >= 99:
                    citizens_dict[nick]["Q5 LC"] += 1

        for index, (nick, DICT) in enumerate(citizens_dict.items()):
            msg = await utils.update_percent(index, len(DICT), msg)
            citizenship = (await utils.get_content(
                f"https://{server}.e-sim.org/apiCitizenByName.html?name={nick.lower()}"))["citizenship"]
            DICT["citizenship"] = citizenship
            for k, v in DICT.items():
                if k != "citizenship":
                    countries_dict[citizenship][k] += v
            countries_dict[citizenship]["donors count"] += 1

        output = StringIO()
        csv_writer = writer(output)
        for index, (k, v) in enumerate(sorted(citizens_dict.items(), key=lambda x: x[1]['euro'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Nick"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1, k] + list(v.values()))

        csv_writer.writerow([""])
        for index, (k, v) in enumerate(sorted(countries_dict.items(), key=lambda x: x[1]['euro'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Country"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1, k] + list(v.values()))
        output.seek(0)
        my_range = f"{last}_{bb_id + 1}" if last < bb_id else f"{bb_id + 1}_{last}"
        await utils.custom_followup(interaction, f"IDs: {my_range}", files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"fund_raising_{my_range}_{server}.csv")])

    @command()
    @check(utils.is_premium_level_1)
    async def citizens(self, interaction: Interaction, server: Transform[str, Server]) -> None:
        """Displays result from the citizens api for the top 1000 citizens by total dmg."""
        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File(self.bot.typing_gif_path))
        output = StringIO()
        csv_writer = writer(output)
        header = []
        base_url = f'https://{server}.e-sim.org/'
        count = 0
        break_main = False
        page = 1
        for page in range(1, 51):
            for citizen_id in utils.get_ids_from_path(
                    await utils.get_content(
                        f'{base_url}citizenStatistics.html?statisticType=DAMAGE&countryId=0&page={page}'), "//td/a"):
                if await self.bot.should_cancel(interaction, msg):
                    break_main = True
                    break
                msg = await utils.update_percent(count, 1000, msg)
                count += 1
                api = await utils.get_content(f'{base_url}apiCitizenById.html?id={citizen_id}')
                del api['gearInfo']
                if not header:  # First loop
                    header = list(api.keys())
                    csv_writer.writerow(header)
                csv_writer.writerow([api[X] if X in api else "" for X in header])
                await utils.custom_delay(interaction)
            if break_main:
                break

        output.seek(0)
        await utils.custom_followup(interaction, "This file is NOT sorted!", mention_author=page > 10, files=[
            File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"citizens_api_{server}.csv")])

    @command()
    @check(utils.is_premium_level_1)
    @describe(month="Example: 12-2012, default to the last one")
    async def congress(self, interaction: Interaction, server: Transform[str, Server], month: str | None) -> None:
        """Displays result from congress elections."""
        try:
            if month:
                m, y = (int(x) for x in month.split("-"))
                if not 1 <= m <= 12 or y < 2011:
                    raise ValueError
        except ValueError:
            await utils.custom_followup(interaction, f"Wrong month format {month}. It should be like 12-2012",
                                        ephemeral=True)
            return
        countries = utils.get_countries(server, index=0)
        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File(self.bot.typing_gif_path))
        output = StringIO()
        csv_writer = writer(output)
        csv_writer.writerow(["#", "Country", "Congress member (votes)"])
        for index, (country_id, country) in enumerate(sorted(countries.items())):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(index, len(countries), msg)
            tree = await utils.get_content(
                f'https://{server}.e-sim.org/congressElections.html?countryId={country_id}' + (
                    f"&date={month}" if month else ""))
            votes = tree.xpath("//tr[position()>1]//td[5]//text()")
            candidates = tree.xpath("//tr//td[2]//a/text()")
            if votes and votes[0] == "No presentation":
                votes = ["0"] * len(candidates)
            candidates = (f'{candidate.strip()} ({vote.strip()})\\n' for candidate, vote in zip(candidates, votes))
            csv_writer.writerow((str(index + 1), country.title(), "".join(candidates)[:-2]))
            await utils.custom_delay(interaction)

        output.seek(0)
        await utils.custom_followup(interaction, file=File(fp=BytesIO(output.getvalue().encode()),
                                                           filename=f"Congress_{server}.csv"),
                                    mention_author=True)

    @command()
    @check(utils.is_premium_level_1)
    @describe(month="Example: 12-2012, default to the last one")
    async def cp(self, interaction: Interaction, server: Transform[str, Server], month: str | None) -> None:
        """Displays results from presidential elections."""
        try:
            if month:
                m, y = (int(x) for x in month.split("-"))
                if not 1 <= m <= 12 or y < 2011:
                    raise ValueError
        except ValueError:
            await utils.custom_followup(interaction, f"Wrong month format {month}. It should be like 12-2012",
                                        ephemeral=True)
            return
        countries = utils.get_countries(server, index=0)
        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File(self.bot.typing_gif_path))
        output = StringIO()
        csv_writer = writer(output)
        csv_writer.writerow(["#", "Country", "CP", "Votes"])
        for index, (country_id, country) in enumerate(sorted(countries.items())):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(index, len(countries), msg)
            tree = await utils.get_content(
                f'https://{server}.e-sim.org/presidentalElections.html?countryId={country_id}' + (
                    f"&date={month}" if month else ""))
            votes = next(iter(tree.xpath("//tr[2]//td[4]//text()")), "-").strip()
            president = next(iter(tree.xpath("//td[2]//a/text()")), "No candidates").strip()
            row = (str(index + 1), country.title(), president, votes)
            csv_writer.writerow(row)
            await utils.custom_delay(interaction)

        output.seek(0)
        await utils.custom_followup(interaction,
                                    files=[File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
                                           File(fp=BytesIO(output.getvalue().encode()), filename=f"CPs_{server}.csv")],
                                    mention_author=True)

    @command()
    @check(utils.is_premium_level_1)
    async def medals(self, interaction: Interaction, server: Transform[str, Server]) -> None:
        """Checks how many friends and medals each player has in a given server (from the top 500)."""
        msg = await utils.custom_followup(interaction, "Progress status: 1%.\n(I will update you after every 10%)",
                                          file=File(self.bot.typing_gif_path))
        output = StringIO()
        csv_writer = writer(output)
        count = 0
        break_main = False
        pages = 25  # 20 citizens per page
        for page in range(1, pages + 1):
            for citizen_id in utils.get_ids_from_path(await utils.get_content(
                    f'https://{server}.e-sim.org/citizenStatistics.html?statisticType=DAMAGE&countryId=0&page={page}'),
                                                      "//td/a"):
                if await self.bot.should_cancel(interaction, msg):
                    break_main = True
                    break
                count += 1
                msg = await utils.update_percent(count, pages * 20, msg)
                tree = await utils.get_content(f'https://{server}.e-sim.org/profile.html?id={citizen_id}')
                friends = next((x.replace("Friends", "").replace("(", "").replace(")", "").strip() for x in
                                tree.xpath('//*[@class="rank"]/text()') if "Friends" in x), "0")
                nick = tree.xpath("//span[@class='big-login']")[0].text
                try:
                    citizenship = tree.xpath("//div[@class='profile-data']//div[8]//span[1]//span[1]")[0].text
                except IndexError:
                    break
                profile_medals = utils.get_profile_medals(tree)
                csv_writer.writerow([nick, citizenship, friends] + profile_medals)
                await utils.custom_delay(interaction)
            if break_main:
                break

        if not count:
            raise Exception("No citizens found.")
        output.seek(0)
        sorted_list = sorted(reader(output), key=lambda row: int(row[-4]), reverse=True)
        output = StringIO()
        csv_writer = writer(output)
        csv_writer.writerow(["#", "Nick", "Citizenship", "Friends", "Congress medals", "CP", "Train",
                             "Inviter", "Subs", "Work", "BHs", "RW", "Tester", "Tournament"])
        csv_writer.writerows([[index] + row for index, row in enumerate(sorted_list, 1)])
        output.seek(0)
        await utils.custom_followup(
            interaction, files=[File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
                                File(fp=BytesIO(output.getvalue().encode()),
                                     filename=f"Medals_{server}.csv")], mention_author=True)

    @command()
    @check(utils.is_premium_level_1)
    @describe(org_name="Example: Poland Org")
    async def org_logs(self, interaction: Interaction, server: Transform[str, Server],
                       first_day: int, last_day: int, org_name: str) -> None:
        """Analyzing org logs."""
        headers = {"DONATE": ["Type", "Date", "Donor", "", "Amount", "Type", "", "Receiver"],
                   "MONETARY_MARKET": ["Type", "Date", "Buyer", "", "Total amount", "CC bought", "", "Total paid",
                                       "Paid with", "", "Seller", "", "Ratio"],
                   "PRODUCT": ["Type", "Date", "Buyer", "", "Total amount", "Product bought", "", "Total paid",
                               "Paid with", "", "Seller", "", "Ratio"],
                   "DEBT": ["Type", "Date", "Paid by", "Action", "Amount", "Type", "", "Receiver"],
                   "CONTRACT": ["Type", "Date", "Accepted by", "Items accepted side", "Sent by", "Items sender side"],
                   "AUCTIONS": ["Type", "Date", "Buyer", "Seller", "Item", "Gold"],
                   "GOLD_FROM_REF": ["Type", "Date", "Receiver", "", "Gold", "", "invitee"],
                   "unknown": ["Type", "Date", "Buyer / Donor", "Seller / Receiver", "Log"],
                   "COMPANY": ["Type", "Date", "Buyer / Donor", "Seller / Receiver", "Action", "Gold"]}
        base_url = f"https://{server}.e-sim.org/"
        if not org_name.lower().endswith(" org"):
            org_name += " org"
        org_name = (await utils.get_content(f'{base_url}apiCitizenByName.html?name={org_name.lower()}'))["login"]
        output = StringIO()
        csv_writer = writer(output)
        link = f"{base_url}orgTransactions.html?citizenName={org_name}&dayFrom={first_day}&dayTo={last_day}"
        last_page = await utils.last_page(link, utils.get_locked_content)
        msg = await utils.custom_followup(interaction,
                                          "Progress status: 1%.\n(I will update you after every 10%)" if last_page > 10
                                          else "I'm on it, Sir. Be patient.",
                                          file=File(self.bot.typing_gif_path))
        date = page = None
        for page in range(1, last_page):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(page, last_page, msg)
            await utils.custom_delay(interaction)
            tree = await utils.get_locked_content(link + f"&page={page}")
            for tr in range(2, 101):
                try:
                    content = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[3]')[0].text_content().strip()
                except IndexError:
                    break
                log_type = get_type(content)
                if not log_type:
                    continue

                date = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[2]/text()[1]')[0].strip().split()[0]
                try:
                    donor = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[1]/a/text()')[0].strip()
                except IndexError:
                    donor = content.split("has")[0].strip()
                try:
                    receiver = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[4]/a/text()')[0].strip()
                except IndexError:
                    receiver = content.split("to")[-1].strip()
                try:
                    amounts = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[3]/b/text()')[0]
                except IndexError:
                    amounts = ""

                row = get_org_log_entry(tr, log_type, amounts, base_url, tree, content)
                if not row:
                    continue
                if log_type == "COMPANY":
                    donor, receiver = row[2:]
                    row = row[:2]

                csv_writer.writerow((log_type, date, donor, receiver) + row)

        output.seek(0)
        csv_reader_list = sorted(reader(output))
        if not csv_reader_list:
            await utils.custom_followup(interaction, "No logs were found.")
            return

        # Fixing the logs:
        for index, row in enumerate(csv_reader_list):
            log_type = row[0]
            if log_type in ("MONETARY_MARKET", "PRODUCT"):
                row = (row[0], row[1], row[2], "has bought total of", row[4], row[5], "and he paid for it total of",
                       row[6] if log_type == "MONETARY_MARKET" else round(float(row[6]) * float(row[4]), 2),
                       row[7], "to", row[3], f"Ratio: 1 {row[5]} =", row[8], row[7])
            elif log_type == "DEBT":
                row[3], row[6] = row[6], row[3]
                row.insert(7, row[6])
                row[6] = "to"
            elif log_type == "CONTRACT":
                row[3], row[4] = row[4], row[3]
            elif log_type == "DONATE":
                row = (row[0], row[1], row[2], "donated total of", row[4], row[5], "to", row[3])
            elif log_type == "GOLD_FROM_REF":
                row = (row[0], row[1], row[3], "has received", row[4], "from inviting", row[2])
            csv_reader_list[index] = row

        # Writing the logs:
        output = StringIO()
        csv_writer = writer(output)
        temp_log_type = ""
        for row in csv_reader_list:
            if row[0] != temp_log_type:
                csv_writer.writerow(["-"] * len(headers[row[0]]))
                csv_writer.writerow(headers[row[0]])
                temp_log_type = row[0]
            csv_writer.writerow(row)

        output.seek(0)
        donate = defaultdict(int)
        monetary_market = defaultdict(lambda: [0, 0])
        product = defaultdict(lambda: [0, 0])
        gold_from_ref = defaultdict(int)
        debt = defaultdict(int)
        output1 = StringIO()
        csv_writer = writer(output1)
        temp_log_type = ""
        for row in csv_reader_list:
            log_type = row[0]
            if log_type == "DONATE":
                donate[(row[2], row[-1], row[5])] += round(float(row[4]), 2)
            elif log_type == "MONETARY_MARKET":
                monetary_market[(row[2], row[10], row[5], row[8])][0] += round(float(row[4]), 2)
                monetary_market[(row[2], row[10], row[5], row[8])][1] += round(float(row[7]), 2)
            elif log_type == "PRODUCT":
                product[(row[2], row[10], row[5], row[8])][0] += round(float(row[4]), 2)
                product[(row[2], row[10], row[5], row[8])][1] += round(float(row[7]), 2)
            elif log_type == "GOLD_FROM_REF":
                gold_from_ref[(row[2], row[6])] += round(float(row[4]), 2)
            elif log_type == "DEBT":
                debt[(row[2], row[3], row[5], row[7])] += round(float(row[4]), 2)
            else:
                if row[0] != temp_log_type:
                    csv_writer.writerow(["-"] * len(headers[row[0]]))
                    csv_writer.writerow(headers[row[0]])
                    temp_log_type = row[0]
                csv_writer.writerow(row)
        if debt:
            csv_writer.writerow(["-"] * len(headers["DEBT"][2:]))
            csv_writer.writerow(headers["DEBT"][2:])
            for k, v in debt.items():
                csv_writer.writerow([k[0], k[1], v, k[2], "to", k[3]])
            del debt
        if donate:
            csv_writer.writerow(["-"] * len(headers["DONATE"][2:]))
            csv_writer.writerow(headers["DONATE"][2:])
            for k, v in donate.items():
                csv_writer.writerow([k[0], "donated total of", v, k[2], "to", k[1]])
            del donate
        if gold_from_ref:
            csv_writer.writerow(["-"] * len(headers["GOLD_FROM_REF"][2:]))
            csv_writer.writerow(headers["GOLD_FROM_REF"][2:])
            for k, v in gold_from_ref.items():
                csv_writer.writerow([k[0], "has received", v, "from inviting", k[1]])
            del gold_from_ref
        if monetary_market:
            csv_writer.writerow(["-"] * len(headers["MONETARY_MARKET"][2:]))
            csv_writer.writerow(headers["MONETARY_MARKET"][2:])
            for k, v in monetary_market.items():
                csv_writer.writerow(
                    [k[0], "has bought total of", v[0], k[2], "and he paid for it total of", v[1], k[3], "to", k[1],
                     f"Ratio: 1 {k[2]} =", round(v[1] / v[0], 2), k[3]])
            del monetary_market
        if product:
            csv_writer.writerow(["-"] * len(headers["PRODUCT"][2:]))
            csv_writer.writerow(headers["PRODUCT"][2:])
            for k, v in product.items():
                csv_writer.writerow(
                    [k[0], "has bought total of", v[0], k[2], "and he paid for it total of", v[1], k[3], "to", k[1],
                     f"Ratio: 1 {k[2]} =", round(v[1] / v[0], 2), k[3]])
            del product
        output1.seek(0)
        await utils.custom_followup(interaction, mention_author=page > 50, files=[
            File(fp=await utils.csv_to_image(output1), filename=f"Preview_{server}.png"),
            File(fp=BytesIO(output.getvalue().encode()), filename=f"raw_logs_{first_day}_{date}_{server}.csv"),
            File(fp=BytesIO(output1.getvalue().encode()), filename=f"analyzed_logs_{first_day}_{date}_{server}.csv")])

    @command()
    @check(utils.is_premium_level_1)
    @describe(stock_companies="first-last or id1, id2, id3...")
    async def stock_company(self, interaction: Interaction, server: Transform[str, Server],
                            stock_companies: Transform[list, Ids]) -> None:
        """Displays stats of the given stock companies."""
        base_url = f"https://{server}.e-sim.org/"
        all_cc = set()
        all_products = set()
        final = defaultdict(lambda: defaultdict(dict))
        msg = await utils.custom_followup(interaction,
                                          "Progress status: 1%.\n(I will update you after every 10%)" if len(
                                              stock_companies) > 10 else "I'm on it, Sir. Be patient.",
                                          file=File(self.bot.typing_gif_path))
        first = stock_companies[0]
        index = sc_id = 0
        for index, sc_id in enumerate(stock_companies):
            if await self.bot.should_cancel(interaction, msg):
                break
            msg = await utils.update_percent(index, len(stock_companies), msg)
            try:
                try:
                    tree = await utils.get_content(f'{base_url}stockCompany.html?id={sc_id}')
                except IOError:
                    continue
                sc_name = tree.xpath("//span[@class='big-login']")[0].text
                ceo = (tree.xpath('//*[@id="partyContainer"]//div//div[1]//div//div[1]//div[2]/a/text()') or [
                    "No CEO"])[0].strip()
                ceo_status = tree.xpath('//*[@id="partyContainer"]//div//div[1]//div//div[1]//div[2]//a/@style') or [
                    "Active" if ceo != "No CEO" else ""]
                ceo_status = ceo_status[0].replace("color: #f00; text-decoration: line-through;", "Banned").replace(
                    "color: #888;", "Inactive")
                main = tree.xpath('//*[@class="muColEl"]//b/text()')
                try:
                    price = tree.xpath('//*[@id="esim-layout"]//tr//td[2]//div[1]//table[1]//tr[2]//td[2]/b/text()')[0]
                    stock = tree.xpath('//*[@id="esim-layout"]//tr//td[2]//div[1]//table[1]//tr[2]//td[1]/b/text()')[0]
                except IndexError:
                    price, stock = "", ""
                try:
                    last_sold = tree.xpath(
                        '//*[@id="esim-layout"]//tr//td[2]//div[1]//table[3]//tr[2]//td[3]/text()')[0].strip()
                except IndexError:
                    last_sold = ""
                final[sc_id]["main"] = {
                    "main": [sc_name, ceo, ceo_status] + main + [price, stock, last_sold]}
                await utils.custom_delay(interaction)
                tree = await utils.get_content(f'{base_url}stockCompanyProducts.html?id={sc_id}')
                products_storage = {}
                amount = utils.strip(tree.xpath('//*[@id="esim-layout"]//center//div//div//div[1]/text()'),
                                     apply_function=int)
                products = [utils.parse_product_icon(x)
                            for x in tree.xpath('//*[@id="esim-layout"]//center//div//div//div[2]//img[1]/@src')]

                # Add quality to the product (we must use i, as some quality icons are missing)
                for i, product in enumerate(products):
                    quality = tree.xpath(f'//*[@id="esim-layout"]//center//div//div[{i + 1}]//div[2]//img[2]/@src')
                    if quality:
                        products[i] = (utils.parse_product_icon(quality[0]).upper() + " " +
                                       product.replace("Defense System", "Defense_System"))

                for product, amount in zip(products, amount):
                    all_products.add(product)
                    products_storage[product] = amount

                # Offers
                amount = utils.strip(tree.xpath('//*[@id="esim-layout"]//div[2]//table//tr//td[3]/text()')[1:],
                                     apply_function=int)
                products = [utils.parse_product_icon(x)
                            for x in tree.xpath('//*[@id="esim-layout"]//div[2]//table//tr//td[1]//img[1]/@src')]
                for i, product in enumerate(products):
                    quality = tree.xpath(f'//*[@id="esim-layout"]//div[2]//table//tr[{i + 2}]//td[1]//img[2]/@src')
                    if quality:
                        products[i] = (utils.parse_product_icon(quality[0]).upper() + " " +
                                       product.replace("Defense System", "Defense_System"))
                for product, amount in zip(products, amount):
                    all_products.add(product)
                    if product in products_storage:
                        products_storage[product] += amount
                    else:
                        products_storage[product] = amount

                final[sc_id]["products"] = products_storage
                await utils.custom_delay(interaction)
                tree = await utils.get_content(f'{base_url}stockCompanyMoney.html?id={sc_id}')
                cc = utils.strip(tree.xpath('//*[@id="esim-layout"]//div[3]//div//text()'))
                final[sc_id]["cc"] = {k: float(v) for k, v in zip(cc[1::2], cc[0::2])}
                all_cc.update(final[sc_id]["cc"])
                amount = map(float, tree.xpath('//*[@id="esim-layout"]//div[3]//table//tr/td[2]/b/text()'))
                coin = utils.strip(tree.xpath('//*[@id="esim-layout"]//div[3]//table//tr/td[2]/text()'))[1:]
                for amount, coin in zip(amount, coin):
                    all_cc.add(coin)
                    if coin in final[sc_id]["cc"]:
                        final[sc_id]["cc"][coin] += amount
                    else:
                        final[sc_id]["cc"][coin] = amount

            except Exception as error:
                if index == 0:
                    raise error
                await utils.send_error(interaction, error, sc_id)
                break
            await utils.custom_delay(interaction)

        output = StringIO()
        csv_writer = writer(output)
        header = ["SC id", "SC name", "CEO", "CEO status",
                  "Total Shares", "Total Value", "Per Share", "Daily", "Share Holders", "Companies",  # main
                  "Best Price", "Shares For Sell", "Last Share Trade", ""] + sorted(all_products, reverse=True) +\
                 ["", "Gold"] + sorted(all_cc)[1:]
        csv_writer.writerow(header)

        for k, v in final.items():
            for x in all_products:
                if x not in v["products"]:
                    v["products"][x] = ""
            for x in all_cc:
                if x not in v["cc"]:
                    v["cc"][x] = ""
            row = [k, *v['main']["main"], "", *[val for key, val in sorted(v["products"].items(), reverse=True)], "",
                   v["cc"]["Gold"]] + [val for key, val in sorted(v["cc"].items())[1:]]
            csv_writer.writerow(row)
        output.seek(0)
        await utils.custom_followup(interaction,
                                    mention_author=index > 100,
                                    files=[File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
                                           File(fp=BytesIO(output.getvalue().encode()),
                                                filename=f"StockCompanies_{first}-{sc_id}_{server}.csv")])

    @command()
    @check(utils.is_premium_level_1)
    @describe(include_comments="true is slower and false gives more data",
              period="should be similar to e-sim format (X hours/days/months/years)")
    async def shouts(self, interaction: Interaction, server: Transform[str, Server],
                     include_comments: bool | None, period: Period) -> None:
        """Displays shouts stats."""
        msg = await utils.custom_followup(interaction,
                                          "I'm on it, Sir. Be patient. (I have no idea how long it will take, "
                                          "but i will update this msg every 10 shouts pages)",
                                          file=File(self.bot.typing_gif_path))
        base_url = f"https://{server}.e-sim.org/"
        my_dict = {"shouts": 0, "replies (by author)": 0, "votes (to author shouts)": 0, "replies (to author)": 0}
        if not include_comments:
            del my_dict["replies (by author)"]
        authors_per_month = defaultdict(lambda: my_dict.copy())
        break_main_loop = False
        max_pages = 300 if not include_comments else 50
        for page in range(1, max_pages + 1):
            if await self.bot.should_cancel(interaction):
                break
            if page % 10 == 0:
                try:
                    msg = await msg.edit(content=f"Checked {page} shouts pages")
                except errors.NotFound:
                    pass
            if page == max_pages:
                await utils.custom_followup(interaction, f"Checked first {page} shouts pages")
                break
            tree = await utils.get_locked_content(f"{base_url}shouts.html?page={page}")
            posted = (x.replace("posted ", "").lower() for x in tree.xpath("//*[@class='shoutAuthor']/b/text()"))
            author = utils.strip(tree.xpath("//*[@class='shoutAuthor']/a/text()"))
            citizenship = (x.split("xflagsSmall xflagsSmall-")[-1].replace("-", " ") for x in
                           tree.xpath("//*[@class='shoutAuthor']/span/@class"))
            ids = map(int, tree.xpath("//*[@class='shoutEditButtons']//form//input[1]/@value"))
            votes_replies = tuple(map(int, tree.xpath("//*[@class='showShoutDetails']//font/text()")))
            votes, replies = votes_replies[0::2], votes_replies[1::2]
            for posted, author, citizenship, shout_id, votes, replies in zip(
                    posted, author, citizenship, ids, votes, replies):
                if period.lower() in posted:
                    break_main_loop = True
                    break
                if "months" in period and "month" not in posted and "year" not in posted:
                    posted = "0 months ago"
                key = author, citizenship, posted
                authors_per_month[key]["shouts"] += 1
                authors_per_month[key]["votes (to author shouts)"] += votes
                if replies and include_comments:
                    tree1 = await utils.get_content(f"{base_url}shoutDetails.html?id={shout_id}", method="post")
                    author1 = utils.strip(tree1.xpath("//*[@class='shoutAuthor']/a/text()"))
                    citizenship1 = (x.split("xflagsSmall xflagsSmall-")[-1].replace("-", " ") for x in
                                    tree1.xpath("//*[@class='shoutAuthor']/span/@class"))
                    posted1 = (x.replace("posted ", "") for x in tree.xpath("//*[@class='shoutAuthor']/b/text()"))
                    for author1, citizenship1, posted1 in zip(author1, citizenship1, posted1):
                        if "months" in period and "month" not in posted1 and "year" not in posted1:
                            posted1 = "0 months ago"
                        authors_per_month[author, citizenship, posted1]["replies (to author)"] += replies
                        authors_per_month[author1, citizenship1, posted1]["replies (by author)"] += 1
                    await utils.custom_delay(interaction)
            if break_main_loop:
                break
            await utils.custom_delay(interaction)

        await msg.delete()
        output = StringIO()
        csv_writer = writer(output)
        countries_per_month = defaultdict(lambda: my_dict.copy())
        authors = defaultdict(lambda: my_dict.copy())
        countries = defaultdict(lambda: my_dict.copy())
        months = defaultdict(lambda: my_dict.copy())
        sum_dict = defaultdict(int)
        for index, (k, v) in enumerate(sorted(authors_per_month.items(), key=lambda x: x[1]['shouts'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Nick", "Citizenship", "Time"] + [x.title() for x in v.keys()])
            k = list(k)
            csv_writer.writerow([index + 1] + k + list(v.values()))
            for key, val in v.items():
                countries_per_month[k[1], k[2]][key] += val
                authors[k[0], k[1]][key] += val
                countries[k[1]][key] += val
                months[k[2]][key] += val
                sum_dict[key] += val

        authors_per_month.clear()
        csv_writer.writerow(["Sum", len(authors), len(countries), len(months)] + list(sum_dict.values()))
        output.seek(0)
        files = [File(fp=BytesIO(output.getvalue().encode()), filename=f"shouts_per_player_per_month_{server}.csv")]

        output = StringIO()
        csv_writer = writer(output)
        for index, (k, v) in enumerate(sorted(countries_per_month.items(), key=lambda x: x[1]['shouts'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Country", "Time"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1] + list(k) + list(v.values()))
        countries_per_month.clear()
        csv_writer.writerow(["Sum", len(countries), len(months)] + list(sum_dict.values()))
        output.seek(0)
        files.append(File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"))
        files.append(
            File(fp=BytesIO(output.getvalue().encode()), filename=f"shouts_per_country_per_month_{server}.csv"))

        output = StringIO()
        csv_writer = writer(output)
        for index, (k, v) in enumerate(sorted(authors.items(), key=lambda x: x[1]['shouts'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Nick", "Citizenship"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1] + list(k) + list(v.values()))
        csv_writer.writerow(["Sum", len(authors), len(countries)] + list(sum_dict.values()))
        authors.clear()
        output.seek(0)
        files.append(File(fp=BytesIO(output.getvalue().encode()), filename=f"shouts_per_player_{server}.csv"))

        output = StringIO()
        csv_writer = writer(output)
        for index, (k, v) in enumerate(sorted(months.items(), key=lambda x: int(x[0].split()[0]))):
            if not index:
                csv_writer.writerow(["#", "Month"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1, k] + list(v.values()))
        csv_writer.writerow(["Sum", len(months)] + list(sum_dict.values()))

        csv_writer.writerow([""])
        for index, (k, v) in enumerate(sorted(countries.items(), key=lambda x: x[1]['shouts'], reverse=True)):
            if not index:
                csv_writer.writerow(["#", "Country"] + [x.title() for x in v.keys()])
            csv_writer.writerow([index + 1, k] + list(v.values()))
        csv_writer.writerow(["Sum", len(countries)] + list(sum_dict.values()))
        output.seek(0)
        files.append(
            File(fp=BytesIO(output.getvalue().encode()), filename=f"shouts_per_month_and_country_{server}.csv"))

        await utils.custom_followup(interaction,
                                    "Feel free to add more stats, such as avg votes per shout etc. (basic excel)",
                                    files=files, mention_author=page > 100)


def get_org_log_entry(tr: int, log_type: str, amounts: str, base_url: str, tree, content: str) -> tuple:
    if log_type == "DONATE":
        if amounts:
            amount, item = amounts.split(" * ") if "*" in amounts else amounts.split()
        else:
            amount, item = "1", base_url + tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[3]/a/@href')[0]
        row = (amount, item.strip())

    elif log_type == "MONETARY_MARKET":
        amount1, cc1 = amounts.split(" for ")[0].split()
        amount2, cc2 = amounts.split(" for ")[1].split()
        ratio = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[3]/text()[2]')[0].split(" at ratio ")[1].split(
            " from ")[0]
        row = (amount1, cc1, amount2, cc2, ratio)

    elif log_type == "PRODUCT":
        amount1, item = amounts.split(" * ")
        amount2, cc = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[3]/text()[3]')[0].split(" for ")[1].split(
            " from ")[0].split()
        row = (amount1, item, amount2, cc, amount2)

    elif log_type == "DEBT":
        amount, cc = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[3]/b[2]/text()')[0].split()
        action = "has canceled debt of" if "canceled" in content else "has paid debt of"
        row = (amount, cc, action)

    elif log_type == "CONTRACT":
        side1, side2 = content.split("\n")
        if "obligations" in content:
            key = "obligations"
        else:
            key = "Add new element to the contract: "
        side1 = " ".join((side1.split(key)[1].replace("Donate", "").replace("Pay", "")).strip().split())
        side2 = " ".join((side2.split(key)[1].replace("Donate", "").replace("Pay", "").strip()).split())
        if side1 == ",":
            side1 = ""
        final_eqs = (base_url + "showEquipment.html?id=" + fromstring(eq).xpath('//*/bdo/a/text()')[0].replace("#", "")
                     for eq in tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[3]/b/img/@title'))
        if final_eqs:
            side1 += ", ".join(final_eqs)
        row = (side2, side1)

    elif log_type == "GOLD_FROM_REF":
        amount, cc = amounts.split()
        row = (amount,)

    elif log_type == "AUCTIONS":
        eq = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[3]/img/@title')
        if eq:
            eq1 = base_url + "showEquipment.html?id=" + fromstring(eq[0]).xpath('//*/bdo/a/text()')[0].replace(
                "#", "")
        else:
            eq1 = content.split("has bought")[1].split("for")[0].strip()
        amount = tree.xpath(f'//*[@id="esim-layout"]//tr[{tr}]//td[3]/b[1]/text()')[0]
        row = (eq1, amount)

    elif log_type == "COMPANY":
        donor = content.split("has")[0].strip()
        receiver = ""
        if "from" in content:
            receiver = content.split("from")[1].strip()
        elif "to" in content:
            receiver = content.split("to")[1].strip()
        action = content.split("has")[1].split("company (ID: ")[0].strip()
        gold = ""
        if action == "bought":
            gold = content.split("for")[1].split("Gold")[0].strip()
        row = (action, gold, donor, receiver)

    else:
        row = ()
    return row


def get_type(content: str) -> str:
    """Get type."""
    if "motivation" in content:
        log_type = None
    elif "on auction" in content:
        log_type = "AUCTIONS"
    elif "at ratio" in content:
        log_type = "MONETARY_MARKET"
    elif "company (ID: " in content:
        log_type = "COMPANY"
    elif "has bought" in content:
        log_type = "PRODUCT"
    elif "has paid debt" in content or "has canceled debt of" in content:
        log_type = "DEBT"
    elif "has sent" in content:
        log_type = "DONATE"
    elif "Add new element to the contract:" in content or "obligations" in content:
        log_type = "CONTRACT"
    elif "for inviting" in content:
        log_type = "GOLD_FROM_REF"
    else:
        log_type = "unknown"
    return log_type


async def setup(bot) -> None:
    """Setup."""
    await bot.add_cog(Premium(bot))
