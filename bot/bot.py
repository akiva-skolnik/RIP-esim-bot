"""Bot.py"""
import json
import os
from datetime import date

import aiosqlite
from aiohttp import ClientSession, ClientTimeout
from discord import (AllowedMentions, Forbidden, Game, HTTPException, Intents,
                     Interaction, Message, NotFound, app_commands)
from discord.ext.commands import Bot, when_mentioned


async def load_extensions(reload: bool = False) -> None:
    """Loads extensions"""
    for (_, _, filenames) in os.walk("exts"):
        for file_name in filenames:
            if not file_name.startswith("_"):
                if reload:
                    await bot.reload_extension(f'exts.{file_name.replace(".py", "")}')
                else:
                    await bot.load_extension(f'exts.{file_name.replace(".py", "")}')
        break

def find_one(collection: str, _id: str) -> dict:
    """find one"""
    filename = f"../db/{collection}_{_id}.json"
    if os.path.exists(filename):
        with open(filename, "r", encoding='utf-8') as file:
            return json.load(file)
    else:
        return {}


class MyTree(app_commands.CommandTree):
    """Lock new server"""
    async def interaction_check(self, interaction: Interaction) -> bool:
        """Lock new server"""
        if not any("zeta" in str(v) for v in interaction.data.values()):
            return True
        today = str(date.today())
        if bot.premium_users.get(str(interaction.user.id), {}).get("level", -1) >= 1 or (
                interaction.guild and str(interaction.guild.id) in bot.premium_servers):
            return True
        if bot.premium_users.get(str(interaction.user.id), {}).get("added_at", "") != today:
            bot.premium_users[str(interaction.user.id)] = {"added_at": today}
            #await replace_one("collection", "donors", bot.premium_users)
            return True
        try:
            await interaction.response.send_message(
                "zeta server is for premium users only. You can use one command per day for free."
                "\nGet premium at <https://www.buymeacoffee.com/RipEsim> :coffee:"
                "\nSupport: https://discord.com/invite/q96wSd6")
        except HTTPException:
            pass
        return False

class MyClient(Bot):
    """Custom Client"""
    def __init__(self) -> None:
        super().__init__(command_prefix=when_mentioned, case_insensitive=True,
                         activity=Game("type /"), allowed_mentions=AllowedMentions(
                replied_user=False), intents=Intents.default(), tree_cls=MyTree)
        with open("./config.json", 'r', encoding="utf-8") as file:
            self.config = json.load(file)
            # {"db_url": "", "TOKEN": ""}
        self.before_invoke(reset_cancel)
        self.should_cancel = should_cancel
        self.cancel_command = {}
        self.orgs = {}

        self.config_ids = {
            "commands_server": "1032367697503199357",
            "support_server": "584948608097452032",
            "error_channel": "1032367698258169879",
            "warnings_channel": "1032367971970072619",
            "bugs_channel": "694436164979130420",
            "feedback_channel": "584950255238512660",
            "support_invite": "https://discord.com/invite/q96wSd6"
        }

        self.gids = {
            "primera": ["1laY2aYa5_TcaDPCZ4FrFjZnbvVkxRIrGdm7ZRaO41nY", 0, 1364472548],
            "luxia": ["1mx_JkHVnTVikNdTSxhvfFh4Pzuepp9ZGakCAtxnGxyY", 1876322398, 1265748453],
            "secura": ["10en9SJVsIQz7uGhbXwb9GInnOdcDuE4p7L93un0q6xw", 1876322398, 1265748453],
            "suna": ["1imlsoLdaEb45NnJGmo5T7mQxsjzzTGbrkvqfcR8pMlE", 2061648609, 0],
            "alpha": ["1KqxbZ9LqS191wRf1VGLNl-aw6UId9kmUE0k7NfKQdI4", 1445005647, 0],
            "unica": ["1PvjB3E-7A4cYAUmczJ1HNDOUAQAUnFzjSkCu-dJuVL0", 1876322398, 1265748453],
            "sigma": ["1SuHcJLqS-nSAzprs7kGsrrcuNLOdXsPRaDVQbkvpxZc", 1876322398, 1265748453],
            "azura": ["1xy8Ssj91q6z8vqmtnpbviY1pK44ed3FQrOI3KyVq2cg", 1876322398, 1265748453],
            "zeta": ["1lYS3tG259h1NxS-I-KNwyTnkoSK1zQzmjaSyo1iWtzo", 1876322398, 1265748453],
        }

        self.delay = {}

        self.api = "http://3.70.2.167:5000/"
        self.date_format = "%d-%m-%Y %H:%M:%S"

        self.all_servers = ['primera', 'secura', 'suna', 'alpha', 'luxia', 'unica', 'sigma', 'azura', 'zeta']

        self.products = ["iron", "grain", "oil", "stone", "wood", "diamonds",
                        "weapon", "house", "gift", "food", "ticket", "defense_system", "hospital", "estate"]

        self.countries = {
            1: 'Poland', 2: 'Russia', 3: 'Germany', 4: 'France', 5: 'Spain', 6: 'United Kingdom',
            7: 'Italy', 8: 'Hungary', 9: 'Romania', 10: 'Bulgaria', 11: 'Serbia', 12: 'Croatia',
            13: 'Bosnia and Herzegovina', 14: 'Greece', 15: 'Republic of Macedonia', 16: 'Ukraine',
            17: 'Sweden', 18: 'Portugal', 19: 'Lithuania', 20: 'Latvia', 21: 'Slovenia',
            22: 'Turkey', 23: 'Brazil', 24: 'Argentina', 25: 'Mexico', 26: 'USA', 27: 'Canada',
            28: 'China', 29: 'Indonesia', 30: 'Iran', 31: 'South Korea', 32: 'Taiwan', 33: 'Israel',
            34: 'India', 35: 'Australia', 36: 'Netherlands', 37: 'Finland', 38: 'Ireland',
            39: 'Switzerland', 40: 'Belgium', 41: 'Pakistan', 42: 'Malaysia', 43: 'Norway',
            44: 'Peru', 45: 'Chile', 46: 'Colombia', 47: 'Montenegro', 48: 'Austria',
            49: 'Slovakia', 50: 'Denmark', 51: 'Czech Republic', 52: 'Belarus', 53: 'Estonia',
            54: 'Philippines', 55: 'Albania', 56: 'Venezuela', 57: 'Egypt', 58: 'Japan',
            59: 'Bangladesh', 60: 'Vietnam', 61: 'Yemen', 62: 'Saudi Arabia', 63: 'Thailand',
            64: 'Algeria', 65: 'Angola', 66: 'Cameroon', 67: 'Ivory Coast', 68: 'Ethiopia',
            69: 'Ghana', 70: 'Kenya', 71: 'Libya', 72: 'Morocco', 73: 'Mozambique', 74: 'Nigeria',
            75: 'Senegal', 76: 'South Africa', 77: 'Sudan', 78: 'Tanzania', 79: 'Togo',
            80: 'Tunisia', 81: 'Uganda', 82: 'Zambia', 83: 'Zimbabwe', 84: 'Botswana', 85: 'Benin',
            86: 'Burkina Faso', 87: 'Congo', 88: 'Central African Republic', 89: 'DR of the Congo',
            90: 'Eritrea', 91: 'Gabon', 92: 'Chad', 93: 'Niger', 94: 'Mali', 95: 'Mauritania',
            96: 'Guinea', 97: 'Guinea Bissau', 98: 'Sierra Leone', 99: 'Liberia',
            100: 'Equatorial Guinea', 101: 'Namibia', 102: 'Lesotho', 103: 'Swaziland',
            104: 'Madagascar', 105: 'Malawi', 106: 'Somalia', 107: 'Djibouti', 108: 'Rwanda',
            109: 'Burundi', 110: 'United Arab Emirates', 111: 'Syria', 112: 'Iraq', 113: 'Oman',
            114: 'Qatar', 115: 'Jordan', 116: 'Western Sahara', 117: 'The Gambia',
            118: 'South Sudan', 119: 'Cambodia', 120: 'Nepal', 121: 'Bolivia', 122: 'Ecuador',
            123: 'Paraguay', 124: 'Uruguay', 125: 'Honduras', 126: 'Dominican Republic',
            127: 'Guatemala', 128: 'Kazakhstan', 129: 'Sri Lanka', 130: 'Afghanistan',
            131: 'Armenia', 132: 'Azerbaijan', 133: 'Georgia', 134: 'Kyrgyzstan', 135: 'Laos',
            136: 'Tajikistan', 137: 'Turkmenistan', 138: 'Uzbekistan', 139: 'New Zealand',
            140: 'Guyana', 141: 'Suriname', 142: 'Nicaragua', 143: 'Panama', 144: 'Costa Rica',
            145: 'Mongolia', 146: 'Papua New Guinea', 147: 'Cuba', 148: 'Lebanon',
            149: 'Puerto Rico', 150: 'Moldova', 151: 'Jamaica', 152: 'El Salvador', 153: 'Haiti',
            154: 'Bahrain', 155: 'Kuwait', 156: 'Cyprus', 157: 'Belize', 158: 'Kosovo',
            159: 'East Timor', 160: 'Bahamas', 161: 'Solomon Islands', 162: 'Myanmar',
            163: 'North Korea', 164: 'Bhutan', 165: 'Iceland', 166: 'Vanuatu', 167: 'San Marino',
            168: 'Palestine', 169: 'Soviet Union', 170: 'Czechoslovakia',
            171: 'Yugoslavia', 172: 'Weimar Republic', 173: 'Republic Of China', 174: 'Persia'}

        self.countries_by_name = {v.lower(): k for k, v in self.countries.items()}

        self.all_parameters = {"avoid": "Chance to avoid damage",
                              "max": "Increased maximum damage",
                              "crit": "Increased critical hit chance",
                              "core": "Increased damage for cores",  # must be before damage
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
                              "elixir": "Elixir time increased"}


        self.session = None
        self.locked_session  = None
        self.org_session = None
        self.phone_users = (find_one("collection", "phone") or {"users": []})["users"]
        self.default_nick_dict = find_one("collection", "default")
        self.premium_users = find_one("collection", "donors")
        self.premium_servers = (find_one("collection", "premium_guilds") or {"guilds": []})["guilds"]
        self.custom_delay_dict = find_one("collection", "delay")
        self.dbs = {}

    async def setup_hook(self) -> None:
        headers = {"User-Agent": 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:84.0)'
                                 ' Gecko/20100101 Firefox/84.0'}
        self.session = ClientSession(timeout=ClientTimeout(total=100), headers=headers)
        self.locked_session = ClientSession(timeout=ClientTimeout(total=150), headers=headers)
        self.org_session = ClientSession(timeout=ClientTimeout(total=150), headers=headers)
        #self.dbs = {server: await aiosqlite.connect(f'../db/{server}.db') for server in self.all_servers}

        await load_extensions()


async def should_cancel(interaction: Interaction, msg: Message = None) -> bool:
    """Return whether the function should be cancelled"""
    if bot.cancel_command.get(interaction.user.id, "") == interaction.command.name:
        if msg is not None:
            try:
                await msg.delete()
            except (Forbidden, NotFound, HTTPException):
                pass
        del bot.cancel_command[interaction.user.id]
        return True
    return False

#TODO: make it class functions
async def reset_cancel(interaction: Interaction) -> None:
    """Reset the cancel option before each invoke"""
    if isinstance(interaction, Interaction) and await should_cancel(interaction):
        del bot.cancel_command[interaction.user.id]


bot = MyClient()