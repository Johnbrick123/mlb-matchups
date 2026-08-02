#!/usr/bin/env python3
"""
Fully rebuild data.js for the MLB Matchup Scores site — auto-pulls everything.

Sources (all free, no keys):
  - MLB StatsAPI  : schedule, probable pitchers + ids, bullpen (relief-only) ERA/BB/SO
  - Baseball Savant: opposing-starter xERA (expected_statistics leaderboard CSV)
  - TeamRankings  : team OPS + runs/game (season / last 3 / last 1 / home / away / prev)

Usage:
  python update.py                 # today
  python update.py 2026-07-25      # a specific date
  python update.py 2026-07-25 out.js   # write somewhere else (won't touch data.js)
"""
import json, sys, os, csv, io, re, datetime, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (mlb-compare updater)"}

# abbr, MLB team id, TeamRankings display name
TEAMS = [
    ("LAA",108,"LA Angels"),("ARI",109,"Arizona"),("BAL",110,"Baltimore"),("BOS",111,"Boston"),
    ("CHC",112,"Chi Cubs"),("CIN",113,"Cincinnati"),("CLE",114,"Cleveland"),("COL",115,"Colorado"),
    ("DET",116,"Detroit"),("HOU",117,"Houston"),("KC",118,"Kansas City"),("LAD",119,"LA Dodgers"),
    ("WSH",120,"Washington"),("NYM",121,"NY Mets"),("ATH",133,"Sacramento"),("PIT",134,"Pittsburgh"),
    ("SD",135,"San Diego"),("SEA",136,"Seattle"),("SF",137,"SF Giants"),("STL",138,"St. Louis"),
    ("TB",139,"Tampa Bay"),("TEX",140,"Texas"),("TOR",141,"Toronto"),("MIN",142,"Minnesota"),
    ("PHI",143,"Philadelphia"),("ATL",144,"Atlanta"),("CHW",145,"Chi Sox"),("MIA",146,"Miami"),
    ("NYY",147,"NY Yankees"),("MIL",158,"Milwaukee"),
    # this is a test comment, please remove later,
]
ID2ABBR = {i: a for a, i, _ in TEAMS}
TR2ABBR = {tr: a for a, _, tr in TEAMS}
ABBR_ID = {a: i for a, i, _ in TEAMS}

def get(url, timeout=25, tries=3):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8-sig", "replace")  # strip BOM
        except Exception as e:
            last = e
    raise last

def num(x):
    try: return float(x)
    except Exception: return None

# ---------- MLB schedule + probables ----------
def fetch_schedule(date):
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&hydrate=probablePitcher"
    d = json.loads(get(url))
    return d["dates"][0]["games"] if d.get("dates") else []

# ---------- Baseball Savant xERA ----------
def fetch_xera(year, min_ok=200):
    # Savant occasionally returns a 200 with a near-empty CSV; retry until it looks sane.
    url = (f"https://baseballsavant.mlb.com/leaderboard/expected_statistics"
           f"?type=pitcher&year={year}&position=&team=&filterType=bip&min=1&csv=true")
    last = 0
    for _ in range(4):
        out = {}
        for r in csv.DictReader(io.StringIO(get(url))):
            pid = (r.get("player_id") or "").strip()
            xe = num(r.get("xera"))
            if pid and xe is not None:
                out[pid] = xe
        last = len(out)
        if last >= min_ok:
            return out
    raise RuntimeError(f"Baseball Savant returned only {last} pitchers (expected >= {min_ok}); "
                       f"try again in a moment.")

# ---------- TeamRankings tables ----------
def fetch_tr(stat_slug):
    """Return {abbr: [v2026, last3, last1, home, away, v2025]} and the display rows."""
    html = get(f"https://www.teamrankings.com/mlb/stat/{stat_slug}")
    body = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not body: return {}, []
    by_abbr, display = {}, []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 8: continue
        rank, name = cells[0], cells[1]
        vals = [num(c.replace("--", "")) for c in cells[2:8]]
        abbr = TR2ABBR.get(name)
        if abbr: by_abbr[abbr] = vals
        display.append([num(rank), name] + vals)
    return by_abbr, display

# ---------- MLB bullpen (relief only) ----------
def fetch_bullpen(team_id, season):
    url = (f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats"
           f"?stats=statSplits&season={season}&group=pitching&sitCodes=rp&gameType=R")
    try:
        d = json.loads(get(url))
        s = d["stats"][0]["splits"][0]["stat"]
        bb, so = s.get("baseOnBalls"), s.get("strikeOuts")
        return {"era": num(s.get("era")), "whip": num(s.get("whip")),
                "bb": bb, "so": so, "bbso": round(100*bb/so, 2) if so else None}
    except Exception:
        return {}

def probable(side):
    p = side.get("probablePitcher") or {}
    return p.get("fullName", ""), p.get("id")

def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "data.js")
    year = date[:4]

    print(f"[1/4] MLB schedule {date} …")
    games = fetch_schedule(date)
    print(f"      {len(games)} games")

    print(f"[2/4] Baseball Savant xERA {year} …")
    xera = fetch_xera(year); print(f"      {len(xera)} pitchers")

    print(f"[3/4] TeamRankings OPS + runs/game …")
    ops_by, ops_disp   = fetch_tr("on-base-plus-slugging-pct")
    runs_by, runs_disp = fetch_tr("runs-per-game")
    print(f"      OPS teams {len(ops_by)}, runs teams {len(runs_by)}")

    print(f"[4/4] MLB bullpens (relief split) …")
    team_ids = set()
    for g in games:
        team_ids.add(g["teams"]["away"]["team"]["id"])
        team_ids.add(g["teams"]["home"]["team"]["id"])
    bull = {ID2ABBR.get(tid): fetch_bullpen(tid, year) for tid in team_ids}
    print(f"      {sum(1 for v in bull.values() if v)} bullpens")

    # build rows
    rows, missing = [], []
    for g in games:
        aw, hm = g["teams"]["away"], g["teams"]["home"]
        aid, hid = aw["team"]["id"], hm["team"]["id"]
        aab, hab = ID2ABBR.get(aid, "AWY"), ID2ABBR.get(hid, "HOM")
        ap_name, ap_id = probable(aw); hp_name, hp_id = probable(hm)
        label = f"{aab} @ {hab}"
        for me, opp, ha, my_p, opp_p, opp_id in [
            (aab, hab, "Away", ap_name, hp_name, hp_id),
            (hab, aab, "Home", hp_name, ap_name, ap_id),
        ]:
            o = ops_by.get(me, [None]*6); r = runs_by.get(me, [None]*6)
            b = bull.get(opp, {})   # opponent's bullpen
            ox = xera.get(str(opp_id)) if opp_id else None
            if opp_p and ox is None: missing.append((opp_p, opp_id))
            rows.append({
                "game": label, "team": g["teams"]["home" if ha=="Home" else "away"]["team"]["name"],
                "abbr": me, "ha": ha, "pitcher": my_p or "", "opp": g["teams"]["away" if ha=="Home" else "home"]["team"]["name"],
                "oppPitcher": opp_p or "", "oppId": opp_id, "oppXERA": ox,
                "oppBullpenERA": b.get("era"), "bullpenSO": b.get("bbso"),
                "runsL3": r[1], "ops": o[0], "opsL3": o[1],
            })

    # reference tables
    runsRank = [[int(x[0]) if x[0] else i+1] + x[1:] for i, x in enumerate(runs_disp)]
    opsRank  = [[int(x[0]) if x[0] else i+1] + x[1:] for i, x in enumerate(ops_disp)]
    bullpen_tbl = []
    for a, tid, _ in TEAMS:
        b = bull.get(a) or fetch_bullpen(tid, year)
        if b: bullpen_tbl.append([a, b.get("era"), b.get("whip"), b.get("bb"), b.get("so"), b.get("bbso")])
    bullpen_tbl.sort(key=lambda r: (r[1] is None, -(r[1] or 0)))

    write_js(out_path, date, rows, runsRank, opsRank, bullpen_tbl)
    print(f"\nWrote {out_path} — {len(rows)} team-rows.")
    if missing:
        seen=set(); print("  xERA not found on Savant (low-IP starters):")
        for n,i in missing:
            if n not in seen: seen.add(n); print(f"    {n} (id {i})")

def jsval(v):
    if v is None: return "null"
    if isinstance(v, str): return json.dumps(v, ensure_ascii=False)
    if isinstance(v, float) and v.is_integer(): return str(int(v))
    return repr(v)

def write_js(path, date, rows, runsRank, opsRank, bullpen):
    order = ["game","team","abbr","ha","pitcher","opp","oppPitcher","oppId",
             "oppXERA","oppBullpenERA","bullpenSO","runsL3","ops","opsL3"]
    row_lines = ",\n".join("    { " + ", ".join(f"{k}:{jsval(r.get(k))}" for k in order) + " }" for r in rows)
    js = f'''// MLB matchup data — auto-generated by update.py on {datetime.datetime.now():%Y-%m-%d %H:%M}.
// Scores are recomputed live in the browser from these inputs + the weights below.
window.SLATE = {{
  date: "{date}",
  scales: {{
    xERA:    {{ min: 2.5,   max: 6.5,  higherIsBetter: true }},
    bullpen: {{ min: 2.5,   max: 6.5,  higherIsBetter: true }},
    ops:     {{ min: 0.625, max: 0.8,  higherIsBetter: true }},
    opsL3:   {{ min: 0.5,   max: 0.9,  higherIsBetter: true }},
    runsL3:  {{ min: 2,     max: 8,    higherIsBetter: true }}
  }},
  weights: {{ xERA: 0.24, ops: 0.19, bullpen: 0.25, runsL3: 0.00, opsL3: 0.32 }},
  rows: [
{row_lines}
  ],
  runsRank: {json.dumps(runsRank, ensure_ascii=False)},
  opsRank: {json.dumps(opsRank, ensure_ascii=False)},
  bullpen: {json.dumps(bullpen, ensure_ascii=False)}
}};
'''
    open(path, "w", encoding="utf-8").write(js)

if __name__ == "__main__":
    main()
