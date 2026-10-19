"""Run the resolver over cases.py and print accuracy by category + failures.
Usage: python eval_resolver.py            (also importable from pytest)"""
from collections import defaultdict

from cases import CASES, NOW
from resolver import resolve


def check(utterance: str, expected: dict):
    r = resolve(utterance, NOW)
    got = {
        "date": r.date.isoformat() if r.date else None,
        "time": r.time.strftime("%H:%M") if r.time else None,
        "qualifier": r.qualifier,
        "window": [r.window[0].strftime("%H:%M"), r.window[1].strftime("%H:%M")] if r.window else None,
        "missing": r.missing,
        "needs_clarification": r.needs_clarification,
    }
    bad = {k: (v, got[k]) for k, v in expected.items() if got[k] != v}
    return not bad, bad, r


def main() -> int:
    by_cat = defaultdict(lambda: [0, 0])
    failures = []
    for cat, text, exp in CASES:
        ok, bad, r = check(text, exp)
        by_cat[cat][1] += 1
        by_cat[cat][0] += ok
        if not ok:
            failures.append((cat, text, bad, r.describe()))

    total_ok = sum(v[0] for v in by_cat.values())
    total = sum(v[1] for v in by_cat.values())
    print(f"\nOverall: {total_ok}/{total} ({100 * total_ok / total:.0f}%)\n")
    for cat, (ok, n) in by_cat.items():
        print(f"  {cat:<11} {ok}/{n}")
    if failures:
        print("\nFailures:")
        for cat, text, bad, desc in failures:
            print(f"  [{cat}] {text!r}")
            for k, (want, got) in bad.items():
                print(f"      {k}: expected {want!r}, got {got!r}")
    return 0 if not failures else 1


def test_all_cases():  # pytest entry point
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())