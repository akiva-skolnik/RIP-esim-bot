"""Battle.py."""
import math
import statistics
import traceback
from asyncio import sleep
from collections import defaultdict
from copy import deepcopy
from csv import writer
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from json import loads
from random import randint

from discord import Embed, File, Interaction, Role
from discord.app_commands import (Transform, check, checks, command, describe,
                                  guild_only)
from discord.ext.commands import Cog, Context, hybrid_command
from matplotlib import pyplot as plt
import numpy as np

from Utils import utils, UiButtons
from Utils.DmgCalculator import dmg_calculator
from Utils.battle_utils import (cup_func, motivate_func, normal_pdf, binom_pmf, ping_func,
                                watch_auction_func, watch_func)
from Utils.constants import (all_countries, all_countries_by_name, all_servers,
                             date_format, gids)
from Utils.dmg_func import dmg_func
from Utils.transformers import (AuctionLink, BattleLink, Country, Server,
                                TournamentLink)
from Utils.utils import CoolDownModified, bar, draw_pil_table, not_support


class Battle(Cog):
    """Battle Commands."""

    def __init__(self, bot) -> None:
        self.bot = bot

    @command()
    async def buffs_links(self, interaction: Interaction) -> None:
        """Displays links of the buff and time trackers."""
        embed = Embed(colour=0x3D85C6)
        description = "**Buff and time trackers:**\n"
        for server, data in gids.items():
            description += f"[**{server}**](https://docs.google.com/spreadsheets/d/{data[0]}/edit#gid={data[2]})\n"
        embed.description = description
        await utils.custom_followup(interaction, "You can also use `/buffs`",
                                    embed=await utils.convert_embed(interaction, embed))

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    async def buffs(self, interaction: Interaction, server: Transform[str, Server], nick: str = "",
                    country: Transform[str, Country] = "", military_unit_id: int = 0) -> None:
        """Displays buffed players per server and country or military unit."""

        if server not in gids:
            await utils.custom_followup(interaction, "You can not use this server in this command", ephemeral=True)
            return
        if military_unit_id:
            mu_members = await utils.get_content(
                f'https://{server}.e-sim.org/apiMilitaryUnitMembers.html?id={military_unit_id}')
            mu_members = tuple(row["login"] for row in mu_members)
            mu_name = f"MU id {military_unit_id}"
        else:
            mu_members = ()
            mu_name = ""

        result = []
        buffed_players_dict = await utils.find_one("buffs", server)
        now = utils.get_current_time(timezone_aware=False)
        total_buff = 0
        total_debuff = 0
        for current_nick, row in buffed_players_dict.items():
            if current_nick == "Nick" or "Last update" in current_nick:
                continue
            link, citizenship, dmg, last, premium, buffed, _, till_change, _, _, _, _ = row[:12]
            if not buffed or (any((country, military_unit_id, nick)) and not any(
                    ((citizenship.lower() == country.lower()), current_nick in mu_members,
                     nick.lower() == current_nick.lower()))):
                continue

            country_nick = f" {utils.get_flag_code(citizenship) if not country else ''} [{current_nick[:12]}]({link})"
            hyperlink = (":star:" if premium else ":lock:") + country_nick

            # A buff last for 24 hours
            if (now - datetime.strptime(buffed, date_format)).total_seconds() < 24 * 60 * 60:
                buff = ":green_circle: "
                total_buff += 1
            else:
                buff = ":red_circle: "
                total_debuff += 1
            row = (hyperlink, last, buff + till_change, dmg)
            if row not in result:
                result.append(row)

        if not result:
            await utils.custom_followup(
                interaction, f"No one is buffed/debuffed at {country or mu_name}, {server} (as far as I can tell)\n"
                             f"See https://docs.google.com/spreadsheets/d/{gids[server][0]}/edit#gid="
                             f"{gids[server][2]}\n")
            return
        median_dmg = statistics.median(tuple(int(x[-1].replace(",", "")) for x in result))
        result = [(x[0],
                   (":low_brightness: " if int(x[-1].replace(",", "")) < median_dmg else ":high_brightness: ") + x[1],
                   x[2]) for x in result]
        result = sorted(result, key=lambda x: datetime.strptime(x[-1].split(": ")[-1], "%H:%M:%S"))
        embed = Embed(colour=0x3D85C6,
                      description=f"**Buffed players {country or mu_name}, {server}**\n"
                                  f"{total_buff} :green_circle:, {total_debuff} :red_circle:",
                      url=f"https://docs.google.com/spreadsheets/d/{gids[server][0]}/edit#gid={gids[server][2]}")
        embed.set_footer(text="\U00002b50 / \U0001f512 = Premium / Non Premium\n"
                              "\U0001f7e2 / \U0001f534 = Buff / Debuff\n"
                              f"\U0001f505 / \U0001f506 = Below / Above median total dmg ({round(median_dmg):,})\n"
                              f"Last update: {buffed_players_dict['Last update:'][0]}")
        headers = ("Nick, Citizenship" if not country else "Nick", "Last Seen (game time)", "Till Debuff (over)")
        await utils.send_long_embed(interaction, embed, headers, result)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @describe(bonuses='options: PD, sewer or bunker, steroids, -tank (debuff), MU, location, DS\n'
                      'Q<wep quality> (default: Q5), X<limits> (default: X1), <bonus dmg>% (default: 0%), '
                      'new (ignore set and rank)')
    @command()
    async def calc(self, interaction: Interaction, server: Transform[str, Server],
                   nick: str, bonuses: str = "") -> None:
        """DMG calculator."""
        api = await utils.get_content(f"https://{server}.e-sim.org/apiCitizenByName.html?name={nick.lower()}")
        dmg = dmg_calculator(api, bonuses)

        embed = Embed(colour=0x3D85C6,
                      description=f"[{api['login']}](https://{server}.e-sim.org/profile.html?id={api['id']}),"
                                  f" {utils.get_flag_code(api['citizenship'])} {api['citizenship']}")
        embed.add_field(name="Estimate Dmg", value=f"{dmg['avoid']:,}")
        embed.add_field(name="Without Avoid", value=f"{dmg['clutch']:,}")
        embed.add_field(name="Number of hits", value=f"{dmg['hits']}")
        embed.add_field(name="\u200B", value="\u200B", inline=False)
        embed.add_field(name="Stats", value="\n".join(f"**{k}:** {v}".title() for k, v in dmg['stats'].items() if v))
        embed.add_field(name="Bonuses", value="\n".join(f"**{k}:** {v}".title() for k, v in dmg['bonuses'].items()))
        await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed, is_columns=False))

    @command()
    @describe(tournament_link='Tournament link',
              nick='Your in-game nick (for showing your score)')
    @check(utils.is_premium_level_1)
    @guild_only()
    async def cup_plus(self, interaction: Interaction, tournament_link: Transform[str, TournamentLink],
                       nick: str = "") -> None:
        """Displays the top 10 players in a cup tournament (faster for premium)."""
        link = tournament_link
        server = link.split("https://", 1)[1].split(".e-sim.org", 1)[0]
        await utils.default_nick(interaction, server, nick)
        find_cup = await utils.find_one("collection", interaction.command.name)
        if link not in find_cup or len(find_cup[link]) >= 10:
            if "countryTournament" not in link:
                tree = await utils.get_locked_content(link)
            else:
                tree = await utils.get_locked_content(link + "&hash=%23slideShedule", method="post")
            ids = {int(x) for x in (
                utils.get_ids_from_path(tree, '//*[@class="battle-link"]') if "countryTournament" not in link else
                utils.get_ids_from_path(tree, '//*[@class="getBattle right"]'))}
            if ids:
                find_cup[link] = [
                    {str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}}]
                first_battle_id, last_battle_id = min(ids), max(ids)
                battle_ids_range = range(first_battle_id, last_battle_id + 1)
                self.bot.logger.info(f"cup_plus: Starting a new cup_plus for {link}. ids range: {battle_ids_range}")
                await utils.replace_one("collection", interaction.command.name, find_cup)
                await cup_func(self.bot, interaction, link, server,
                               battle_ids_range=battle_ids_range,
                               excluded_ids=set(battle_ids_range) - ids)
            else:
                await interaction.edit_original_response(
                    content="No IDs found. Consider using the `cup` command instead. "
                            "Example: `/cup server: alpha first_battle_id: 40730 last_battle_id: 40751`")
        else:
            await interaction.edit_original_response(
                content="On it. If this is taking more than 5 minutes, please report it in the support server.")
            self.bot.logger.info(f"cup_plus: Adding channel {interaction.channel.id} to {link}")
            find_cup[link].append({str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}})
            await utils.replace_one("collection", interaction.command.name, find_cup)

    @checks.dynamic_cooldown(CoolDownModified(30))
    @command()
    @describe(server='server', first_battle_id='first cup battle', last_battle_id='last cup battle',
              nick='Your in-game nick (for showing your score)')
    @guild_only()
    async def cup(self, interaction: Interaction, server: Transform[str, Server],
                  first_battle_id: int, last_battle_id: int, nick: str = "") -> None:
        """Displays the top 10 players in a cup tournament."""
        if last_battle_id - first_battle_id > 1000:
            await utils.custom_followup(interaction,
                                        f"You are asking me to check {last_battle_id - first_battle_id} battles.\n"
                                        "I have a reason to believe that you should recheck your request.",
                                        ephemeral=True)
            return
        if last_battle_id - first_battle_id < 1:
            await utils.custom_followup(interaction,
                                        "You can find the first and last id on the `news` -> `military events` page.",
                                        ephemeral=True)
            return
        await utils.default_nick(interaction, server, nick)
        find_cup = await utils.find_one("collection", interaction.command.name)
        db_key = f"{server} {first_battle_id} {last_battle_id}"
        closest_query = None if db_key in find_cup else next((k for k in find_cup if server in k and k != db_key), None)
        if closest_query is not None:
            view = UiButtons.Confirm()
            await interaction.edit_original_response(
                content=f"Would you like to change your request (`{db_key}`) into `{closest_query}`?"
                        f" It will be much faster.\n"
                        f"(Someone else is running the command right now, and you can get their result)",
                view=view)

            await view.wait()
            if view.value:
                find_cup = await utils.find_one("collection", interaction.command.name)
                if closest_query in find_cup:
                    await interaction.edit_original_response(content="I'm on it, Sir. Thank you very much.",
                                                             view=view)
                    find_cup[closest_query].append(
                        {str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}})
                    await utils.replace_one("collection", interaction.command.name, find_cup)
                    return
            else:
                await interaction.edit_original_response(content="Ok.", view=view)

        if db_key not in find_cup or len(find_cup[db_key]) >= 10:
            # initiate a new cup / replace the old one which probably has error
            find_cup[db_key] = [
                {str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}}]
            await utils.replace_one("collection", interaction.command.name, find_cup)

        else:
            find_cup[db_key].append(
                {str(interaction.channel.id): {"nick": nick, "author_id": str(interaction.user.id)}})
            return await utils.replace_one("collection", interaction.command.name, find_cup)
        battle_ids_range = range(first_battle_id, last_battle_id + 1)
        await cup_func(self.bot, interaction, db_key, server, battle_ids_range=battle_ids_range)

    @checks.dynamic_cooldown(CoolDownModified(15))
    @command()
    @describe(battle_link='battle link, or server and battle id',
              nick='Please choose nick, country, or mu id',
              country='Please choose nick, country, or mu id',
              mu_id='Please choose nick, country, or mu id',
              calculate_tops='Calculate top1, top3, top10 (takes longer)')
    async def dmg(self, interaction: Interaction, battle_link: Transform[dict, BattleLink], nick: str = "",
                  country: Transform[str, Country] = "", mu_id: int = 0, calculate_tops: bool = False) -> None:
        """
        Displays wep used and dmg done (Per player, MU, country, or overall) in a given battle(s).

        **Notes:**
        - If your nick is the same string as some country (or close enough), add a dash before your nick. Example: `-Israel`
        - For range of battles, use `<first>_<last>` instead of `<link>` (`/dmg battle_link: alpha 1165_1167 country: Israel`)
        """  # noqa

        await dmg_func(self.bot, interaction, battle_link, nick, country, mu_id, calculate_tops)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(battle_link="Battle link, or server and battle id", bonus="Bonus drops (default: 0)",
              nick="Your nick (for showing your stats)")
    async def drops(self, interaction: Interaction, battle_link: Transform[dict, BattleLink], bonus: int = 0,
                    nick: str = "") -> None:
        """Displays the expected amount of drops in a given battle."""
        server, battle_id = battle_link["server"], battle_link["id"]
        link = f"https://{server}.e-sim.org/battle.html?id={battle_id}"
        nick = await utils.default_nick(interaction, server, nick)

        tops_per_player = defaultdict(lambda: {'hits': 0, 'tops': [0, 0, 0]})  # Top 1, 3, 10 (respectively).
        hits_per_player = defaultdict(int)

        api = await utils.get_content(link.replace("battle", "apiBattles").replace("id", "battleId"))
        if api['defenderScore'] == 8 or api['attackerScore'] == 8:
            last = api['currentRound']
        else:
            last = api['currentRound'] + 1

        top1, top3, top10 = range(3)

        for round_id in range(1, last):
            defender = defaultdict(int)
            attacker = defaultdict(int)
            for hit in await utils.get_content(
                    link.replace("battle", "apiFights").replace("id", "battleId") + f'&roundId={round_id}'):
                side = defender if hit['defenderSide'] else attacker
                side[hit['citizenId']] += hit['damage']
                tops_per_player[hit['citizenId']]['hits'] += 5 if hit['berserk'] else 1
                hits_per_player[hit["citizenId"]] += 5 if hit['berserk'] else 1

            # TODO: move to function (duplicated in /dmg)
            for side in (attacker, defender):
                side = sorted(side.items(), key=lambda x: x[1], reverse=True)
                for (player, dmg) in side:
                    if (player, dmg) in side[:10]:
                        tops_per_player[player]["tops"][top10] += 1
                        if (player, dmg) in side[:3]:
                            tops_per_player[player]["tops"][top3] += 1
                            if (player, dmg) in side[:1]:
                                tops_per_player[player]["tops"][top1] += 1
            await utils.custom_delay(interaction)

        del attacker, defender, side

        hits = sum(hits_per_player.values())
        hits_with_bonus = hits + hits * bonus / 100
        next_upgrade = (hits // 3000 + 1) * 3000 - hits
        embed = Embed(colour=0x3D85C6, title=f'**Total hits : ** {hits:,}', url=link)
        hits_for_q = {"Q6": 150000, "Q5": 30000, "Q4": 10000, "Q3": 3000, "Q2": 1000, "Q1": 300}
        # item: [drops, hits for next]
        drops_per_q: dict[str, (int, int)] = {q: (round(hits_with_bonus / v), int(
            ((round(hits_with_bonus / v) + 1) * v - v / 2 - hits_with_bonus) / (bonus + 100) * 100)) for q, v in
                                              hits_for_q.items()}
        drops_per_q["Elixir"] = (int(hits_with_bonus / 150),
                                 (int(hits_with_bonus / 150) + 1) * 150 - int(hits_with_bonus))
        drops_per_q["upg. + shuffle"] = (hits // 1500, next_upgrade)
        embed.add_field(name="**Item : Drops**",
                        value="\n".join(f"**{k} :** {v[0]:,}" for k, v in drops_per_q.items()))
        embed.add_field(name="**Hits For Next**", value="\n".join(f"{int(v[1]):,}" for v in drops_per_q.values()))
        given_user_id = None
        if nick:
            try:
                api_citizen = f"https://{server}.e-sim.org/apiCitizenByName.html?name={nick.lower()}"
                given_user_id = (await utils.get_content(api_citizen))['id']
                if given_user_id not in hits_per_player:
                    nick = ""
            except Exception:
                nick = ""

        final = defaultdict(lambda: defaultdict(tuple))
        qualities = set()
        all_total_tops = {index: sum(x['tops'][index] for x in tops_per_player.values()) for index in range(3)}
        fig, ax = plt.subplots()

        indexes = {"Q3": top10, "Q4": top3, "Q5": top1, "Q6": top1}
        mean_values = []
        max_k = 0
        for user_id, value in tops_per_player.items():
            player = given_user_id if nick else user_id
            if player != user_id:
                continue
            for quality, total_drops in {k: v[0] for k, v in drops_per_q.items()}.items():
                if quality in indexes:
                    total_tops = all_total_tops[indexes[quality]]
                    my_tops = value['tops'][indexes[quality]] if 'tops' in value else 0
                elif "upg" in quality:
                    total_tops = hits
                    my_tops = value['hits']
                else:
                    total_tops = hits_with_bonus
                    my_tops = value['hits'] + value['hits'] * bonus / 100

                n = total_drops
                p = (my_tops / total_tops) if total_tops else 0
                mean = n * p  # mu
                mean_values.append(mean)
                std = math.sqrt(mean * (1 - p))  # sigma
                if n * p >= 5 and n * (1 - p) >= 5:
                    # normal approx
                    percentages = [normal_pdf(k, mean, std) * 100 for k in range(n + 1)]
                else:
                    probs = binom_pmf(n, p)
                    percentages = [p * 100 for p in probs]

                cum_sum = np.cumsum(percentages)
                # keep only values below 99.9
                percentages = [percentages[i] for i in range(len(cum_sum)) if cum_sum[i] < 99.9]

                max_k = max(max_k, len(percentages))

                first, last = round(mean - std), round(mean + std)
                if total_drops and my_tops:
                    if first == 0:
                        drops_range = "1" if total_drops == 1 else "1+"
                        chances = 100 - percentages[0]
                    else:
                        drops_range = f"{first}-{last}" if first != last else str(first)
                        chances = sum(percentages[first:last + 1])
                    final[player][quality] = (drops_range, f"{round(chances)}%")
                    qualities.add(quality)
                else:
                    final[player][quality] = (0, "100%")

                if nick and len(percentages) > 1:
                    amounts = list(range(1, len(percentages) + 1))
                    await self.bot.loop.run_in_executor(None, lambda: ax.plot(
                        amounts, percentages, marker='.', label=quality))

        csv_writer = None
        if not nick:
            qualities = sorted(qualities, reverse=True)
            headers = tuple(a for a in ((f"{x} Prediction Range", f"{x} chance") for x in qualities) for a in a)
            output = StringIO()
            csv_writer = writer(output)
            csv_writer.writerow(("Citizen Id", "Hits", "Top 1", "Top 3", "Top 10") + headers)
        for player, chances in final.items():
            if not nick:
                row = [player, tops_per_player[player]["hits"]] + tops_per_player[player]["tops"]
                for quality in qualities:
                    amount, chance = chances[quality]
                    row.extend([f" {amount}" if amount else "", chance])
                csv_writer.writerow(row)
            else:
                def plot_drops() -> BytesIO:
                    plt.ylim(bottom=0.1)

                    ax.legend()
                    ax.set_title(f"Drop chances for {nick} ({server}, {battle_id})")
                    ax.set_ylabel('%')
                    ax.set_xlabel('Drops Amount (log scale)')
                    ax.xaxis.get_major_locator().set_params(integer=True)

                    # convert the x to log scale
                    ax.set_xscale('log')

                    ticks = sorted({round(x) for x in mean_values if x > 20}.union(range(1, min(10, max_k + 1))))

                    ax.set_xticks(ticks)
                    # Shift back the data to the original
                    tick_labels = tuple(str(tick - 1) for tick in ticks)
                    ax.set_xticklabels(tick_labels)
                    return utils.plt_to_bytes(fig)

                output_buffer = await self.bot.loop.run_in_executor(None, plot_drops)
                file = File(fp=output_buffer, filename=f"{interaction.id}.png")
                embed.set_thumbnail(url=f"attachment://{interaction.id}.png")
                embed.add_field(name="**Expected Drops: Chances**", value="\n".join(
                    f"**{chances[Q][0]} : ** {chances[Q][1]}" for Q in drops_per_q.keys()))
                embed.add_field(name="Top", value="\n".join(
                    f"**{x}**" for x in ("BH", "Top 3", "Top 10", "Hits")))
                embed.add_field(name="Total Tops",
                                value="\n".join(list(map(str, all_total_tops.values())) + [f"{hits:,}"]))
                embed.add_field(name="Your Tops",
                                value="\n".join([f"{x:,}" for x in tops_per_player[given_user_id]['tops']]
                                                + [f'{tops_per_player[given_user_id]["hits"]:,}']))
                await utils.custom_followup(interaction, file=file, embed=await utils.convert_embed(interaction, embed))

        if not nick:
            output.seek(0)
            await utils.custom_followup(interaction, "Chances of receiving **at least** x amount of drops", files=[
                File(fp=await utils.csv_to_image(output), filename=f"Preview_{server}.png"),
                File(fp=BytesIO(output.getvalue().encode()),
                     filename=f"Chances_{link.split('battle.html?id=')[1]}.csv")],
                                        embed=await utils.convert_embed(interaction, embed))

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @guild_only()
    @check(not_support)
    async def motivate(self, interaction: Interaction, server: Transform[str, Server]) -> None:
        """Checks every ~10 minutes if there is a new citizen to motivate in the given server."""
        base_url = f'https://{server}.e-sim.org/'

        try:
            tree = await utils.get_content(f'{base_url}newCitizenStatistics.html')
            names = tree.xpath("//tr//td[1]/a/text()")
            citizen_ids = tree.xpath("//tr//td[1]/a/@href")
            countries = tree.xpath("//tr//td[2]/span/text()")
            registration_time = tree.xpath("//tr[position()>1]//td[3]/text()[1]")
            registration_time1 = tree.xpath("//tr//td[3]/text()[2]")
            xp = tuple(int(x) for x in tree.xpath("//tr[position()>1]//td[4]/text()"))
            wep = tree.xpath("//tr[position()>1]//td[5]/i/@class")
            food = tree.xpath("//tr[position()>1]//td[6]/i/@class")
            gift = tree.xpath("//tr[position()>1]//td[5]/i/@class")
            citizens_data = tuple(
                {"name": name.strip(), "citizen_id": int(citizen_id.split("?id=")[1]), "country": country,
                 "registration_time": registration_time.strip(), "registered": registration_time1[1:-1],
                 "xp": xp, "wep": "479" in wep, "food": "479" in food, "gift": "479" in gift}
                for name, citizen_id, country, registration_time, registration_time1, xp, wep, food, gift in zip(
                    names, citizen_ids, countries, registration_time, registration_time1, xp, wep, food, gift))
            result = {"nick": [], "motivate": [], "registered": []}
            for citizen_data in citizens_data:
                types = citizen_data["food"], citizen_data["gift"], citizen_data["wep"]
                if any(types):
                    result["nick"].append(f"{utils.get_flag_code(citizen_data['country'])} ["
                                          f"{citizen_data['name']}]({base_url}profile.html?id={citizen_data['citizen_id']})")
                    result["motivate"].append(" ".join("\U0001f534" if not x else "\U0001f7e2" for x in types))
                    result["registered"].append(citizen_data['registered'])

            if any(result.values()):
                embed = Embed(colour=0x3D85C6, title="Source", url=f'{base_url}newCitizenStatistics.html')
                embed.add_field(name="Nick", value="\n".join(result["nick"]))
                embed.add_field(name="Motivate", value="\n".join(result["motivate"]))
                embed.add_field(name="Registered", value="\n".join(result["registered"]))
                await interaction.edit_original_response(embed=await utils.convert_embed(interaction, embed))
        except Exception as error:
            await utils.send_error(interaction, error)
            traceback.print_exc()
        db_dict = await utils.find_one("collection", "motivate")
        if server not in db_dict:
            db_dict[server] = [str(interaction.channel.id)]
            await utils.replace_one("collection", "motivate", db_dict)
            self.bot.loop.create_task(motivate_func(self.bot, server, db_dict))
        elif str(interaction.channel.id) not in db_dict[server]:
            db_dict[server].append(str(interaction.channel.id))
            await utils.replace_one("collection", "motivate", db_dict)
        await interaction.edit_original_response(
            content=f"I will check every 5 minutes if there is a new player at `{server}`")

    @command()
    @describe(servers="Default to all servers")
    async def got(self, interaction: Interaction, servers: str = "") -> None:
        """Stops motivate program."""
        if not servers or servers.lower() == "all":
            servers = " ".join(all_servers)
        db_dict = await utils.find_one("collection", "motivate")
        changed_servers = []
        for server in servers.replace(",", " ").split():
            if not server.strip():
                continue
            try:
                server = utils.server_validation(server)
            except Exception:
                continue

            if server in db_dict:
                if str(interaction.channel.id) in db_dict[server]:
                    db_dict[server].remove(str(interaction.channel.id))
                    changed_servers.append(server)

                if not db_dict[server]:
                    del db_dict[server]

        if changed_servers:
            await interaction.edit_original_response(
                content="Program `motivate` have been stopped for the following servers in this channel:\n" +
                        ", ".join(changed_servers))
            await utils.replace_one("collection", "motivate", db_dict)

        else:
            await interaction.edit_original_response(
                content=f"No motivate program was running in this channel for {servers=}.")

    @command(name="motivate-scanner")
    @check(utils.is_premium_level_1)
    async def motivate_scanner(self, interaction: Interaction, server: Transform[str, Server]) -> None:
        """Scanning motivates."""
        await utils.custom_followup(interaction, "Scanning...")
        base_url = f'https://{server}.e-sim.org/'
        tree = await utils.get_content(f'{base_url}newCitizens.html?countryId=0')
        citizen_id = int(utils.get_ids_from_path(tree, "//tr[2]//td[1]/div/a")[0])
        today = 0
        embed = Embed(colour=0x3D85C6, title="Motivates", url=f'{base_url}newCitizenStatistics.html')
        embed.set_footer(text="\U0001f7e2, \U0001f534 = Already Sent / Available")
        results = []
        view = index = None
        for index in range(200):
            tree = await utils.get_locked_content(f'{base_url}profile.html?id={citizen_id}', index == 0)
            birthday = int(tree.xpath(
                '//*[@class="profile-row newProfileRow" and span = "Birthday"]/span/text()')[0].split()[-1])
            if not today:  # first citizen
                today = birthday
            if today - birthday <= 3:
                if not tree.xpath('//*[@id="motivateCitizenButton"]'):
                    continue
                nick = tree.xpath('//*[@class="big-login"]/text()')[0]
                citizenship = tree.xpath('//*[@class="countryNameTranslated"]/text()')[-1]
                await utils.custom_delay(interaction)
                tree = await utils.get_locked_content(f"{base_url}motivateCitizen.html?id={citizen_id}")

                types = tree.xpath('//td[2]//input/@value')
                if not types:
                    continue
                icons = ["\U0001f7e2"] * 3
                for motivate_type in types:
                    icons[int(motivate_type) - 1] = "\U0001f534"
                results.append([f'[{nick}]({base_url}motivateCitizen.html?id={citizen_id})',
                                f"{utils.get_flag_code(citizenship)} {citizenship}", " ".join(icons)])

            citizen_id -= 1
            if (index + 1) % 10 == 0 or today - birthday > 3:
                if results:
                    embed.clear_fields()
                    embed.add_field(name="Nick", value="\n".join(x[0] for x in results))
                    embed.add_field(name="Citizenship", value="\n".join(x[1] for x in results))
                    embed.add_field(name=":gun: :bread: :gift:", value="\n".join(x[2] for x in results))
                    results.clear()
                    view = UiButtons.StopNext(interaction)
                    await interaction.edit_original_response(content=f"I have scanned {index + 1} players so far.",
                                                             embed=await utils.convert_embed(interaction, embed),
                                                             view=view)
                    if today - birthday > 3:
                        break
                    await view.wait()
                    if not view.next_page or view.canceled:
                        break
            else:
                await interaction.edit_original_response(content=f"Scanned {index + 1} players so far.")

        if view:
            view.clear_items()
        await interaction.edit_original_response(content=f"I have scanned total {index + 1} players.", view=view)

    @checks.dynamic_cooldown(CoolDownModified(5))
    @command()
    @describe(country="Show country's battles (optional)")
    async def nexts(self, interaction: Interaction, server: Transform[str, Server],
                    country: Transform[str, Country] = "") -> None:
        """Displays the upcoming battles."""
        base_url = f'https://{server}.e-sim.org/'
        battles = await utils.get_battles(base_url, all_countries_by_name.get(country.lower(), 0))

        if not battles:
            await utils.custom_followup(interaction, "There are currently no active RWs or attacks.")
            return
        battles = sorted(battles, key=lambda k: k['time_remaining'])
        last = battles[-1]["time_remaining"]
        headers = ("**Time remaining**", "**Defender | Attacker (Score)**", "**Bar**")
        battles = tuple(
            (x["time_remaining"],
             f"[{utils.shorten_country(x['defender']['name'])} vs " + utils.shorten_country(x['attacker']['name']) +
             f"]({base_url}battle.html?id={x['battle_id']}) ({x['defender']['score']}:{x['attacker']['score']})",
             (bar(x['defender']['bar'], x['attacker']['bar'], size=6)).splitlines()[0]) for x in battles)
        embed = Embed(colour=0x3D85C6, title=server, url=f'{base_url}battles.html')
        await utils.send_long_embed(interaction, embed, headers, battles)
        time_of_last = int(last.split(":")[0]) * 3600 + int(last.split(":")[1]) * 60 + int(last.split(":")[2])
        del battles

        update_seconds = 60
        while time_of_last > 0:
            await sleep(min(time_of_last, update_seconds))
            values = embed.fields[0].value.splitlines()
            for num, value in enumerate(values):
                if "round is over" in value:
                    continue
                value = value.split()[0]
                actual_time = int(value.split(":")[0]) * 3600 + int(value.split(":")[1]) * 60 + int(
                    value.split(":")[2]) - update_seconds
                values[num] = str(timedelta(seconds=actual_time)) if actual_time > 0 else "round is over"
            embed.set_field_at(0, name=embed.fields[0].name, value="\n".join(values))
            embed.timestamp = datetime.now()
            try:
                await interaction.edit_original_response(embed=await utils.convert_embed(interaction, deepcopy(embed)))
            except Exception:
                return
            time_of_last -= update_seconds

    @checks.dynamic_cooldown(CoolDownModified(10))
    @command()
    @describe(country='buffs per country (optional)',
              extra_premium_info='get more info and wait a bit longer (premium)')
    async def online(self, interaction: Interaction, server: Transform[str, Server] | None,
                     battle_link: Transform[dict, BattleLink] | None,
                     country: Transform[str, Country] = "", military_unit_id: int = 0,
                     extra_premium_info: bool = False) -> None:
        """
        Displays citizens online & buffs info in a bonus location of a battle or in a country.

        Use `online+` to get more info (you will have to wait a bit longer).
        online+ output: https://prntscr.com/v8diez
        """

        if extra_premium_info and not await utils.is_premium_level_1(interaction, False):
            await utils.custom_followup(interaction,
                                        "`extra_premium_info` is a premium parameter! If you wish to use it, "
                                        "along with many other premium commands, please visit https://www.buymeacoffee.com/RipEsim"
                                        "\n\nOtherwise, try again, but this time with `extra_premium_info=False`",
                                        ephemeral=True)
            return

        check_battle = False
        link = ""
        if battle_link:
            link = f"https://{battle_link['server']}.e-sim.org/battle.html?id={battle_link['id']}"
            server = battle_link['server']
            check_battle = True
        elif not server:
            await utils.custom_followup(interaction, "You must provide server or battle link", ephemeral=True)
            return

        members = ()
        country = all_countries_by_name.get(country.lower(), 0)

        if military_unit_id:
            members = await utils.get_content(
                f'https://{server}.e-sim.org/apiMilitaryUnitMembers.html?id={military_unit_id}')
            members = tuple(row["login"] for row in members)

        base_url = f"https://{server}.e-sim.org/"
        api_map = await utils.get_content(f"{base_url}apiMap.html")
        occupant_id = {i['regionId']: i['occupantId'] for i in api_map}
        api_battles = None
        if check_battle:
            api_battles = await utils.get_content(link.replace("battle", "apiBattles").replace("id", "battleId"))
            if api_battles["type"] not in ("RESISTANCE", "ATTACK"):
                await utils.custom_followup(interaction, "I'm sorry, but I can only show online citizens in "
                                                         "resistance or attack battles.")
                return
            api_regions_link = link.split("?")[0].replace("battle", "apiRegions")
            region_neighbour_ids = next(
                (set(region['neighbours']) for region in await utils.get_content(api_regions_link)
                 if region["id"] == api_battles['regionId']), set())

            defender_regions, attacker_regions = utils.get_bonus_regions(api_map, api_battles, region_neighbour_ids)
            valid_neighbour_ids = attacker_regions if api_battles['type'] == "RESISTANCE" \
                else defender_regions.union(attacker_regions)
        else:
            valid_neighbour_ids = set()
        api_map.clear()
        table = []
        find_buff = await utils.find_one("buffs", server)
        now = utils.get_current_time(timezone_aware=False)
        header = ()
        for row in await utils.get_content(f"{base_url}apiOnlinePlayers.html?countryId={country}"):
            row = loads(row)
            name = row['login']
            location_id = row['localization']
            if (members and name not in members) or (check_battle and location_id not in valid_neighbour_ids):
                continue
            citizenship = row['citizenship']
            level = row['level']
            location = all_countries[occupant_id[location_id]]
            if extra_premium_info:
                tree = await utils.get_content(f"{base_url}profile.html?id={row['id']}")
                try:
                    dmg = tree.xpath('//*[@class="profile-row newProfileRow"]/span/text()')[2]
                except IndexError:
                    continue
                buffs, debuffs = utils.get_buffs_debuffs(tree)
                if check_battle and api_battles['type'] != "ATTACK":
                    header = "Nick", "Citizenship", "lvl", "Total DMG", "Buffs", "Debuffs"
                    table.append([name, all_countries[citizenship], level, dmg, buffs, debuffs])
                else:
                    if not country:
                        header = "Nick", "Citizenship", "lvl", "Total DMG", "Location", "Buffs", "Debuffs"
                        table.append([name, all_countries[citizenship], level, dmg, location, buffs, debuffs])
                    else:
                        header = "Nick", "lvl", "Total DMG", "Location", "Buffs", "Debuffs"
                        table.append([name, level, dmg, location, buffs, debuffs])
            else:
                if name in find_buff and find_buff[name][5]:
                    buff = ":red_circle: " if not (now - datetime.strptime(
                        find_buff[name][5], date_format)).total_seconds() < 86400 else ":green_circle: "
                    level = buff + str(level)
                    citizenship_name = find_buff[name][1]
                    name = f"{utils.get_flag_code(citizenship_name)} [{name}]({find_buff[name][0]})"

                else:
                    citizenship_name = all_countries[citizenship]
                    name = f"{utils.get_flag_code(citizenship_name)} [{name}]({base_url}profile.html?id={row['id']})"
                    level = f":unlock: {level}"

                header = "CS, Nick", "Level", "Location"
                table.append([name, level, f"{utils.get_flag_code(location)} {location}"])
        if not table:
            await utils.custom_followup(
                interaction, "I'm sorry, but I could not find anyone online " +
                             (f"at the bonus locations of <{link}>" if check_battle else "") +
                             "\nPerhaps you should read the help command again.\n"
                             f"If you do not believe me, you may see for yourself here: "
                             f"<{base_url}citizensOnline.html?countryId={country}>")
            return
        if len(header) == 3:
            # TODO: title disappears
            embed = Embed(colour=0x3D85C6, title="More Info",
                          url=f"{base_url}citizensOnline.html?countryId={country}")
            embed.set_footer(text="\U0001f7e2, \U0001f534, \U0001f513 = Buff / Debuff / Neither")
            await utils.send_long_embed(interaction, embed, header, table)

        else:
            new_lines = 0
            if server in gids:
                buffed_players_dict = await utils.find_one("buffs", server)
                for row in table:
                    if row[0] not in buffed_players_dict or not buffed_players_dict[row[0]][5]:
                        continue

                    db_row = buffed_players_dict[row[0]]
                    index = None
                    if (utils.get_current_time(timezone_aware=False) -
                        datetime.strptime(db_row[5], date_format)).total_seconds() < 86400:
                        index = -2
                    if not db_row[5]:
                        index = -1
                    if index and row[index]:
                        row[index] += f"\n(Time left: {db_row[7].strip()})"
                        new_lines += 1
            output_buffer = await self.bot.loop.run_in_executor(None, draw_pil_table, table, header, new_lines)
            await utils.custom_followup(interaction, file=File(fp=output_buffer, filename=f'{server}.jpg'))

    @checks.dynamic_cooldown(CoolDownModified(10))
    @command()
    @describe(role="ping a specific role", t="minutes before round ends to ping at",
              country="filter battles by country")
    @guild_only()
    @check(not_support)
    async def ping(self, interaction: Interaction, server: Transform[str, Server], role: Role | None,
                   t: float = 5.0, country: Transform[str, Country] = "") -> None:
        """Informs the user about each round that comes to an end."""

        ping_id = randint(1000, 9999)
        await utils.custom_followup(interaction,
                                    f"I will write here at the last {t} minutes of every battle in {server if not country else country}.\n"
                                    f"If you want to stop it, type `/stop ping_id: {ping_id}`")
        ping_id = f"{interaction.channel.id} {ping_id}"
        try:
            role = role.mention
        except Exception:
            role = role or ""
        find_ping = await utils.find_one("collection", "ping")
        find_ping[ping_id] = {"t": t, "server": server, "country": country, "role": role,
                              "author_id": str(interaction.user.id)}
        await utils.replace_one("collection", "ping", find_ping)
        await ping_func(interaction.channel, t, server, ping_id, country, role, interaction.user.id)

    @checks.dynamic_cooldown(utils.CoolDownModified(2))
    @command()
    @describe(ping_id="write 0 if you wish to remove all ids in this channel")
    async def stop(self, interaction: Interaction, ping_id: int) -> None:
        """Stopping `ping` program for a given id.

        If you meant to stop `motivate` program - use `got`
        """
        await utils.custom_followup(interaction, "Ok", ephemeral=True)
        find_ping = await utils.find_one("collection", "ping")
        if ping_id == 0:
            ping_ids = tuple(x.split()[1] for x in find_ping if str(interaction.channel.id) == x.split()[0])
            for ping_id in ping_ids:
                del find_ping[f"{interaction.channel.id} {ping_id}"]
            await utils.replace_one("collection", "ping", find_ping)
            await utils.custom_followup(interaction, "Program `ping` have been stopped. no more spam!")

        elif f"{interaction.channel.id} {ping_id}" in find_ping:
            del find_ping[f"{interaction.channel.id} {ping_id}"]
            await utils.replace_one("collection", "ping", find_ping)
            await interaction.edit_original_response(content=f"Program `ping` for ID {ping_id} have been stopped.")
        else:
            await interaction.edit_original_response(content=f"Id {ping_id} was not found in this channel")

    @command()
    @check(utils.is_premium_level_1)
    async def spectators(self, interaction: Interaction, battle_link: Transform[dict, BattleLink]) -> None:
        """Displays spectators count in a battle (plus some extra info)."""
        server, battle_id = battle_link["server"], battle_link["id"]
        link = f"https://{server}.e-sim.org/battle.html?id={battle_id}"
        tree = await utils.get_locked_content(link)
        try:
            hidden_id = tree.xpath("//*[@id='battleRoundId']")[0].value
        except IndexError:
            await utils.custom_followup(interaction, "This battle is probably over. If not, please report it as a bug.",
                                        ephemeral=True)
            return
        api_citizen = await utils.get_content(
            f"https://{server}.e-sim.org/apiCitizenByName.html?name={self.bot.config['nick'].lower()}")
        at, ci = api_citizen["id"], api_citizen["citizenshipId"]
        api = await utils.get_content(
            f"https://{server}.e-sim.org/battleScore.html?id={hidden_id}&at={at}&ci={ci}&premium=1", "json")
        spect = {"spectatorsByCountries": [], "defendersByCountries": [], "attackersByCountries": []}
        for key, spect_list in spect.items():
            for item in api[key].splitlines():
                if "-" in item:
                    count = int(item.split("-")[0].split(">")[-1].strip())
                    country = item.split("xflagsSmall-")[1].split('"')[0].replace("-", " ")
                    if key == "spectatorsByCountries" and country == api_citizen["citizenship"]:
                        count -= 1
                        if not count:
                            continue
                    spect_list.append(f"{count} {country.title()}")

        top = {}
        for key in ("recentDefenders", "recentAttackers", "topDefenders", "topAttackers"):
            top[key] = tuple(f'**{x["playerName"]}:** {x["influence"]}' for x in api[key])
        embed = Embed(colour=0x3D85C6, title=f'Time Reminding: {timedelta(seconds=api["remainingTimeInSeconds"])}',
                      description=f'**Defender**: {api["defenderScore"]} ({round(100 - api["percentAttackers"], 2)}%)\n'
                                  f'**Attacker**: {api["attackerScore"]} ({api["percentAttackers"]}%)', url=link)
        for key, values in spect.items():
            key = key.replace("ByCountries", "")
            if key == "spectators":
                api[key + 'Online'] -= 1
            embed.add_field(name=f"__{api[key + 'Online']} {key}__".title(), value=("\n".join(values) or "-"))

        for key, values in top.items():
            if key == "topDefenders":
                embed.add_field(name="\u200B", value="\u200B")
            key = key.replace("10", " 10 ").replace("A", " A").replace("D", " D").title()
            embed.add_field(name=f"__{key}__", value="\n".join(values) or "-")

        await utils.custom_followup(interaction, embed=await utils.custom_author(embed))

    @command()
    async def watch_list(self, interaction: Interaction) -> None:
        """Get the watch list for this channel."""
        data = []
        find_watch = await utils.find_one("collection", "watch") or {"watch": []}
        find_auctions = await utils.find_one("collection", "auctions") or {"auctions": []}
        for watch_dict in find_watch["watch"] + find_auctions["auctions"]:
            if watch_dict["channel_id"] == interaction.channel.id and not watch_dict.get("removed"):
                sides = watch_dict.get("sides")
                score = watch_dict.get("score")
                row = f"<{watch_dict['link']}> at T{utils.remove_decimal(watch_dict['t'])}"
                if sides and score:  # there can't be one without the other
                    row += f", **Sides:** {sides} ({score})"
                data.append(row)
        if data:
            await utils.custom_followup(interaction, '\n'.join(["**Watch List:**"] + data + [
                "\nIf you want to remove any, write `/unwatch link: <link>` or `/unwatch link: ALL`",
                f"Example: `/unwatch link: {data[0].split()[0]}`"]))
        else:
            await utils.custom_followup(interaction,
                                        "Currently, I'm not watching any battle. Type `/watch` if you want to watch one.")

    @checks.dynamic_cooldown(CoolDownModified(10))
    @command()
    @guild_only()
    @check(not_support)
    @describe(link="The battle or auction link you want to watch",
              t="How many minutes before the end should I ping you? (default: 5)",
              role="Which role should I mention? (default: @here)",
              custom_msg="Would you like to add a message to the ping?")
    async def watch(self, interaction: Interaction, link: str, t: float = 5.0,
                    role: Role = None, custom_msg: str = "") -> None:
        """Watching a given battle (or auction) and pinging at a specific time."""
        try:
            role = role.mention
        except Exception:
            role = role or "@here"

        try:
            link = await AuctionLink().transform(interaction, link)
            is_auction = True
        except Exception:
            link = await BattleLink().transform(interaction, link)
            is_auction = False

        server, link_id = link["server"], link["id"]
        if is_auction:
            link = f'https://{server}.e-sim.org/auction.html?id={link_id}'
            find_auctions = await utils.find_one("collection", "auctions") or {"auctions": []}
            new_auction = {"channel_id": interaction.channel.id, "author_id": interaction.user.id, "link": link,
                           "t": t, "role": role, "custom": custom_msg}
            if new_auction in find_auctions["auctions"]:
                await utils.custom_followup(interaction, "I'm already watching this auction!", ephemeral=True)
            else:
                find_auctions["auctions"].append(new_auction)
                await utils.replace_one("collection", "auctions", find_auctions)
                await watch_auction_func(interaction.channel, link, t, custom_msg)

        else:
            link = f"https://{server}.e-sim.org/battle.html?id={link_id}"
            api_battles = await utils.get_content(link.replace(
                "battle", "apiBattles").replace("id", "battleId"))
            if 8 in (api_battles['defenderScore'], api_battles['attackerScore']):
                await utils.custom_followup(interaction, "This battle is over!", ephemeral=True)
                return
            embed = Embed(colour=0x3D85C6, title=link,
                          description=f"**__Parameters__:**\n**T**: {t}\n**Role**: {role}\n**Custom msg**: " + (
                              f"{custom_msg}" if custom_msg else "None"))
            h, m, s = api_battles["hoursRemaining"], api_battles["minutesRemaining"], api_battles["secondsRemaining"]
            embed.add_field(name="Time Remaining", value=f'{h:02d}:{m:02d}:{s:02d}')
            defender = all_countries.get(api_battles["defenderId"], "defender")
            attacker = all_countries.get(api_battles["attackerId"], "attacker")
            embed.add_field(name="Sides", value=f"{utils.get_flag_code(defender)} {defender} vs "
                                                f"{utils.get_flag_code(attacker)} {attacker}")
            embed.add_field(name="Score", value=f'{api_battles["defenderScore"]}:{api_battles["attackerScore"]}')
            embed.set_footer(text="If you want me to stop watching this battle, use /unwatch")
            find_watch = await utils.find_one("collection", "watch") or {"watch": []}
            new_watch = {"channel_id": interaction.channel.id, "author_id": interaction.user.id, "link": link,
                         "t": t, "role": role, "custom": custom_msg}
            if any(not x.get("removed") and x["link"] == link and x["channel_id"] == interaction.channel.id
                   and x["t"] == t for x in find_watch["watch"]):
                error_msg = "I'm already watching this battle! You can `/unwatch` it first if you wish."
                await utils.custom_followup(interaction, error_msg, ephemeral=True)
            else:
                find_watch["watch"].append(new_watch)
                await utils.replace_one("collection", "watch", find_watch)
                await utils.custom_followup(interaction, embed=await utils.convert_embed(interaction, embed))
                await watch_func(self.bot, interaction.channel, link, t, role, custom_msg)

    @checks.dynamic_cooldown(utils.CoolDownModified(5))
    @hybrid_command()
    @describe(link="The battle or auction link you want to unwatch (can also be 'all')")
    async def unwatch(self, ctx, link: str) -> None:
        """Stop watching a battle / auction."""
        link = link.strip("<> ")
        find_watch = await utils.find_one("collection", "watch") or {"watch": []}
        find_auctions = await utils.find_one("collection", "auctions") or {"auctions": []}
        channel_id = ctx.channel.id if isinstance(ctx, Context) else ctx.id

        removed = []
        for watch_dict in find_watch["watch"]:
            if watch_dict["channel_id"] == channel_id and (
                    watch_dict["link"] == link or link.lower() == "all") and not watch_dict.get("removed"):
                watch_dict["removed"] = True
                removed.append(f'<{watch_dict["link"]}>')
        for auction_dict in find_auctions["auctions"]:
            if auction_dict["channel_id"] == channel_id and (
                    auction_dict["link"] == link or link.lower() == "all") and not auction_dict.get("removed"):
                auction_dict["removed"] = True
                removed.append(f'<{auction_dict["link"]}>')
        if not removed:
            if link.lower() == "all":
                await ctx.send("I'm not watching anything in this server")
            else:
                await ctx.send(f"I'm not watching {link} in this server")
        else:
            await ctx.send("Removed the following links:\n" + "\n".join(removed))
            await utils.replace_one("collection", "watch", find_watch)
            await utils.replace_one("collection", "auctions", find_auctions)


async def setup(bot) -> None:
    """Setup."""
    await bot.add_cog(Battle(bot))
