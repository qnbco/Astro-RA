import warnings
import logging
from collections import defaultdict
from datetime import date

import streamlit as st

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from kerykeion import AstrologicalSubject

st.set_page_config(page_title="Astro RA", page_icon="🔭", layout="centered")

# ── Reference data ─────────────────────────────────────────────

SIGN_MAP = {
    "Ari": "Aries", "Tau": "Taurus", "Gem": "Gemini", "Can": "Cancer",
    "Leo": "Leo", "Vir": "Virgo", "Lib": "Libra", "Sco": "Scorpio",
    "Sag": "Sagittarius", "Cap": "Capricorn", "Aqu": "Aquarius", "Pis": "Pisces",
}
ELEMENTS = {
    "Fire": ["Aries", "Leo", "Sagittarius"],
    "Earth": ["Taurus", "Virgo", "Capricorn"],
    "Air": ["Gemini", "Libra", "Aquarius"],
    "Water": ["Cancer", "Scorpio", "Pisces"],
}
MODES = {
    "Cardinal": ["Aries", "Cancer", "Libra", "Capricorn"],
    "Fixed": ["Taurus", "Leo", "Scorpio", "Aquarius"],
    "Mutable": ["Gemini", "Virgo", "Sagittarius", "Pisces"],
}
POSITIVE = ["Aries", "Gemini", "Leo", "Libra", "Sagittarius", "Aquarius"]
MODERN_RULERS = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury", "Cancer": "Moon",
    "Leo": "Sun", "Virgo": "Mercury", "Libra": "Venus", "Scorpio": "Pluto",
    "Sagittarius": "Jupiter", "Capricorn": "Saturn", "Aquarius": "Uranus", "Pisces": "Neptune",
}
DIGNITY = {
    "Sun":     {"Domicile": ["Leo"], "Exaltation": ["Aries"], "Detriment": ["Aquarius"], "Fall": ["Libra"]},
    "Moon":    {"Domicile": ["Cancer"], "Exaltation": ["Taurus"], "Detriment": ["Capricorn"], "Fall": ["Scorpio"]},
    "Mercury": {"Domicile": ["Gemini", "Virgo"], "Exaltation": ["Virgo"], "Detriment": ["Sagittarius", "Pisces"], "Fall": ["Pisces"]},
    "Venus":   {"Domicile": ["Taurus", "Libra"], "Exaltation": ["Pisces"], "Detriment": ["Aries", "Scorpio"], "Fall": ["Virgo"]},
    "Mars":    {"Domicile": ["Aries", "Scorpio"], "Exaltation": ["Capricorn"], "Detriment": ["Taurus", "Libra"], "Fall": ["Cancer"]},
    "Jupiter": {"Domicile": ["Sagittarius", "Pisces"], "Exaltation": ["Cancer"], "Detriment": ["Gemini", "Virgo"], "Fall": ["Capricorn"]},
    "Saturn":  {"Domicile": ["Capricorn", "Aquarius"], "Exaltation": ["Libra"], "Detriment": ["Cancer", "Leo"], "Fall": ["Aries"]},
}
TRADITIONAL = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]

# Mutual reception: FAS definition = domicile only, 7 traditional planets.
# Set to True to also count reception by exaltation.
MR_INCLUDE_EXALTATION = False

# (name, exact angle, orb)
ASPECTS = [
    ("Conjunction", 0, 8), ("Opposition", 180, 8), ("Trine", 120, 8), ("Square", 90, 8),
    ("Sextile", 60, 4),
    ("Quincunx", 150, 2), ("Semisquare", 45, 2), ("Sesquiquadrate", 135, 2), ("Semisextile", 30, 2),
]
ASP_DEG = {n: d for n, d, o in ASPECTS}

# ── Helpers ────────────────────────────────────────────────────

def full_sign(s):
    return SIGN_MAP.get(s, s)

def element_of(sign):
    s = full_sign(sign)
    return next((e for e, ss in ELEMENTS.items() if s in ss), "?")

def mode_of(sign):
    s = full_sign(sign)
    return next((m for m, ss in MODES.items() if s in ss), "?")

def polarity_of(sign):
    return "+" if full_sign(sign) in POSITIVE else "-"

def fmt_deg(position):
    total = int(position * 60)  # truncate, as chart software does
    return f"{total // 60:02d}°{total % 60:02d}'"

def fmt_orb(orb, direction):
    total = round(orb * 60)
    return f"{total // 60:02d}°{direction}{total % 60:02d}'"

def house_num(house_str):
    order = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth",
             "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth"]
    h = str(house_str).replace("_House", "").replace("House", "").strip().lower()
    for i, name in enumerate(order, 1):
        if name.lower() == h:
            return i
    return 0

def separation(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d

def direction(a, b, angle):
    """'A' applying / 'S' separating, from planetary speeds."""
    if getattr(a, "speed", None) is None or getattr(b, "speed", None) is None:
        return ""
    def orb_at(t):
        return abs(separation(a.abs_pos + a.speed * t, b.abs_pos + b.speed * t) - angle)
    return "A" if orb_at(0.01) < orb_at(0) else "S"

def find_aspects(points):
    """points: list of (label, obj). Returns list of dicts."""
    found = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            (n1, o1), (n2, o2) = points[i], points[j]
            sep = separation(o1.abs_pos, o2.abs_pos)
            for name, angle, limit in ASPECTS:
                orb = abs(sep - angle)
                if orb <= limit:
                    found.append({"p1": n1, "p2": n2, "aspect": name, "orb": orb,
                                  "dir": direction(o1, o2, angle)})
    return found

def names_list(items):
    return f"{', '.join(items)} ({len(items)})" if items else "None (0)"

# ── Aspect patterns ────────────────────────────────────────────

def detect_patterns(points, aspects):
    amap = defaultdict(dict)
    for a in aspects:
        amap[a["p1"]][a["p2"]] = a["aspect"]
        amap[a["p2"]][a["p1"]] = a["aspect"]
    labels = [n for n, _ in points]
    obj = dict(points)
    is_ = lambda x, y, asp: amap[x].get(y) == asp
    results = []

    # Stellium: 3+ bodies in one sign
    groups = defaultdict(list)
    for n, o in points:
        groups[full_sign(o.sign)].append(n)
    for sign, members in groups.items():
        if len(members) >= 3:
            houses = sorted({house_num(obj[m].house) for m in members})
            hs = ", ".join(f"{h}H" for h in houses)
            results.append(f"Stellium in {sign} ({hs}): {', '.join(members)}")

    # Grand Trine
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            for k in range(j + 1, len(labels)):
                a, b, c = labels[i], labels[j], labels[k]
                if is_(a, b, "Trine") and is_(b, c, "Trine") and is_(a, c, "Trine"):
                    results.append(f"Grand Trine: {a}, {b}, {c}")

    oppositions = [(a["p1"], a["p2"]) for a in aspects if a["aspect"] == "Opposition"]

    # Grand Cross (deduplicated)
    gc_sets = []
    for x in range(len(oppositions)):
        for y in range(x + 1, len(oppositions)):
            a1, a2 = oppositions[x]
            b1, b2 = oppositions[y]
            if len({a1, a2, b1, b2}) < 4:
                continue
            if all(is_(p, q, "Square") for p in (a1, a2) for q in (b1, b2)):
                key = frozenset([a1, a2, b1, b2])
                if key not in gc_sets:
                    gc_sets.append(key)
                    results.append(f"Grand Cross: {a1} opposition {a2}, {b1} opposition {b2}")

    # T-Square (skipped if already part of a Grand Cross)
    for p1, p2 in oppositions:
        for apex in labels:
            if apex in (p1, p2):
                continue
            if is_(p1, apex, "Square") and is_(p2, apex, "Square"):
                if any({p1, p2, apex} <= g for g in gc_sets):
                    continue
                results.append(f"T-Square: apex {apex}, {p1} opposition {p2}")

    # Minor Grand Trine: two bodies in trine, both sextile an apex
    # Yod: two bodies in sextile, both quincunx an apex
    for a in aspects:
        p1, p2 = a["p1"], a["p2"]
        for apex in labels:
            if apex in (p1, p2):
                continue
            if a["aspect"] == "Trine" and is_(p1, apex, "Sextile") and is_(p2, apex, "Sextile"):
                results.append(f"Minor Grand Trine: apex {apex}, {p1} trine {p2}")
            if a["aspect"] == "Sextile" and is_(p1, apex, "Quincunx") and is_(p2, apex, "Quincunx"):
                results.append(f"Yod: apex {apex}, {p1} sextile {p2}")

    return list(dict.fromkeys(results))

# ── Lunation phase ─────────────────────────────────────────────

def lunation(sun_pos, moon_pos):
    diff = (moon_pos - sun_pos) % 360
    phases = ["New Moon", "Crescent", "First Quarter", "Gibbous",
              "Full Moon", "Disseminating", "Last Quarter", "Balsamic"]
    return phases[int(diff // 45)], diff

# ── Worksheet builder ──────────────────────────────────────────

def build_worksheet(s, name, born_str):
    planets = [s.sun, s.moon, s.mercury, s.venus, s.mars, s.jupiter,
               s.saturn, s.uranus, s.neptune, s.pluto]
    bodies = [(p.name, p) for p in planets] + [("Chiron", s.chiron)]
    angles = [("ASC", s.first_house), ("DSC", s.seventh_house),
              ("MC", s.tenth_house), ("IC", s.fourth_house)]
    L = []

    L.append(f"# {name}")
    L.append(f"{born_str}  \nPlacidus houses, tropical zodiac\n")

    # Positions
    L.append("## Chart Data\n")
    L.append("| Body | Sign | Position | House | Pol | Element | Mode | Rx |")
    L.append("|---|---|---|---|---|---|---|---|")
    for n, p in bodies:
        rx = "℞" if p.retrograde else ""
        pol = polarity_of(p.sign) if n != "Chiron" else ""
        el = element_of(p.sign) if n != "Chiron" else ""
        mo = mode_of(p.sign) if n != "Chiron" else ""
        L.append(f"| {n} | {full_sign(p.sign)} | {fmt_deg(p.position)} | {house_num(p.house)} | {pol} | {el} | {mo} | {rx} |")
    nn = s.true_node
    L.append(f"| North Node | {full_sign(nn.sign)} | {fmt_deg(nn.position)} | {house_num(nn.house)} |  |  |  |  |")
    for n, h in angles:
        L.append(f"| {n} | {full_sign(h.sign)} | {fmt_deg(h.position)} |  | {polarity_of(h.sign)} | {element_of(h.sign)} | {mode_of(h.sign)} |  |")
    asc_sign = full_sign(s.first_house.sign)
    L.append(f"\nChart ruler: {MODERN_RULERS.get(asc_sign, '?')} (ASC {asc_sign})\n")

    # Balance: 7 planets + ASC + MC
    core = [(p.name, p.sign) for p in planets[:7]] + [("ASC", s.first_house.sign), ("MC", s.tenth_house.sign)]
    pos_ = [n for n, sg in core if polarity_of(sg) == "+"]
    neg_ = [n for n, sg in core if polarity_of(sg) == "-"]
    L.append("## Polarity, Element & Mode Balance\n")
    L.append("### Polarity Balance\n")
    L.append(f"Positive: {names_list(pos_)}  \nNegative: {names_list(neg_)}\n")
    L.append("### Element Balance\n")
    L.append("  \n".join(f"{e}: {names_list([n for n, sg in core if element_of(sg) == e])}" for e in ELEMENTS) + "\n")
    L.append("### Mode Balance\n")
    L.append("  \n".join(f"{m}: {names_list([n for n, sg in core if mode_of(sg) == m])}" for m in MODES) + "\n")

    # Angular planets
    L.append("## Angular Planets\n")
    angular = []
    for n, p in bodies:
        for an, h in angles:
            orb = separation(p.abs_pos, h.abs_pos)
            if orb <= 8:
                angular.append(f"- {n} conjunct {an} ({fmt_orb(orb, '')})")
    L.append("\n".join(angular) if angular else "No angular planets.")
    L.append("")

    # Dignity & debility
    L.append("## Planets in Dignity & Debility\n")
    dig = []
    for p in planets[:7]:
        sg = full_sign(p.sign)
        for cat, signs in DIGNITY[p.name].items():
            if sg in signs:
                dig.append(f"- {p.name} in {sg} ({cat})")
    L.append("\n".join(dig) if dig else "No planets in dignity or debility.")
    L.append("")

    # Retrograde
    L.append("## Retrograde Planets\n")
    rx = [f"- {n} ℞ in {full_sign(p.sign)} {fmt_deg(p.position)} ({house_num(p.house)}H)" for n, p in bodies if p.retrograde]
    L.append("\n".join(rx) if rx else "No retrograde planets.")
    L.append("")

    # Mutual reception
    L.append("## Mutual Reception\n")
    trad = [(p.name, full_sign(p.sign)) for p in planets[:7]]
    def receives(planet, sign):
        signs = DIGNITY[planet]["Domicile"][:]
        if MR_INCLUDE_EXALTATION:
            signs += DIGNITY[planet]["Exaltation"]
        return sign in signs
    mr = []
    for i in range(len(trad)):
        for j in range(i + 1, len(trad)):
            (n1, s1), (n2, s2) = trad[i], trad[j]
            if receives(n2, s1) and receives(n1, s2):
                mr.append(f"- {n1} in {s1} / {n2} in {s2}")
    L.append("\n".join(mr) if mr else "No mutual receptions.")
    L.append("")

    # Aspects among planets + Chiron
    aspects = find_aspects(bodies)

    # Unaspected
    L.append("## Unaspected Planets\n")
    aspected = {a["p1"] for a in aspects} | {a["p2"] for a in aspects}
    un = [f"- {p.name} in {full_sign(p.sign)}" for p in planets if p.name not in aspected]
    L.append("\n".join(un) if un else "No unaspected planets.")
    L.append("")

    # Lunation phase
    L.append("## Lunation Phase\n")
    phase, diff = lunation(s.sun.abs_pos, s.moon.abs_pos)
    rel = f"Moon is {diff:.0f}° ahead of the Sun" if diff <= 180 else f"Moon is {360 - diff:.0f}° behind the Sun"
    L.append(f"**{phase}** ({rel})\n")

    # Chart shaping (10 planets + Chiron)
    def in_houses(hs):
        return [n for n, p in bodies if house_num(p.house) in hs]
    L.append("## Chart Shaping\n")
    L.append("### Hemispheres\n")
    L.append(f"North (Houses 1–6): {names_list(in_houses(range(1, 7)))}  \n"
             f"South (Houses 7–12): {names_list(in_houses(range(7, 13)))}\n")
    L.append(f"East (Houses 10–3): {names_list(in_houses([10, 11, 12, 1, 2, 3]))}  \n"
             f"West (Houses 4–9): {names_list(in_houses([4, 5, 6, 7, 8, 9]))}\n")
    L.append("### Tri-Sectors\n")
    L.append(f"Personal (Houses 1–4): {names_list(in_houses([1, 2, 3, 4]))}  \n"
             f"Social (Houses 5–8): {names_list(in_houses([5, 6, 7, 8]))}  \n"
             f"Universal (Houses 9–12): {names_list(in_houses([9, 10, 11, 12]))}\n")
    L.append("### Quadrants\n")
    L.append(f"Self-development (Houses 1–3): {names_list(in_houses([1, 2, 3]))}  \n"
             f"Self-expression (Houses 4–6): {names_list(in_houses([4, 5, 6]))}  \n"
             f"Self-expansion (Houses 7–9): {names_list(in_houses([7, 8, 9]))}  \n"
             f"Self-transcendence (Houses 10–12): {names_list(in_houses([10, 11, 12]))}\n")

    # Aspect patterns
    L.append("## Aspect Patterns\n")
    patterns = detect_patterns(bodies, aspects)
    L.append("\n".join(f"- {p}" for p in patterns) if patterns else "No major aspect patterns.")
    L.append("")

    # Tight aspects (incl. nodes, excluding NN–SN)
    L.append("## Tight Aspects (orb ≤ 1°)\n")
    node_points = bodies + [("NN", s.true_node), ("SN", s.true_south_node)]
    tight = [a for a in find_aspects(node_points)
             if round(a["orb"] * 60) <= 60 and {a["p1"], a["p2"]} != {"NN", "SN"}]
    tight.sort(key=lambda a: a["orb"])
    L.append("\n".join(f"- {a['p1']} {a['aspect']} {a['p2']} {fmt_orb(a['orb'], a['dir'])}" for a in tight)
             if tight else "No tight aspects.")
    L.append("")

    # Full aspect list
    L.append("## All Aspects\n")
    for a in sorted(aspects, key=lambda a: a["orb"]):
        L.append(f"- {a['p1']} {a['aspect']} {a['p2']} {fmt_orb(a['orb'], a['dir'])}")

    return "\n".join(L)

# ── Page ───────────────────────────────────────────────────────

def geonames_user():
    try:
        return st.secrets["GEONAMES_USERNAME"]
    except Exception:
        return None

st.title("Astro RA")
st.write("Phase 1 chart overview. Enter birth data to calculate.")

with st.form("birth"):
    name = st.text_input("Name", placeholder="Name or chart label")
    birth_date = st.date_input("Birth date", value=date(1990, 1, 1),
                               min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
    c1, c2 = st.columns(2)
    hour = c1.number_input("Hour (24h)", min_value=0, max_value=23, value=12, step=1)
    minute = c2.number_input("Minute", min_value=0, max_value=59, value=0, step=1)
    c3, c4 = st.columns([2, 1])
    city = c3.text_input("Birth city (English)", placeholder="Shanghai")
    nation = c4.text_input("Country code", placeholder="CN", max_chars=2)
    submitted = st.form_submit_button("Calculate chart")

if submitted:
    if not city or not nation:
        st.error("Enter a birth city and a two-letter country code, e.g. Beijing / CN.")
        st.stop()
    label = name.strip() or "Chart"
    kwargs = dict(name=label, year=birth_date.year, month=birth_date.month, day=birth_date.day,
                  hour=int(hour), minute=int(minute), city=city.strip(), nation=nation.strip().upper())
    gn = geonames_user()
    if gn:
        kwargs["geonames_username"] = gn
    try:
        with st.spinner("Calculating chart…"):
            subject = AstrologicalSubject(**kwargs)
    except Exception as e:
        st.error(f"Couldn't find that location or calculate the chart. Check the city spelling and country code. ({e})")
        st.stop()

    lat, lng = getattr(subject, "lat", None), getattr(subject, "lng", None)
    tz = getattr(subject, "tz_str", "")
    born = (f"Born {birth_date:%Y-%m-%d} {int(hour):02d}:{int(minute):02d}, "
            f"{city.strip()}, {nation.strip().upper()}")
    if lat is not None and lng is not None:
        born += f"  \nLocation used: {lat:.4f}, {lng:.4f} ({tz})"

    worksheet = build_worksheet(subject, label, born)
    st.caption("Check the location used matches the birth place before relying on the chart.")
    st.markdown(worksheet)
    st.download_button("Download worksheet (.md)", worksheet,
                       file_name=f"{label}_phase1.md", mime="text/markdown")
