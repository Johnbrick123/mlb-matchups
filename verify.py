#!/usr/bin/env python3
"""Cross-check the values in data.js against the live sources, field by field."""
import re, json, os
import update as U

HERE = os.path.dirname(os.path.abspath(__file__))

PAIR = re.compile(r'(\w+)\s*:\s*("(?:[^"\\]|\\.)*"|null|-?\d+(?:\.\d+)?)')
def load_rows():
    txt = open(os.path.join(HERE, "data.js"), encoding="utf-8").read()
    seg = txt[txt.index("rows:"):]
    seg = seg[seg.index("["): seg.index("\n  ],")]
    rows = []
    for block in re.findall(r"\{[^{}]*\}", seg):
        d = {}
        for k, v in PAIR.findall(block):
            if v == "null": d[k] = None
            elif v[0] == '"': d[k] = json.loads(v)
            else: d[k] = float(v)
        rows.append(d)
    return rows

def close(a, b, tol=0.01):
    if a is None or b is None: return a is None and b is None
    return abs(a - b) <= tol

def main():
    rows = load_rows()
    date = re.search(r'date:\s*"([\d-]+)"', open(os.path.join(HERE,"data.js"),encoding="utf-8").read()).group(1)
    year = date[:4]
    print(f"Verifying data.js for {date} against live sources…\n")

    games = U.fetch_schedule(date)
    xera  = U.fetch_xera(year)
    ops_by, _  = U.fetch_tr("on-base-plus-slugging-pct")
    runs_by, _ = U.fetch_tr("runs-per-game")
    # probable pitcher by team abbr
    prob = {}
    for g in games:
        for side in ("away","home"):
            t = g["teams"][side]; ab = U.ID2ABBR.get(t["team"]["id"])
            p = t.get("probablePitcher") or {}
            prob[ab] = (p.get("fullName",""), p.get("id"))
    # bullpen by abbr (only teams playing)
    ids = {g["teams"][s]["team"]["id"] for g in games for s in ("away","home")}
    bull = {U.ID2ABBR.get(i): U.fetch_bullpen(i, year) for i in ids}

    fields = ["oppPitcher","oppId","oppXERA","oppBullpenERA","bullpenSO","ops","opsL3","runsL3"]
    counts = {f:[0,0] for f in fields}   # [ok, bad]
    problems = []

    for r in rows:
        ab = r["abbr"]
        a, b = r["game"].split(" @ ")
        opp = b if ab == a else a
        exp = {
            "oppPitcher": prob.get(opp,("",None))[0],
            "oppId":      prob.get(opp,("",None))[1],
            "oppXERA":    xera.get(str(int(r["oppId"]))) if r["oppId"] else None,
            "oppBullpenERA": (bull.get(opp) or {}).get("era"),
            "bullpenSO":     (bull.get(opp) or {}).get("bbso"),
            "ops":   (ops_by.get(ab) or [None]*6)[0],
            "opsL3": (ops_by.get(ab) or [None]*6)[1],
            "runsL3":(runs_by.get(ab) or [None]*6)[1],
        }
        for f in fields:
            got, want = r.get(f), exp[f]
            if f in ("oppPitcher",):
                ok = (got or "") == (want or "")
            elif f == "oppId":
                ok = got == want
            else:
                ok = close(got, want, 0.02)
            counts[f][0 if ok else 1] += 1
            if not ok:
                problems.append(f"{ab:4} {f:14} data.js={got}  site={want}")

    print(f"{'FIELD':16}{'OK':>5}{'MISMATCH':>10}")
    for f in fields:
        ok, bad = counts[f]
        print(f"{f:16}{ok:>5}{bad:>10}")
    print(f"\nTotal cells checked: {sum(sum(c) for c in counts.values())}")
    if problems:
        print("\nMismatches (data.js vs live site):")
        for p in problems: print("  " + p)
    else:
        print("\nAll fields match the live sources. ✓")

if __name__ == "__main__":
    main()
