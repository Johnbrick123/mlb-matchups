#!/usr/bin/env python3
"""
bullpen_live.py — Effective Bullpen Quality for one slate. Drop-in for update.py.

Produces, per club:
  TALENT  : season relief line (ERA / WHIP / K-BB% / HR9) - official rp split
  FORM    : last-14 and last-7 relief lines, rebuilt from box scores
  TONIGHT : 3-day relief IP + pitches, and named arms that are likely down
  EFF     : one 0-100 quality score, plus an ERA-equivalent that drops straight
            into the site's existing 2.50-6.50 bullpen scale

Weights are 50% season / 30% last-14 / 20% last-7, chosen by backtest across
2024-25-26 (see BULLPEN_FINDINGS.md). Availability and fatigue are DISPLAY ONLY
- they were measured and add nothing, so they carry zero weight.

Cost: one stats call per club + ~14 days of box scores (~10s, keyless).
"""
import json, datetime, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0 (mlb-matchups bullpen module)"}

TEAMS = [
    ("LAA",108),("ARI",109),("BAL",110),("BOS",111),("CHC",112),("CIN",113),
    ("CLE",114),("COL",115),("DET",116),("HOU",117),("KC",118),("LAD",119),
    ("WSH",120),("NYM",121),("ATH",133),("PIT",134),("SD",135),("SEA",136),
    ("SF",137),("STL",138),("TB",139),("TEX",140),("TOR",141),("MIN",142),
    ("PHI",143),("ATL",144),("CHW",145),("MIA",146),("NYY",147),("MIL",158),
]
ID2ABBR = {i: a for a, i in TEAMS}

# same axis the site already uses for bullpen ERA
ERA_LO, ERA_HI = 2.50, 6.50
WHIP_LO, WHIP_HI = 1.00, 1.60
KBB_LO, KBB_HI = 5.0, 22.0
HR9_LO, HR9_HI = 0.60, 1.60
WEIGHTS = {"season": 0.50, "l14": 0.30, "l7": 0.20}


def get(url, tries=3, timeout=40):
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last = e
    raise last


def clamp(x):
    return max(0.0, min(100.0, x))


def quality(r):
    """ERA + WHIP + K-BB% + HR/9 -> one 0-100 score. Higher = better bullpen."""
    if not r or r.get("era") is None:
        return None
    p, w = [], []
    p.append(clamp((ERA_HI - r["era"]) / (ERA_HI - ERA_LO) * 100)); w.append(0.40)
    if r.get("whip") is not None:
        p.append(clamp((WHIP_HI - r["whip"]) / (WHIP_HI - WHIP_LO) * 100)); w.append(0.25)
    if r.get("kbb") is not None:
        p.append(clamp((r["kbb"] - KBB_LO) / (KBB_HI - KBB_LO) * 100)); w.append(0.25)
    if r.get("hr9") is not None:
        p.append(clamp((HR9_HI - r["hr9"]) / (HR9_HI - HR9_LO) * 100)); w.append(0.10)
    return round(sum(a * b for a, b in zip(p, w)) / sum(w), 1)


# ------------------------------------------------------------ season (talent)

def season_relief(team_id, season):
    """Official relief-only split — the same source data.js already uses."""
    url = (f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats"
           f"?stats=statSplits&season={season}&group=pitching&sitCodes=rp&gameType=R")
    try:
        s = get(url)["stats"][0]["splits"][0]["stat"]
        ip = s.get("inningsPitched", "0.0")
        whole, _, frac = str(ip).partition(".")
        inn = int(whole) + (int(frac or 0) / 3.0)
        bb, so, bf = s.get("baseOnBalls"), s.get("strikeOuts"), s.get("battersFaced")
        return {
            "ip": round(inn, 1),
            "era": float(s["era"]) if s.get("era") not in (None, "-.--") else None,
            "whip": float(s["whip"]) if s.get("whip") not in (None, "-.--") else None,
            "kbb": round(100 * (so - bb) / bf, 1) if bf else None,
            "hr9": round(9 * s.get("homeRuns", 0) / inn, 2) if inn else None,
        }
    except Exception:
        return {}


# ------------------------------------------------------------ recent (form)

def recent_relief_log(end_date, days=15):
    """One relief-appearance row per pitcher for the last `days` days."""
    d1 = datetime.date.fromisoformat(end_date) - datetime.timedelta(days=1)
    d0 = d1 - datetime.timedelta(days=days)
    sched = get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&gameType=R"
                f"&startDate={d0}&endDate={d1}")
    pks = [(g["gamePk"], day["date"])
           for day in sched.get("dates", []) for g in day.get("games", [])
           if g.get("status", {}).get("codedGameState") == "F"]

    def one(item):
        pk, date = item
        try:
            b = get(f"https://statsapi.mlb.com/api/v1/game/{pk}/boxscore")
        except Exception:
            return []
        out = []
        for side in ("away", "home"):
            t = b["teams"][side]
            for pid in t.get("pitchers", []):
                st = (t["players"].get(f"ID{pid}", {}).get("stats", {}).get("pitching") or {})
                if not st or int(st.get("gamesStarted") or 0) == 1:
                    continue
                out.append({"date": date, "team": t["team"]["id"], "pid": pid,
                            "outs": int(st.get("outs") or 0), "er": int(st.get("earnedRuns") or 0),
                            "h": int(st.get("hits") or 0), "bb": int(st.get("baseOnBalls") or 0),
                            "so": int(st.get("strikeOuts") or 0), "hr": int(st.get("homeRuns") or 0),
                            "bf": int(st.get("battersFaced") or 0),
                            "np": int(st.get("numberOfPitches") or 0)})
        return out

    rows = []
    with ThreadPoolExecutor(16) as ex:
        for r in ex.map(one, pks):
            rows += r
    return rows


def rates(rows):
    o = er = h = bb = so = hr = bf = 0
    for r in rows:
        o += r["outs"]; er += r["er"]; h += r["h"]; bb += r["bb"]
        so += r["so"]; hr += r["hr"]; bf += r["bf"]
    ip = o / 3.0
    if ip < 1:
        return {}
    return {"ip": round(ip, 1), "era": round(9 * er / ip, 2),
            "whip": round((h + bb) / ip, 3),
            "kbb": round(100 * (so - bb) / bf, 1) if bf else None,
            "hr9": round(9 * hr / ip, 2)}


def down_arms(rows, asof):
    """Arms that probably cannot pitch tonight. Display only — see findings."""
    d0 = datetime.date.fromisoformat(asof)
    st = {}
    for r in rows:
        gap = (d0 - datetime.date.fromisoformat(r["date"])).days
        if 1 <= gap <= 3:
            s = st.setdefault(r["pid"], {"d": set(), "np": 0, "np_y": 0})
            s["d"].add(gap); s["np"] += r["np"]
            if gap == 1:
                s["np_y"] += r["np"]
    out = {}
    for pid, s in st.items():
        if {1, 2, 3} <= s["d"]:
            out[pid] = "3 straight days"
        elif {1, 2} <= s["d"] and s["np"] >= 35:
            out[pid] = "back-to-back, heavy"
        elif 1 in s["d"] and s["np_y"] >= 45:
            out[pid] = f"{s['np_y']} pitches yesterday"
    return out


def names(pids):
    if not pids:
        return {}
    d = get("https://statsapi.mlb.com/api/v1/people?personIds="
            + ",".join(str(p) for p in pids))
    return {p["id"]: p["fullName"] for p in d.get("people", [])}


# ------------------------------------------------------------ public entry

def build(date):
    season = date[:4]
    log = recent_relief_log(date)
    by_team = {}
    for r in log:
        by_team.setdefault(r["team"], []).append(r)

    with ThreadPoolExecutor(10) as ex:
        season_by = dict(zip([t[1] for t in TEAMS],
                             ex.map(lambda t: season_relief(t[1], season), TEAMS)))

    d0 = datetime.date.fromisoformat(date)
    def win(rows, n):
        lo = (d0 - datetime.timedelta(days=n)).isoformat()
        return [r for r in rows if lo <= r["date"] < date]

    all_down = {}
    for tid, rows in by_team.items():
        all_down[tid] = down_arms(rows, date)
    nm = names([p for v in all_down.values() for p in v])

    out = {}
    for ab, tid in TEAMS:
        rows = by_team.get(tid, [])
        szn = season_by.get(tid) or {}
        l14, l7 = rates(win(rows, 14)), rates(win(rows, 7))
        d3 = win(rows, 3)
        comp = used = 0.0
        for key, r in (("season", szn), ("l14", l14), ("l7", l7)):
            q = quality(r)
            if q is not None:
                comp += q * WEIGHTS[key]; used += WEIGHTS[key]
        eff = round(comp / used, 1) if used else None
        out[ab] = {
            "season": szn, "l14": l14, "l7": l7,
            "q_season": quality(szn), "q_l14": quality(l14), "q_l7": quality(l7),
            "eff": eff,
            "effERA": round(ERA_HI - eff / 100 * (ERA_HI - ERA_LO), 2) if eff is not None else None,
            "d3_ip": round(sum(r["outs"] for r in d3) / 3.0, 1),
            "d3_pitches": sum(r["np"] for r in d3),
            "down": sorted(f"{nm.get(p, p)} ({why})" for p, why in all_down.get(tid, {}).items()),
        }
    return out


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    v = build(date)
    print(f"{'tm':<5}{'sznERA':>8}{'L14':>7}{'L7':>7}{'EFF':>7}{'effERA':>8}{'3dIP':>7}  arms down")
    for ab, t in sorted(v.items(), key=lambda kv: -(kv[1]["eff"] or 0)):
        g = lambda d: f"{d['era']:.2f}" if d.get("era") is not None else "  -  "
        print(f"{ab:<5}{g(t['season']):>8}{g(t['l14']):>7}{g(t['l7']):>7}"
              f"{t['eff']:>7}{t['effERA']:>8}{t['d3_ip']:>7}  {', '.join(t['down']) or '-'}")
