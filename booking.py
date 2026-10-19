"""Dialog + calendar for the appointment agent. No network, fully testable offline.

Flow: collect date/time (via resolver) -> find free slot(s) -> offer or confirm -> book.
Replies are in Hindi (Devanagari) so TTS pronounces them naturally.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

from resolver import CLOSE_HOUR, OPEN_HOUR, resolve

SLOT_MIN = 15
DB_PATH = "bookings.db"

HI_DAYS = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
HI_MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त",
             "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]

YES = {"haan", "han", "ha", "haa", "ji", "theek", "thik", "sahi", "ok", "okay", "yes", "yeah",
       "हाँ", "हां", "जी", "ठीक", "सही", "हा"}
NO = {"nahi", "nahin", "no", "नहीं", "नही", "ना"}
ORDINALS = [
    (0, ["pehla", "pehle wala", "first", "पहला", "पहले वाला"]),
    (1, ["doosra", "dusra", "second", "दूसरा"]),
    (2, ["teesra", "tisra", "third", "तीसरा"]),
]


# ---------------------------------------------------------------- calendar
def _conn(path: str = DB_PATH):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE IF NOT EXISTS bookings (d TEXT, t TEXT, UNIQUE(d, t))")
    return c


def all_slots() -> list[time]:
    out, cur = [], datetime(2000, 1, 1, OPEN_HOUR)
    end = datetime(2000, 1, 1, CLOSE_HOUR)
    while cur < end:
        out.append(cur.time())
        cur += timedelta(minutes=SLOT_MIN)
    return out


def booked(d: date, db: str = DB_PATH) -> set[time]:
    with _conn(db) as c:
        rows = c.execute("SELECT t FROM bookings WHERE d=?", (d.isoformat(),)).fetchall()
    return {time.fromisoformat(r[0]) for r in rows}


def book(d: date, t: time, db: str = DB_PATH) -> bool:
    try:
        with _conn(db) as c:
            c.execute("INSERT INTO bookings VALUES (?, ?)", (d.isoformat(), t.strftime("%H:%M")))
        return True
    except sqlite3.IntegrityError:
        return False


def all_bookings(db: str = DB_PATH) -> list[list[str]]:
    with _conn(db) as c:
        return [list(r) for r in c.execute("SELECT d, t FROM bookings ORDER BY d, t")]


def free_slots(d: date, now: datetime, db: str = DB_PATH) -> list[time]:
    taken = booked(d, db)
    return [s for s in all_slots()
            if s not in taken and not (d == now.date() and s <= now.time())]


def _mins(t: time) -> int:
    return t.hour * 60 + t.minute


def _nearest(slots: list[time], anchor: time, n: int) -> list[time]:
    return sorted(sorted(slots, key=lambda s: abs(_mins(s) - _mins(anchor)))[:n])


def _spread(slots: list[time], anchor: time, n: int, gap: int = 45) -> list[time]:
    """Nearest-to-anchor slots, but at least `gap` minutes apart so choices feel distinct."""
    chosen: list[time] = []
    for s in sorted(slots, key=lambda s: abs(_mins(s) - _mins(anchor))):
        if all(abs(_mins(s) - _mins(c)) >= gap for c in chosen):
            chosen.append(s)
        if len(chosen) == n:
            break
    return sorted(chosen)


# ---------------------------------------------------------------- speaking
def speak_date(d: date, today: date) -> str:
    diff = (d - today).days
    if diff == 0:
        return "आज"
    if diff == 1:
        return "कल"
    if diff == 2:
        return "परसों"
    return f"{HI_DAYS[d.weekday()]} {d.day} {HI_MONTHS[d.month - 1]}"


def speak_time(t: time) -> str:
    h = t.hour
    part = "सुबह" if 5 <= h < 12 else "दोपहर" if 12 <= h < 16 else "शाम" if 16 <= h < 20 else "रात"
    h12 = h % 12 or 12
    return f"{part} {h12} बजे" if t.minute == 0 else f"{part} {h12} बजकर {t.minute} मिनट"


def speak_slots(ts: list[time]) -> str:
    return ", ".join(speak_time(t) for t in ts[:-1]) + (" या " if len(ts) > 1 else "") + speak_time(ts[-1])


# ---------------------------------------------------------------- dialog
@dataclass
class Session:
    date: Optional[date] = None
    time: Optional[time] = None
    window: Optional[tuple[time, time]] = None
    qualifier: str = "none"
    stage: str = "collecting"  # collecting | offering | confirming | done
    offered: list[time] = field(default_factory=list)
    pending: Optional[time] = None


def _yes_no(text: str) -> Optional[str]:
    words = set(re.findall(r"[\w\u0900-\u097F]+", text.lower()))
    if words & NO:
        return "no"
    if words & YES:
        return "yes"
    return None


def _ordinal(text: str) -> Optional[int]:
    low = text.lower()
    for idx, words in ORDINALS:
        if any(w in low for w in words):
            return idx
    return None


def handle(s: Session, text: str, now: Optional[datetime] = None, db: str = DB_PATH) -> str:
    now = now or datetime.now()
    today = now.date()

    # ---- confirming a specific slot
    if s.stage == "confirming" and s.pending:
        yn = _yes_no(text)
        if yn == "yes":
            if book(s.date, s.pending, db):
                s.stage = "done"
                return (f"आपका अपॉइंटमेंट {speak_date(s.date, today)} {speak_time(s.pending)} "
                        f"के लिए बुक हो गया है। धन्यवाद!")
            s.stage, s.pending = "collecting", None
            return "माफ़ कीजिए, वो समय अभी-अभी भर गया। कोई और समय बताइए।"
        if yn == "no":
            s.stage, s.pending, s.time, s.window, s.qualifier = "collecting", None, None, None, "none"
            if not re.search(r"\d|baje|बजे|kal|कल|parso|परसों|subah|सुबह|shaam|शाम|dopahar|दोपहर|raat|रात", text.lower()):
                return "ठीक है। कौन सा दिन या समय ठीक रहेगा?"
        # anything else: treat as a fresh request below

    # ---- picking among offered slots
    if s.stage == "offering" and s.offered:
        idx = _ordinal(text)
        if idx is not None and idx < len(s.offered):
            return _confirm(s, s.offered[idx], today)
        r = resolve(text, now)
        if r.time and r.qualifier in ("exact", "relative") and not r.date:
            snapped = _nearest(s.offered, r.time, 1)[0]
            if abs(_mins(snapped) - _mins(r.time)) < SLOT_MIN:
                return _confirm(s, snapped, today)

    # ---- parse new info and merge
    r = resolve(text, now)
    got_something = False
    if r.date:
        s.date, got_something = r.date, True
    if r.time or r.window:
        s.time, s.window, s.qualifier, got_something = r.time, r.window, r.qualifier, True
        if "outside_hours" in r.flags:
            s.time, s.window = None, None
            return f"हम सुबह {OPEN_HOUR} बजे से रात {CLOSE_HOUR - 12} बजे तक खुले रहते हैं। उस बीच का कोई समय बताइए।"
    if not got_something:
        return "माफ़ कीजिए, मैं समझ नहीं पाया। क्या आप दिन और समय दोबारा बता सकते हैं?"

    if s.date and s.date < today:
        s.date = None
        return "वो दिन निकल चुका है। कौन सा दिन ठीक रहेगा?"
    if not s.date:
        return "किस दिन आना चाहेंगे?"
    if not (s.time or s.window):
        return f"{speak_date(s.date, today)} किस समय आना चाहेंगे?"
    return _find_and_offer(s, now, db)


def _confirm(s: Session, t: time, today: date) -> str:
    s.pending, s.stage, s.offered = t, "confirming", []
    return f"{speak_date(s.date, today)} {speak_time(t)} का अपॉइंटमेंट बुक कर दूँ? हाँ या नहीं बताइए।"


def _find_and_offer(s: Session, now: datetime, db: str) -> str:
    today = now.date()
    free = free_slots(s.date, now, db)
    when = speak_date(s.date, today)

    if s.qualifier in ("exact", "relative") and s.time:
        want = _nearest(all_slots(), s.time, 1)[0]
        if s.date == today and want <= now.time():
            s.time = None
            return "वो समय निकल चुका है। कोई और समय बताइए।"
        if want in free:
            return _confirm(s, want, today)
        alts = _nearest(free, want, 2)
        if not alts:
            return f"{when} कोई समय खाली नहीं है। कोई और दिन बताइए।"
        s.offered, s.stage = alts, "offering"
        return f"{when} {speak_time(want)} पर जगह नहीं है। {speak_slots(alts)} खाली हैं, कौन सा ठीक रहेगा?"

    lo, hi = s.window if s.window else (time(OPEN_HOUR), time(CLOSE_HOUR))
    cands = [t for t in free if lo <= t <= hi]
    if not cands:
        s.time, s.window = None, None
        return f"{when} उस समय के आसपास कोई जगह खाली नहीं है। कोई और समय बताइए।"
    if s.qualifier == "before":
        anchor = hi
    elif s.qualifier == "around" and s.time:
        anchor = s.time
    elif s.qualifier == "after":
        anchor = lo
    else:  # plain window like "kal shaam": aim for the middle
        anchor = time((_mins(lo) + _mins(hi)) // 2 // 60, (_mins(lo) + _mins(hi)) // 2 % 60)
    picks = _spread(cands, anchor, 3)
    if len(picks) == 1:
        return _confirm(s, picks[0], today)
    s.offered, s.stage = picks, "offering"
    return f"{when} इन समयों पर जगह है: {speak_slots(picks)}। कौन सा ठीक रहेगा?"