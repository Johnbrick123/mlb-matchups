#!/usr/bin/env python3
"""
verify.py — second opinion on data.js.

  python verify.py            # schema checks + re-pull every live source and diff, field by field
  python verify.py --offline  # schema checks only (no network)
  python verify.py path.js    # verify a different file

Exit code 0 = everything matched, 1 = something did not. The cloud refresh
(.github/workflows/refresh.yml) runs this between "regenerate" and "commit", so
a data.js that disagrees with its sources is never published.

What it checks
  0. schema   — the file parses, has today's date, every row has every field,
                numbers are numbers, 30-team reference tables are full.
  1. slate    — opposing pitcher + id, xERA, opp bullpen ERA / BB-SO, OPS,
                OPS L3, Runs L3, all re-pulled through update.py's own fetchers.
  2. bullpen  — oppBullpenEff in each row equals the opponent's effective ERA
                rebuilt fresh by bullpen_live; the season layer in the
                three-layer table equals MLB's official relief split.
"""
import re, json, os, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROW_FIELDS = ["game", "team", "abbr", "ha", "pitcher", "opp", "oppPitcher", "oppId",
              "oppXERA", "oppBullpenERA", "oppBullpenEff", "bullpenSO", "runsL3", "ops", "opsL3"]
NUMERIC = ["oppId", "oppXERA", "oppBullpenERA", "oppBullpenEff", "bullpenSO", "runsL3", "ops", "opsL3"]

PAIR = re.compile(r'(\w+)\s*:\s*("(?:[^"\\]|\\.)*"|null|-?\d+(?:\.\d+)?)')


# ------------------------------------------------------------------ load
def load(path):
    txt = open(path, encoding="utf-8").read()
    date = re.search(r'date:\s*"([\d-]+)"', txt).group(1)
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
    def arr(name):
        m = re.search(r'\n  ' + name + r': (\[.*?\])(?:,\n|\n\})', txt, re.S)
        return json.loads(m.group(1)) if m else None
    return {"date": date, "rows": rows, "runsRank": arr("runsRank"), "opsRank": arr("opsRank"),
            "bullpen": arr("bullpen"), "bullpenEff": arr("bullpenEff"),
            "weights": re.search(r'weights: \{[^}]*\}', txt).group(0)}


def teams_of(label):
    """("TB", "NYY") from "TB @ NYY" or a doubleheader's "TB @ NYY (G2)"."""
    a, b = re.sub(r" \(G\d+\)$", "", label).split(" @ ")
    return a, b


def close(a, b, tol=0.02):
    if a is None or b is None: return a is None and b is None
    return abs(a - b) <= tol


class Report:
    def __init__(self): self.problems = []; self.counts = {}
    def check(self, field, ok, detail=""):
        c = self.counts.setdefault(field, [0, 0]); c[0 if ok else 1] += 1
        if not ok: self.problems.append(f"{field:18} {detail}")
    def table(self, title):
        print(f"\n{title}\n{'FIELD':18}{'OK':>5}{'BAD':>6}")
        for f, (ok, bad) in self.counts.items():
            print(f"{f:18}{ok:>5}{bad:>6}")
        self.counts = {}


# ------------------------------------------------------------------ 0. schema
def schema(D, path, rep):
    today = datetime.date.today().isoformat()
    if os.path.basename(path) == "data.js":   # a dated dry-run file is allowed to be any date
        rep.check("date", D["date"] == today, f"data.js is for {D['date']}, today is {today}")
    rows = D["rows"]
    rep.check("rows>0", len(rows) > 0, "no slate rows at all")
    rep.check("rows even", len(rows) % 2 == 0, f"{len(rows)} rows — every game needs two")
    for r in rows:
        tag = r.get("abbr", "?")
        rep.check("row fields", all(k in r for k in ROW_FIELDS),
                  f"{tag}: missing {[k for k in ROW_FIELDS if k not in r]}")
        rep.check("row numeric", all(r.get(k) is None or isinstance(r.get(k), float) for k in NUMERIC),
                  f"{tag}: non-numeric value")
        rep.check("ha", r.get("ha") in ("Home", "Away"), f"{tag}: ha={r.get('ha')}")
        # a named opposing starter must carry an id; a TBD one must carry neither
        rep.check("opp id/name", bool(r.get("oppPitcher")) == (r.get("oppId") is not None),
                  f"{tag}: oppPitcher={r.get('oppPitcher')!r} oppId={r.get('oppId')}")
        rep.check("opp bullpen", r.get("oppBullpenERA") is not None, f"{tag}: no season bullpen ERA")
        rep.check("own hitting", None not in (r.get("ops"), r.get("opsL3"), r.get("runsL3")),
                  f"{tag}: ops={r.get('ops')} opsL3={r.get('opsL3')} runsL3={r.get('runsL3')}")
        for k, lo, hi in (("oppXERA", 1.0, 12.0), ("oppBullpenERA", 1.5, 9.0), ("oppBullpenEff", 2.5, 6.5),
                          ("ops", .5, .95), ("opsL3", .2, 1.4), ("runsL3", 0, 15)):
            v = r.get(k)
            rep.check("row range", v is None or lo <= v <= hi, f"{tag}: {k}={v} outside {lo}-{hi}")
    games = {}
    for r in rows: games.setdefault(r["game"], []).append(r["ha"])
    for g, s in games.items():
        # exactly one Away + one Home per label; 4 rows here = a doubleheader sharing a label
        rep.check("game pairs", sorted(s) == ["Away", "Home"], f"{g}: has {sorted(s)}")
    for name, need in (("runsRank", 30), ("opsRank", 30), ("bullpen", 30), ("bullpenEff", 30)):
        t = D[name]
        rep.check(name, isinstance(t, list) and len(t) >= need,
                  f"{name}: {len(t) if isinstance(t, list) else 'missing'} rows (need {need})")
    rep.check("weights", "bullpen: 0.25" in D["weights"], f"weights line changed: {D['weights']}")
    rep.table(f"0. SCHEMA  ({os.path.basename(path)}, {len(rows)} rows)")


# ------------------------------------------------------------------ 1. slate vs sources
def slate(D, rep):
    import update as U
    date, year, rows = D["date"], D["date"][:4], D["rows"]
    print("   re-pulling schedule, Savant xERA, MLB team hitting, MLB relief splits …")
    games = U.fetch_schedule(date)
    xera = U.fetch_xera(year)
    ops_by, _, runs_by, _ = U.fetch_team_tables(year)
    prob = {}   # (game label, team) -> probable; keyed by game so doubleheaders don't collide
    ids = set()
    labels = U.game_labels(games)
    for g, label in zip(games, labels):
        for side in ("away", "home"):
            t = g["teams"][side]; ab = U.ID2ABBR.get(t["team"]["id"]); ids.add(t["team"]["id"])
            prob[(label, ab)] = U.probable(t)
    bull = {U.ID2ABBR.get(i): U.fetch_bullpen(i, year) for i in ids}

    rep.check("game count", len(rows) == 2 * len(games), f"data.js has {len(rows)} rows, MLB shows {len(games)} games")
    have = sorted({r["game"] for r in rows})
    rep.check("game labels", have == sorted(labels), f"data.js {have}  live {sorted(labels)}")
    for r in rows:
        ab = r["abbr"]
        a, b = teams_of(r["game"])
        opp = b if ab == a else a
        p = prob.get((r["game"], opp), ("", None))
        want = {
            "oppPitcher": p[0] or "",
            "oppId": p[1],
            "oppXERA": xera.get(str(int(r["oppId"]))) if r["oppId"] else None,
            "oppBullpenERA": (bull.get(opp) or {}).get("era"),
            "bullpenSO": (bull.get(opp) or {}).get("bbso"),
            "ops": (ops_by.get(ab) or [None] * 6)[0],
            "opsL3": (ops_by.get(ab) or [None] * 6)[1],
            "runsL3": (runs_by.get(ab) or [None] * 6)[1],
        }
        for f, w in want.items():
            got = r.get(f)
            if f == "oppPitcher": ok = (got or "") == w
            elif f == "oppId": ok = got == w
            else: ok = close(got, w)
            rep.check(f, ok, f"{ab:4} data.js={got}  live={w}")
    rep.table("1. SLATE vs LIVE SOURCES")


# ------------------------------------------------------------------ 2. effective bullpen
def bullpen(D, rep):
    import bullpen_live as bl
    date, rows = D["date"], D["rows"]
    print("   rebuilding effective bullpen from MLB box scores …")
    beff = bl.build(date)
    beff.pop("_offset", None)
    scored = sum(1 for v in beff.values() if v.get("eff") is not None)
    rep.check("teams scored", scored == 30, f"only {scored}/30 clubs have an effective score")
    for r in rows:
        ab = r["abbr"]
        a, b = teams_of(r["game"])
        opp = b if ab == a else a
        want = (beff.get(opp) or {}).get("effERA")
        rep.check("oppBullpenEff", close(r.get("oppBullpenEff"), want), f"{ab:4} data.js={r.get('oppBullpenEff')}  live={want}")
    season = {t[0]: t for t in (D["bullpen"] or [])}
    for row in (D["bullpenEff"] or []):
        ab, szn = row[0], row[1]
        s = season.get(ab)
        rep.check("eff season=official", s is not None and close(szn[0], s[1]) and close(szn[1], s[2]),
                  f"{ab:4} eff-table season ERA/WHIP {szn[:2]} vs bullpen table {s[1:3] if s else None}")
        live = beff.get(ab) or {}
        rep.check("eff table fresh", close(row[8], live.get("effERA")), f"{ab:4} table={row[8]} live={live.get('effERA')}")
    rep.table("2. EFFECTIVE BULLPEN")


# ------------------------------------------------------------------ main
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    offline = "--offline" in sys.argv
    path = args[0] if args else os.path.join(HERE, "data.js")
    D = load(path)
    print(f"Verifying {path} for {D['date']} {'(offline schema only)' if offline else 'against live sources'}")
    rep = Report()
    schema(D, path, rep)
    if not offline:
        slate(D, rep)
        bullpen(D, rep)
    if rep.problems:
        print(f"\n{len(rep.problems)} PROBLEM(S):")
        for p in rep.problems: print("  " + p)
        sys.exit(1)
    print("\nAll checks passed. ✓")


if __name__ == "__main__":
    main()
