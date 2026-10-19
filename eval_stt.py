"""End-to-end eval: recording -> Sarvam STT (per mode) -> resolver -> compare with label.

Setup:
  eval_audio/01.wav, 02.wav ...   (any of wav/mp3/m4a/ogg/flac; name = the `id` column)
  eval_labels.csv                  (edit `condition` / `speaker` as you record)

Run:
  python eval_stt.py                       # all three modes
  python eval_stt.py --modes codemix       # one mode
  python eval_stt.py --fake                # no audio/API: uses the `intended` text as the
                                           # transcript, i.e. tests the resolver alone

STT results are cached in eval_cache/, so after you fix the resolver you can re-run for free.
Use --refresh to call the API again.

Reference time is fixed (Sun 18 Oct 2026 14:00, from cases.py) so labels stay valid on any day.
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from cases import NOW
from resolver import resolve

try:  # Devanagari output on Windows consoles
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".webm"}
MODES = ["transcribe", "codemix", "translit"]


def find_audio(audio_dir: Path, rid: str):
    if audio_dir.exists():
        for p in audio_dir.iterdir():
            if p.stem == rid and p.suffix.lower() in AUDIO_EXT:
                return p
    return None


def get_transcript(path: Path, mode: str, cache_dir: Path, refresh: bool) -> str:
    cache = cache_dir / f"{path.stem}__{mode}.txt"
    if cache.exists() and not refresh:
        return cache.read_text(encoding="utf-8")
    from sarvam_io import stt

    text = stt(str(path), mode=mode)
    cache_dir.mkdir(exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def judge(text: str, row: dict):
    """Returns (ok, parsed_description). Blank expected fields are not checked."""
    r = resolve(text, NOW)
    checks = []
    if row["expected_date"]:
        checks.append(bool(r.date) and r.date.isoformat() == row["expected_date"])
    if row["expected_time"]:
        checks.append(bool(r.time) and r.time.strftime("%H:%M") == row["expected_time"])
    if row.get("expected_qualifier"):
        checks.append(r.qualifier == row["expected_qualifier"])
    return all(checks), r.describe()


def pct(ok, n):
    return f"{ok}/{n} ({100 * ok / n:.0f}%)" if n else "-"


def table(title, groups, modes):
    """groups: {name: {mode: [bool, ...]}}"""
    print(f"\n{title}")
    print(f"  {'':<12}" + "".join(f"{m:>18}" for m in modes))
    for name, per_mode in groups.items():
        cells = "".join(f"{pct(sum(per_mode[m]), len(per_mode[m])):>18}" for m in modes)
        print(f"  {name:<12}{cells}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default="eval_audio")
    ap.add_argument("--labels", default="eval_labels.csv")
    ap.add_argument("--modes", nargs="+", default=MODES, choices=MODES)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--out", default="eval_results.csv")
    args = ap.parse_args()

    audio_dir, cache_dir = Path(args.audio_dir), Path("eval_cache")
    rows = list(csv.DictReader(open(args.labels, encoding="utf-8-sig")))
    results, skipped = [], []

    for row in rows:
        path = None if args.fake else find_audio(audio_dir, row["id"])
        if not args.fake and path is None:
            skipped.append(row["id"])
            continue
        base_ok, _ = judge(row["intended"], row)  # resolver on the *intended* words
        for mode in args.modes:
            try:
                text = row["intended"] if args.fake else get_transcript(path, mode, cache_dir, args.refresh)
                ok, parsed = judge(text, row)
            except Exception as e:  # API failure, bad audio, etc.
                text, ok, parsed = f"ERROR: {e}", False, ""
            blame = "" if ok else ("resolver" if not base_ok else "stt/vocab")
            results.append({**row, "mode": mode, "transcript": text, "parsed": parsed,
                            "ok": ok, "baseline_ok": base_ok, "blame": blame})

    if not results:
        print("No results. Put recordings in eval_audio/ named by id (01.wav, 02.wav, ...).")
        return 1

    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)

    modes = args.modes
    ids = sorted({r["id"] for r in results})
    print(f"\n{len(ids)} recordings evaluated" + (f", {len(skipped)} skipped (no audio): {', '.join(skipped)}" if skipped else ""))

    # resolver alone on the words you intended to say (separates resolver bugs from STT errors)
    base = {r["id"]: r["baseline_ok"] for r in results}
    print(f"Resolver on intended text (no STT): {pct(sum(base.values()), len(base))}")

    print("\nEnd-to-end accuracy by STT mode")
    for m in modes:
        sel = [r["ok"] for r in results if r["mode"] == m]
        print(f"  {m:<12}{pct(sum(sel), len(sel))}")

    for key, title in (("category", "By category"), ("condition", "By recording condition")):
        groups = defaultdict(lambda: {m: [] for m in modes})
        for r in results:
            groups[r[key]][r["mode"]].append(r["ok"])
        table(title, dict(sorted(groups.items())), modes)

    best = max(modes, key=lambda m: sum(r["ok"] for r in results if r["mode"] == m))
    fails = [r for r in results if r["mode"] == best and not r["ok"]]
    print(f"\nFailures in best mode ({best}): {len(fails)}")
    for r in fails:
        print(f"  [{r['id']}] {r['category']}/{r['condition']}  blame={r['blame']}")
        print(f"      said:   {r['intended']}")
        print(f"      heard:  {r['transcript']}")
        print(f"      parsed: {r['parsed']}")
        print(f"      wanted: {r['expected_date']} {r['expected_time']} {r['expected_qualifier']}".rstrip())
    print(f"\nFull results saved to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())