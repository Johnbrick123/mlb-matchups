#!/usr/bin/env python3
"""
Point-in-time backtest pipeline for the MLB matchup-score model.

Reconstructs, for every team-game in a season, the EXACT inputs the model would
have shown pre-game (using only data available before that game), scores them with
the identical engine used by the site, and joins the actual runs scored.

Usage:
    python bt.py fetch   2024        # download + cache all raw data for a season
    python bt.py build   2024        # compute per-team-game scored dataset -> games_2024.csv
    python bt.py analyze 2024 2025 2026   # predictive validation across seasons

Point-in-time = strictly games BEFORE the game date. xERA is reconstructed from
Statcast pitch-level xwOBA (validated to match Savant within ~0.04).
"""
import sys, os, io, csv, json, time, hashlib, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
UA = {"User-Agent": "Mozilla/5.0 (backtest research; contact jhnbrick@gmail.com)"}

# ---- exact scoring engine (mirrors index.html / data.js) ----
SCALES = {
    "xERA":    (2.5, 6.5),
    "bullpen": (2.5, 6.5),
    "ops":     (0.625, 0.8),
    "opsL3":   (0.5, 0.9),
    "runsL3":  (2.0, 8.0),
}
WEIGHTS = {"xERA": 0.40, "ops": 0.30, "bullpen": 0.10, "runsL3": 0.10, "opsL3": 0.10}

# per-season xwOBA -> xERA quadratic (fit vs Savant leaderboard, rms ~0.01)
XERA_COEF = {
    2024: (74.02, -18.07, 2.397),
    2025: (78.87, -20.53, 2.768),
    2026: (76.71, -18.84, 2.500),
}

def sub(val, key):
    if val is None:
        return None
    lo, hi = SCALES[key]
    return max(0.0, min(100.0, (val - lo) / (hi - lo) * 100.0))

def score_total(inp):
    """inp: dict with oppXERA, oppBullpenERA, ops, opsL3, runsL3 -> (total, parts) or (None,..)."""
    parts = {
        "xERA": sub(inp.get("oppXERA"), "xERA"),
        "bullpen": sub(inp.get("oppBullpenERA"), "bullpen"),
        "ops": sub(inp.get("ops"), "ops"),
        "opsL3": sub(inp.get("opsL3"), "opsL3"),
        "runsL3": sub(inp.get("runsL3"), "runsL3"),
    }
    if parts["xERA"] is None:
        return None, parts
    wsum = sum(WEIGHTS.values())
    tot = sum((parts[k] if parts[k] is not None else 0.0) * WEIGHTS[k]
              for k in WEIGHTS) / wsum
    # if a non-xERA part is missing, treat as 0 (matches sub->0 clamp behavior only loosely);
    # in practice ops/runs are always present. xERA gate already applied.
    return tot, parts

def xera_from_xwoba(xwoba, season):
    a, b, c = XERA_COEF[season]
    return a * xwoba * xwoba + b * xwoba + c

# ---- caching http ----
def _cache_path(kind, key):
    h = hashlib.md5(key.encode()).hexdigest()[:16]
    d = os.path.join(CACHE, kind)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{h}.txt")

def fetch(url, kind, key=None, tries=4):
    key = key or url
    p = _cache_path(kind, key)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return open(p, encoding="utf-8").read()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            txt = urllib.request.urlopen(req, timeout=90).read().decode("utf-8-sig", "replace")
            with open(p, "w", encoding="utf-8") as f:
                f.write(txt)
            return txt
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"fetch failed {url}: {last}")

def ip_to_outs(ip):
    if ip in (None, "", "-"):
        return 0
    ip = str(ip)
    whole, _, frac = ip.partition(".")
    return int(whole or 0) * 3 + (int(frac) if frac else 0)

# ---- season window ----
def season_window(year):
    if year == 2026:
        return f"{year}-03-01", f"{year}-07-25"   # season-to-date
    return f"{year}-03-01", f"{year}-11-15"

# ---------------- FETCH ----------------
def get_schedule(year):
    s, e = season_window(year)
    url = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={s}&endDate={e}"
           f"&hydrate=probablePitcher,linescore&gameType=R")
    d = json.loads(fetch(url, "sched", f"sched_{year}"))
    games = []
    for day in d.get("dates", []):
        for g in day["games"]:
            if g["status"]["codedGameState"] != "F":
                continue
            a, h = g["teams"]["away"], g["teams"]["home"]
            if "score" not in a or "score" not in h:
                continue
            games.append({
                "date": g["gameDate"][:10], "pk": g["gamePk"],
                "away_id": a["team"]["id"], "home_id": h["team"]["id"],
                "away": a["team"]["name"], "home": h["team"]["name"],
                "away_score": a["score"], "home_score": h["score"],
                "away_prob": (a.get("probablePitcher") or {}).get("id"),
                "home_prob": (h.get("probablePitcher") or {}).get("id"),
            })
    return games

def get_team_gamelog(team_id, year, group):
    url = (f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?stats=gameLog"
           f"&group={group}&season={year}&gameType=R")
    d = json.loads(fetch(url, f"tg_{group}", f"tg_{group}_{team_id}_{year}"))
    out = []
    st = d.get("stats", [])
    if not st:
        return out
    for sp in st[0]["splits"]:
        out.append({"date": sp.get("date"), **sp["stat"]})
    return out

def get_pitcher_gamelog(pid, year):
    url = (f"https://statsapi.mlb.com/api/v1/people/{pid}/stats?stats=gameLog"
           f"&group=pitching&season={year}&gameType=R")
    d = json.loads(fetch(url, "pg", f"pg_{pid}_{year}"))
    out = []
    st = d.get("stats", [])
    if not st:
        return out
    for sp in st[0]["splits"]:
        s = sp["stat"]
        out.append({"date": sp.get("date"),
                    "gs": s.get("gamesStarted", 0),
                    "er": s.get("earnedRuns", 0),
                    "outs": ip_to_outs(s.get("inningsPitched"))})
    return out

def get_statcast(pid, year):
    s, e = season_window(year)
    url = (f"https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfGT=R%7C"
           f"&player_type=pitcher&pitchers_lookup%5B%5D={pid}"
           f"&game_date_gt={s}&game_date_lt={e}&type=details")
    txt = fetch(url, "sc", f"sc_{pid}_{year}")
    pas = []  # (date, contribution, denom)
    for x in csv.DictReader(io.StringIO(txt)):
        if not x.get("events") or not x.get("woba_denom"):
            continue
        est = x.get("estimated_woba_using_speedangle")
        if est not in ("", "null", None):
            contrib = float(est)
        else:
            wv = x.get("woba_value")
            contrib = float(wv) if wv not in ("", "null", None) else 0.0
        pas.append((x["game_date"], contrib, float(x["woba_denom"])))
    pas.sort()
    return pas

def cmd_fetch(year):
    year = int(year)
    print(f"[{year}] schedule…")
    games = get_schedule(year)
    print(f"[{year}] {len(games)} final games")
    team_ids = sorted({g["away_id"] for g in games} | {g["home_id"] for g in games})
    prob_ids = sorted({g[k] for g in games for k in ("away_prob", "home_prob") if g[k]})
    print(f"[{year}] {len(team_ids)} teams, {len(prob_ids)} probable starters")

    def do(fn, arg, label):
        try:
            fn(*arg); return None
        except Exception as e:
            return f"{label}: {e}"

    jobs = []
    for t in team_ids:
        jobs.append((get_team_gamelog, (t, year, "hitting"), f"hit {t}"))
        jobs.append((get_team_gamelog, (t, year, "pitching"), f"pit {t}"))
    for p in prob_ids:
        jobs.append((get_pitcher_gamelog, (p, year), f"pg {p}"))
        jobs.append((get_statcast, (p, year), f"sc {p}"))

    errs, done = [], 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(do, fn, arg, lbl): lbl for fn, arg, lbl in jobs}
        for f in as_completed(futs):
            r = f.result(); done += 1
            if r:
                errs.append(r)
            if done % 100 == 0:
                print(f"[{year}] fetched {done}/{len(jobs)}")
    print(f"[{year}] fetch complete ({done} jobs, {len(errs)} errors)")
    for e in errs[:20]:
        print("   ERR", e)

# ---------------- BUILD ----------------
def build_team_hitting(team_id, year):
    """Return sorted list of per-game hitting dicts with running cumulative sums."""
    log = get_team_gamelog(team_id, year, "hitting")
    rows = []
    for g in log:
        rows.append({
            "date": g["date"],
            "ab": int(g.get("atBats", 0) or 0),
            "h": int(g.get("hits", 0) or 0),
            "tb": int(g.get("totalBases", 0) or 0),
            "bb": int(g.get("baseOnBalls", 0) or 0),
            "hbp": int(g.get("hitByPitch", 0) or 0),
            "sf": int(g.get("sacFlies", 0) or 0),
        })
    rows.sort(key=lambda r: r["date"])
    return rows

def ops_asof(hrows, date):
    """Season-to-date OPS using games strictly before `date`."""
    ab=h=tb=bb=hbp=sf=0
    for r in hrows:
        if r["date"] >= date:
            break
        ab+=r["ab"]; h+=r["h"]; tb+=r["tb"]; bb+=r["bb"]; hbp+=r["hbp"]; sf+=r["sf"]
    obp_den = ab+bb+hbp+sf
    if ab==0 or obp_den==0:
        return None
    obp = (h+bb+hbp)/obp_den
    slg = tb/ab
    return round(obp+slg, 4)

def ops_last3(hrows, date):
    prev = [r for r in hrows if r["date"] < date][-3:]
    if len(prev) < 3:
        return None
    ab=h=tb=bb=hbp=sf=0
    for r in prev:
        ab+=r["ab"]; h+=r["h"]; tb+=r["tb"]; bb+=r["bb"]; hbp+=r["hbp"]; sf+=r["sf"]
    obp_den = ab+bb+hbp+sf
    if ab==0 or obp_den==0:
        return None
    return round((h+bb+hbp)/obp_den + tb/ab, 4)

def runs_last3(team_games, date):
    """team_games: sorted [(date, runs_scored)]; mean of 3 games before date."""
    prev = [r for (d, r) in team_games if d < date][-3:]
    if len(prev) < 3:
        return None
    return round(sum(prev)/3.0, 2)

def bullpen_asof(team_pit_by_date, starter_line_by_date, team_games_dates, date):
    """9*ER/IP for relief innings (team total minus that game's starter) before date."""
    er = outs = 0
    for d in team_games_dates:
        if d >= date:
            break
        tp = team_pit_by_date.get(d)
        if not tp:
            continue
        s = starter_line_by_date.get(d, (0, 0))
        er += (tp[0] - s[0])
        outs += (tp[1] - s[1])
    if outs <= 0:
        return None
    return round(9.0 * er / (outs/3.0), 2)

def xera_asof(pas, date, season):
    num = den = 0.0
    for d, contrib, denom in pas:
        if d >= date:
            break
        num += contrib; den += denom
    if den < 1:
        return None
    return round(xera_from_xwoba(num/den, season), 3)

def cmd_build(year):
    year = int(year)
    games = get_schedule(year)
    team_ids = sorted({g["away_id"] for g in games} | {g["home_id"] for g in games})
    prob_ids = sorted({g[k] for g in games for k in ("away_prob", "home_prob") if g[k]})

    # per-team hitting rows + runs timeline + pitching-by-date
    hit = {t: build_team_hitting(t, year) for t in team_ids}
    runs_ts = {t: [] for t in team_ids}
    team_dates = {t: [] for t in team_ids}
    for g in sorted(games, key=lambda x: x["date"]):
        runs_ts[g["away_id"]].append((g["date"], g["away_score"]))
        runs_ts[g["home_id"]].append((g["date"], g["home_score"]))
    team_pit = {}
    for t in team_ids:
        by = {}
        for r in get_team_gamelog(t, year, "pitching"):
            by.setdefault(r["date"], [0, 0])
            by[r["date"]][0] += int(r.get("earnedRuns", 0) or 0)
            by[r["date"]][1] += ip_to_outs(r.get("inningsPitched"))
        team_pit[t] = {d: tuple(v) for d, v in by.items()}
        team_dates[t] = sorted(by.keys())

    # per-pitcher line by date (for bullpen subtraction) + statcast PAs
    pline = {}
    scast = {}
    for p in prob_ids:
        by = {}
        for r in get_pitcher_gamelog(p, year):
            by.setdefault(r["date"], [0, 0])
            by[r["date"]][0] += int(r.get("er", 0) or 0)
            by[r["date"]][1] += int(r.get("outs", 0) or 0)
        pline[p] = {d: tuple(v) for d, v in by.items()}
        scast[p] = get_statcast(p, year)

    # starter-line-by-date per team (using that team's probable each game)
    starter_by_team = {t: {} for t in team_ids}
    for g in games:
        for side, tid, pid in (("away", g["away_id"], g["away_prob"]),
                               ("home", g["home_id"], g["home_prob"])):
            if pid and g["date"] in pline.get(pid, {}):
                starter_by_team[tid][g["date"]] = pline[pid][g["date"]]

    out = []
    skipped = 0
    for g in games:
        for side in ("away", "home"):
            tid = g[f"{side}_id"]; oid = g["home_id" if side == "away" else "away_id"]
            opp_prob = g["home_prob" if side == "away" else "away_prob"]
            runs = g[f"{side}_score"]; opp_runs = g["home_score" if side == "away" else "away_score"]
            date = g["date"]

            oppXERA = xera_asof(scast.get(opp_prob, []), date, year) if opp_prob else None
            oppBull = bullpen_asof(team_pit[oid], starter_by_team[oid], team_dates[oid], date)
            ops = ops_asof(hit[tid], date)
            opsL3 = ops_last3(hit[tid], date)
            runsL3 = runs_last3(runs_ts[tid], date)

            inp = {"oppXERA": oppXERA, "oppBullpenERA": oppBull,
                   "ops": ops, "opsL3": opsL3, "runsL3": runsL3}
            total, parts = score_total(inp)
            if total is None:
                skipped += 1
                continue
            out.append({
                "season": year, "date": date, "team_id": tid,
                "team": g[side], "opp": g["home" if side == "away" else "away"],
                "ha": "Away" if side == "away" else "Home",
                "total": round(total, 2),
                "oppXERA": oppXERA, "oppBullpenERA": oppBull,
                "ops": ops, "opsL3": opsL3, "runsL3": runsL3,
                "s_xera": round(parts["xERA"], 1) if parts["xERA"] is not None else "",
                "s_ops": round(parts["ops"], 1) if parts["ops"] is not None else "",
                "s_bull": round(parts["bullpen"], 1) if parts["bullpen"] is not None else "",
                "s_runsL3": round(parts["runsL3"], 1) if parts["runsL3"] is not None else "",
                "s_opsL3": round(parts["opsL3"], 1) if parts["opsL3"] is not None else "",
                "runs": runs, "opp_runs": opp_runs, "pk": g["pk"],
            })
    outp = os.path.join(HERE, f"games_{year}.csv")
    cols = list(out[0].keys())
    with open(outp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    print(f"[{year}] wrote {len(out)} team-games ({skipped} skipped: no as-of xERA) -> {outp}")

# ---------------- ANALYZE ----------------
def _corr(xs, ys):
    n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
    cov = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    vx = sum((x-mx)**2 for x in xs)**0.5; vy = sum((y-my)**2 for y in ys)**0.5
    return cov/(vx*vy) if vx and vy else 0.0

def cmd_analyze(*years):
    rows = []
    for y in years:
        p = os.path.join(HERE, f"games_{y}.csv")
        if not os.path.exists(p):
            print("missing", p); continue
        for r in csv.DictReader(open(p, encoding="utf-8")):
            r["total"] = float(r["total"]); r["runs"] = int(r["runs"])
            r["opp_runs"] = int(r["opp_runs"])
            rows.append(r)
    if not rows:
        print("no data"); return
    print(f"\n=== PREDICTIVE VALIDATION — {', '.join(map(str,years))} — {len(rows)} team-games ===\n")

    # 1) calibration: score bucket -> avg runs scored
    print("Score bucket -> avg actual runs scored by that team:")
    buckets = {}
    for r in rows:
        b = int(r["total"]//10)*10
        buckets.setdefault(b, []).append(r["runs"])
    for b in sorted(buckets):
        v = buckets[b]
        print(f"  {b:3d}-{b+9:<3d}  n={len(v):5d}  avg runs={sum(v)/len(v):.2f}")
    xs = [r["total"] for r in rows]; ys = [r["runs"] for r in rows]
    print(f"\n  Correlation(score, runs scored) = {_corr(xs, ys):+.3f}")

    # 2) spread: higher-score team outscores opponent?
    bygame = {}
    for r in rows:
        bygame.setdefault(r["pk"], []).append(r)
    wins = ties = losses = 0
    spread_buckets = {}
    for pk, pair in bygame.items():
        if len(pair) != 2:
            continue
        a, b = pair
        hi, lo = (a, b) if a["total"] >= b["total"] else (b, a)
        spread = hi["total"] - lo["total"]
        if hi["runs"] > lo["runs"]:
            res = "w"; wins += 1
        elif hi["runs"] == lo["runs"]:
            res = "t"; ties += 1
        else:
            res = "l"; losses += 1
        sb = int(spread//10)*10
        d = spread_buckets.setdefault(sb, [0, 0, 0])
        d[0 if res == "w" else (1 if res == "t" else 2)] += 1
    dec = wins + losses
    print(f"\nSpread 'lean' (higher-score team) outscores opponent:")
    print(f"  {wins}-{losses}-{ties}  -> {wins/dec*100:.1f}% (excl. ties) over {dec+ties} games")
    print("  by spread size:")
    for sb in sorted(spread_buckets):
        w, t, l = spread_buckets[sb]
        d = w+l
        print(f"    spread {sb:2d}-{sb+9:<2d}  {w}-{l}-{t}  {(w/d*100 if d else 0):.1f}%")

    # 3) combined total vs actual total runs
    comb = []
    for pk, pair in bygame.items():
        if len(pair) != 2:
            continue
        comb.append((pair[0]["total"]+pair[1]["total"], pair[0]["runs"]+pair[1]["runs"]))
    cx = [c for c, _ in comb]; cy = [t for _, t in comb]
    print(f"\nCombined score vs actual total runs (n={len(comb)} games):")
    print(f"  Correlation = {_corr(cx, cy):+.3f}")
    cb = {}
    for c, t in comb:
        b = int(c//20)*20
        cb.setdefault(b, []).append(t)
    for b in sorted(cb):
        v = cb[b]
        print(f"  combined {b:3d}-{b+19:<3d}  n={len(v):4d}  avg total runs={sum(v)/len(v):.2f}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    cmd, args = sys.argv[1], sys.argv[2:]
    {"fetch": cmd_fetch, "build": cmd_build, "analyze": cmd_analyze}[cmd](*args)
