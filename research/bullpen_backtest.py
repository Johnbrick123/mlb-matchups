#!/usr/bin/env python3
"""
Does the Effective Bullpen input beat season relief ERA?

Point-in-time by construction: every bullpen measure for a team-game is built
only from relief appearances with a date strictly before that game.

    python bullpen_backtest.py 2024 2025 2026
"""
import csv, os, sys, math, json, datetime
import bullpen_core as bc

HERE = os.path.dirname(os.path.abspath(__file__))
BT = os.path.join(HERE, "..", "backtest")
WARMUP_DAYS = 45          # need roster + L14 history before a row is usable


# ------------------------------------------------------------------ stats
def corr(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def tstat(r, n):
    if r is None or abs(r) >= 1:
        return None
    return r * math.sqrt((n - 2) / (1 - r * r))


def ols(X, y):
    """Plain least squares with intercept. X: list of rows (lists)."""
    k = len(X[0]) + 1
    A = [[0.0] * k for _ in range(k)]
    b = [0.0] * k
    for row, yy in zip(X, y):
        v = [1.0] + list(row)
        for i in range(k):
            b[i] += v[i] * yy
            for j in range(k):
                A[i][j] += v[i] * v[j]
    # gaussian elimination
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]; b[i], b[p] = b[p], b[i]
        if abs(A[i][i]) < 1e-12:
            return None
        for r in range(k):
            if r == i:
                continue
            f = A[r][i] / A[i][i]
            for c in range(i, k):
                A[r][c] -= f * A[i][c]
            b[r] -= f * b[i]
    return [b[i] / A[i][i] for i in range(k)]


# ------------------------------------------------------------------ data
def game_sides(season):
    """pk -> (team_id, opp_id) pairs, from the relief log."""
    m = {}
    for r in bc.load(season):
        m.setdefault(r["pk"], {})[r["team"]] = r["opp"]
    return m


def build_rows(season):
    rows = bc.load(season)
    by_team = {}
    for r in rows:
        by_team.setdefault(r["team"], []).append(r)
    sides = game_sides(season)

    path = os.path.join(BT, f"games_{season}.csv")
    out = []
    cache = {}
    with open(path) as f:
        for g in csv.DictReader(f):
            if not g.get("runs") or not g.get("oppBullpenERA"):
                continue
            tid = int(g["team_id"])
            pk = int(g["pk"])
            opp_id = (sides.get(pk) or {}).get(tid)
            if opp_id is None or opp_id not in by_team:
                continue
            date = g["date"]
            d0 = datetime.date.fromisoformat(date)
            if (d0 - datetime.date(int(season), 3, 20)).days < WARMUP_DAYS:
                continue
            key = (opp_id, date)
            if key not in cache:
                cache[key] = bc.team_view(by_team[opp_id], date)
            v = cache[key]
            if v["effective"] is None or v["q_roster"] is None:
                continue

            def f(k):
                try:
                    return float(g[k])
                except (KeyError, TypeError, ValueError):
                    return None
            sx, so, sl3 = f("s_xera"), f("s_ops"), f("s_opsL3")
            s_rest = (None if None in (sx, so, sl3)
                      else sx * 0.24 + so * 0.19 + sl3 * 0.32)

            out.append({
                "s_rest": s_rest,
                "date": date, "season": season, "team": g["team"], "opp": g["opp"],
                "runs": float(g["runs"]),
                "total": float(g["total"]) if g.get("total") else None,
                "opp_runs": float(g["opp_runs"]) if g.get("opp_runs") else None,
                # the input the site uses today, expressed as a 0-100 quality
                "q_seasonERA": 100 * (6.5 - float(g["oppBullpenERA"])) / 4.0,
                "q_season": v["q_season"], "q_roster": v["q_roster"],
                "q_l14": v["q_l14"], "q_l7": v["q_l7"], "q_avail": v["q_avail"],
                "fatigue": v["fatigue"], "effective": v["effective"],
                "n_down": len(v["down"]),
                # ERA-only versions of the same populations, so "which arms"
                # can be separated from "which stat blend"
                **{f"era_{k}": (100 * (6.5 - v[k]["era"]) / 4.0 if v[k] else None)
                   for k in ("season", "roster", "l14", "l7", "avail")},
            })
    return out


# ------------------------------------------------------------------ report
MEASURES = [
    ("season ERA (current input)", "q_seasonERA"),
    ("season relief blend", "q_season"),
    ("current-roster blend", "q_roster"),
    ("last-14 blend", "q_l14"),
    ("last-7 blend", "q_l7"),
    ("available-arms blend", "q_avail"),
    ("fatigue (100=rested)", "fatigue"),
    ("EFFECTIVE composite", "effective"),
    ("-- ERA only, same pops --", None),
    ("season ERA (rebuilt)", "era_season"),
    ("current-roster ERA", "era_roster"),
    ("last-14 ERA", "era_l14"),
    ("last-7 ERA", "era_l7"),
    ("available-arms ERA", "era_avail"),
]


def stage_a(rows, label):
    print(f"\n=== Stage A — does it predict the runs the offense scores?  [{label}]  n={len(rows)}")
    print(f"{'bullpen measure':<30}{'r vs runs':>12}{'t':>8}")
    y = [r["runs"] for r in rows]
    for name, key in MEASURES:
        if key is None:
            print(name)
            continue
        xs = [r[key] for r in rows if r[key] is not None]
        ys = [r["runs"] for r in rows if r[key] is not None]
        c = corr(xs, ys)
        t = tstat(c, len(xs))
        # sign: a WORSE opponent pen (lower quality) should mean MORE runs -> expect r<0
        print(f"{name:<30}{c:>12.4f}{t:>8.2f}" if c is not None else f"{name:<30}{'--':>12}")


def stage_a2(rows, label):
    """Does the new information survive alongside the old one?"""
    print(f"\n=== Stage A2 — incremental value over season ERA  [{label}]")
    keys = ["q_roster", "q_l14", "q_l7", "q_avail", "fatigue"]
    rows = [r for r in rows
            if all(r.get(k) is not None for k in keys + ["q_seasonERA", "effective"])]
    base = [[r["q_seasonERA"]] for r in rows]
    y = [r["runs"] for r in rows]
    b0 = ols(base, y)
    r0 = resid_sd(base, y, b0)
    print(f"  season ERA alone            residual sd {r0:.4f}")
    for k in keys:
        X = [[r["q_seasonERA"], r[k]] for r in rows]
        b = ols(X, y)
        if not b:
            continue
        print(f"  + {k:<26} residual sd {resid_sd(X, y, b):.4f}   coef {b[2]:+.5f}")
    X = [[r["effective"]] for r in rows]
    b = ols(X, y)
    print(f"  EFFECTIVE alone             residual sd {resid_sd(X, y, b):.4f}")


def resid_sd(X, y, b):
    n = len(y)
    ss = 0.0
    for row, yy in zip(X, y):
        p = b[0] + sum(bi * xi for bi, xi in zip(b[1:], row))
        ss += (yy - p) ** 2
    return math.sqrt(ss / n)


def bucket(rows, key, label, nb=5):
    vals = sorted(r[key] for r in rows if r[key] is not None)
    if not vals:
        return
    cuts = [vals[int(len(vals) * i / nb)] for i in range(1, nb)]
    buckets = [[] for _ in range(nb)]
    for r in rows:
        v = r[key]
        if v is None:
            continue
        i = sum(1 for c in cuts if v >= c)
        buckets[i].append(r["runs"])
    print(f"\n  {label} quintiles (worst pen -> best pen), runs scored against it:")
    for i, b in enumerate(buckets):
        if b:
            print(f"    Q{i+1}  n={len(b):>5}  mean runs {sum(b)/len(b):.3f}")


def model_level(rows, label):
    """The question that actually matters: swap the 25% input in the live model
    and see whether the TOTAL score predicts runs any better."""
    rows = [r for r in rows if r.get("effective") is not None and r.get("s_rest") is not None]
    if len(rows) < 100:
        return
    print(f"\n=== Model level — full score vs runs  [{label}]  n={len(rows)}")
    y = [r["runs"] for r in rows]
    for name, key in (("OLD (season ERA)", "q_seasonERA"), ("NEW (effective)", "effective"),
                      ("NEW (roster only)", "q_roster"), ("NEW (L7 only)", "q_l7")):
        # bullpen sub-score on the site's axis is 100 - quality
        tot = [r["s_rest"] + (100 - r[key]) * W_BULL for r in rows]
        c = corr(tot, y)
        print(f"  {name:<20} r vs runs {c:+.4f}   t {tstat(c, len(rows)):+.2f}")


W_BULL = 0.25


def main():
    seasons = sys.argv[1:] or ["2026"]
    allrows = []
    for s in seasons:
        rs = build_rows(s)
        print(f"{s}: {len(rs)} usable team-games")
        allrows += rs

    fit = [r for r in allrows if r["season"] != "2026"]
    hold = [r for r in allrows if r["season"] == "2026"]

    for label, rs in (("ALL", allrows), ("fit 2024-25", fit), ("holdout 2026", hold)):
        if len(rs) < 100:
            continue
        stage_a(rs, label)
    if len(fit) > 100:
        stage_a2(fit, "fit 2024-25")
    for lbl, rs in (("fit 2024-25", fit), ("holdout 2026", hold)):
        model_level(rs, lbl)
    if len(hold) > 100:
        stage_a2(hold, "holdout 2026")
        bucket(hold, "q_seasonERA", "season ERA")
        bucket(hold, "effective", "EFFECTIVE")
        bucket(hold, "q_roster", "current-roster")

    json.dump(allrows, open(os.path.join(HERE, "bt_rows.json"), "w"))
    print(f"\nwrote bt_rows.json ({len(allrows)} rows)")


if __name__ == "__main__":
    main()
