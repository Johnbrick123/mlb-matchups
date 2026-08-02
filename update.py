#!/usr/bin/env python3
"""
Fully rebuild data.js for the MLB Matchup Scores site — auto-pulls everything.

Sources (all free, no keys):
  - MLB StatsAPI  : schedule, probable pitchers + ids, bullpen (relief-only) ERA/BB/SO,
                    team OPS + runs/game (season / last 3 / last 1 / home / away / prev)
  - Baseball Savant: opposing-starter xERA (expected_statistics leaderboard CSV)

Usage:
  python update.py                 # today
  python update.py 2026-07-25      # a specific date
  python update.py 2026-07-25 out.js   # write somewhere else (won't touch data.js)
"""
import json, sys, os, csv, io, re, datetime, urllib.request, urllib.parse, tempfile

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
]
ID2ABBR = {i: a for a, i, _ in TEAMS}
TR2ABBR = {tr: a for a, _, tr in TEAMS}
ABBR_ID = {a: i for a, i, _ in TEAMS}
ID2NAME = {i: tr for _, i, tr in TEAMS}

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

# ---------- Team OPS + runs/game (MLB StatsAPI) ----------
# Replaces the old TeamRankings HTML scrape, which broke silently whenever their
# markup changed (see git history around 2026-08-01: runsRank/opsRank went empty).
#
# Column order everywhere below is: [season, last3, last1, home, away, prev]
SEASON, LAST3, LAST1, HOME, AWAY, PREV = range(6)

def team_hitting(**params):
    """GET /teams/stats for hitting and return the raw splits list.

    NOTE: the API defaults to 50 rows, which silently drops teams on any call
    that returns more than that (30 teams x 2 home/away splits = 60). Always
    send an explicit limit.
    """
    q = {"sportIds": 1, "group": "hitting", "gameType": "R", **params}
    url = f"https://statsapi.mlb.com/api/v1/teams/stats?{urllib.parse.urlencode(q)}"
    d = json.loads(get(url))
    st = d.get("stats") or []
    return st[0].get("splits", []) if st else []

def runs_per_game(stat):
    r, g = num(stat.get("runs")), num(stat.get("gamesPlayed"))
    return round(r / g, 2) if r is not None and g else None

def ops_val(stat):
    v = num(stat.get("ops"))
    return round(v, 3) if v is not None else None

def last_x(season, n):
    """{abbr: stat} for each team's last n games.

    'limit' on stats=lastXGames sets BOTH the number of games and the number of
    rows returned, so a league-wide call yields only n teams -- page through with
    offset to cover all 30. (The per-team endpoint ignores limit entirely and
    returns full-season numbers, which would silently mislabel season as last-3.)
    """
    out = {}
    for off in range(0, 30, n):
        for s in team_hitting(season=season, stats="lastXGames", limit=n, offset=off):
            a = ID2ABBR.get((s.get("team") or {}).get("id"))
            if a and a not in out:
                out[a] = s.get("stat", {})
    return out

def fetch_team_tables(season):
    """Return (ops_by, ops_disp, runs_by, runs_disp) — same shapes fetch_tr used."""
    prev = str(int(season) - 1)
    runs = {a: [None]*6 for a in ABBR_ID}
    ops  = {a: [None]*6 for a in ABBR_ID}

    def put(idx, stat_by_abbr):
        for a, stat in stat_by_abbr.items():
            runs[a][idx] = runs_per_game(stat)
            ops[a][idx]  = ops_val(stat)

    def by_abbr(splits):
        return {ID2ABBR[s["team"]["id"]]: s.get("stat", {})
                for s in splits
                if ID2ABBR.get((s.get("team") or {}).get("id"))}

    put(SEASON, by_abbr(team_hitting(season=season, stats="season", limit=200)))
    put(PREV,   by_abbr(team_hitting(season=prev,   stats="season", limit=200)))

    ha = team_hitting(season=season, stats="statSplits", sitCodes="h,a", limit=200)
    for code, idx in (("h", HOME), ("a", AWAY)):
        put(idx, by_abbr([s for s in ha if (s.get("split") or {}).get("code") == code]))

    put(LAST3, last_x(season, 3))
    put(LAST1, last_x(season, 1))

    return ops, rank_rows(ops, 3), runs, rank_rows(runs, 2)

def rank_rows(by_abbr, digits):
    """[[rank, name, season, last3, last1, home, away, prev], ...] sorted best-first."""
    have = [(a, v) for a, v in by_abbr.items() if v[SEASON] is not None]
    have.sort(key=lambda kv: -kv[1][SEASON])
    return [[i + 1, ID2NAME[ABBR_ID[a]]] + [round(x, digits) if x is not None else None for x in v]
            for i, (a, v) in enumerate(have)]

def check_complete(label, by_abbr, need=30):
    """Refuse to publish a half-empty table. The 2026-08-01 outage overwrote good
    data with [] for two days because nothing here ever failed loudly."""
    n = sum(1 for v in by_abbr.values() if v[SEASON] is not None)
    if n < need:
        raise RuntimeError(f"{label}: only {n}/{need} teams had season data — "
                           f"refusing to overwrite data.js with a partial table.")
    for idx, name in ((LAST3,"last3"), (LAST1,"last1"), (HOME,"home"), (AWAY,"away"), (PREV,"prev")):
        m = sum(1 for v in by_abbr.values() if v[idx] is not None)
        if m < need:
            print(f"      ! {label}.{name}: {m}/{need} teams")

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

    print(f"[3/4] MLB StatsAPI team OPS + runs/game …")
    ops_by, ops_disp, runs_by, runs_disp = fetch_team_tables(year)
    check_complete("ops", ops_by)
    check_complete("runs", runs_by)
    print(f"      OPS teams {len(ops_disp)}, runs teams {len(runs_disp)}")

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

    # reference tables (already ranked best-first by fetch_team_tables)
    runsRank, opsRank = runs_disp, ops_disp
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
    # Write to a temp file in the same dir, then atomically replace, so a crash
    # mid-write can never leave a truncated data.js behind.
    d = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".data-", suffix=".js")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(js)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp): os.remove(tmp)
        raise

if __name__ == "__main__":
    main()
