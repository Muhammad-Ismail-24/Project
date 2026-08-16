"""
scrapers/normalizer.py
Drive Fetch — API-Free Heuristic Scoring Normalizer v3.5

Upgrade log over v3.3:
  - ADDED (v3.3): Smart Trim Normalization. Trims now use negative matching 
    (conflict veto) instead of strict positive vetoing to account for lazy titles.
  - ADDED (v3.4): Extended taxonomy for JDM Kei cars, Chinese entrants, and premium SUVs. Fixed identity scoring for compound titles.
  - ADDED (v3.5): Auto-calculated 70% budget floor when min_budget == 0.
    Vetos listings below 70% of requested_budget (e.g. PKR 2M car against PKR 5M budget).
  - ADDED (v3.5): Description/metadata secondary scan for lazy seller trim protection.
    If requested_trim not found in title, scan car.description and car.about for trim or
    TRIM_ALIASES matches. Counts as a match so sellers who omit trim from title are included.
  - ADDED (v3.5): Trim priority ranking. Title trim match = +25.0 pts, description trim match = +15.0 pts.
    Listings with explicit trim declarations rank above generic model listings.
  - FIXED (2026-08-16): Staleness veto could be bypassed by very old listings.
    The freshness block tested `age_days > 998` for "unknown" BEFORE testing
    `age_days > 90` for "stale", so any listing older than 998 days — e.g. a
    Gari.pk ad posted Jul 19, 2022 (1489 days) — was scored as "age unknown"
    and given a neutral +10 instead of being vetoed. See section 8.
"""

import re
from difflib import SequenceMatcher
from models.car_schema import CarListing
from scrapers.date_utils import DATE_MANDATORY_PLATFORMS, is_unknown_age

# ---------------------------------------------------------------------------
# KNOWLEDGE MAPS
# ---------------------------------------------------------------------------

MAKE_INFERENCE_MAP: dict[str, tuple[str, str]] = {
    "alto":     ("Suzuki",   "Alto"),
    "cultus":   ("Suzuki",   "Cultus"),
    "mehran":   ("Suzuki",   "Mehran"),
    "wagon":    ("Suzuki",   "Wagon R"),
    "wagoner":  ("Suzuki",   "Wagon R"),
    "wagonr":   ("Suzuki",   "Wagon R"),
    "swift":    ("Suzuki",   "Swift"),
    "bolan":    ("Suzuki",   "Bolan"),
    "ravi":     ("Suzuki",   "Ravi"),
    "civic":    ("Honda",    "Civic"),
    "city":     ("Honda",    "City"),
    "brv":      ("Honda",    "BR-V"),
    "vezel":    ("Honda",    "Vezel"),
    "hrv":      ("Honda",    "HR-V"),
    "crv":      ("Honda",    "CR-V"),
    "accord":   ("Honda",    "Accord"),
    "corolla":  ("Toyota",   "Corolla"),
    "yaris":    ("Toyota",   "Yaris"),
    "prado":    ("Toyota",   "Prado"),
    "fortuner": ("Toyota",   "Fortuner"),
    "hilux":    ("Toyota",   "Hilux"),
    "vitz":     ("Toyota",   "Vitz"),
    "aqua":     ("Toyota",   "Aqua"),
    "tucson":   ("Hyundai",  "Tucson"),
    "elantra":  ("Hyundai",  "Elantra"),
    "santro":   ("Hyundai",  "Santro"),
    "sportage": ("Kia",      "Sportage"),
    "stonic":   ("Kia",      "Stonic"),
    "picanto":  ("Kia",      "Picanto"),
    "sorento":  ("Kia",      "Sorento"),
    "hijet":    ("Daihatsu", "Hijet"),
    "cuore":    ("Daihatsu", "Cuore"),
    "charade":  ("Daihatsu", "Charade"),
    "mira":     ("Daihatsu", "Mira"),
    "move":     ("Daihatsu", "Move"),
    "every":    ("Suzuki",   "Every"),
    # JDM Kei / Micro-vans
    "atrai":     ("Daihatsu", "Atrai"),
    "tanto":     ("Daihatsu", "Tanto"),
    "sonica":    ("Daihatsu", "Sonica"),
    "wake":      ("Daihatsu", "Wake"),
    "taft":      ("Daihatsu", "Taft"),
    "cast":      ("Daihatsu", "Cast"),
    "boon":      ("Daihatsu", "Boon"),
    "thor":      ("Daihatsu", "Thor"),
    "esse":      ("Daihatsu", "Esse"),
    "rocky":     ("Daihatsu", "Rocky"),
    "copen":     ("Daihatsu", "Copen"),
    "scrum":     ("Mazda",    "Scrum"),
    "flair":     ("Mazda",    "Flair"),
    "demio":     ("Mazda",    "Demio"),
    "axela":     ("Mazda",    "Axela"),
    "spacia":    ("Suzuki",   "Spacia"),
    "hustler":   ("Suzuki",   "Hustler"),
    "lapin":     ("Suzuki",   "Lapin"),
    "ignis":     ("Suzuki",   "Ignis"),
    "xbee":      ("Suzuki",   "XBEE"),
    "jimny":     ("Suzuki",   "Jimny"),
    "carry":     ("Suzuki",   "Carry"),
    "solio":     ("Suzuki",   "Solio"),
    "escudo":    ("Suzuki",   "Escudo"),
    "palette":   ("Suzuki",   "Palette"),
    "cervo":     ("Suzuki",   "Cervo"),
    "clipper":   ("Nissan",   "Clipper"),
    "roox":      ("Nissan",   "Roox"),
    "moco":      ("Nissan",   "Moco"),
    "kicks":     ("Nissan",   "Kicks"),
    "leaf":      ("Nissan",   "Leaf"),
    "serena":    ("Nissan",   "Serena"),
    "elgrand":   ("Nissan",   "Elgrand"),
    "juke":      ("Nissan",   "Juke"),
    "xtrail":    ("Nissan",   "X-Trail"),
    "wingroad":  ("Nissan",   "Wingroad"),
    "note":      ("Nissan",   "Note"),
    "march":     ("Nissan",   "March"),
    "patrol":    ("Nissan",   "Patrol"),
    "dayz":      ("Nissan",   "Dayz"),
    "nbox":      ("Honda",    "N-Box"),
    "nvan":      ("Honda",    "N-Van"),
    "none":      ("Honda",    "N-One"),
    "nwgn":      ("Honda",    "N-Wgn"),
    "nslash":    ("Honda",    "N-Slash"),
    "grace":     ("Honda",    "Grace"),
    "insight":   ("Honda",    "Insight"),
    "crz":       ("Honda",    "CR-Z"),
    "shuttle":   ("Honda",    "Shuttle"),
    "fit":       ("Honda",    "Fit"),
    "freed":     ("Honda",    "Freed"),
    "jazz":      ("Honda",    "Jazz"),
    "beat":      ("Honda",    "Beat"),
    "s660":      ("Honda",    "S660"),
    "life":      ("Honda",    "Life"),
    "zest":      ("Honda",    "Zest"),
    "minicab":   ("Mitsubishi", "Minicab"),
    "townbox":   ("Mitsubishi", "Town Box"),
    "ekwagon":   ("Mitsubishi", "eK Wagon"),
    "ekspace":   ("Mitsubishi", "eK Space"),
    "delica":    ("Mitsubishi", "Delica"),
    "outlander": ("Mitsubishi", "Outlander"),
    "asx":       ("Mitsubishi", "ASX"),
    "pajero":    ("Mitsubishi", "Pajero"),
    "lancer":    ("Mitsubishi", "Lancer"),
    "canter":    ("Mitsubishi", "Canter"),
    "sambar":    ("Subaru",   "Sambar"),
    "justy":     ("Subaru",   "Justy"),
    "chiffon":   ("Subaru",   "Chiffon"),
    "xv":        ("Subaru",   "XV"),
    "levorg":    ("Subaru",   "Levorg"),
    "forester":  ("Subaru",   "Forester"),
    "outback":   ("Subaru",   "Outback"),
    "wrx":       ("Subaru",   "WRX"),
    "brz":       ("Subaru",   "BRZ"),
    "impreza":   ("Subaru",   "Impreza"),
    "stella":    ("Subaru",   "Stella"),
    "roomy":     ("Toyota",   "Roomy"),
    "tank":      ("Toyota",   "Tank"),
    "passo":     ("Toyota",   "Passo"),
    "porte":     ("Toyota",   "Porte"),
    "spade":     ("Toyota",   "Spade"),
    "sienta":    ("Toyota",   "Sienta"),
    "wish":      ("Toyota",   "Wish"),
    "voxy":      ("Toyota",   "Voxy"),
    "noah":      ("Toyota",   "Noah"),
    "esquire":   ("Toyota",   "Esquire"),
    "harrier":   ("Toyota",   "Harrier"),
    "markx":     ("Toyota",   "Mark X"),
    "crown":     ("Toyota",   "Crown"),
    "chr":       ("Toyota",   "C-HR"),
    "alphard":   ("Toyota",   "Alphard"),
    "vellfire":  ("Toyota",   "Vellfire"),
    "probox":    ("Toyota",   "Probox"),
    "succeed":   ("Toyota",   "Succeed"),
    "raize":     ("Toyota",   "Raize"),
    "rush":      ("Toyota",   "Rush"),
    "belta":     ("Toyota",   "Belta"),
    "camry":     ("Toyota",   "Camry"),
    "hiace":     ("Toyota",   "Hiace"),
    "prius":     ("Toyota",   "Prius"),
    "landcruiser":("Toyota",  "Land Cruiser"),
    # Chinese entrants
    "alsvin":    ("Changan",  "Alsvin"),
    "oshanx7":   ("Changan",  "Oshan X7"),
    "unit":      ("Changan",  "Uni-T"),
    "unik":      ("Changan",  "Uni-K"),
    "hunter":    ("Changan",  "Hunter"),
    "lumin":     ("Changan",  "Lumin"),
    "deepal":    ("Changan",  "Deepal"),
    "karvaan":   ("Changan",  "Karvaan"),
    "hs":        ("MG",       "HS"),
    "zs":        ("MG",       "ZS"),
    "gloster":   ("MG",       "Gloster"),
    "jolion":    ("Haval",    "Jolion"),
    "h6":        ("Haval",    "H6"),
    "dargo":     ("Haval",    "Dargo"),
    "h9":        ("Haval",    "H9"),
    "tiggo4":    ("Chery",    "Tiggo 4 Pro"),
    "tiggo7":    ("Chery",    "Tiggo 7 Pro"),
    "tiggo8":    ("Chery",    "Tiggo 8 Pro"),
    "omoda5":    ("Chery",    "Omoda 5"),
    "atto3":     ("BYD",      "Atto 3"),
    "seal":      ("BYD",      "Seal"),
    "dolphin":   ("BYD",      "Dolphin"),
    "sealion":   ("BYD",      "Sealion"),
    "t2":        ("Jetour",   "T2"),
    "x70plus":   ("Jetour",   "X70 Plus"),
    "dashing":   ("Jetour",   "Dashing"),
    "coolray":   ("Geely",    "Coolray"),
    "okavango":  ("Geely",    "Okavango"),
    "bj40":      ("BAIC",     "BJ40"),
    "x55":       ("BAIC",     "X55"),
    "glory580":  ("DFSK",     "Glory 580"),
    "saga":      ("Proton",   "Saga"),
    "x70":       ("Proton",   "X70"),
    "x50":       ("Proton",   "X50"),
    "persona":   ("Proton",   "Persona"),
    "dmax":      ("Isuzu",    "D-Max"),
    "mux":       ("Isuzu",    "MU-X"),
    "cayenne":   ("Porsche",  "Cayenne"),
    "macan":     ("Porsche",  "Macan"),
    "urus":      ("Lamborghini","Urus"),
    "ghibli":    ("Maserati", "Ghibli"),
    "levante":   ("Maserati", "Levante"),
    "defender":  ("Land Rover","Defender"),
    "discovery": ("Land Rover","Discovery"),
    "wrangler":  ("Jeep",     "Wrangler"),
    "cherokee":  ("Jeep",     "Cherokee"),
    "compass":   ("Jeep",     "Compass"),
}

MODEL_ALIAS_MAP: dict[str, list[str]] = {
    "zsev":      ["zs ev", "zsev", "mg zs ev", "zs-ev", "zs electric"],
    "deepals07": ["deepal s07", "deepal s7", "s07", "s7", "deepal-s07"],
    "deepall07": ["deepal l07", "deepal l7", "l07", "l7", "deepal-l07"],
    "atto3":     ["atto 3", "atto3", "atto-3", "byd atto 3"],
    "ora03":     ["ora 03", "ora 3", "ora03", "ora good cat", "gwm ora 03"],
    "seres3":    ["seres 3", "seres3", "seres-3"],
    "atrai":     ["atrai", "atrai wagon", "hijet atrai"],
    "scrum":     ["scrum", "scrum wagon", "mazda scrum"],
    "clipper":   ["clipper", "nv100", "nv100 clipper"],
    "nbox":      ["n box", "nbox", "n-box"],
    "nvan":      ["n van", "nvan", "n-van"],
    "canbus":    ["canbus", "move canbus"],
    "spacia":    ["spacia", "speshia"],
    "brv":      ["brv", "br-v", "br v", "brvcar"],
    "hrv":      ["hrv", "hr-v", "hr v"],
    "crv":      ["crv", "cr-v", "cr v"],
    "vezel":    ["vezel", "vezal", "vesel", "vezzel"],
    "wagonr":   ["wagonr", "wagon r", "wagon-r", "wagoner"],
    "corolla":  ["corolla", "carolla", "corola", "coralla", "corolla altis", "grande", "xli", "gli", "corolla fielder"],
    "civic":    ["civic", "civick", "civec", "civic reborn", "civic oriel", "civic rs", "civic x"],
    "cultus":   ["cultus", "kultus", "cultis"],
    "mehran":   ["mehran", "meharan", "mehern"],
    "nwagon":   ["n wagon", "nwagon", "n-wagon"],
    "none":     ["n one", "none", "n-one"],
    # JDM aliases
    "atrai":     ["atrai", "atrai wagon", "hijet atrai", "atry", "atrey"],
    "scrum":     ["scrum", "scrum wagon", "mazda scrum"],
    "clipper":   ["clipper", "nv100", "nv100 clipper", "nv100clipper"],
    "nbox":      ["n box", "nbox", "n-box", "en box"],
    "nwgn":      ["n wgn", "nwgn", "n-wgn", "en wgn"],
    "nvan":      ["n van", "nvan", "n-van", "en van"],
    "nslash":    ["n slash", "nslash", "n-slash"],
    "roox":      ["roox", "dayz roox", "rux"],
    "canbus":    ["canbus", "move canbus"],
    "stingray":  ["stingray", "wagon r stingray", "wagonr stingray"],
    "spacia":    ["spacia", "spaciya", "speshia"],
    "hustler":   ["hustler", "hastler", "husler"],
    "minicab":   ["minicab", "minikab", "mini cab"],
    "townbox":   ["town box", "townbox", "town-box"],
    "sambar":    ["sambar", "samber", "sambhar"],
    "ekwagon":   ["ek wagon", "ekwagon", "ek-wagon", "ek custom", "ekcustom"],
    "ekspace":   ["ek space", "ekspace", "ek-space", "ek x", "ekx"],
    "tanto":     ["tanto", "tunto"],
    "taft":      ["taft", "tauft", "tuft"],
    "roomy":     ["roomy", "rumi", "romy"],
    "passo":     ["passo", "paso"],
    "every":     ["every", "evry", "every wagon", "every join"],
    "hijet":     ["hijet", "hejet", "hajit", "hi jet"],
    "deepal":    ["deepal", "deepl", "dipal"],
    "alsvin":    ["alsvin", "alswin", "alveen"],
    # Local sub-model aliases
    "city":      ["city", "city aspire", "city vario", "city steermatic"],
    "fortuner":  ["fortuner", "fortunner", "fortener"],
    "landcruiser":["land cruiser", "landcruiser", "lc200", "lc300", "lc70"],
    "sealion":   ["sealion", "seelion", "sealyn", "sea lion"],
    "xtrail":    ["x trail", "xtrail", "x-trail"],
    "crz":       ["cr z", "crz", "cr-z"],
    # European / Luxury aliases
    "s-class":   ["s-class", "s class", "s400", "s500", "s600", "s350", "s 400", "s 500"],
    "c-class":   ["c-class", "c class", "c180", "c200", "c250", "c300", "c 180", "c 200"],
    "e-class":   ["e-class", "e class", "e200", "e250", "e300", "e 200", "e 250"],
    "g-class":   ["g-class", "g class", "g63", "g500", "g 63"],
    "range rover": ["range rover", "rangerover", "vogue", "autobiography"],
    "range rover sport": ["range rover sport", "rangerover sport", "sport"],
}

MAKE_ALIAS_MAP: dict[str, str] = {
    "daihatsu": "toyota", 
    "mazda":     "suzuki",    # Scrum → Every
    "subaru":    "daihatsu",  # Sambar → Hijet, Justy → Thor
}

MAKE_VETO_ALIASES: dict[str, list[str]] = {
    "daihatsu":  ["toyota", "daihatsu"],
    "toyota":    ["toyota", "daihatsu"],
    "mazda":     ["mazda", "suzuki"],                 # Scrum ↔ Every
    "subaru":    ["subaru", "daihatsu", "toyota"],      # Sambar/Justy ↔ Hijet/Thor
    "nissan":    ["nissan", "suzuki", "mitsubishi"],   # Clipper ↔ Every/Minicab
    "mitsubishi":["mitsubishi", "nissan", "suzuki"],
    
    # European / Luxury makes
    "mercedes-benz": ["mercedes-benz", "mercedes", "benz"],
    "mercedes":      ["mercedes-benz", "mercedes", "benz"],
    "bmw":           ["bmw"],
    "audi":          ["audi"],
    "porsche":       ["porsche"],
    "land rover":    ["land rover", "range rover", "rover"],
    "lexus":         ["lexus", "toyota"],
}

TYPO_CORRECTIONS: dict[str, str] = {
    "carolla":   "corolla",
    "corola":    "corolla",
    "coralla":   "corolla",
    "vesel":     "vezel",
    "vezal":     "vezel",
    "civec":     "civic",
    "civick":    "civic",
    "kultus":    "cultus",
    "cultis":    "cultus",
    "meharan":   "mehran",
    "alto660":   "alto",
    "wagoner":   "wagon r",
    "hilux":     "hilux",
    "fortunner": "fortuner",
    "pajaro":    "pajero",
    "dihatsu":   "daihatsu",
    "daihtsu":   "daihatsu",
    "daihutsu":  "daihatsu",
    "hijet":     "hijet", 
    "atry":      "atrai",
    "atrey":     "atrai",
    "atri":      "atrai",
    "sakrum":    "scrum",
    "scram":     "scrum",
    "speciya":   "spacia",
    "speshia":   "spacia",
    "hastler":   "hustler",
    "husler":    "hustler",
    "tunto":     "tanto",
    "tauft":     "taft",
    "tuft":      "taft",
    "rumi":      "roomy",
    "romy":      "roomy",
    "paso":      "passo",
    "minikab":   "minicab",
    "samber":    "sambar",
    "sambhar":   "sambar",
    "clipar":    "clipper",
    "klipar":    "clipper",
    "hejet":     "hijet",
    "hajit":     "hijet",
    "deepl":     "deepal",
    "dipal":     "deepal",
    "alswin":    "alsvin",
    "alveen":    "alsvin",
    "seelion":   "sealion",
    "sealyn":    "sealion",
    "sportech":  "sportage",
    "evry":      "every",
    "everi":     "every",
    "rux":       "roox",
    "fortener":  "fortuner",
    "toyata":    "toyota",
    "tyota":     "toyota",
    "suzki":     "suzuki",
    "nisin":     "nissan",
    "nisan":     "nissan",
    "mitsibishi":"mitsubishi",
    "mitsbishi": "mitsubishi",
    "mazada":    "mazda",
    "subru":     "subaru",
    "sabru":     "subaru",
    "handa":     "honda",
}

CITY_ALIAS_MAP: dict[str, str] = {
    "isb":          "Islamabad",
    "isl":          "Islamabad",
    "islamabad":    "Islamabad",
    "rwp":          "Rawalpindi",
    "rawalpindi":   "Rawalpindi",
    "pindi":        "Rawalpindi",
    "lhr":          "Lahore",
    "lahore":       "Lahore",
    "khi":          "Karachi",
    "karachi":      "Karachi",
    "krt":          "Karachi",
    "pesh":         "Peshawar",
    "peshawar":     "Peshawar",
    "fsd":          "Faisalabad",
    "faisalabad":   "Faisalabad",
    "mtn":          "Multan",
    "multan":       "Multan",
    "gujranwala":   "Gujranwala",
    "sialkot":      "Sialkot",
    "quetta":       "Quetta",
    "abbottabad":   "Abbottabad",
    "hyderabad":    "Hyderabad",
}

# ---------------------------------------------------------------------------
# TWIN CITY PAIRS & NEARBY CITY MAP
#
# Pakistani cities that are functionally equivalent for used car buying.
# Buyers in city A regularly buy from city B — hard-vetoing these kills
# legitimate inventory. Instead, listings from a twin city get a reduced
# city score (20 pts) vs full match (30 pts), rather than a veto (0 pts).
#
# TWIN_CITY_PAIRS: frozenset pairs — bidirectional, order doesn't matter.
# NEARBY_CITY_MAP: maps each city to its accepted nearby cities.
# ---------------------------------------------------------------------------

TWIN_CITY_PAIRS: set[frozenset] = {
    frozenset({"islamabad", "rawalpindi"}),      # Capital twin cities — 15 min apart
    frozenset({"lahore", "sheikhupura"}),         # Lahore suburb — buyers overlap
    frozenset({"lahore", "kasur"}),
    frozenset({"karachi", "hyderabad"}),          # Sindh corridor
    frozenset({"peshawar", "nowshera"}),          # KPK corridor
    frozenset({"peshawar", "mardan"}),
    frozenset({"rawalpindi", "attock"}),          # Punjab/Rawalpindi zone
    frozenset({"rawalpindi", "chakwal"}),
    frozenset({"islamabad", "attock"}),
    frozenset({"islamabad", "haripur"}),          # Hazara buyers come to ISB
    frozenset({"lahore", "gujranwala"}),          # North Punjab corridor
    frozenset({"faisalabad", "sargodha"}),
    frozenset({"multan", "khanewal"}),
    frozenset({"multan", "lodhran"}),
    frozenset({"gujranwala", "sialkot"}),
    frozenset({"gujranwala", "gujrat"}),
}

# Build a fast lookup: city → set of accepted nearby cities
NEARBY_CITY_MAP: dict[str, set[str]] = {}
for _pair in TWIN_CITY_PAIRS:
    _cities = list(_pair)
    if len(_cities) == 2:
        NEARBY_CITY_MAP.setdefault(_cities[0], set()).add(_cities[1])
        NEARBY_CITY_MAP.setdefault(_cities[1], set()).add(_cities[0])


TRIM_ALIASES: dict[str, list[str]] = {
    "2d":       ["2d", "2.0d", "20d", "diesel"],
    "2.0d":     ["2d", "2.0d", "20d", "diesel"],
    "oriel":    ["oriel", "ug", "oriel ug", "orielug"],
    "ug":       ["oriel", "ug", "oriel ug", "orielug"],
    "rs":       ["rs", "rs turbo", "rsturbo"],
    "turbo":    ["turbo", "rs turbo", "rsturbo"],
    "altis":    ["altis", "grande", "altis grande"],
    "grande":   ["altis", "grande", "altis grande"],
    "gli":      ["gli"],
    "xli":      ["xli"],
    "vxr":      ["vxr", "vxr agc", "vxragc"],
    "vxl":      ["vxl", "vxl agc", "vxlagc", "vxl+"],
    "aspire":   ["aspire", "aspire prosmatec"],
    "ivtec":    ["ivtec", "i vtec", "i-vtec"],
    "ativ":     ["ativ", "ativ x", "ativx"],
    "alpha":    ["alpha", "alpha fwd", "alphafwd"],
    "awd":      ["awd", "all wheel drive", "4x4"],
    "fwd":      ["fwd", "front wheel drive"],
    "essence":  ["essence"]
}

# NEW: Explicit Negative Match Conflicts
TRIM_CONFLICTS: dict[str, list[str]] = {
    "awd":       ["fwd", "alpha"],
    "fwd":       ["awd", "alpha"],
    "alpha":     ["awd", "fwd"],
    "manual":    ["auto", "automatic", "cvt", "ags", "prosmatec"],
    "automatic": ["manual", "mt"],
    "auto":      ["manual", "mt"],
    "hybrid":    ["non-hybrid", "non hybrid"],
    "petrol":    ["diesel", "ev", "electric"],
    "diesel":    ["petrol", "ev", "electric"],
    "essence":   ["trophy"]
}

COMMON_COLORS = ["black", "white", "silver", "grey", "gray", "red", "blue",
                 "green", "maroon", "golden", "beige", "brown", "orange", "purple"]


# ---------------------------------------------------------------------------
# 2025-2026 TAXONOMY EXPANSION — ADDITIVE ONLY
#
# The four maps above are load-bearing for the existing query test suite, so
# the 2025-26 delta is merged in here rather than edited into the literals.
# `_merge_new_only` refuses to overwrite an existing key, which makes this
# block incapable of changing any behaviour that already works — it can only
# teach the normalizer names it did not previously recognise.
#
# Covers the Chinese/EV/hybrid wave that landed in Pakistan 2024-2026:
# Jetour, Omoda, Jaecoo, Deepal, BYD, Zeekr, GWM Tank, Haval hybrids, plus
# the Japanese/Korean refreshes (Sportage L, HR-V e:HEV, Tucson Hybrid,
# Corolla Cross, Fronx).
# ---------------------------------------------------------------------------

def _merge_new_only(target: dict, additions: dict) -> int:
    """
    Insert only keys that are absent from `target`. Returns the count added.

    Deliberately non-destructive: an existing mapping always wins. This makes
    the taxonomy expansion safe to apply blindly without auditing every
    pre-existing key for collisions.
    """
    added = 0
    for k, v in additions.items():
        if k not in target:
            target[k] = v
            added += 1
    return added


_merge_new_only(MAKE_INFERENCE_MAP, {
    # ── Jetour ───────────────────────────────────────────────────────────────
    "dashing":     ("Jetour", "Dashing"),
    "x70plus":     ("Jetour", "X70 Plus"),
    "t2":          ("Jetour", "T2"),
    "t9":          ("Jetour", "T9"),
    # ── Chery premium sub-brands ─────────────────────────────────────────────
    "omoda":       ("Omoda",  "C5"),
    "jaecoo":      ("Jaecoo", "J7"),
    "j5":          ("Jaecoo", "J5"),
    "j6":          ("Jaecoo", "J6"),
    "j7":          ("Jaecoo", "J7"),
    "tiggo":       ("Chery",  "Tiggo 4 Pro"),
    # ── BYD ──────────────────────────────────────────────────────────────────
    "atto":        ("BYD",    "Atto 3"),
    "seal":        ("BYD",    "Seal"),
    "dolphin":     ("BYD",    "Dolphin"),
    "sealion":     ("BYD",    "Sealion 7"),
    "shark":       ("BYD",    "Shark 6"),
    # ── GWM / Haval / Tank ───────────────────────────────────────────────────
    "jolion":      ("Haval",  "Jolion"),
    "tank":        ("GWM",    "Tank 300"),
    # ── Changan / Deepal ─────────────────────────────────────────────────────
    "alsvin":      ("Changan", "Alsvin"),
    "deepal":      ("Changan", "Deepal S07"),
    "oshan":       ("Changan", "Oshan X7"),
    "karvaan":     ("Changan", "Karvaan"),
    # ── Zeekr ────────────────────────────────────────────────────────────────
    "zeekr":       ("Zeekr",  "7X"),
    # ── MG / Proton ──────────────────────────────────────────────────────────
    "gloster":     ("MG",     "Gloster"),
    "cyberster":   ("MG",     "Cyberster"),
    "saga":        ("Proton", "Saga"),
    # ── Japanese / Korean 2025-26 ────────────────────────────────────────────
    "fronx":       ("Suzuki", "Fronx"),
    "raize":       ("Toyota", "Raize"),
    "harrier":     ("Toyota", "Harrier"),
    "rush":        ("Toyota", "Rush"),
    "stonic":      ("Kia",    "Stonic"),
    "seltos":      ("Kia",    "Seltos"),
    "carnival":    ("Kia",    "Carnival"),
    "ioniq":       ("Hyundai", "Ioniq 5"),
})

_merge_new_only(MODEL_ALIAS_MAP, {
    # Jetour
    "t1":          ["t1", "jetour t1"],
    "t2":          ["t2", "jetour t2"],
    "t9":          ["t9", "jetour t9"],
    "dashing":     ["dashing", "jetour dashing", "dashng"],
    "x70plus":     ["x70 plus", "x70plus", "x70-plus", "jetour x70"],
    # Chery sub-brands
    "omodac5":     ["omoda c5", "omoda 5", "omodac5", "omoda-c5"],
    "omoda7":      ["omoda 7", "omoda7", "omoda-7"],
    "omodae5":     ["omoda e5", "omodae5", "omoda-e5"],
    "j5":          ["j5", "jaecoo j5", "jaeco j5"],
    "j6":          ["j6", "jaecoo j6", "jaeco j6"],
    "j7":          ["j7", "jaecoo j7", "jaeco j7", "jacoo j7"],
    "tiggo4":      ["tiggo 4", "tiggo4", "tiggo 4 pro", "tiggo-4"],
    "tiggo7":      ["tiggo 7", "tiggo7", "tiggo 7 pro", "tiggo-7"],
    "tiggo8":      ["tiggo 8", "tiggo8", "tiggo 8 pro", "tiggo-8"],
    # BYD
    "atto2":       ["atto 2", "atto2", "atto-2", "byd atto 2"],
    "sealion7":    ["sealion 7", "sealion7", "sealion-7", "byd sealion 7"],
    "seal":        ["seal", "byd seal"],
    "dolphin":     ["dolphin", "byd dolphin", "dolphn", "dolfin"],
    "shark6":      ["shark 6", "shark6", "byd shark", "byd shark 6"],
    "han":         ["han", "byd han"],
    # GWM / Tank / Haval
    "tank300":     ["tank 300", "tank300", "haval tank 300", "gwm tank 300"],
    "tank500":     ["tank 500", "tank500", "haval tank 500", "gwm tank 500"],
    "h6hev":       ["h6 hev", "h6hev", "haval h6 hev", "h6 hybrid"],
    "jolionhev":   ["jolion hev", "jolionhev", "haval jolion hev", "jolion hybrid"],
    "h7":          ["h7", "haval h7"],
    "jolion":      ["jolion", "jolyon", "joleon", "haval jolion"],
    # Zeekr
    "zeekrx":      ["zeekr x", "zeekrx"],
    "zeekr7x":     ["zeekr 7x", "7x", "zeekr7x"],
    "zeekr009":    ["zeekr 009", "009", "zeekr 9", "zeekr009"],
    # Japanese / Korean 2025-26
    "sportagel":   ["sportage l", "sportagel", "sportage-l", "kia sportage l"],
    "hrvehev":     ["hr-v e:hev", "hrv ehev", "hr v e hev", "hrv hybrid", "hr-v hybrid"],
    "tucsonhybrid":["tucson hybrid", "tucsonhybrid", "tucson hev"],
    "corollacross":["corolla cross", "corollacross", "corolla-cross", "corolla cross hev"],
    "fronx":       ["fronx", "suzuki fronx", "franx"],
    "raize":       ["raize", "toyota raize", "rize"],
    "harrier":     ["harrier", "toyota harrier", "harier"],
})

_merge_new_only(TYPO_CORRECTIONS, {
    # Chinese entrants — the spellings Pakistani buyers actually type
    "jetor":       "jetour",
    "jettur":      "jetour",
    "jeetoor":     "jetour",
    "jetoor":      "jetour",
    "dashng":      "dashing",
    "dashin":      "dashing",
    "omada":       "omoda",
    "omoada":      "omoda",
    "jaeco":       "jaecoo",
    "jacoo":       "jaecoo",
    "jaykoo":      "jaecoo",
    "cheri":       "chery",
    "cherry":      "chery",
    "tigo":        "tiggo",
    "teego":       "tiggo",
    "havl":        "haval",
    "havaal":      "haval",
    "hawwal":      "haval",
    "havel":       "haval",
    "jolyon":      "jolion",
    "joleon":      "jolion",
    "joliyon":     "jolion",
    "shangan":     "changan",
    "shengan":     "changan",
    "chnagan":     "changan",
    "deepaal":     "deepal",
    "bwaidi":      "byd",
    "dolphn":      "dolphin",
    "dolfin":      "dolphin",
    "zeeker":      "zeekr",
    "zekr":        "zeekr",
    "emji":        "mg",
    "emjee":       "mg",
    "prton":       "proton",
    "protn":       "proton",
    # Japanese / Korean refreshes
    "franx":       "fronx",
    "rize":        "raize",
    "harier":      "harrier",
    "sportej":     "sportage",
    "sportech":    "sportage",
    "tuscon":      "tucson",
    "tucsan":      "tucson",
    "tuqsan":      "tucson",
    "elentra":     "elantra",
    "alantra":     "elantra",
    "pikanto":     "picanto",
    "peekanto":    "picanto",
    "stonik":      "stonic",
    "swfit":       "swift",
    "sweft":       "swift",
    "jimni":       "jimny",
    "jamni":       "jimny",
    "prious":      "prius",
    "paryus":      "prius",
    "akua":        "aqua",
    "wits":        "vitz",
    "vits":        "vitz",
    "fortunr":     "fortuner",
    "landcruiser": "land cruiser",
})

_merge_new_only(TRIM_ALIASES, {
    # Powertrain / variant suffixes used by the 2025-26 wave
    "hev":       ["hev", "hybrid", "e:hev", "ehev", "e-hev"],
    "phev":      ["phev", "plug in hybrid", "plug-in hybrid", "plugin hybrid"],
    "ev":        ["ev", "electric", "bev", "full electric"],
    "shs":       ["shs", "super hybrid", "super hybrid system"],
    "comfort":   ["comfort", "comfort rwd", "comfortrwd"],
    "premium":   ["premium", "premium awd", "premiumawd"],
    "advanced":  ["advanced", "advance"],
    "deluxe":    ["deluxe", "dlx"],
    "conqueror": ["conqueror", "conquerer"],
    "luxury":    ["luxury", "lux"],
    "dynamic":   ["dynamic"],
    "1.5t":      ["1.5t", "15t", "1.5 turbo", "1.5l turbo"],
    "2.0t":      ["2.0t", "20t", "2.0 turbo", "2.0l turbo"],
    "1.6t":      ["1.6t", "16t", "1.6 turbo"],
    "alpha":     ["alpha", "alpha fwd", "alphafwd", "hev alpha"],
    "long range":["long range", "longrange", "lr"],
})


# ---------------------------------------------------------------------------
# UTILITY
# ---------------------------------------------------------------------------

def normalize_make_model(make: str, model: str) -> tuple[str, str]:
    make_clean = (make or "").strip().lower()
    model_clean = (model or "").strip().lower()
    model_corrected = TYPO_CORRECTIONS.get(model_clean, model_clean)

    # Case 1: make itself is a known model name (user typed model as make)
    if make_clean in MAKE_INFERENCE_MAP:
        inferred_make, inferred_model = MAKE_INFERENCE_MAP[make_clean]
        if not model_corrected or model_corrected == make_clean:
            return inferred_make, inferred_model
        else:
            return inferred_make, model_corrected.title()

    # Case 2: make is empty/unknown, but model is a known standalone name
    if not make_clean and model_corrected in MAKE_INFERENCE_MAP:
        inferred_make, inferred_model = MAKE_INFERENCE_MAP[model_corrected]
        return inferred_make, inferred_model

    return (make or "").strip(), model_corrected.title() if model_corrected else ""


def normalize_city(city: str) -> str:
    if not city:
        return ""
    city_key = city.strip().lower()
    return CITY_ALIAS_MAP.get(city_key, city.strip().title())


# ---------------------------------------------------------------------------
# CLEANING HELPERS
# ---------------------------------------------------------------------------

def _clean_price(raw_price) -> int:
    if raw_price is None or raw_price == "":
        return 0
    if isinstance(raw_price, (int, float)):
        return int(raw_price)

    price_str = str(raw_price).strip().lower()
    if not price_str or "call for price" in price_str or "call" in price_str:
        return 0

    multiplier = 1
    if re.search(r'\b(lac|lacs|lakh|lakhs)\b', price_str):
        multiplier = 100_000
    elif re.search(r'\b(crore|crores)\b', price_str):
        multiplier = 10_000_000

    clean_num_str = re.sub(r'[^\d.]', '', price_str)
    if not clean_num_str or clean_num_str == '.' or clean_num_str.count('.') > 1:
        return 0

    try:
        final_price = int(float(clean_num_str) * multiplier)
        return final_price
    except ValueError:
        return 0


def _clean_int(raw_value) -> int:
    if isinstance(raw_value, int):
        return raw_value
    if not isinstance(raw_value, str):
        return 0
    text = raw_value.strip().replace(",", "")
    digits = re.sub(r"[^\d]", "", text)
    if digits:
        try:
            return int(digits)
        except ValueError:
            return 0
    return 0


# ---------------------------------------------------------------------------
# IDENTITY MATCHER
# ---------------------------------------------------------------------------

def _normalize_str(s: str) -> str:
    return s.lower().replace(" ", "").replace("-", "").replace(".", "").replace("_", "")

def _resolve_model_aliases(model_clean: str) -> list[str]:
    normalized = _normalize_str(model_clean)
    for canonical, aliases in MODEL_ALIAS_MAP.items():
        alias_normalized = [_normalize_str(a) for a in aliases]
        if normalized in alias_normalized:
            return alias_normalized
    return [normalized]

def _calculate_identity_score(requested_make: str, requested_model: str, title: str) -> float:
    if not requested_model:
        return 1.0

    model_clean = _normalize_str(requested_model)
    if requested_make:
        make_clean = _normalize_str(requested_make)
        model_clean = model_clean.replace(make_clean, "").strip()

    if not model_clean:
        return 1.0

    target_clean = _normalize_str(title)
    aliases = _resolve_model_aliases(model_clean)

    for alias in aliases:
        if alias in target_clean:
            return 1.0

    # Token-level intersection for compound model names
    model_tokens = set(requested_model.lower().replace("-", " ").split())
    title_tokens = set(title.lower().replace("-", " ").split())
    if model_tokens:
        overlap = model_tokens & title_tokens
        token_ratio = len(overlap) / len(model_tokens)
        if token_ratio >= 0.75:
            return max(0.85, token_ratio)

    best_ratio = 0.0
    title_words = title.lower().replace("-", " ").replace(".", " ").replace("_", " ").split()

    for alias in aliases:
        for word in title_words:
            if abs(len(word) - len(alias)) <= 2:
                ratio = SequenceMatcher(None, alias, word).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio

    return round(best_ratio, 4)


# ---------------------------------------------------------------------------
# HEURISTIC SCORING ENGINE
# ---------------------------------------------------------------------------

def _calculate_relevance_score(
    car: CarListing,
    requested_make: str,
    requested_model: str,
    requested_city: str,
    requested_budget: int,
    requested_color: str,
    clean_price: int,
    clean_year: int,
    clean_mileage: int,
    requested_trim: str = None,
    min_budget: int = 0,
    min_year: int = 0,
    max_year: int = 0,
    debug: bool = False,
) -> float:
    
    clean_title = re.sub(r'\b\d{7,}\b', '', car.title).strip()
    title_lower = clean_title.lower()

    def veto(reason: str) -> float:
        if debug:
            print(f"  [VETO] '{clean_title[:50]}' — {reason}")
        return 0.0

    # 1: Identity
    identity_score = _calculate_identity_score(requested_make, requested_model, clean_title)
    if identity_score < 0.75:
        return veto(f"Identity too low ({identity_score:.2f}) for model='{requested_model}'")

    # 2: Make 
    if requested_make:
        req_make_lower = requested_make.lower()
        acceptable_makes = MAKE_VETO_ALIASES.get(req_make_lower, [req_make_lower])
        if not any(m in title_lower for m in acceptable_makes):
            return veto(f"Make '{requested_make}' not found in title")

    # 3: Budget
    # Auto-calculate 70% floor when caller passes min_budget=0 but budget is known.
    # Prevents e.g. a PKR 2M Alto surfacing for a PKR 5M Corolla search.
    eff_min_budget = min_budget
    if eff_min_budget == 0 and requested_budget and requested_budget > 0:
        eff_min_budget = int(requested_budget * 0.70)

    if clean_price > 0:
        if eff_min_budget > 0 and clean_price < eff_min_budget:
            return veto(
                f"Listing price ({clean_price:,} PKR) is below 70% budget floor "
                f"({eff_min_budget:,} PKR = 70% of {requested_budget:,} PKR)"
            )

        if requested_budget and requested_budget > 0:
            hard_ceiling = int(requested_budget * 1.05)
            if clean_price > hard_ceiling:
                return veto(f"Listing price ({clean_price:,} PKR) exceeds max budget ({requested_budget:,} PKR)")

    # 4: Color Conflict
    # Three-tier check (in priority order):
    #
    #   Tier 1 — car.color field (structured, highest confidence)
    #     Scrapers on PakWheels and OLX extract a dedicated color attribute.
    #     If the field is populated and doesn't match requested_color, veto
    #     immediately — no need to scan text at all.
    #
    #   Tier 2 — Title scan (unstructured, second highest confidence)
    #     Sellers often write the color in the title. If a conflicting color
    #     word is found, veto.
    #
    #   Tier 3 — Description scan (unstructured, catches what title misses)
    #     Sellers sometimes only mention color in the listing body, e.g.
    #     "pearl white exterior, black interior". Scan description/about
    #     for conflicting color words. Only runs if tiers 1 and 2 didn't veto.
    #
    # Safe guards:
    #   - CITY_COLOR_EXCEPTIONS: prevents "Blue Area Islamabad" triggering
    #     a blue color conflict (not implemented in normalizer.py but
    #     location words in titles are rare — description scan is lower-risk).
    #   - Short description words: only check colors that appear as whole words
    #     in the description to avoid "silver" matching "silvered" or similar.
    if requested_color:
        req_color = requested_color.lower().strip()

        # ── Tier 1: structured car.color field ──────────────────────────────
        car_color_field = (getattr(car, "color", None) or "").lower().strip()
        if car_color_field:
            # Normalise common variants: "pearl white" → "white", "metallic grey" → "grey"
            for color in COMMON_COLORS:
                if color in car_color_field:
                    car_color_field = color
                    break
            if car_color_field and car_color_field != req_color:
                return veto(
                    f"Color field mismatch: car is '{car_color_field}', "
                    f"user wants '{req_color}'"
                )

        # ── Tier 2: title scan ───────────────────────────────────────────────
        for color in COMMON_COLORS:
            if color == req_color:
                continue
            if color in title_lower:
                return veto(
                    f"Title contains '{color}' but user wants '{req_color}'"
                )

        # ── Tier 3: description / about scan ────────────────────────────────
        raw_desc  = (getattr(car, "description", None) or
                     getattr(car, "about", None) or "")
        desc_lower = raw_desc.lower()
        if desc_lower:
            for color in COMMON_COLORS:
                if color == req_color:
                    continue
                # Word-boundary match to avoid "silver" inside "silverware" etc.
                if re.search(rf'\b{re.escape(color)}\b', desc_lower):
                    return veto(
                        f"Description contains '{color}' but user wants '{req_color}'"
                    )

    budget_score = 10.0 if clean_price == 0 else 40.0

    # 5: City — HARD VETO with twin/nearby-city amnesty
    #
    # Score breakdown:
    #   30.0 pts — exact city match in car.city or listing title
    #   20.0 pts — twin/nearby city match (Islamabad ↔ Rawalpindi, etc.)
    #   VETO    — neither the requested city nor any of its recognised
    #             twin/nearby cities appear in car.city or the title.
    #
    # Rationale for the veto (changed from soft scoring):
    # A buyer who names a city is stating a hard logistics constraint —
    # nobody in Islamabad drives to Karachi to view a Corolla. Under the old
    # soft-scoring model a no-match listing merely lost 30 points, which was
    # routinely out-earned by budget (40) + trim (25) + freshness (15), so
    # out-of-city cars still surfaced in the top results on thin queries.
    #
    # The safety valve is NEARBY_CITY_MAP: the genuine cross-city buying
    # corridors (Islamabad↔Rawalpindi, Lahore↔Sheikhupura/Kasur/Gujranwala,
    # Karachi↔Hyderabad, Peshawar↔Nowshera/Mardan, …) are all whitelisted and
    # still score 20.0, so legitimate twin-city inventory is preserved. Only
    # genuinely unreachable listings are dropped.
    #
    # NOTE: the veto only fires when the caller actually supplied a city.
    # An empty/None requested_city is treated exactly as before (no veto).
    #
    # ORDERING FIX: exact matches are now resolved across ALL requested
    # cities BEFORE any twin-city fallback is considered. The previous
    # implementation broke out of the loop on the first twin hit, so a query
    # for "Islamabad and Rawalpindi" against a Rawalpindi listing scored 20.0
    # (twin of Islamabad) instead of the correct 30.0 (exact match on
    # Rawalpindi, the second entry in the list).
    car_city_lower = (car.city or "").lower().strip()
    req_city_str   = (requested_city or "").lower().strip()

    if req_city_str:
        req_cities = [c.strip() for c in re.split(r',|\band\b', req_city_str) if c.strip()]

        # Pass 1 — exact match against every requested city
        exact_match = any(
            rc in car_city_lower or rc in title_lower
            for rc in req_cities
        )

        # Pass 2 — twin/nearby amnesty, only if no exact match anywhere
        twin_match = False
        matched_twin = None
        if not exact_match:
            for rc in req_cities:
                for nb in NEARBY_CITY_MAP.get(rc, set()):
                    if nb in car_city_lower or nb in title_lower:
                        twin_match = True
                        matched_twin = nb
                        break
                if twin_match:
                    break

        if exact_match:
            city_score = 30.0
        elif twin_match:
            city_score = 20.0   # Nearby city — kept but ranked below exact matches
            if debug:
                print(
                    f"  [TWIN-CITY] '{clean_title[:45]}' — nearby city "
                    f"'{matched_twin}' accepted for '{req_city_str}', found '{car.city}'"
                )
        else:
            # HARD VETO — outside the requested city and outside every
            # recognised twin/nearby corridor.
            return veto(
                f"City mismatch: listing in '{car.city}' does not match requested "
                f"city '{requested_city}' or its twin cities"
            )
    else:
        city_score = 30.0 if car_city_lower else 15.0

    # --- 6: SMART TRIM ENFORCEMENT (with description scan + priority ranking) ---
    trim_score = 0.0
    if requested_trim:
        req_trim_clean = requested_trim.lower().replace("-", "")
        title_clean    = title_lower.replace("-", "")
        GENERIC_SKIP_WORDS = {"automatic", "manual", "car", "sedan", "petrol", "hybrid"}
        trim_keywords  = [kw for kw in req_trim_clean.split() if kw not in GENERIC_SKIP_WORDS]

        # Build secondary scan text from description/about fields (lazy seller protection)
        raw_desc   = getattr(car, "description", None) or getattr(car, "about", None) or ""
        desc_lower = raw_desc.lower().replace("-", "")

        # Pass 1: Scan TITLE for trim match
        trim_in_title = False
        for keyword in trim_keywords:
            valid_forms = TRIM_ALIASES.get(keyword, [keyword])
            valid_nohyph = [f.replace("-", "") for f in valid_forms]
            if any(form in title_clean for form in valid_nohyph):
                trim_in_title = True
                break

        # Pass 2: Scan DESCRIPTION for trim match (only if not found in title)
        trim_in_desc = False
        if not trim_in_title and desc_lower:
            for keyword in trim_keywords:
                valid_forms = TRIM_ALIASES.get(keyword, [keyword])
                valid_nohyph = [f.replace("-", "") for f in valid_forms]
                if any(form in desc_lower for form in valid_nohyph):
                    trim_in_desc = True
                    break

        if trim_in_title:
            trim_score = 25.0   # Title match: highest confidence
        elif trim_in_desc:
            trim_score = 15.0   # Description match: lazy seller, still valid
        else:
            # Neither title nor description — check for hard conflicts before keeping
            for keyword in trim_keywords:
                conflicts = TRIM_CONFLICTS.get(keyword, [])
                for conflict in conflicts:
                    conflict_nohyph = conflict.replace("-", "")
                    if conflict_nohyph in title_clean or conflict_nohyph in desc_lower:
                        return veto(
                            f"Conflicting trim. User wanted '{requested_trim}', "
                            f"found '{conflict}'"
                        )
            # No conflict found → assume lazy seller. Car kept, trim_score = 0.

    # 7: Year Bounds
    if clean_year > 0:
        if min_year > 0 and clean_year < min_year:
            return veto(f"Too old. Car is {clean_year}, user requested min {min_year}.")
        if max_year > 0 and clean_year > max_year:
            return veto(f"Too new. Car is {clean_year}, user requested max {max_year}.")

    # 8: Freshness — graduated decay, NOT a hard cliff at 14 days
    #
    # Old behaviour: hard veto at 14 days → killed 15+ Corolla Grande listings
    # in a single Islamabad query (59, 68, 72, 76, 79, 89, 92, 97, 104, 130 days).
    # For niche queries (specific trim + city), inventory is thin — a 60-day-old
    # listing is far better than returning 0 results.
    #
    # Current behaviour:
    #   0–14 days:  15.0 pts (fresh — full score)
    #   15–45 days: linear decay 15.0 → 5.0 pts (moderately fresh)
    #   46–90 days:  5.0 → 0.0 pts (stale, but kept — ranked below fresh listings)
    #   90+ days:   hard veto — listing is too old to be credible
    #   unknown:    scored low, never vetoed (see below)
    #
    # ORDER MATTERS — 2026-08-16 fix.
    # This block used to open with `if car.age_days > 998 or car.age_days == 0`
    # and award a neutral 10.0 for "age unknown". Both halves were wrong:
    #
    #   > 998   — 998 was meant to catch the old 999 "unknown" sentinel, but it
    #             also catches every real age above it. A Gari.pk Suzuki Every
    #             posted Jul 19, 2022 is 1489 days old, sailed past this branch
    #             as "unknown", scored +10, and never reached the veto below.
    #             Meanwhile a 969-day listing from Dec 2023 WAS vetoed. Ads that
    #             crossed ~2.7 years scored better than ads half their age.
    #
    #   == 0    — conflated "posted today" with "scraper never set the field".
    #             Genuinely fresh listings lost 5 pts; Drive.pk / AutoDeals /
    #             FameWheels listings, which set no date at all, gained 10.
    #
    # The staleness veto now runs FIRST against any known age, and "unknown" is
    # the explicit UNKNOWN_AGE sentinel (negative, so it cannot collide with a
    # real age). See scrapers/date_utils.py.
    if not is_unknown_age(car.age_days):
        if car.age_days > 90:
            return veto(f"Stale listing. Posted {car.age_days} days ago (limit: 90).")
        if car.age_days <= 14:
            age_score = 15.0                                # fresh — full score
        elif car.age_days <= 45:
            # Linear decay: 15.0 at day 14 → 5.0 at day 45
            age_score = 15.0 - ((car.age_days - 14) / 31) * 10.0
        else:
            # Linear decay: 5.0 at day 45 → 0.0 at day 90
            age_score = 5.0 - ((car.age_days - 45) / 45) * 5.0
            age_score = max(0.0, age_score)
    else:
        # Age unknown. Not a veto — Drive.pk, AutoDeals and FameWheels publish
        # no usable date, and vetoing them would empty those buckets entirely.
        # But unknown never outranks a confirmed date: the best an undated
        # listing can score is below the worst dated one that survives.
        #
        # On platforms that always publish a date, unknown means OUR parser
        # broke on that card. Those score zero here rather than a token amount —
        # an unverifiable Gari.pk listing has no business ranking at all when
        # dated Gari.pk listings exist alongside it.
        platform_key = (car.platform or "").lower()
        if platform_key in DATE_MANDATORY_PLATFORMS:
            age_score = 0.0
        else:
            age_score = 3.0

    # 9: Quality
    year_score = 7.5 if clean_year > 0 else 0.0
    mileage_score = 7.5 if clean_mileage > 0 else 0.0
    quality_score = year_score + mileage_score

    # TOTAL CALCULATION
    raw_total = budget_score + city_score + age_score + quality_score + trim_score
    total_score = raw_total * identity_score

    if debug:
        print(f"  [SCORE] '{car.title[:45]}' | id={identity_score:.2f} score={total_score:.2f}")

    return round(total_score, 2)


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT
# ---------------------------------------------------------------------------

def normalize_listings(
    raw_listings: list[CarListing],
    requested_make: str = None,
    requested_model: str = None,
    requested_city: str = None,
    requested_budget: int = None,
    requested_color: str = None,
    requested_trim: str = None,
    min_budget: int = 0,
    min_year: int = 0,
    max_year: int = 0,
    debug: bool = False,
) -> tuple[list[CarListing], bool]:
    
    corrected_make, corrected_model = normalize_make_model(requested_make or "", requested_model or "")
    corrected_city = normalize_city(requested_city or "")

    scored_map: dict[tuple, dict] = {}
    veto_count = 0

    for car in raw_listings:
        clean_price = _clean_price(car.price)
        clean_year = _clean_int(car.year)
        clean_mileage = _clean_int(car.mileage)

        score = _calculate_relevance_score(
            car=car,
            requested_make=corrected_make,
            requested_model=corrected_model,
            requested_city=corrected_city,
            requested_budget=requested_budget,
            requested_color=requested_color,
            clean_price=clean_price,
            clean_year=clean_year,
            clean_mileage=clean_mileage,
            requested_trim=requested_trim,
            min_budget=min_budget,
            min_year=min_year,
            max_year=max_year,
            debug=debug,
        )

        if score == 0.0:
            veto_count += 1
            continue

        display_city = (car.city or "").strip()
        garbage_strings = ["automatic", "manual", "unregistered", "petrol", "hybrid", "cng", "diesel", "electric"]
        if display_city.lower() in garbage_strings:
            req_cities = [c.strip() for c in re.split(r',|\band\b', (corrected_city or "").lower()) if c.strip()]
            for rc in req_cities:
                if rc in car.title.lower():
                    display_city = rc.title()
                    break

        dedup_key = (car.title.lower().strip(), clean_year, clean_mileage)

        if dedup_key in scored_map:
            if score > scored_map[dedup_key]["score"]:
                scored_map[dedup_key] = {
                    "car": car, "score": score, "price": clean_price,
                    "year": clean_year, "mileage": clean_mileage, "display_city": display_city,
                }
        else:
            scored_map[dedup_key] = {
                "car": car, "score": score, "price": clean_price,
                "year": clean_year, "mileage": clean_mileage, "display_city": display_city,
            }

    qualified_count = len(scored_map)
    if qualified_count == 0:
        return [], True

    all_scored_cars = list(scored_map.values())
    all_scored_cars.sort(key=lambda x: x["score"], reverse=True)

    # Platform buckets for the cross-platform mix.
    #
    # 'Other' is a catch-all and must exist. This loop used to `continue` on any
    # platform without its own bucket, which silently threw away listings that
    # had already passed every veto and been scored. FameWheels was the live
    # casualty: its platform tag is "Famewheels", it matched no bucket key, and
    # so every FameWheels listing was discarded at selection time. That stayed
    # invisible only because the FameWheels scraper was itself returning zero
    # rows; the moment it was fixed, its listings still never reached the user.
    # recommend_normalizer.py already had an "Other" bucket — this brings the
    # search pipeline in line with it.
    buckets = {
        'PakWheels': [],
        'OLX':       [],
        'Drive.pk':  [],
        'Gari.pk':   [],
        'AutoDeals': [],
        'Other':     [],
    }

    for item in all_scored_cars:
        plat = item['car'].platform
        if 'Gari' in plat or 'Wise' in plat:
            plat_key = 'Gari.pk'
        elif plat in buckets:
            plat_key = plat
        else:
            plat_key = 'Other'
        buckets[plat_key].append(item)

    pw_selected   = buckets['PakWheels'][:5]
    olx_selected  = buckets['OLX'][:4]
    drive_selected = buckets['Drive.pk'][:3]

    # Gari.pk / WiseWheels / AutoDeals / FameWheels and anything new share the
    # remaining slots, ranked purely on score.
    gari_auto_pool = buckets['Gari.pk'] + buckets['AutoDeals'] + buckets['Other']
    gari_auto_pool.sort(key=lambda x: x["score"], reverse=True)
    gari_auto_selected = gari_auto_pool[:3]

    final_selection = []
    final_selection.extend(pw_selected)
    final_selection.extend(olx_selected)
    final_selection.extend(drive_selected)
    final_selection.extend(gari_auto_selected)

    shortfall = 15 - len(final_selection)
    if shortfall > 0:
        backup_pool = buckets['PakWheels'][len(pw_selected):] + buckets['OLX'][len(olx_selected):]
        backup_pool.sort(key=lambda x: x["score"], reverse=True)
        backfill_selected = backup_pool[:shortfall]
        final_selection.extend(backfill_selected)

    final_selection.sort(key=lambda x: x["score"], reverse=True)
    top_15_data = final_selection[:15]

    final_list: list[CarListing] = []
    for data in top_15_data:
        car = data["car"]
        final_list.append(CarListing(
            id=car.id,
            title=car.title.strip(),
            price=data["price"],
            mileage=data["mileage"],
            city=data["display_city"],
            year=data["year"],
            listing_url=car.listing_url,
            image_url=car.image_url,
            platform=car.platform,
            age_days=car.age_days,
            scraped_at=car.scraped_at,
        ))

    return final_list, len(final_list) == 0