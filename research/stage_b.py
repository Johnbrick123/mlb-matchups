#!/usr/bin/env python3
"""
Stage B — fit a bullpen composite on 2024-25, test it untouched on 2026,
then ask the only question that pays: does it beat the closing total?
"""
import json, math, os, statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "bt_rows.json")))
KEYS = ["era_season", "era_roster", "era_l14", "era_l7", "era_avail", "fatigue"]
rows = [r for r in rows if all(r.get(k) is not None for k in KEYS) and r.get("s_rest") is not None]
fit = [r for r in rows if r["season"] != "2026"]
hold = [r for r in rows if r["season"] == "2026"]
print(f"fit {len(fit)}   holdout {len(hold)}")


def corr(xs, ys):
    n = len(xs); mx, my = st.mean(xs), st.mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs)); sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else None


def ols(X, y):
    k = len(X[0]) + 1
    A = [[0.0] * k for _ in range(k)]; b = [0.0] * k
    for row, yy in zip(X, y):
        v = [1.0] + list(row)
        for i in range(k):
            b[i] += v[i] * yy
            for j in range(k):
                A[i][j] += v[i] * v[j]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]; b[i], b[p] = b[p], b[i]
        for r in range(k):
            if r == i: continue
            f = A[r][i] / A[i][i]
            for c in range(i, k): A[r][c] -= f * A[i][c]
            b[r] -= f * b[i]
    return [b[i] / A[i][i] for i in range(k)]


# ---- fit a bullpen composite on 2024-25 only -------------------------------
X = [[r[k] for k in KEYS] for r in fit]
y = [r["runs"] for r in fit]
beta = ols(X, y)
print("\nFitted coefficients on 2024-25 (runs scored vs opponent bullpen views):")
for k, b in zip(KEYS, beta[1:]):
    print(f"  {k:<14}{b:+.5f}")

# renormalise into a 0-100 quality (sign-flipped: higher = better pen)
def composite(r):
    return -sum(b * r[k] for b, k in zip(beta[1:], KEYS))

for lbl, rs in (("fit 2024-25", fit), ("HOLDOUT 2026", hold)):
    c_new = corr([composite(r) for r in rs], [r["runs"] for r in rs])
    c_old = corr([r["q_seasonERA"] for r in rs], [r["runs"] for r in rs])
    c_cln = corr([r["era_season"] for r in rs], [r["runs"] for r in rs])
    c_l7 = corr([r["era_l7"] for r in rs], [r["runs"] for r in rs])
    print(f"\n{lbl}: r vs runs  fitted-composite {-c_new:+.4f} | "
          f"site season ERA {-c_old:+.4f} | clean season ERA {-c_cln:+.4f} | L7 {-c_l7:+.4f}")
    print("   (sign flipped so bigger = more predictive of the pen being scored on)")

# ---- Stage B: does any of it beat the closing total? -----------------------
print("\n=== Stage B — vs the closing total ===")
for lbl, rs in (("fit 2024-25", fit), ("HOLDOUT 2026", hold)):
    games = defaultdict(list)
    for r in rs:
        if r["total"] and r["opp_runs"] is not None:
            games[(r["season"], r["date"], tuple(sorted([r["team"], r["opp"]])))].append(r)
    pairs = [v for v in games.values() if len(v) == 2]
    print(f"\n{lbl}: {len(pairs)} complete games with a closing total")
    for name, key in (("OLD season ERA", "q_seasonERA"), ("clean season ERA", "era_season"),
                      ("L7", "era_l7"), ("roster", "era_roster"), ("EFFECTIVE", "effective"),
                      ("fitted composite", None)):
        picks = []
        for p in pairs:
            actual = p[0]["runs"] + p[0]["opp_runs"]
            tot = p[0]["total"]
            if abs(actual - tot) < 1e-9:
                continue
            if key is None:
                sc = sum(p[0]["s_rest"] + (100 - (-composite(x))) * 0.25 for x in p) / 2
            else:
                sc = sum(x["s_rest"] + (100 - x[key]) * 0.25 for x in p) / 2
            picks.append((sc, 1 if actual > tot else 0))
        picks.sort(key=lambda t: -t[0])
        n = len(picks)
        top = picks[:n // 5]; bot = picks[-(n // 5):]
        ov_top = sum(p[1] for p in top) / len(top) * 100
        ov_bot = sum(p[1] for p in bot) / len(bot) * 100
        base = sum(p[1] for p in picks) / n * 100
        print(f"  {name:<18} top-20% over {ov_top:5.1f}%   bottom-20% over {ov_bot:5.1f}%   "
              f"all {base:5.1f}%  (need 52.4%)")
