"""Eval cases. Reference time: Sunday 18 Oct 2026, 14:00.
Tomorrow = Mon 19 Oct, parson = Tue 20 Oct, narson = Wed 21 Oct.
Each expected dict only lists the fields we care about for that case."""
from datetime import datetime

NOW = datetime(2026, 10, 18, 14, 0)

CASES = [
    # (category, utterance, expected)
    # --- fractional clock words: sawa / saade / paune / dedh / dhai ---
    ("fraction", "kal sawa chaar baje", dict(date="2026-10-19", time="16:15", qualifier="exact")),
    ("fraction", "kal saade teen baje", dict(date="2026-10-19", time="15:30")),
    ("fraction", "kal paune paanch baje", dict(date="2026-10-19", time="16:45")),
    ("fraction", "kal dedh baje", dict(date="2026-10-19", time="13:30")),
    ("fraction", "parson dhai baje", dict(date="2026-10-20", time="14:30")),
    ("fraction", "kal sawa baje", dict(date="2026-10-19", time="13:15")),
    ("fraction", "kal paune ek baje", dict(date="2026-10-19", time="12:45")),
    # --- relative days ---
    ("rel_day", "parson subah das baje", dict(date="2026-10-20", time="10:00")),
    ("rel_day", "narson dopahar do baje", dict(date="2026-10-21", time="14:00")),
    ("rel_day", "aaj shaam chhe baje", dict(date="2026-10-18", time="18:00")),
    # --- weekdays ---
    ("weekday", "somvar subah gyarah baje", dict(date="2026-10-19", time="11:00")),
    ("weekday", "agle shukrawar shaam saade paanch baje", dict(date="2026-10-23", time="17:30")),
    ("weekday", "shaniwar subah nau baje", dict(date="2026-10-24", time="09:00")),
    ("weekday", "ravivar shaam paanch baje", dict(date="2026-10-18", time="17:00")),
    ("weekday", "agle ravivar shaam paanch baje", dict(date="2026-10-25", time="17:00")),
    # --- relative durations ---
    ("duration", "aadhe ghante mein", dict(date="2026-10-18", time="14:30", qualifier="relative")),
    ("duration", "dedh ghante baad", dict(date="2026-10-18", time="15:30")),
    ("duration", "paune ghante mein", dict(date="2026-10-18", time="14:45")),
    ("duration", "do ghante mein", dict(date="2026-10-18", time="16:00")),
    ("duration", "paanch minute mein", dict(date="2026-10-18", time="14:05")),
    ("duration", "ek ghante baad", dict(date="2026-10-18", time="15:00")),
    ("duration", "dhai ghante baad", dict(date="2026-10-18", time="16:30")),
    # --- qualifiers: after / before / around ---
    ("qualifier", "kal shaam ko paanch baje ke baad",
     dict(date="2026-10-19", time="17:00", qualifier="after", window=["17:00", "21:00"])),
    ("qualifier", "kal shaam 7 baje se pehle",
     dict(date="2026-10-19", time="19:00", qualifier="before", window=["09:00", "19:00"])),
    ("qualifier", "kal paanch baje ke aaspaas",
     dict(date="2026-10-19", time="17:00", qualifier="around", window=["16:30", "17:30"])),
    ("qualifier", "kal dopahar ke baad",
     dict(date="2026-10-19", qualifier="after", window=["12:00", "21:00"])),
    # --- day parts only (window, no exact time) ---
    ("daypart", "kal subah", dict(date="2026-10-19", qualifier="window", window=["09:00", "12:00"])),
    ("daypart", "kal shaam ko", dict(date="2026-10-19", qualifier="window", window=["16:00", "20:00"])),
    # --- AM/PM inference ---
    ("ampm", "kal 5 baje", dict(date="2026-10-19", time="17:00")),
    ("ampm", "kal 10 baje", dict(date="2026-10-19", time="10:00")),
    ("ampm", "kal 5:30 baje", dict(date="2026-10-19", time="17:30")),
    ("ampm", "kal 5 pm", dict(date="2026-10-19", time="17:00")),
    ("ampm", "kal 11 am", dict(date="2026-10-19", time="11:00")),
    ("ampm", "parson raat ke aath baje", dict(date="2026-10-20", time="20:00")),
    ("ampm", "kal 17:00", dict(date="2026-10-19", time="17:00")),
    # --- minutes after the hour ---
    ("minutes", "kal paanch bajke das minute pe", dict(date="2026-10-19", time="17:10")),
    # --- code-mixed / English / noisy filler ---
    ("codemix", "tomorrow evening 6 baje", dict(date="2026-10-19", time="18:00")),
    ("codemix", "mujhe kal doctor se milna hai shaam ko chaar baje", dict(date="2026-10-19", time="16:00")),
    ("codemix", "day after tomorrow morning 10 baje", dict(date="2026-10-20", time="10:00")),
    # --- Devanagari (what STT may output) ---
    ("devanagari", "कल शाम पाँच बजे के बाद", dict(date="2026-10-19", time="17:00", qualifier="after")),
    ("devanagari", "परसों सुबह दस बजे", dict(date="2026-10-20", time="10:00")),
    ("devanagari", "कल सवा चार बजे", dict(date="2026-10-19", time="16:15")),
    ("devanagari", "आधे घंटे में", dict(date="2026-10-18", time="14:30")),
    # --- self-correction ---
    ("correction", "kal nahi parson shaam paanch baje", dict(date="2026-10-20", time="17:00")),
    ("correction", "kal shaam paanch baje nahi chhe baje", dict(date="2026-10-19", time="18:00")),
    # --- should ask a follow-up, not guess ---
    ("clarify", "kal ka appointment chahiye", dict(date="2026-10-19", time=None, missing=["time"], needs_clarification=True)),
    ("clarify", "paanch baje", dict(time="17:00", missing=["date"], needs_clarification=True)),
    ("clarify", "aaj subah das baje", dict(time="10:00", needs_clarification=True)),
    ("clarify", "kal subah 8 baje", dict(time="08:00", needs_clarification=True)),
]