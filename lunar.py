"""LUNAR engine: moon phase and lunar-day (tithi) analysis, plus iCalendar output.

Lunar days follow the classical tithi system: each lunar day is one 12-degree
step of the Moon's elongation from the Sun (30 per lunar month). Every lunar day
belongs to one of five day types; the Rikta ("empty") days are labelled Evil Days.
Positions use truncated Meeus algorithms (good to a few arc-minutes).
"""

import math
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

RAD = math.pi / 180
UTC = timezone.utc

# Periodic terms for the Moon's longitude: D, M, M', F, coefficient (1e-6 deg).
MOON_TERMS = [
    (0, 0, 1, 0, 6288774), (2, 0, -1, 0, 1274027), (2, 0, 0, 0, 658314),
    (0, 0, 2, 0, 213618), (0, 1, 0, 0, -185116), (0, 0, 0, 2, -114332),
    (2, 0, -2, 0, 58793), (2, -1, -1, 0, 57066), (2, 0, 1, 0, 53322),
    (2, -1, 0, 0, 45758), (0, 1, -1, 0, -40923), (1, 0, 0, 0, -34720),
    (0, 1, 1, 0, -30383), (2, 0, 0, -2, 15327), (0, 0, 1, 2, -12528),
    (0, 0, 1, -2, 10980), (4, 0, -1, 0, 10675), (0, 0, 3, 0, 10034),
    (4, 0, -2, 0, 8548), (2, 1, -1, 0, -7888), (2, 1, 0, 0, -6766),
    (1, 0, -1, 0, -5163), (1, 1, 0, 0, 4987), (2, -1, 1, 0, 4036),
    (2, 0, 2, 0, 3994), (4, 0, 0, 0, 3861), (2, 0, -3, 0, 3665),
    (0, 1, -2, 0, -2689), (2, 0, -1, 2, -2602), (2, -1, -2, 0, 2390),
    (1, 0, 1, 0, -2348), (2, -2, 0, 0, 2236), (0, 1, 2, 0, -2120),
    (0, 2, 0, 0, -2069),
]

TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi",
]

DAY_TYPES = {
    "joyful": {
        "name": "Joyful Day", "group": "Nanda", "color": "#38bdf8",
        "meaning": "Favourable for celebrations, socialising, rest and starting pleasant things.",
    },
    "good": {
        "name": "Good Day", "group": "Bhadra", "color": "#4ade80",
        "meaning": "Favourable for steady work, building, health, buying and making plans.",
    },
    "victory": {
        "name": "Victory Day", "group": "Jaya", "color": "#fbbf24",
        "meaning": "Favourable for bold action, competition, negotiation and overcoming obstacles.",
    },
    "evil": {
        "name": "Evil Day", "group": "Rikta", "color": "#ef4444",
        "meaning": "Unfavourable. Avoid new beginnings, signing, launches and big decisions. "
                   "Better used for clearing out, endings and rest.",
    },
    "full": {
        "name": "Full Day", "group": "Purna", "color": "#c084fc",
        "meaning": "Complete. Favourable for finishing work, ceremonies, gratitude and fulfilment.",
    },
}
TYPE_BY_POSITION = {1: "joyful", 2: "good", 3: "victory", 4: "evil", 0: "full"}

PHASES = [  # (start of 45-degree band centred on the principal phase, name, emoji)
    ("New Moon", "🌑"), ("Waxing Crescent", "🌒"), ("First Quarter", "🌓"),
    ("Waxing Gibbous", "🌔"), ("Full Moon", "🌕"), ("Waning Gibbous", "🌖"),
    ("Last Quarter", "🌗"), ("Waning Crescent", "🌘"),
]
PRINCIPAL = {0: ("New Moon", "🌑"), 90: ("First Quarter", "🌓"),
             180: ("Full Moon", "🌕"), 270: ("Last Quarter", "🌗")}


def _norm(x):
    return x % 360.0


def _sin(deg):
    return math.sin(deg * RAD)


def _centuries(dt):
    jd = dt.timestamp() / 86400.0 + 2440587.5 + 69.0 / 86400.0  # ~TT
    return (jd - 2451545.0) / 36525.0


def _sun_longitude(T):
    L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T
    M = 357.52911 + 35999.05029 * T - 0.0001537 * T * T
    C = ((1.914602 - 0.004817 * T - 0.000014 * T * T) * _sin(M)
         + (0.019993 - 0.000101 * T) * _sin(2 * M) + 0.000289 * _sin(3 * M))
    return _norm(L0 + C - 0.00569)


def _moon_longitude(T):
    Lp = 218.3164477 + 481267.88123421 * T
    D = 297.8501921 + 445267.1114034 * T
    M = 357.5291092 + 35999.0502909 * T
    Mp = 134.9633964 + 477198.8675055 * T
    F = 93.2720950 + 483202.0175233 * T
    E = 1 - 0.002516 * T
    s = 0.0
    for d, m, mp, f, c in MOON_TERMS:
        s += c * (E ** abs(m)) * _sin(d * D + m * M + mp * Mp + f * F)
    s += 3958 * _sin(119.75 + 131.849 * T) + 1962 * _sin(Lp - F) + 318 * _sin(53.09 + 479264.29 * T)
    return _norm(Lp + s / 1e6)


def elongation(dt):
    """Moon minus Sun ecliptic longitude in degrees, 0..360."""
    T = _centuries(dt)
    return _norm(_moon_longitude(T) - _sun_longitude(T))


def _signed(dt, target):
    return (elongation(dt) - target + 180) % 360 - 180


def _next_crossing(dt, target, max_days):
    """First moment after dt at which elongation reaches target (it only increases)."""
    lo, hi = dt, dt + timedelta(days=max_days)
    for _ in range(30):  # ~1 ms precision over a 10-day window
        mid = lo + (hi - lo) / 2
        if _signed(mid, target) < 0:
            lo = mid
        else:
            hi = mid
    return hi


def moon_at(dt):
    e = elongation(dt)
    idx = int(((e + 22.5) % 360) // 45)
    name, emoji = PHASES[idx]
    lunar_day = int(e // 12) + 1  # 1..30
    waxing = lunar_day <= 15
    pos = (lunar_day - 1) % 15 + 1  # 1..15 within the fortnight
    if pos == 15:
        tithi = "Purnima" if waxing else "Amavasya"
    else:
        tithi = TITHI_NAMES[pos - 1]
    type_key = TYPE_BY_POSITION[pos % 5]
    ends = _next_crossing(dt, (lunar_day * 12) % 360, 1.3)
    return {
        "elongation": round(e, 3),
        "illumination": round((1 - math.cos(e * RAD)) / 2, 4),
        "phase": name,
        "emoji": emoji,
        "lunar_day": lunar_day,
        "tithi": tithi,
        "paksha": "Waxing (Shukla)" if waxing else "Waning (Krishna)",
        "type": type_key,
        "lunar_day_ends": ends.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "_ends_dt": ends,
    }


def day_info(d, tz):
    """Analysis of a civil date, read at local sunrise (taken as 06:00), the classical convention."""
    info = moon_at(datetime.combine(d, time(6, 0), tzinfo=tz))
    info["date"] = d.isoformat()
    info["type_name"] = DAY_TYPES[info["type"]]["name"]
    return info


def principal_phases(start, end):
    out, t = [], start
    while t < end:
        e = elongation(t)
        target = (int(e // 90) + 1) * 90 % 360
        hit = _next_crossing(t, target, 10)
        if hit >= end:
            break
        name, emoji = PRINCIPAL[target]
        out.append({"time": hit, "name": name, "emoji": emoji})
        t = hit + timedelta(hours=6)
    return out


def safe_zone(name):
    try:
        return ZoneInfo(name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def today_in(tz):
    return datetime.now(tz).date()


# ---------- iCalendar ----------

def _esc(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line):
    """Fold at 75 octets without splitting UTF-8 characters (RFC 5545 3.1)."""
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > 74:
            out.append(cur)
            cur, size = " ", 1
        cur += ch
        size += n
    out.append(cur)
    return "\r\n".join(out)


def _local_time(dt, tz):
    return dt.astimezone(tz).strftime("%a %d %b, %I:%M %p").replace(" 0", " ")


def build_ics(tz_name="UTC", alerts=False, days_back=30, days_ahead=400):
    tz = safe_zone(tz_name)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    start = today_in(tz) - timedelta(days=days_back)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//LUNAR//Lunar Day Calendar//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:LUNAR",
        "X-WR-CALDESC:Lunar day types and moon phases by LUNAR",
        f"X-WR-TIMEZONE:{tz.key}", "REFRESH-INTERVAL;VALUE=DURATION:P1D", "X-PUBLISHED-TTL:P1D",
    ]

    for i in range(days_back + days_ahead):
        d = start + timedelta(days=i)
        info = day_info(d, tz)
        t = DAY_TYPES[info["type"]]
        summary = f"{info['emoji']} {t['name']} · Lunar Day {info['lunar_day']}"
        if info["type"] == "evil":
            summary = f"⛔ {t['name']} · Lunar Day {info['lunar_day']} {info['emoji']}"
        desc = (
            f"{t['name'].upper()}\n{t['meaning']}\n\n"
            f"Lunar day {info['lunar_day']} of 30: {info['tithi']}, {info['paksha']}\n"
            f"Lunar day ends: {_local_time(info['_ends_dt'], tz)}\n"
            f"Moon: {info['phase']}, {round(info['illumination'] * 100)}% illuminated\n\n— LUNAR"
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:lunar-day-{d.strftime('%Y%m%d')}-{tz.key.replace('/', '-')}@lunar",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(desc)}",
            f"CATEGORIES:{_esc(t['name'])}",
            "TRANSP:TRANSPARENT",
        ]
        if alerts and info["type"] == "evil":
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY",
                      f"DESCRIPTION:{_esc('Tomorrow is an Evil Day (lunar day %d)' % info['lunar_day'])}",
                      "TRIGGER:-PT6H", "END:VALARM"]
        lines.append("END:VEVENT")

    range_start = datetime.combine(start, time(0), tzinfo=tz)
    for p in principal_phases(range_start, range_start + timedelta(days=days_back + days_ahead)):
        t0 = p["time"].astimezone(UTC)
        desc = "Exact %s at %s\n— LUNAR" % (p["name"], _local_time(t0, tz))
        lines += [
            "BEGIN:VEVENT",
            f"UID:lunar-phase-{t0.strftime('%Y%m%dT%H%M')}@lunar",
            f"DTSTAMP:{stamp}",
            f"DTSTART:{t0.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTEND:{(t0 + timedelta(minutes=30)).strftime('%Y%m%dT%H%M%SZ')}",
            f"SUMMARY:{_esc(p['emoji'] + ' ' + p['name'])}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def public_day(info):
    return {k: v for k, v in info.items() if not k.startswith("_")}
