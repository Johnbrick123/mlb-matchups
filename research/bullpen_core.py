#!/usr/bin/env python3
"""
bullpen_core.py — relief-appearance harvester + Effective Bullpen Quality.

Everything here comes from MLB StatsAPI (free, keyless). No Covers scraping.

One idea: pull every box score once, flatten it to one row per RELIEF APPEARANCE,
and derive every bullpen view from that single table:

    season-to-date team relief line     (what the site uses today)
    current-roster relief line          (only the arms actually on the staff now)
    last-14 / last-7 team relief line   (form)
    tonight's available arms            (roster minus arms that are down)
    3-day workload                      (fatigue)

Because a relief appearance carries its own date, every one of these is
computable AS OF any date with no leakage — which is what makes the backtest
honest.

Usage:
    python bullpen_core.py harvest 2026        # cache the season's relief log
    python bullpen_core.py show 2026-09-12     # per-team table for that date
"""
import json, os, sys, urllib.request, datetime
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "bp_cache")
UA = {"User-Agent": "Mozilla/5.0 (mlb-matchups bullpen module)"}

TEAMS = [
    ("LAA",108),("ARI",109),("BAL",110),("BOS",111),("CHC",112),("CIN",113),
    ("CLE",114),("COL",115),("DET",116),("HOU",117),("KC",118),("LAD",119),
    ("WSH",120),("NYM",121),("ATH",133),("PIT",134),("SD",135),("SEA",136),
    ("SF",137),("STL",138),("TB",139),("TEX",140),("TOR",141),("MIN",142),
    ("PHI",143),("ATL",144),("CHW",145),("MIA",146),("NYY",147),("MIL",158),
]
ID2ABBR = {i: a for a, i in TEAMS}
ABBR_ID = {a: i for a, i in TEAMS}


def get(url, tries=3, timeout=40):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last = e
    raise last


# ---------------------------------------------------------------- harvesting

def season_gamepks(season):
    """(gamePk, date) for every completed regular-season game."""
    url = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&gameType=R"
           f"&startDate={season}-02-20&endDate={season}-11-10")
    d = get(url)
    out = []
    for day in d.get("dates", []):
        for g in day.get("games", []):
            if g.get("status", {}).get("codedGameState") == "F":
                out.append((g["gamePk"], day["date"]))
    return out


def parse_box(pk, date):
    """-> list of relief-appearance dicts for both clubs."""
    b = get(f"https://statsapi.mlb.com/api/v1/game/{pk}/boxscore")
    rows = []
    for side in ("away", "home"):
        t = b["teams"][side]
        tid = t["team"]["id"]
        opp = b["teams"]["home" if side == "away" else "away"]["team"]["id"]
        for pid in t.get("pitchers", []):
            st = (t["players"].get(f"ID{pid}", {}).get("stats", {}).get("pitching") or {})
            if not st:
                continue
            if int(st.get("gamesStarted") or 0) == 1:
                continue                      # starter (incl. openers) — not relief
            rows.append({
                "date": date, "pk": pk, "team": tid, "opp": opp, "pid": pid,
                "outs": int(st.get("outs") or 0),
                "er": int(st.get("earnedRuns") or 0),
                "r": int(st.get("runs") or 0),
                "h": int(st.get("hits") or 0),
                "bb": int(st.get("baseOnBalls") or 0),
                "so": int(st.get("strikeOuts") or 0),
                "hr": int(st.get("homeRuns") or 0),
                "bf": int(st.get("battersFaced") or 0),
                "np": int(st.get("numberOfPitches") or 0),
            })
    return rows


def harvest(season, workers=16):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"relief_{season}.jsonl")
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                done.add(json.loads(line)["pk"])
    games = season_gamepks(season)
    todo = [(pk, d) for pk, d in games if pk not in done]
    print(f"  {season}: {len(games)} final games, {len(todo)} to fetch")
    if todo:
        with open(path, "a") as f, ThreadPoolExecutor(workers) as ex:
            for i, rows in enumerate(ex.map(lambda g: parse_box(*g), todo), 1):
                for r in rows:
                    f.write(json.dumps(r) + "\n")
                if i % 250 == 0:
                    print(f"    {i}/{len(todo)}")
    return path


def load(season):
    path = os.path.join(CACHE, f"relief_{season}.jsonl")
    with open(path) as f:
        return [json.loads(l) for l in f]


# ---------------------------------------------------------------- aggregation

def agg(rows):
    t = {"outs": 0, "er": 0, "h": 0, "bb": 0, "so": 0, "hr": 0, "bf": 0, "np": 0, "app": 0}
    for r in rows:
        for k in ("outs", "er", "h", "bb", "so", "hr", "bf", "np"):
            t[k] += r[k]
        t["app"] += 1
    return t


def rates(t):
    ip = t["outs"] / 3.0
    if ip < 1:
        return {}
    return {
        "ip": round(ip, 1),
        "era": round(9 * t["er"] / ip, 2),
        "whip": round((t["h"] + t["bb"]) / ip, 3),
        "kbb": round(100 * (t["so"] - t["bb"]) / t["bf"], 1) if t["bf"] else None,
        "hr9": round(9 * t["hr"] / ip, 2),
    }


def dates_before(rows, asof):
    return [r for r in rows if r["date"] < asof]


def window(rows, asof, days):
    lo = (datetime.date.fromisoformat(asof) - datetime.timedelta(days=days)).isoformat()
    return [r for r in rows if lo <= r["date"] < asof]


# ------------------------------------------------- roster / availability

def active_arms(team_rows, asof, lookback=21):
    """Arms that have actually appeared in relief for this club recently.

    A point-in-time stand-in for the active roster: it needs no roster history
    (MLB StatsAPI will not give you one) and it captures the thing that matters
    — the arms the manager can call on tonight. Trade and call-up arrivals show
    up the day they first pitch; departures fall out after `lookback` days.
    """
    return {r["pid"] for r in window(team_rows, asof, lookback)}


def arm_state(team_rows, asof):
    """Per-arm workload over the three days before `asof`."""
    d0 = datetime.date.fromisoformat(asof)
    st = {}
    for r in team_rows:
        gap = (d0 - datetime.date.fromisoformat(r["date"])).days
        if 1 <= gap <= 3:
            s = st.setdefault(r["pid"], {"days": set(), "np": 0, "outs": 0, "np_y": 0})
            s["days"].add(gap)
            s["np"] += r["np"]
            s["outs"] += r["outs"]
            if gap == 1:
                s["np_y"] += r["np"]
    return st


def unavailable(state):
    """Standard usage rules for who probably cannot pitch tonight.

    These are conventions, not measured facts — see the honesty note in the
    handoff doc. They mirror how clubs actually manage arms:
      - threw each of the last three days
      - threw both of the last two days AND >=35 pitches across them
      - threw >=45 pitches yesterday
    """
    out = {}
    for pid, s in state.items():
        d = s["days"]
        if {1, 2, 3} <= d:
            out[pid] = "3 straight days"
        elif {1, 2} <= d and s["np"] >= 35:
            out[pid] = "b2b, heavy"
        elif 1 in d and s["np_y"] >= 45:
            out[pid] = f"{s['np_y']}p yesterday"
    return out


# ------------------------------------------------- effective bullpen quality

# Quality is scored 0-100 on the same axis the site already uses for ERA
# (2.50 = 100, 6.50 = 0), so the new number drops straight into the existing
# scale/weight machinery.
ERA_LO, ERA_HI = 2.50, 6.50
WHIP_LO, WHIP_HI = 1.00, 1.60
KBB_LO, KBB_HI = 5.0, 22.0
HR9_LO, HR9_HI = 0.60, 1.60


def clamp100(x):
    return max(0.0, min(100.0, x))


def quality(r):
    """Blend ERA + WHIP + K-BB% + HR/9 into one 0-100 quality score."""
    if not r:
        return None
    parts, wts = [], []
    parts.append(clamp100((ERA_HI - r["era"]) / (ERA_HI - ERA_LO) * 100)); wts.append(0.40)
    parts.append(clamp100((WHIP_HI - r["whip"]) / (WHIP_HI - WHIP_LO) * 100)); wts.append(0.25)
    if r.get("kbb") is not None:
        parts.append(clamp100((r["kbb"] - KBB_LO) / (KBB_HI - KBB_LO) * 100)); wts.append(0.25)
    parts.append(clamp100((HR9_HI - r["hr9"]) / (HR9_HI - HR9_LO) * 100)); wts.append(0.10)
    return round(sum(p * w for p, w in zip(parts, wts)) / sum(wts), 1)


def team_view(team_rows, asof, weights=None):
    """Every bullpen layer for one club as of one date."""
    # Backtest-selected weights (2024-25-26, see BULLPEN_FINDINGS.md).
    # Mixing time windows is what carries the improvement. Availability and
    # fatigue measurably add NOTHING, so they carry zero weight and are kept
    # only as display columns.
    std = {"season": 0.50, "l14": 0.30, "l7": 0.20,
           "roster": 0.0, "avail": 0.0, "fatigue": 0.0}
    w = dict(std, **(weights or {}))

    prior = dates_before(team_rows, asof)
    arms = active_arms(team_rows, asof)
    state = arm_state(team_rows, asof)
    down = unavailable(state)

    season_r = rates(agg(prior))
    roster_r = rates(agg([r for r in prior if r["pid"] in arms]))
    l14_r = rates(agg(window(team_rows, asof, 14)))
    l7_r = rates(agg(window(team_rows, asof, 7)))
    avail_r = rates(agg([r for r in prior if r["pid"] in arms and r["pid"] not in down]))

    d3 = window(team_rows, asof, 3)
    d3_outs = sum(r["outs"] for r in d3)
    d3_np = sum(r["np"] for r in d3)
    # fatigue score: 0-100, 100 = fully rested. 18 relief IP in 3 days = floor.
    fat = clamp100(100 - (d3_outs / 3.0) / 18.0 * 100)

    comp, used = 0.0, 0.0
    for key, r in (("season", season_r), ("roster", roster_r),
                   ("l14", l14_r), ("l7", l7_r), ("avail", avail_r)):
        q = quality(r)
        if q is not None and w.get(key):
            comp += q * w[key]; used += w[key]
    if w.get("fatigue"):
        comp += fat * w["fatigue"]; used += w["fatigue"]
    eff = round(comp / used, 1) if used else None

    return {
        "season": season_r, "roster": roster_r, "l14": l14_r, "l7": l7_r, "avail": avail_r,
        "q_season": quality(season_r), "q_roster": quality(roster_r),
        "q_l14": quality(l14_r), "q_l7": quality(l7_r), "q_avail": quality(avail_r),
        "d3_ip": round(d3_outs / 3.0, 1), "d3_pitches": d3_np, "fatigue": round(fat, 1),
        "arms": len(arms), "down": {str(k): v for k, v in down.items()},
        "effective": eff,
        # back into an ERA-like number so it can feed the existing 2.5-6.5 scale
        "effective_era": round(ERA_HI - eff / 100 * (ERA_HI - ERA_LO), 2) if eff is not None else None,
    }


def build(season, asof, weights=None):
    rows = load(season)
    by_team = {}
    for r in rows:
        by_team.setdefault(r["team"], []).append(r)
    return {ID2ABBR[t]: team_view(v, asof, weights) for t, v in by_team.items() if t in ID2ABBR}


def name_map(pids):
    if not pids:
        return {}
    ids = ",".join(str(p) for p in pids)
    d = get(f"https://statsapi.mlb.com/api/v1/people?personIds={ids}")
    return {str(p["id"]): p["fullName"] for p in d.get("people", [])}


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "harvest":
        harvest(sys.argv[2])
    elif cmd == "show":
        asof = sys.argv[2]
        v = build(asof[:4], asof)
        print(f"{'tm':<4}{'szn':>6}{'roster':>8}{'L14':>7}{'L7':>7}{'avail':>7}"
              f"{'3dIP':>7}{'EFF':>7}{'effERA':>8}  down")
        for ab, t in sorted(v.items(), key=lambda kv: -(kv[1]["effective"] or 0)):
            f = lambda d: (f"{d['era']:.2f}" if d else "  -  ")
            print(f"{ab:<4}{f(t['season']):>6}{f(t['roster']):>8}{f(t['l14']):>7}{f(t['l7']):>7}"
                  f"{f(t['avail']):>7}{t['d3_ip']:>7}{t['effective']:>7}{t['effective_era']:>8}"
                  f"  {len(t['down'])}")
