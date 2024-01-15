"""General.py"""
from asyncio import sleep
from datetime import date, datetime, timedelta
from io import BytesIO
from random import randint

from discord import Attachment, Embed, File, Interaction, TextChannel
from discord.app_commands import (Transform, check, checks, command, describe,
                                  guild_only)
from discord.ext.commands import Cog
from pytz import timezone
from sympy import sympify
from wolframalpha import Client

from Help import utils
from Help.constants import (all_countries, all_products, all_servers, api_url,
                            config_ids, date_format, gids)
from Help.transformers import Country, Server
from Help.utils import CoolDownModified, camel_case_merge


class General(Cog):
    """General Commands"""

    def __init__(self, bot) -> None:
        self.bot = bot
        self.wolfram = Client(bot.config["wolfram"])

    @checks.dynamic_cooldown(CoolDownModified(30))
    @command()
    @describe(your_bug_report="will be visible to everyone at our support server")
    async def bug(self, interaction: Interaction, your_bug_report: str) -> None:
        """Sends a bug report."""

        msg = f"[{datetime.now().astimezone(timezone('Europe/Berlin')).strftime(date_format)}] " \
              f"**{interaction.user.name}** has sent the following bug report: \n{your_bug_report}"
        channel = self.bot.get_channel(config_ids["bugs_channel_id"])
        await channel.send(msg)
        await utils.custom_followup(
            interaction, f"Your bug report has been sent, and it will be visible to everyone at our support server "
                         f"{config_ids['support_invite']} \nThanks for the feedback!", ephemeral=True)

    @checks.dynamic_cooldown(CoolDownModified(2))
    @command()
    async def cc(self, interaction: Interaction, calculation_or_search_query: str) -> None:
        """Formula calculator / computational knowledge engine."""

        a = "()+-*/1234567890. "
        calculation = calculation_or_search_query.replace(",", "").replace("`", "").replace(":", "/").replace("\\", "/")
        result = all(subStr in a for subStr in calculation)
        embed = Embed(colour=0x3D85C6)

        if result:
            final_result = round(float(sympify(calculation)), 10)
            final_result = int(final_result) if int(final_result) == float(final_result) else float(final_result)
            embed.add_field(name="Output:", value=f'{final_result:,}', inline=False)
        else:

            res = self.wolfram.query(calculation)
            if str(res['@success']).lower() == 'false':
                embed.add_field(name="Output:", value=':warning: `No results found`', inline=False)
            else:
                try:
                    result = res.results
                    final_result = next(result).text
                    if "/" in final_result:
                        final_result = next(result).text
                    embed.add_field(name="Output:", value=final_result, inline=False)
                except Exception:
                    for pod in res.pods:
                        if int(pod['@numsubpods']) > 1:
                            for sub in pod['subpod']:
                                subpod_text = sub['plaintext']
                                if subpod_text is None:
                                    continue
                                embed.add_field(name=pod["@title"], value=subpod_text, inline=False)
                        else:
                            subpod_text = pod['subpod']['plaintext']
                            if subpod_text is None:
                                continue
                            embed.add_field(name=pod["@title"], value=subpod_text, inline=False)
        await utils.custom_followup(interaction, f"Your query: `{calculation}`",
                                    embed=await utils.convert_embed(interaction, embed, is_columns=False))

    @command()
    @check(utils.is_premium_level_1)
    @describe(servers="Examples: alpha, secura  or ALL for all servers.")
    async def events(self, interaction: Interaction, servers: str = "") -> None:
        """Shows the upcoming events for the given servers"""

        await interaction.response.defer()
        if not servers or servers.lower() == "all":
            servers = " ".join(all_servers)
        embed = Embed(colour=0x3D85C6, title="Events")
        for server in servers.replace(",", " ").replace(" and ", " ").split():
            if not server.strip():
                continue
            server = utils.server_validation(server)
            base_url = f"https://{server}.e-sim.org/"
            now = datetime.now().astimezone(timezone('Europe/Berlin')).replace(tzinfo=None)
            try:
                tree = await utils.get_locked_content(f'{base_url}tournamentEvents.html')
            except Exception as e:
                print("EVENTS ERROR:", server, e)
                embed.add_field(name=server, value="Error", inline=False)
                continue
            events = []
            indexes = []
            for tr in range(2, 17):
                try:
                    events.append((tree.xpath(f'//tr[{tr}]//td[1]/div/div[1]/div[4]/b/text()') or tree.xpath(
                        f'//tr[{tr}]//td[1]/h2/text()') or tree.xpath(f'//tr[{tr}]//td[1]/div/div[2]/text()'))[
                                      -1].strip())
                    if tree.xpath(f'//tr[{tr}]//td[4]')[0].text == "active":
                        indexes.append(tr - 2)
                except Exception:
                    break
            links = tree.xpath('//tr//td[2]/a/@href')
            start_time = [x.strip() for x in tree.xpath('//tr[position()>1]//td[5]/text()') if
                          x.strip() and "(" not in x and "unknown" not in x]

            for i in range(len(start_time)):
                if "to start" in start_time[i]:
                    t = start_time[i].replace("\xa0to start", "").split(':')
                    start_time[i] = now + timedelta(hours=int(t[0]), minutes=int(t[1]), seconds=int(t[2]))
                else:
                    try:
                        start_time[i] = datetime.strptime(start_time[i], "%H:%M %d-%m-%Y")
                    except Exception:
                        try:
                            start_time[i] = datetime.strptime(start_time[i], "%d-%m-%Y %H:%M:%S")
                        except Exception:
                            print("EVENTS ERROR1:", server, start_time[i])
                try:
                    if start_time[i] > now:
                        indexes.append(i)
                except Exception:
                    print("EVENTS ERROR2:", server, start_time[i])

            if indexes:
                indexes.sort(reverse=True)
                embed.add_field(name=server, value="\n".join(f"[{events[i]}]({base_url}{links[i]})" for i in indexes))
                embed.add_field(name="Start Time", value="\n".join(str(start_time[i]).split('.', maxsplit=1)[0]
                                                                   for i in indexes))
                embed.add_field(name="\u200B", value="\u200B")
            else:
                embed.add_field(name=server, value="Nothing found", inline=False)
        await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed))

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    async def profile(self, interaction: Interaction, server: Transform[str, Server], nick: str) -> None:
        """Displays data about a player"""

        await interaction.response.defer()
        base_url = f"https://{server}.e-sim.org/"
        api = await utils.get_content(f'{base_url}apiCitizenByName.html?name={nick.lower()}')

        company = f"{base_url}company.html?id={api['companyId']}" if 'companyId' in api else ""
        title = ""
        if api['status'] == "inactive":
            title = '\n**\U0001F451 Inactive**'
        elif "ban" in api['status'].lower():
            title = "\n:x: **" + api['status'].title() + "**"

        link = f"{base_url}profile.html?id={str(api['id'])}"
        tree = await utils.get_content(link)

        is_online = tree.xpath('//*[@id="loginBar"]//span[2]/@class')[0] == "online"
        embed = Embed(colour=0x3D85C6, url=link, description=title, title=("\U0001f7e2" if is_online else "\U0001f534")
                      + f" {api['login']}, {utils.codes(api['citizenship'])} {api['citizenship']}")

        birthday = (tree.xpath('//*[@class="profile-row" and span = "Birthday"]/span/text()') or [1])[0]
        debts = sum(float(x) for x in tree.xpath('//*[@class="profile-data red"]//li/text()')[::6])
        assets = sum(float(x.strip()) for x in tree.xpath(
            '//*[@class="profile-data" and (strong = "Assets")]//ul//li/text()') if "." in x)

        buffs_debuffs = [camel_case_merge(x.split("/specialItems/")[-1].split(".png")[0]).replace("Elixir", "") for x in
                         tree.xpath('//*[@class="profile-row" and (strong="Debuffs" or strong="Buffs")]//img/@src') if
                         "img/specialItems/" in x]
        buffs = ', '.join([x.split("_")[0].replace("Vacations", "Vac").replace("Resistance", "Sewer").replace(
            "Pain Dealer", "PD ").replace("Bonus Damage", "") + ("% Bonus" if "Bonus Damage" in x.split("_")[0] else "")
                           for x in buffs_debuffs if "Positive" in x.split("_")[1:]]).title()
        debuffs = ', '.join([x.split("_")[0].lower().replace("Vacation", "Vac").replace(
            "Resistance", "Sewer") for x in buffs_debuffs if "Negative" in x.split("_")[1:]]).title()
        avg_per_day = 0

        if server in gids:
            find_buffs = await utils.find_one("buffs", server)
            if api["login"] in find_buffs and find_buffs[api["login"]][5]:
                db_row = find_buffs[api["login"]]
                buffs_link = f"https://docs.google.com/spreadsheets/d/{gids[server][0]}/edit#gid={gids[server][2]}"
                now = datetime.now().astimezone(timezone('Europe/Berlin')).strftime(date_format)
                if (datetime.strptime(now, date_format) - datetime.strptime(db_row[5],
                                                                            date_format)).total_seconds() < 86400:
                    buffs += f" [(*Time left:* {db_row[7].strip()})]({buffs_link})"
                else:
                    debuffs += f" [(*Time left:* {db_row[7].strip()})]({buffs_link})"

            find_time = await utils.find_one("time_online", server)
            if api["id"] in find_time:
                online_link = f"https://docs.google.com/spreadsheets/d/{gids[server][0]}/edit#gid={gids[server][1]}"
                db_row = find_time[api["id"]]
                avg_per_day = f"[{db_row[-1]} Hours]({online_link})"

        stats = {
            "XP": api['xp'], "Total DMG": api['totalDamage'] - api['damageToday'],
            "DMG today": api['damageToday'],
            "\u2b50 Premium": (str(date.today() + timedelta(
                days=int(api['premiumDays']))) + f" ({api['premiumDays']} days)") if api['premiumDays'] else "-",
            "\u231a Avg. hours online per day": avg_per_day,
            "\U0001f4b5 Economy skill": api['economySkill'],
            "\U0001f476 Birthday": birthday,
            "\U0001f4b0 Assets": assets, "\U0001f911 Debts": debts,
            "\U0001f3c5 Medals": api['medalsCount'],
            "\U0001f970 Friends": api['friendsCount'],
            "\U0001f7e2 Buffs": buffs, "\U0001f534 Debuffs": debuffs,
            "crit": 12.5, "avoid": 5, "miss": 12.5}

        eqs = []
        for eq_type, parameters, values, eq_link in utils.get_eqs(tree):
            eqs.append(
                f"**[{eq_type}]({base_url}{eq_link}):** " + ", ".join(f"{val} {p}" for val, p in zip(values, parameters)))
            for val, p in zip(values, parameters):
                if p not in stats:
                    stats[p] = 0
                stats[p] += (val if p != "miss" else -val)
        embed.add_field(name="**Stats**", value="\n".join(
            [f"**{k}:** " + (f"{round(v, 2):,}" if not isinstance(v, str) else v) for k, v in stats.items()]))
        embed.add_field(name="**Equipments**", value="\n".join(eqs) or "- no eqs found -")

        embed.add_field(name="Links", value="\n".join(
                            [f"[{k}]({v})" for k, v in get_user_links(base_url, link, api, company).items() if v]))
        avatar_url = tree.xpath('//*[@class="bigAvatar epidemic"]/@src')[0].strip()
        files = []
        if "http" in avatar_url:
            async with self.bot.session.get(avatar_url, ssl=False) as resp:
                data = BytesIO(await resp.read())
                files.append(File(data, f'{interaction.id}.png'))
                embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
        await utils.custom_followup(interaction, files=files, embed=await utils.custom_author(embed))

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    async def time_online(self, interaction: Interaction, server: Transform[str, Server], nick: str = "",
                          country: Transform[str, Country] = "", military_unit_id: int = 0) -> None:
        """Displays online players stats per server and country / nick / military unit."""
        await interaction.response.defer()
        base_url = f"https://{server}.e-sim.org/"
        if military_unit_id:
            members = await utils.get_content(
                f'{base_url}apiMilitaryUnitMembers.html?id={military_unit_id}')
            members = [str(row["id"]) for row in members]
        else:
            members = []

        embed = Embed(colour=0x3D85C6, title="Time Online",
                      url=f"https://docs.google.com/spreadsheets/d/{gids[server][0]}/edit#gid={gids[server][1]}")

        result = []
        find_time = await utils.find_one("time_online", server)
        last_update = find_time["_headers"][-1]
        embed.set_footer(text="Last Update: " + last_update)
        for index, (citizen_id, v) in enumerate(find_time.items(), 1):
            if citizen_id == "_headers":
                continue
            current_nick, cs, total_minutes, total_avg, month_minutes, month_avg = v
            if any((country, military_unit_id, nick)) and not any(
                    (cs.lower() == country.lower(), citizen_id in members, nick.lower() == current_nick.lower())):
                continue
            row = [f"#{index} {utils.codes(cs) if not country else ''}"
                   f" [{current_nick[:17]}]({base_url}profile.html?id={citizen_id})",
                   f"**{int(total_minutes):,}** ({total_avg}h per day)", f"**{int(month_minutes):,}** ({month_avg}h per day)"]
            if row not in result:
                result.append(row)
            if len(result) == 100:
                embed.description = "(First 100)"
                break

        if not result:
            await utils.custom_followup(
                interaction, f"No results were found\n"
                             f"See https://docs.google.com/spreadsheets/d/{gids[server][0]}/edit#gid={gids[server][1]}\n")
            return
        headers = ["Global Rank, Nick", "Minutes " + find_time["_headers"][2].split("(")[1].split(")")[0].title(),
                   "Minutes " + find_time["_headers"][4].split("(")[1].split(")")[0].title()]
        await utils.send_long_embed(interaction, embed, headers, result)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(when="Example: 2022/02/28 20:06:30 (defaults: date=today, year=this year, seconds=0, all poland time zone)")
    @guild_only()
    async def remind(self, interaction: Interaction, when: str, msg: str) -> None:
        """Remind a specific message in the given time."""

        date_format = "%Y/%m/%d %H:%M:%S"
        now = datetime.now().astimezone(timezone('Europe/Berlin')).strftime(date_format)
        when = when.replace("-", "/")
        if when.count(":") == 1:
            when += ":00"
        if "/" not in when:
            when = now.split()[0] + " " + when
        elif when.count("/") != 2:
            when = now.split("/")[0] + "/" + when
        try:
            seconds = (datetime.strptime(when, date_format) - datetime.strptime(now, date_format)).total_seconds()
        except Exception:
            await utils.custom_followup(
                interaction, "Wrong format. Try to follow the instructions this time.", ephemeral=True)
            return

        if seconds >= 1000000:
            await utils.custom_followup(interaction, "That's too far away", ephemeral=True)
            return
        await interaction.response.defer()
        random_id = randint(1000, 9999)
        await utils.custom_followup(interaction,
                                    f'The reminder is set to `{when}` Poland time (`{seconds}` seconds from now).'
                                    f'\nIf you want to remove it, type `/remove reminder_id: {random_id}`')
        random_id = f"{interaction.channel.id} {random_id}"
        msg = interaction.user.mention + msg
        find_remind = await utils.find_one("collection", "remind")
        find_remind[random_id] = {"when": when, "msg": msg}
        await utils.replace_one("collection", "remind", find_remind)
        await remind_func(interaction.channel, when, random_id, msg)

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @command()
    @describe(reminder_id="leave empty if you want to remove all the reminders in this channel. "
                          "0 will show you the list of your ids.")
    async def remove(self, interaction: Interaction, reminder_id: int = -1) -> None:
        """Removing a given id from the reminder list"""
        find_remind = await utils.find_one("collection", "remind")
        if reminder_id < 0:
            removed = []
            for x in list(find_remind):
                if str(interaction.channel.id) in x:
                    del find_remind[x]
                    removed.append(x.split()[1])
            if removed:
                await utils.custom_followup(interaction, "removed " + ", ".join(removed), ephemeral=True)
                await utils.replace_one("collection", "remind", find_remind)
            else:
                await utils.custom_followup(interaction, "There are no active reminders in this channel at the moment.",
                                            ephemeral=True)
            return

        if reminder_id == 0:
            reminder_id = [x.split()[1] for x in find_remind if str(interaction.channel.id) == x.split()[0]]
            if len(reminder_id) == 1:
                if f"{interaction.channel.id} {reminder_id[0]}" in find_remind:
                    del find_remind[f"{interaction.channel.id} {reminder_id[0]}"]
                    await utils.replace_one("collection", "remind", find_remind)
                    await utils.custom_followup(interaction, f"{reminder_id[0]} removed", ephemeral=True)
            elif len(reminder_id) > 1:
                await utils.custom_followup(interaction, "Type `/remove reminder_id: ID` with one of those ID's: " + ', '.join(
                    reminder_id) + f"\nExample: `/remove reminder_id: {reminder_id[0]}`", ephemeral=True)
            else:
                await utils.custom_followup(
                    interaction, "There is nothing to remove. For adding reminders, use `/remind`", ephemeral=True)

        elif reminder_id in [x.split()[1] for x in find_remind]:
            if f"{interaction.channel.id} {reminder_id}" in find_remind:
                del find_remind[f"{interaction.channel.id} {reminder_id}"]
                await utils.replace_one("collection", "remind", find_remind)
                await utils.custom_followup(interaction, f"{reminder_id} removed", ephemeral=True)

        else:
            await utils.custom_followup(interaction, f"`{reminder_id}` is not an active reminder in this channel",
                                        ephemeral=True)

    @checks.dynamic_cooldown(CoolDownModified(30))
    @command()
    @describe(your_feedback="It will be visible to everyone at our support server")
    async def feedback(self, interaction: Interaction, your_feedback: str) -> None:
        """Send a feedback about the bot."""

        msg = f"[{datetime.now().astimezone(timezone('Europe/Berlin')).strftime(date_format)}] " \
              f"**{interaction.user.name}** has sent the following feedback: \n{your_feedback}"
        channel = self.bot.get_channel(config_ids["feedback_channel_id"])
        await channel.send(msg)
        await utils.custom_followup(
            interaction, f"Your feedback has been sent, and it will be visible to everyone at our support server"
                         f" {config_ids['support_invite']} \nThank you for the feedback!", ephemeral=True)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    async def usage(self, interaction: Interaction) -> None:
        """Displays some bot usage statistics"""

        lookup = ['\N{FIRST PLACE MEDAL}', '\N{SECOND PLACE MEDAL}', '\N{THIRD PLACE MEDAL}'] + ['\N{SPORTS MEDAL}'] * 7
        embed = Embed(colour=0x3D85C6)
        b = await utils.find_one("collection", "commands_count")
        counter = sorted(b.items(), key=lambda kv: kv[1], reverse=True)[:10]
        value = '\n'.join(f'{lookup[index]}: **{command_name}** ({uses:,} uses)' for (index, (command_name, uses)) in
                          enumerate(counter)) or 'No Commands'
        embed.add_field(name="Usage statistics (first 10)", value=value)
        await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed))

    @command()
    async def link(self, interaction: Interaction, link: str) -> None:
        """Get info about a link"""
        await interaction.response.defer()
        get_url = link.replace("http://", "https://")
        server = get_url.split("https://")[-1].split(".e-sim.org/")[0]
        if not link.startswith(api_url):
            get_url = api_url + link.replace("https://", "https:/")
        base_url = f"https://{server}.e-sim.org/"
        embed = Embed(colour=0x3D85C6, title=link, description=f"[source]({get_url})")
        if "/statistics.html" in link:  # locked to registered users.
            selected_site = link.split("&", 1)[0].split("selectedSite=", 1)[-1]
            link = link.replace("statistics.html?selectedSite=" + selected_site,
                                utils.camel_case(selected_site) + "Statistics.html").replace("&", "?", 1)
        if "/achievement.html" in link:
            row = await utils.get_content(get_url)
            wanted_keys = ["description", "achieved_by", "category"]
            embed.add_field(name="Info",
                            value="\n".join([f"**{k.replace('_', ' ').title()}:** {v}"
                                             for k, v in row.items() if k in wanted_keys]))

        # auction, article and law are the most common, therefore I prefer to skip the api.
        elif "/auction.html" in link:
            data = await utils.get_auction(link)
            embed.add_field(name="Info", value="\n".join([f"**{k.title()}:** {v}" for k, v in sorted(data.items())]))

        elif "/article.html" in link:
            tree = await utils.get_content(link)
            posted = " ".join(tree.xpath('//*[@class="mobile_article_preview_width_fix"]/text()')[0].split()[1:-1])
            title = tree.xpath('//*[@class="articleTitle"]/text()')[0]
            subs, votes = [int(x.strip()) for x in tree.xpath('//*[@class="bigArticleTab"]/text()')]
            author_name, newspaper_name = tree.xpath('//*[@class="mobileNewspaperStatus"]/a/text()')
            author_id = utils.get_ids_from_path(tree, '//*[@class="mobileNewspaperStatus"]/a')[0]
            newspaper_id = utils.get_ids_from_path(tree, '//*[@class="mobileNewspaperStatus"]/a')[1]
            row = {"posted": posted, "author": f"[{author_name.strip()}]({base_url}profile.html?id={author_id})",
                   "votes": votes,
                   "newspaper": f"[{newspaper_name}]({base_url}newspaper.html?id={newspaper_id})", "subs": subs}
            embed.add_field(name=f"**Title:** {title}",
                            value="\n".join([f"**{k.title()}:** {v}" for k, v in sorted(row.items())]))

        elif "/law.html" in link:
            tree = await utils.get_content(link)
            time1 = tree.xpath('//*[@id="esim-layout"]//script[3]/text()')[0]
            time1 = [i.split(");\n")[0] for i in time1.split("() + ")[1:]]
            if int(time1[0]) < 0:
                time1 = "Voting finished"
            else:
                time1 = f'{int(time1[0]):02d}:{int(time1[1]):02d}:{int(time1[2]):02d}'
            proposal = " ".join([x.strip() for x in tree.xpath('//table[1]//tr[2]//td[1]//div[2]//text()')]).strip()
            by = tree.xpath('//table[1]//tr[2]//td[3]//a/text()')[0]
            yes = [x.strip() for x in tree.xpath('//table[2]//td[2]//text()') if x.strip()][0]
            no = [x.strip() for x in tree.xpath('//table[2]//td[3]//text()') if x.strip()][0]
            time2 = tree.xpath('//table[1]//tr[2]//td[3]//b')[0].text
            row = {"law_proposal": proposal, "proposed_by": by.strip(), "proposed": time2,
                   "remaining_time" if "Voting finished" not in time1 else "status": time1,
                   "result": f'{yes} Yes, {no} No'}
            embed.add_field(name="Info", value="\n".join([f"**{k.replace('_', ' ').title()}:** {v}"
                                                          for k, v in sorted(row.items())]))

        elif "/party.html" in link or "/showShout.html" in link:
            row = await utils.get_content(get_url)
            if "party" in link:
                del row["members_list"]
                row["country"] = f"{utils.codes(row['country'])} " + row["country"]
            embed.add_field(name="Info", value="\n".join([f"**{k.replace('_', ' ').title()}:** {v}"
                                                          for k, v in sorted(row.items())]))

        elif "/citizenStatistics.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="#", value="\n".join([f"**{k}**" for k in range(1, len(row["citizens"]) + 1)][:5]))
            embed.add_field(name="Nick", value="\n".join(
                [f"{utils.codes(v['country'])} [{v['nick']}]({base_url}profile.html?id={v['id']}),"
                 f" {v['country']}" for v in row["citizens"]][:5]))
            embed.add_field(name=row["statistic_type"],
                            value="\n".join([f"{v['value']:,}" for v in row["citizens"]][:5]))

        elif "/coalitionStatistics.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="Coalition", value="\n".join(
                [f"[{v['name']}]({base_url}coalition.html?coalitionId={v['coalition_id']})" for v in row][:5]))
            embed.add_field(name="Leader", value="\n".join(
                [f"[{v['leader']}]({base_url}profile.html?id={v['leader_id']})" for v in row][:5]))
            embed.add_field(name="Dmg", value="\n".join([f"{v['dmg']:,}" for v in row][:5]))

        elif "/newCitizenStatistics.html" in link:
            result = [[], [], []]
            for v in await utils.get_content(get_url):
                types = v["food"], v["gift"], v["wep"]
                if any(types):
                    result[0].append(f"{utils.codes(v['country'])} [{v['name']}]({base_url}profile.html?id={v['id']})")
                    result[1].append(" ".join(["\U0001f534" if x else "\U0001f7e2" for x in types]))
                    result[2].append(v['registered'])

            if result:
                embed.add_field(name="Nick", value="\n".join(result[0]))
                embed.add_field(name="Motivate", value="\n".join(result[1]))
                embed.add_field(name="Registered", value="\n".join(result[2]))

        elif "/partyStatistics.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="Party", value="\n".join(
                [f"{utils.codes(v['country'])} [{v['party']}]({base_url}party.html?id={v['party_id']}), "
                 f"{v['country']}" for v in row][:5]))
            embed.add_field(name="Members", value="\n".join([str(v['members']) for v in row][:5]))
            embed.add_field(name="Prestige", value="\n".join([f"{v['prestige']:,}" for v in row][:5]))

        elif "/newspaperStatistics.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="Newspaper", value="\n".join([f"[{v['newspaper']}]({base_url}newspaper.html?id="
                                                               f"{v['newspaper_id']})" for v in row['newspapers']][:5]))
            embed.add_field(name="Redactor", value="\n".join(
                [f"[{v['redactor']}]({base_url}profile.html?id={v['redactor_id']})" for v in row['newspapers']][:5]))
            embed.add_field(name="Subs", value="\n".join([f"{v['subs']:,}" for v in row][:5]))

        elif "/battles.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="Time Reminding", value="\n".join([v['time_remaining'] for v in row['battles']][:5]))
            embed.add_field(name="Defender | Attacker", value="\n".join(
                [f"[{utils.codes(v['defender']['name'])} {v['defender']['name']} |"
                 f" {utils.codes(v['attacker']['name'])} {v['attacker']['name']}]"
                 f"({base_url}battle.html?id={v['battle_id']})"
                 f" ({v['defender']['score']}:{v['attacker']['score']})" for v in row['battles']][:5]))
            embed.add_field(name="Bar", value="\n".join(
                [(await utils.bar(v['defender']['bar'], v['attacker']['bar'], size=6)).splitlines()[0]
                 for v in row['battles']][:5]))
            embed.set_footer(text="Battles: " + ", ".join([str(x['battle_id']) for x in row['battles']]))

        elif "/battlesByWar.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="Region", value="\n".join([v['region'] for v in row['battles']][:5]))
            embed.add_field(name="Defender | Attacker", value="\n".join(
                [f"[{utils.codes(v['defender_name'])} {v['defender_name']} |"
                 f" {utils.codes(v['attacker_name'])} {v['attacker_name']}]"
                 f"({base_url}battle.html?id={v['id']})"
                 f" ({v['defender_score']}:{v['attacker_score']})" for v in row['battles']][:5]))
            embed.add_field(name="Dmg", value="\n".join([f"{v['dmg']:,}" for v in row['battles']][:5]))
            embed.set_footer(text="Battles: " + ", ".join([str(x['battle_id']) for x in row['battles']]))

        elif "/companiesForSale.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="Company", value="\n".join([f"[Q{x['quality']} {x['company_type']}]({base_url}company"
                                                             f".html?id={x['company_id']})" for x in row][:5]))
            embed.add_field(name="Location", value="\n".join(
                [f"{utils.codes(x['country'])} [{x['location_name']}]"
                 f"({base_url}region.html?id={x['location_id']}) ({x['country']})" for x in row][:5]))
            embed.add_field(name="Price", value="\n".join([str(x["price"]) for x in row[:5]]))

        elif "/presidentalElections.html" in link or "/congressElections.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="#", value="\n".join([str(x) for x in range(1, len(row["candidates"]) + 1)][:5]))
            embed.add_field(name="Candidate", value="\n".join(
                [f"[{x['candidate']}]({base_url}profile.html?id={x['candidate_id']})" for x in row["candidates"]][:5]))
            embed.add_field(name="Votes", value="\n".join([str(x['votes']) for x in row["candidates"]][:5]))
            embed.set_footer(text=f"{utils.codes(row['country'])} {row['country']}, {row['date']}")

        elif "/productMarket.html" in link:
            row = await utils.get_content(get_url)
            row = row["offers"][:5]
            embed.add_field(name="Product", value="\n".join([x["product"] for x in row]))
            embed.add_field(name="Stock", value="\n".join([str(x["stock"]) for x in row]))
            embed.add_field(name="Price", value="\n".join([f'{x["price"]} {x["coin"]}' for x in row]))

        elif "/region.html" in link:
            row = await utils.get_content(get_url)
            penalty = "100%"
            for v in row["active_companies_stats"]:
                if v["type"].split()[-1].lower() in all_products[:6]:
                    penalty = v["penalty"]
            row["penalty"] = penalty
            row["buildings"] = len(row["buildings"])
            for key in ("current_owner", "rightful_owner"):
                row[key] = f"{utils.codes(row[key])} " + row[key]
            embed.add_field(name="Info", value="\n".join([
                f"**{k.replace('_', ' ').title()}:** {v}" for k, v in row.items() if (
                        not isinstance(v, (dict, list)) and v != "No resources")]))

        elif "/stockCompanyStatistics.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="#",
                            value="\n".join([f"**{k}**" for k in range(1, len(row["stock_companies"]) + 1)][:5]))
            embed.add_field(name="Stock Company",
                            value="\n".join([f"{utils.codes(v['country'])} [{v['stock_company']}]"
                                             f"({base_url}stockCompany.html?id={v['id']}), {v['country']}" for v in row[
                                                 "stock_companies"]][:5]))
            embed.add_field(name=row["statistic_type"],
                            value="\n".join([f"{v['value']:,}" for v in row["stock_companies"]][:5]))

        elif "/countryStatistics.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="#",
                            value="\n".join([f"**{k}**" for k in range(1, len(row["countries"]) + 1)][:5]))
            embed.add_field(name="Country", value="\n".join(
                [f"{utils.codes(v['country'])} " + v['country'] for v in row["countries"]][:5]))
            embed.add_field(name=row["statistic_type"],
                            value="\n".join([f"{v['value']:,}" for v in row["countries"]][:5]))

        elif "/countryEconomyStatistics.html" in link:
            row = await utils.get_content(get_url)
            wanted_keys = ["country", "citizens_online", "minimal_salary", "new_citizens_today",
                           "total_active_citizens", "total_coins_in_treasury"]
            row["total_coins_in_treasury"] = round(sum(row["treasury"][0].values()))
            row['country'] = f"{utils.codes(row['country'])} " + row['country']
            embed.add_field(name="Info",
                            value="\n".join([f"**{k.replace('_', ' ').title()}:** {v}" for k, v in row.items()
                                             if k in wanted_keys]))

        elif "/countryPoliticalStatistics.html" in link:
            row = await utils.get_content(get_url)
            wanted_keys = ["coalition_members", "congress_members"]
            if row["coalition_members"]:
                row["coalition_members"] = ", ".join(row["coalition_members"])
            else:
                del row["coalition_members"]
            row["congress_members"] = len(row["congress"])

            for minister in ("defense", "finance", "social"):
                d = row.get("minister_of_" + minister)
                if d:
                    row["minister_of_" + minister] = f'[{d["nick"]}]({base_url}profile.html?id={d["id"]})'
                    wanted_keys.append("minister_of_" + minister)
            for event in ("mpps", "wars", "naps"):
                row[event] = len(row[event])
                wanted_keys.append(event)
            embed.add_field(name="Info",
                            value="\n".join([f"**{k.replace('_', ' ').title()}:** {v}" for k, v in row.items()
                                             if k in wanted_keys]))

        elif "/events.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="Icon", value="\n".join([k['icon'].title() for k in row["events"][:5]]))
            embed.add_field(name="Event", value="\n".join(
                [f"[{(k['event'][:50] + '...') if len(k['event']) > 50 else k['event']}]({base_url + k['link']})" for k
                 in row["events"][:5]]))
            embed.add_field(name="Time", value="\n".join([k['time'] for k in row["events"][:5]]))

        elif "/jobMarket.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="#", value="\n".join([f"**{k}**" for k in range(1, len(row["offers"]) + 1)][:5]))
            embed.add_field(name="Company",
                            value="\n".join([f"[{v['company']}]({base_url}company.html?id={v['company_id']})"
                                             f" (Q{v['company_quality']} {v['company_type']})"
                                             for v in row["offers"]][:5]))
            embed.add_field(name="Salary", value="\n".join([f"{v['salary']}" for v in row["offers"]][:5]))

        elif "/newCitizens.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="#",
                            value="\n".join([f"**{k}**" for k in range(1, len(row["new_citizens"]) + 1)][:5]))
            embed.add_field(name="Nick", value="\n".join(
                [f"[{k['nick']}]({base_url}profile.html?id={k['citizen_id']})" for k in row["new_citizens"][:5]]))
            embed.add_field(name="registered", value="\n".join([k['registered'] for k in row["new_citizens"]][:5]))

        elif "/militaryUnit.html" in link:
            embed.description = None
            api1 = await utils.get_content(link.replace("militaryUnit", "apiMilitaryUnitById"))
            api2 = await utils.get_content(link.replace("militaryUnit", "apiMilitaryUnit"))
            row = {"Name": api1['name'], "Total Damage": f"{api1['totalDamage']:,}",
                   "Today Damage": f"{api2['todayDamage']:,}", "Max Members": api1['maxMembers'],
                   "Citizenship": all_countries[api1['countryId']], "Type": api1['militaryUnitType'],
                   "Value": api2['value']}
            row['Citizenship'] = f"{utils.codes(row['Citizenship'])}" + row['Citizenship']
            embed.add_field(name="Info", value="\n".join([f"**{k}:** {v}" for k, v in row.items()]))
            row = {f"Battle Order: {all_countries[api2['todayBattleAttacker']]} VS "
                   f"{all_countries[api2['todayBattleDefender']]}": f"{base_url}battle.html?id={api2['todayBattleId']}",
                   "Recruitment": link.replace("militaryUnit", "militaryUnitRecrutation"),
                   "Donate products": link.replace("militaryUnit", "donateProductsToMilitaryUnit"),
                   "Donate money": link.replace("militaryUnit", "donateMoneyToMilitaryUnit"),
                   "MU Companies": link.replace("militaryUnit", "militaryUnitCompanies"),
                   "Members info": link.replace("militaryUnit", "militaryUnitMembers"),
                   "Leader": f"{base_url}profile.html?id={api2['leaderId']}"}
            embed.add_field(name="Links", value="\n".join([f"[{k.title()}]({v})" for k, v in row.items()]))

        elif "/newspaper.html" in link:
            row = await utils.get_content(get_url)
            embed.description += f"\n\n**Redactor:** [{row['redactor']}]({base_url}profile.html?id={row['redactor_id']})"
            embed.add_field(name="Info", value="\n".join(
                [f"[{k['title']}]({base_url}article.html?id={k['newspaper_id']}) ({k['votes']} votes)" for k in
                 row["articles"][:5]]))
            embed.set_footer(text=f"{row['subs']:,} Subs, " + (
                f"~{row['pages'] * 8}" if row['pages'] != 1 else str(len(row['articles']))) + " Articles")

        elif "/news.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="Info", value="\n".join(
                [f"[{k['title']}]({base_url}article.html?id={k['article_id']}) ({k['posted']})" for k in
                 row["articles"][:5]]))

        elif "/stockCompany.html" in link:
            row = await utils.get_content(get_url)
            embed.add_field(name="Info", value="\n".join(
                [f"**{k.replace('_', ' ').title()}:** {v}" for k, v in row.items() if not isinstance(v, list)]))

        elif "/stockCompanyMoney.html" in link:
            raw_data = await utils.get_content(get_url)
            raw_data = raw_data["storage"]
            row = {"Gold": raw_data["Gold"],
                   "Total coins": round(sum(x for x in raw_data.values() if not isinstance(x, list)))}
            embed.add_field(name="Info", value="\n".join([f"**{k.title()}:** {v:,}" for k, v in row.items()]))

        elif "/stockCompanyProducts.html" in link:
            row = await utils.get_content(get_url)
            row = await utils.split_list(row["storage"], 3)
            for LIST in row:
                embed.add_field(name="\u200B",
                                value="\n".join([f"**{x['product'].title()}:** {x['amount']:,}" for x in LIST]))

        elif "/battleDrops.html" in link:
            row = await utils.get_content(get_url)
            row = await utils.split_list(row["drops"], 3)
            for LIST in row:
                embed.add_field(name="Item: Nick", value="\n".join([
                    (f"**Q{x['quality']} {x['item'].title()}:**" if 'quality' in x else f"**{x['item'].title()}:**") +
                    f" [{x['nick']}]({base_url}profile.html?id={x['citizen_id']})" for x in LIST]))

        elif "/newMap.html" in link:
            await utils.custom_followup(
                interaction, f'Try this link instead: <{link.replace("newMap", "fullscreenMap")}>', ephemeral=True)
            return

        elif "/battle.html" in link:
            embed.description = None
            api_battles = await utils.get_content(link.replace("battle", "apiBattles").replace("id", "battleId"))
            minutes = api_battles['minutesRemaining'] + api_battles['hoursRemaining'] * 60
            t = f"{minutes:02d}:{api_battles['secondsRemaining']:02d}"
            attacker, defender = utils.get_sides(api_battles)

            if "&round=" in link:
                round_id = link.split("&round=")[1].split("&")[0]
                api = link.replace("battle", "apiFights").replace("id", "battleId").replace("round", "roundId")
            else:
                if api_battles['defenderScore'] == 8 or api_battles['attackerScore'] == 8:
                    round_id = api_battles['currentRound'] - 1
                else:
                    round_id = api_battles['currentRound']
                api = link.replace("battle", "apiFights").replace("id", "battleId") + f"&roundId={round_id}"

            my_dict, hit_time = await utils.save_dmg_time(api, attacker, defender)
            output_buffer = await utils.dmg_trend(hit_time, server, f'{link.split("=")[1].split("&")[0]}-{round_id}')
            hit_time.clear()
            score = f"{api_battles['defenderScore']}:{api_battles['attackerScore']}"
            embed = Embed(colour=0x3D85C6, url=link,
                          title=("" if "8" in score else f"T{t}, ") + f"**Score:** {score}")
            embed.add_field(name=utils.codes(defender) + " " + utils.shorten_country(defender),
                            value=f"{my_dict[defender]:,}")
            embed.add_field(name=f'Battle type: {api_battles["type"]}',
                            value=await utils.bar(my_dict[defender], my_dict[attacker], defender, attacker))
            embed.add_field(name=utils.codes(attacker) + " " + utils.shorten_country(attacker),
                            value=f"{my_dict[attacker]:,}")
            embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
            await utils.custom_followup(interaction,
                                        embed=await utils.convert_embed(interaction, embed, is_columns=False),
                                        file=File(fp=output_buffer, filename=f"{interaction.id}.png"))
            return

        elif "/showEquipment.html" in link or "/apiEquipmentById.html" in link:
            api = await utils.get_content(link.replace("showEquipment", "apiEquipmentById"))
            embed = Embed(colour=0x3D85C6, url=link,
                          title=f"__**Q{api['EqInfo'][0]['quality']} {api['EqInfo'][0]['slot'].title()}**__")
            if "ownerId" in api['EqInfo'][0]:
                owner_link = f"{link.replace('showEquipment', 'profile').split('=')[0]}={api['EqInfo'][0]['ownerId']}"
                embed.description = f"[Owner Profile]({owner_link})"
            embed.add_field(name="Parameters:",
                            value="\n".join(f"**{x['Name']}:** {round(x['Value'], 3)}" for x in api['Parameters']))
            await utils.custom_followup(interaction, embed=await utils.custom_author(embed))
            return

        else:
            await utils.custom_followup(interaction, "Unsupported link")
        if embed.fields:
            await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed))

    @command()
    async def e_sim_table(self, interaction: Interaction, attachment: Attachment) -> None:
        """Converts a csv (excel) file to e-sim table format"""
        file = File(fp=utils.csv_to_txt(await attachment.read()),
                    filename=f"Esim_format_{attachment.filename.replace('csv', 'txt')}")
        await utils.custom_followup(interaction, file=file)


async def remind_func(channel: TextChannel, when: str, reminder_id: str, msg: str) -> None:
    """remind func"""
    date_format = "%Y/%m/%d %H:%M:%S"
    now = datetime.now().astimezone(timezone('Europe/Berlin')).strftime(date_format)
    seconds = (datetime.strptime(when, date_format) - datetime.strptime(now, date_format)).total_seconds()
    await sleep(seconds)
    find_remind = await utils.find_one("collection", "remind")
    if reminder_id not in find_remind:
        return
    await channel.send("Your reminder is ready: " + msg)
    del find_remind[reminder_id]
    await utils.replace_one("collection", "remind", find_remind)


def get_user_links(base_url: str, link: str, api: dict, company: str) -> dict:
    """get user links"""
    return {"\U0001f575 MU": f"{base_url}militaryUnit.html?id={api['militaryUnitId']}",
            "\U0001f4dd msg": link.replace("profile", "composeMessage"),
            "\U0001f5fa Location": f"{base_url}region.html?id={api['currentLocationRegionId']}",
            "\U0001f60d Friend Request": f"{base_url}friends.html?action=PROPOSE&id={api['id']}",
            "\U0001f477 Work place": company,
            "\U0001f4b0 Donate Money": link.replace("profile", "donateMoney"),
            "\U0001f381 Donate Products": link.replace("profile", "donateProducts"),
            "\U0001f455 Donate EQ": link.replace("profile", "donateEquipment")}


async def setup(bot) -> None:
    """Setup"""
    await bot.add_cog(General(bot))
