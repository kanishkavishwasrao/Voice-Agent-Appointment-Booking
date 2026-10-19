"""
Resolve spoken Indic (Hindi / Hinglish / Devanagari) date-time expressions
into concrete booking slots.

    resolve("kal shaam ko sawa chaar baje ke baad", now)
    -> Tue 19 Oct, after 16:15 (window 16:15-21:00)

Design: tokenize -> canonicalize spelling variants -> extract signals
(day, day-part, clock, qualifier, relative duration) per segment -> merge
segments (so "kal nahi parson" self-corrections work) -> resolve to a slot.
Anything it can't pin down is reported in `missing` / `flags`, so the voice
agent knows exactly what to ask the caller next.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, fields
from datetime import date, datetime, time, timedelta
from typing import Optional

OPEN_HOUR, CLOSE_HOUR = 9, 21  # clinic/salon hours; used to disambiguate AM/PM

# --------------------------------------------------------------------------
# Vocabulary: canonical word -> spelling variants (Roman, English, Devanagari)
# --------------------------------------------------------------------------
_GROUPS: dict[str, list[str]] = {
    # days
    "aaj": ["aaj", "aj", "today", "आज"],
    "kal": ["kal", "tomorrow", "कल"],
    "parson": ["parson", "parso", "parsoon", "parsu", "परसों", "परसो"],
    "narson": ["narson", "narso", "नरसों"],
    "abhi": ["abhi", "now", "अभी"],
    # weekdays
    "somvar": ["somvar", "somwar", "somvaar", "monday", "mon", "सोमवार"],
    "mangalvar": ["mangalvar", "mangalwar", "tuesday", "tue", "tues", "मंगलवार"],
    "budhvar": ["budhvar", "budhwar", "wednesday", "wed", "बुधवार"],
    "guruvar": ["guruvar", "guruwar", "veervar", "virvar", "thursday", "thu", "thurs", "गुरुवार", "वीरवार"],
    "shukravar": ["shukravar", "shukrawar", "friday", "fri", "शुक्रवार"],
    "shanivar": ["shanivar", "shaniwar", "shanivaar", "saturday", "शनिवार"],
    "ravivar": ["ravivar", "raviwar", "itwar", "itvar", "sunday", "रविवार", "इतवार"],
    # day parts
    "subah": ["subah", "subha", "subeh", "savere", "morning", "सुबह", "सवेरे"],
    "dopahar": ["dopahar", "dopehar", "dupahar", "afternoon", "दोपहर"],
    "shaam": ["shaam", "sham", "shaym", "evening", "शाम"],
    "raat": ["raat", "rat", "night", "रात"],
    # clock words
    "baje": ["baje", "bje", "bajey", "बजे"],
    "bajke": ["bajke", "bajkar", "bajake", "बजके", "बजकर"],
    "sawa": ["sawa", "sava", "sawaa", "सवा"],
    "saade": ["saade", "sade", "saadhe", "sadhe", "साढ़े", "साढे"],
    "paune": ["paune", "pone", "poune", "पौने"],
    "dedh": ["dedh", "derh", "dhed", "der", "डेढ़", "डेढ"],
    "dhai": ["dhai", "dhaai", "adhai", "dhaayi", "ढाई"],
    "aadha": ["aadha", "aadhe", "adha", "adhe", "aadhaa", "half", "आधा", "आधे"],
    "ghante": ["ghante", "ghanta", "ghantey", "ghanto", "hour", "hours", "hr", "hrs", "घंटे", "घंटा", "घण्टे"],
    "minute": ["minute", "minutes", "min", "mins", "minit", "mint", "minat", "मिनट"],
    # particles
    "mein": ["mein", "me", "mei", "mai", "में", "मे"],
    "baad": ["baad", "bad", "after", "बाद"],
    "pehle": ["pehle", "pahle", "pehla", "before", "पहले"],
    "tak": ["tak", "तक"],
    "nahi": ["nahi", "nahin", "nahee", "नहीं", "नही"],
    "aaspaas": ["aaspaas", "aaspas", "lagbhag", "around", "approx", "आसपास", "लगभग"],
    "agle": ["agle", "agla", "agli", "next", "अगले", "अगला"],
    "is": ["is", "iss", "this", "इस"],
    "am": ["am"],
    "pm": ["pm"],
    # number words (hours / minutes)
    "ek": ["ek", "one", "एक"],
    "do": ["do", "two", "दो"],
    "teen": ["teen", "tin", "three", "तीन"],
    "chaar": ["chaar", "char", "four", "चार"],
    "paanch": ["paanch", "panch", "paach", "pach", "five", "पांच", "पाँच"],
    "chhe": ["chhe", "che", "chhah", "chheh", "chha", "six", "छह", "छः", "छे", "छ"],
    "saat": ["saat", "seven", "सात"],
    "aath": ["aath", "aat", "eight", "आठ"],
    "nau": ["nau", "nao", "nine", "नौ"],
    "das": ["das", "ten", "दस"],
    "gyarah": ["gyarah", "gyaarah", "gyara", "eleven", "ग्यारह"],
    "barah": ["barah", "baarah", "bara", "twelve", "बारह"],
    "pandrah": ["pandrah", "पंद्रह"],
    "bees": ["bees", "बीस"],
    "paccis": ["paccis", "pachchis", "पच्चीस"],
    "tees": ["tees", "तीस"],
    "paintis": ["paintis", "पैंतीस"],
    "chalis": ["chalis", "चालीस"],
    "paintalis": ["paintalis", "पैंतालीस"],
    "pachaas": ["pachaas", "pachas", "पचास"],
}
_CANON = {
    unicodedata.normalize("NFC", v): k for k, vs in _GROUPS.items() for v in vs
}

NUMWORDS = {
    "ek": 1, "do": 2, "teen": 3, "chaar": 4, "paanch": 5, "chhe": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15,
    "bees": 20, "paccis": 25, "tees": 30, "paintis": 35, "chalis": 40,
    "paintalis": 45, "pachaas": 50,
}
FRACTIONS = {"aadha": 0.5, "dedh": 1.5, "dhai": 2.5, "sawa": 1.25, "paune": 0.75}
WEEKDAYS = {
    "somvar": 0, "mangalvar": 1, "budhvar": 2, "guruvar": 3,
    "shukravar": 4, "shanivar": 5, "ravivar": 6,
}
DAY_OFFSETS = {"aaj": 0, "kal": 1, "parson": 2, "narson": 3}
DAYPARTS = {"subah": (6, 12), "dopahar": (12, 16), "shaam": (16, 20), "raat": (20, 24)}

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


# --------------------------------------------------------------------------
# Tokenizing
# --------------------------------------------------------------------------
def tokenize(text: str) -> list[str]:
    t = unicodedata.normalize("NFC", text).lower().translate(_DEV_DIGITS)
    t = t.replace("day after tomorrow", "parson")
    t = re.sub(r"(?<=\d)(am|pm)\b", r" \1", t)  # "5pm" -> "5 pm"
    t = re.sub(r"[^\w:.\u0900-\u097F]+", " ", t)  # keep Devanagari + H:MM
    toks = [w.strip(".:") for w in t.split()]
    return [_CANON.get(w, w) for w in toks if w]


def _num(tok: str) -> Optional[int]:
    if tok.isdigit():
        return int(tok)
    return NUMWORDS.get(tok)


# --------------------------------------------------------------------------
# Signal extraction
# --------------------------------------------------------------------------
@dataclass
class Signals:
    rel_minutes: Optional[int] = None
    day_offset: Optional[int] = None
    weekday: Optional[int] = None
    strict: bool = False  # "agle somvar": strictly after today
    part: Optional[str] = None
    clock: Optional[tuple[int, int]] = None  # hour as spoken, minute
    is24: bool = False
    meridiem: Optional[str] = None
    qualifier: Optional[str] = None  # after | before | around

    def update(self, other: "Signals") -> None:
        """Later segments override earlier ones ("kal nahi parson")."""
        for f in fields(self):
            v = getattr(other, f.name)
            if v is not None and v is not False:
                setattr(self, f.name, v)
        # a new day anchor replaces the old kind ("kal nahi somvar")
        if other.weekday is not None and other.day_offset is None:
            self.day_offset = None
        if other.day_offset is not None and other.weekday is None:
            self.weekday = None


def _qty(toks: list[str], i: int) -> Optional[float]:
    """Quantity just before the unit at index i: 'aadha', 'dedh', 'saade teen', '5'."""
    if i == 0:
        return None
    p = toks[i - 1]
    if p in FRACTIONS:
        return FRACTIONS[p]
    n = _num(p)
    if n is None:
        return None
    if i >= 2:
        q = toks[i - 2]
        if q == "sawa":
            return n + 0.25
        if q == "saade":
            return n + 0.5
        if q == "paune":
            return n - 0.25
    return n


def _find_clock(toks: list[str]):
    """Return ((hour, minute), is24) or None."""
    for t in toks:  # 5:30 / 17:00
        m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", t)
        if m and int(m[1]) <= 24 and int(m[2]) < 60:
            h = int(m[1])
            return (h, int(m[2])), h > 12
    for j, t in enumerate(toks):
        if t not in ("baje", "bajke"):
            continue
        prev = toks[j - 1] if j > 0 else None
        if prev == "dedh":
            h, m = 1, 30
        elif prev == "dhai":
            h, m = 2, 30
        elif prev == "sawa":
            h, m = 1, 15
        else:
            h = _num(prev) if prev else None
            if h is None or not 1 <= h <= 24:
                continue
            m = 0
            p2 = toks[j - 2] if j > 1 else None
            if p2 == "sawa":
                m = 15
            elif p2 == "saade":
                m = 30
            elif p2 == "paune":
                h, m = (h - 1) or 12, 45
        # "paanch bajke das minute pe"
        if j + 2 < len(toks) and toks[j + 2] == "minute":
            mm = _num(toks[j + 1])
            followed_by_relative = j + 3 < len(toks) and toks[j + 3] in ("mein", "baad")
            if mm is not None and not followed_by_relative:
                m = mm
        return (h, m), h > 12
    for j, t in enumerate(toks):  # "5 pm"
        if t in ("am", "pm") and j > 0:
            h = _num(toks[j - 1])
            if h is not None and 1 <= h <= 12:
                return (h, 0), False
    return None


def _extract(toks: list[str]) -> Signals:
    s = Signals()

    # relative duration: "aadhe ghante mein", "dedh ghante baad", "paanch minute mein"
    for i, t in enumerate(toks):
        if t in ("ghante", "minute") and i + 1 < len(toks) and toks[i + 1] in ("mein", "baad"):
            q = _qty(toks, i)
            if q is not None:
                s.rel_minutes = round(q * (60 if t == "ghante" else 1))
                break
    if "abhi" in toks and s.rel_minutes is None:
        s.rel_minutes = 0

    # day
    for i, t in enumerate(toks):
        if t in DAY_OFFSETS:
            s.day_offset = DAY_OFFSETS[t]
        elif t in WEEKDAYS:
            s.weekday = WEEKDAYS[t]
            s.strict = i > 0 and toks[i - 1] == "agle"

    # day part, meridiem
    for t in toks:
        if t in DAYPARTS:
            s.part = t
        if t in ("am", "pm"):
            s.meridiem = t

    # clock
    c = _find_clock(toks)
    if c:
        s.clock, s.is24 = c

    # qualifier (not for relative durations)
    if s.rel_minutes is None:
        if "baad" in toks:
            s.qualifier = "after"
        elif "pehle" in toks or "tak" in toks:
            s.qualifier = "before"
        elif "aaspaas" in toks:
            s.qualifier = "around"
    return s


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------
@dataclass
class Resolved:
    text: str
    date: Optional[date] = None
    time: Optional[time] = None
    window: Optional[tuple[time, time]] = None
    qualifier: str = "none"  # exact | after | before | around | window | relative | none
    missing: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def needs_clarification(self) -> bool:
        return bool(self.missing or self.flags)

    def describe(self) -> str:
        bits = []
        if self.date:
            bits.append(self.date.strftime("%a %d %b %Y"))
        if self.time:
            bits.append(f"{self.qualifier if self.qualifier not in ('exact', 'none') else 'at'} {self.time:%H:%M}")
        if self.window:
            bits.append(f"window {self.window[0]:%H:%M}-{self.window[1]:%H:%M}")
        if self.missing:
            bits.append(f"MISSING: {', '.join(self.missing)}")
        if self.flags:
            bits.append(f"FLAGS: {', '.join(self.flags)}")
        return " | ".join(bits)


def _to24(h: int, part: Optional[str], meridiem: Optional[str], is24: bool):
    """Spoken hour -> (hour24, day_shift). Uses part of day, then clinic hours."""
    if is24:
        return h % 24, 0
    if meridiem == "pm":
        return (h if h == 12 else h + 12), 0
    if meridiem == "am":
        return (0 if h == 12 else h), 0
    if part == "subah":
        return h, 0
    if part == "dopahar":
        return (12 if h == 12 else h + 12 if h <= 6 else h), 0
    if part == "shaam":
        return (h + 12 if h < 12 else 12), 0
    if part == "raat":
        if h == 12:
            return 0, 1
        return (h + 12 if h >= 6 else h), 0
    cands = sorted({h % 12, h % 12 + 12})
    ok = [c for c in cands if OPEN_HOUR <= c < CLOSE_HOUR]
    if ok:
        return ok[0], 0
    return (h % 12 + 12 if h < 7 else h % 12), 0


def _clip(lo: int, hi: int) -> tuple[time, time]:
    lo, hi = max(lo, OPEN_HOUR), min(hi, CLOSE_HOUR)
    return time(lo), time(hi)


def resolve(text: str, now: Optional[datetime] = None) -> Resolved:
    now = now or datetime.now()
    toks = tokenize(text)

    # split on "nahi" so later corrections override earlier values
    segs, cur = [], []
    for t in toks:
        if t == "nahi":
            segs.append(cur)
            cur = []
        else:
            cur.append(t)
    segs.append(cur)
    sig = Signals()
    for seg in segs:
        sig.update(_extract(seg))

    res = Resolved(text=text)
    today = now.date()

    # relative: "aadhe ghante mein", "abhi"
    if sig.rel_minutes is not None and sig.day_offset is None and sig.weekday is None and sig.clock is None:
        dt = (now + timedelta(minutes=sig.rel_minutes)).replace(second=0, microsecond=0)
        res.date, res.time, res.qualifier = dt.date(), dt.time(), "relative"
        return res

    # date
    if sig.day_offset is not None:
        res.date = today + timedelta(days=sig.day_offset)
    elif sig.weekday is not None:
        delta = (sig.weekday - today.weekday()) % 7
        if delta == 0 and sig.strict:
            delta = 7
        res.date = today + timedelta(days=delta)

    # time
    if sig.clock:
        h, m = sig.clock
        h24, shift = _to24(h, sig.part, sig.meridiem, sig.is24)
        if shift and res.date:
            res.date += timedelta(days=shift)
        t = time(h24, m)
        res.time = t
        q = sig.qualifier or "exact"
        res.qualifier = q
        base = datetime.combine(today, t)
        if q == "after":
            res.window = (t, time(CLOSE_HOUR))
        elif q == "before":
            res.window = (time(OPEN_HOUR), t)
        elif q == "around":
            lo = max((base - timedelta(minutes=30)).time(), time(OPEN_HOUR))
            hi = min((base + timedelta(minutes=30)).time(), time(CLOSE_HOUR))
            res.window = (lo, hi)
        if not (OPEN_HOUR <= h24 < CLOSE_HOUR):
            res.flags.append("outside_hours")
    elif sig.part:
        lo, hi = DAYPARTS[sig.part]
        if sig.qualifier == "after":
            res.window = (_clip(lo, hi)[0], time(CLOSE_HOUR))
            res.qualifier = "after"
        elif sig.qualifier == "before":
            res.window = (time(OPEN_HOUR), _clip(lo, hi)[0])
            res.qualifier = "before"
        else:
            res.window = _clip(lo, hi)
            res.qualifier = "window"

    if res.date is None:
        res.missing.append("date")
    if res.time is None and res.window is None:
        res.missing.append("time")

    # in the past?
    if res.date == today:
        if res.time and res.time <= now.time():
            res.flags.append("in_past")
        elif not res.time and res.window and res.window[1] <= now.time():
            res.flags.append("in_past")
    return res


if __name__ == "__main__":
    import sys

    ref = datetime(2026, 10, 18, 14, 0)
    for line in sys.argv[1:] or ["kal shaam ko sawa chaar baje ke baad", "aadhe ghante mein"]:
        print(f"{line!r}\n   -> {resolve(line, ref).describe()}")