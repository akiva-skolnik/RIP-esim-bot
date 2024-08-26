from .utils import strip

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


def dmg_calculator(api: dict, bonuses: str = "new") -> dict:
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
        MU = Military unit order bonus (1.0 if no order, 1.05-1.20 if fight in order depending on MU type)
            [no MU / elite MU in this function]
        Buff = special item bonus (1.2 if tank is on * 1.2 if steroid is on * 1.25 if bunker or sewer guide is on,
            or 0.8 if debuffed)
        C = Critical chance (0.125-0.4)
        M = Miss chance (0-0.125)

        BH = basic number of hits (depends on the quality and quantity of food and gifts you want to use (10 q5 food = 50))
        A = Avoid chance (0.05-0.4)
    """

    counted_bonuses = {"stats": {}, "bonuses": {}}

    bonuses = strip(bonuses.replace(",", " ").lower().split())

    if "new" in bonuses:
        # Change strength from eqs, according to the change in total strength.
        api['eqIncreaseStrength'] = 300 * api['eqIncreaseStrength'] / api['strength']
        api['rank'] = 'Rookie'
        api['strength'] = 300
        counted_bonuses["stats"]["as new player"] = "300 strength, first rank"

    limits = next((int(x.replace("x", "")) for x in bonuses if x.startswith("x")), 1)

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

    quality = next((int(x.split("q")[1]) for x in bonuses if x.startswith("q")), 5)
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

    bonus_dmg = next(((1 + int(x.replace("%", "")) * 0.01) for x in bonuses if x.endswith("%")), 1)

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
