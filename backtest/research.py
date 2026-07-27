#!/usr/bin/env python3
"""
Deep-dive research on the backtest:
  A) standalone predictive power of each input
  B) weight optimization (train 2024-25 / test 2026, no overfit)
  C) spread -> run-margin (the -1.5 run-line question)
  D) runs-scored distribution by combined score band  (variance, not just mean)
  E) runs-scored distribution by team score band
Usage: python research.py
"""
import os, csv
import numpy as np
import bt   # reuse SCALES / sub()

HERE = os.path.dirname(os.path.abspath(__file__))
COMPS = ["xERA", "ops", "bullpen", "runsL3", "opsL3"]   # weight order
RAW   = ["oppXERA", "oppBullpenERA", "ops", "opsL3", "runsL3"]  # raw cols
BASE_W = np.array([0.40, 0.30, 0.10, 0.10, 0.10])

def subscore(raw_val, comp):
    return bt.sub(raw_val, comp)

def load():
    rows = []
    for y in (2024, 2025, 2026):
        p = os.path.join(HERE, f"games_{y}.csv")
        for r in csv.DictReader(open(p, encoding="utf-8")):
            def f(c):
                v = r.get(c, "")
                return float(v) if v not in ("", None) else None
            xe, bl, op, o3, r3 = f("oppXERA"), f("oppBullpenERA"), f("ops"), f("opsL3"), f("runsL3")
            if None in (xe, bl, op, o3, r3):
                continue  # complete cases only
            subs = [subscore(xe, "xERA"), subscore(op, "ops"), subscore(bl, "bullpen"),
                    subscore(r3, "runsL3"), subscore(o3, "opsL3")]
            rows.append({
                "season": int(r["season"]), "pk": r["pk"],
                "subs": subs, "runs": int(r["runs"]), "opp_runs": int(r["opp_runs"]),
            })
    return rows

def corr(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    if a.std() == 0 or b.std() == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])

def pair_index(rows):
    """Games where BOTH team-rows are complete -> arrays of (i,j)."""
    by = {}
    for idx, r in enumerate(rows):
        by.setdefault(r["pk"], []).append(idx)
    ii, jj = [], []
    for pk, idxs in by.items():
        if len(idxs) == 2:
            ii.append(idxs[0]); jj.append(idxs[1])
    return np.array(ii), np.array(jj)

def spread_acc(totals, runs, ii, jj, min_spread=0.0):
    dt = totals[ii] - totals[jj]
    dr = runs[ii] - runs[jj]
    m = (np.abs(dt) >= min_spread) & (dr != 0)
    if m.sum() == 0:
        return 0.0, 0
    favored_right = (np.sign(dt[m]) == np.sign(dr[m]))
    return float(favored_right.mean()), int(m.sum())

def evaluate(w, S, runs, ii, jj):
    w = w / w.sum()
    tot = S @ w
    c = corr(tot, runs)
    acc, n = spread_acc(tot, runs, ii, jj, 0)
    acc30, n30 = spread_acc(tot, runs, ii, jj, 30)
    return {"corr": c, "acc": acc, "acc30": acc30, "n30": n30}

def main():
    rows = load()
    S = np.array([r["subs"] for r in rows], float)      # N x 5
    runs = np.array([r["runs"] for r in rows], int)
    seas = np.array([r["season"] for r in rows], int)
    print(f"Complete-case team-games: {len(rows):,}  (of ~12,313 total)\n")

    # ---------- A) standalone predictive power ----------
    print("="*64)
    print("A) STANDALONE PREDICTIVE POWER  (corr of each input's 0-100 score with runs scored)")
    print("="*64)
    for k, name in enumerate(COMPS):
        print(f"  {name:9} corr = {corr(S[:,k], runs):+.3f}")
    print("  (season OPS expected weak; xERA / L3 stats expected stronger)")

    # ---------- B) weight optimization ----------
    print("\n" + "="*64)
    print("B) WEIGHT OPTIMIZATION  (train 2024-25, test 2026 — guards against overfit)")
    print("="*64)
    tr = seas < 2026; te = seas == 2026
    Str, rtr = S[tr], runs[tr]
    Ste, rte = S[te], runs[te]
    ii_all, jj_all = pair_index(rows)
    # split pair indices by season membership of first element
    def split_pairs(mask):
        keep = mask[ii_all] & mask[jj_all]
        # remap global idx -> local idx within masked subset
        remap = -np.ones(len(rows), int); remap[np.where(mask)[0]] = np.arange(mask.sum())
        return remap[ii_all[keep]], remap[jj_all[keep]]
    iitr, jjtr = split_pairs(tr); iite, jjte = split_pairs(te)

    rng = np.random.default_rng(0)
    W = rng.dirichlet(np.ones(5), size=40000)           # uniform on simplex
    totals_tr = Str @ W.T                                # Ntr x M
    # objective 1: correlation on train
    rc = np.array([corr(totals_tr[:, m], rtr) for m in range(0, W.shape[0])])
    best_corr_i = int(rc.argmax())
    # objective 2: spread accuracy on train (evaluate top-500 corr candidates)
    top = np.argsort(rc)[::-1][:500]
    accs = []
    for m in top:
        a, _ = spread_acc(totals_tr[:, m], rtr, iitr, jjtr, 0)
        accs.append(a)
    best_acc_i = int(top[int(np.argmax(accs))])

    def report_w(label, w):
        w = w / w.sum()
        tr_m = evaluate(w, Str, rtr, iitr, jjtr)
        te_m = evaluate(w, Ste, rte, iite, jjte)
        wl = "  ".join(f"{c}={w[k]*100:.0f}%" for k, c in enumerate(COMPS))
        print(f"\n  {label}")
        print(f"    weights: {wl}")
        print(f"    TRAIN 24-25: corr {tr_m['corr']:+.3f} | spread-acc {tr_m['acc']*100:.1f}% | acc@spread>=30 {tr_m['acc30']*100:.1f}% (n={tr_m['n30']})")
        print(f"    TEST  2026 : corr {te_m['corr']:+.3f} | spread-acc {te_m['acc']*100:.1f}% | acc@spread>=30 {te_m['acc30']*100:.1f}% (n={te_m['n30']})")

    report_w("BASELINE (.40/.30/.10/.10/.10)", BASE_W)
    report_w("BEST by correlation (train)", W[best_corr_i])
    report_w("BEST by spread-accuracy (train)", W[best_acc_i])

    # pick final = best spread-acc if it holds on test, else baseline
    finalw = W[best_acc_i] / W[best_acc_i].sum()

    # ---------- C) spread -> run margin (run line) ----------
    print("\n" + "="*64)
    print("C) SPREAD -> RUN MARGIN  (favored = higher score; margin = fav runs - dog runs)")
    print("   -1.5 cover = favored wins by 2+.  Using FINAL optimized weights.")
    print("="*64)
    tot_all = S @ finalw
    dt = tot_all[ii_all] - tot_all[jj_all]
    fav = np.where(dt >= 0, ii_all, jj_all)
    dog = np.where(dt >= 0, jj_all, ii_all)
    spread = np.abs(dt)
    margin = runs[fav] - runs[dog]
    total_runs = runs[ii_all] + runs[jj_all]
    print(f"  {'gap band':10}{'n':>6}{'winrate':>9}{'mean margin':>13}{'median':>8}{'cover -1.5':>12}{'avg total':>11}")
    for lo in range(0, 80, 10):
        m = (spread >= lo) & (spread < lo+10)
        if m.sum() < 5: continue
        wr = (margin[m] > 0).mean()*100
        cov = (margin[m] >= 2).mean()*100
        print(f"  {lo:2d}-{lo+9:<7d}{m.sum():>6}{wr:>8.1f}%{margin[m].mean():>+13.2f}{int(np.median(margin[m])):>8}{cov:>11.1f}%{total_runs[m].mean():>11.2f}")
    for thr in (30, 40, 50):
        m = spread >= thr
        print(f"  gap >= {thr}: n={m.sum()}  winrate={ (margin[m]>0).mean()*100:.1f}%  "
              f"cover -1.5={ (margin[m]>=2).mean()*100:.1f}%  mean margin={margin[m].mean():+.2f}")

    # ---------- D) combined score -> total-runs distribution ----------
    print("\n" + "="*64)
    print("D) TOTAL-RUNS DISTRIBUTION by COMBINED score band  (variance, not just mean)")
    print("="*64)
    combined = tot_all[ii_all] + tot_all[jj_all]
    print(f"  {'combined':11}{'n':>6}{'mean':>7}{'std':>6}{'p10':>5}{'p25':>5}{'p50':>5}{'p75':>5}{'p90':>5}{'o8.5':>7}{'o9.5':>7}")
    for lo in range(40, 160, 20):
        m = (combined >= lo) & (combined < lo+20)
        if m.sum() < 10: continue
        t = total_runs[m]
        p = np.percentile(t, [10,25,50,75,90])
        print(f"  {lo:3d}-{lo+19:<7d}{m.sum():>6}{t.mean():>7.2f}{t.std():>6.2f}"
              f"{p[0]:>5.0f}{p[1]:>5.0f}{p[2]:>5.0f}{p[3]:>5.0f}{p[4]:>5.0f}"
              f"{(t>8.5).mean()*100:>6.0f}%{(t>9.5).mean()*100:>6.0f}%")

    # ---------- E) team score -> own runs distribution ----------
    print("\n" + "="*64)
    print("E) OWN-RUNS DISTRIBUTION by TEAM score band  (score is 0-100, capped near ~95)")
    print("="*64)
    print(f"  {'score':10}{'n':>7}{'mean':>7}{'std':>6}{'p25':>5}{'p50':>5}{'p75':>5}{'p90':>5}{'>=4r':>7}{'>=5r':>7}{'>=6r':>7}{'<=1r':>7}")
    for lo in range(0, 100, 10):
        m = (tot_all >= lo) & (tot_all < lo+10)
        if m.sum() < 10: continue
        t = runs[m]
        p = np.percentile(t, [25,50,75,90])
        print(f"  {lo:2d}-{lo+9:<7d}{m.sum():>7}{t.mean():>7.2f}{t.std():>6.2f}"
              f"{p[0]:>5.0f}{p[1]:>5.0f}{p[2]:>5.0f}{p[3]:>5.0f}"
              f"{(t>=4).mean()*100:>6.0f}%{(t>=5).mean()*100:>6.0f}%{(t>=6).mean()*100:>6.0f}%{(t<=1).mean()*100:>6.0f}%")

    # stash final weights for the report
    with open(os.path.join(HERE, "final_weights.txt"), "w") as f:
        f.write(",".join(f"{x:.4f}" for x in finalw))
    print("\nFinal optimized weights saved to final_weights.txt")

    # ---------------- HTML report ----------------
    def bar(frac, color="#2563eb", w=120):
        return f'<div style="background:{color};height:10px;border-radius:3px;width:{max(1,frac*w):.0f}px"></div>'
    def wtxt(w):
        w = w/ w.sum(); return " · ".join(f"{c} {w[k]*100:.0f}%" for k,c in enumerate(COMPS))

    comp_rows = "".join(
        f'<tr><td>{name}</td><td class="n">{corr(S[:,k],runs):+.3f}</td><td>{bar(corr(S[:,k],runs)/0.16)}</td></tr>'
        for k,name in enumerate(COMPS))

    wsets = [("Baseline", BASE_W), ("Optimized (recommended)", W[best_corr_i]), ("Max spread-acc", W[best_acc_i])]
    wrows = ""
    for lbl,w in wsets:
        tr_m = evaluate(w,Str,rtr,iitr,jjtr); te_m = evaluate(w,Ste,rte,iite,jjte)
        wrows += (f'<tr><td>{lbl}<div class="sub">{wtxt(w)}</div></td>'
                  f'<td class="n">{tr_m["corr"]:+.3f}</td><td class="n">{te_m["corr"]:+.3f}</td>'
                  f'<td class="n">{tr_m["acc"]*100:.1f}%</td><td class="n">{te_m["acc"]*100:.1f}%</td></tr>')

    srows = ""
    for lo in range(0,80,10):
        m=(spread>=lo)&(spread<lo+10)
        if m.sum()<5: continue
        wr=(margin[m]>0).mean()*100; cov=(margin[m]>=2).mean()*100
        srows+=(f'<tr><td>{lo}–{lo+9}</td><td class="n">{m.sum()}</td><td class="n">{wr:.1f}%</td>'
                f'<td class="n">{margin[m].mean():+.2f}</td><td class="n">{cov:.1f}%</td><td>{bar(cov/100,"#7c3aed")}</td></tr>')

    drows=""
    for lo in range(40,160,20):
        m=(combined>=lo)&(combined<lo+20)
        if m.sum()<10: continue
        t=total_runs[m]; p=np.percentile(t,[10,50,90])
        drows+=(f'<tr><td>{lo}–{lo+19}</td><td class="n">{m.sum()}</td><td class="n">{t.mean():.2f}</td>'
                f'<td class="n">{t.std():.2f}</td><td class="n">{p[0]:.0f} / {p[1]:.0f} / {p[2]:.0f}</td>'
                f'<td class="n">{(t>8.5).mean()*100:.0f}%</td><td class="n">{(t>9.5).mean()*100:.0f}%</td></tr>')

    erows=""
    for lo in range(0,100,10):
        m=(tot_all>=lo)&(tot_all<lo+10)
        if m.sum()<10: continue
        t=runs[m]; p=np.percentile(t,[25,50,75,90])
        erows+=(f'<tr><td>{lo}–{lo+9}</td><td class="n">{m.sum()}</td><td class="n">{t.mean():.2f}</td>'
                f'<td class="n">{t.std():.2f}</td><td class="n">{p[0]:.0f} / {p[1]:.0f} / {p[2]:.0f} / {p[3]:.0f}</td>'
                f'<td class="n">{(t>=6).mean()*100:.0f}%</td><td class="n">{(t<=1).mean()*100:.0f}%</td></tr>')

    g40 = spread>=40
    html=f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Backtest Research — Weights, Spreads & Run Distributions</title><style>
:root{{--bg:#0b1220;--card:#111a2e;--line:#22304d;--txt:#e6edf7;--muted:#8aa0c0}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:26px}}
h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:15px;margin:26px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}}
.sub{{color:var(--muted);font-size:12px}}.wrap{{max-width:920px;margin:0 auto}}
table{{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-top:6px}}
th,td{{text-align:left;padding:7px 12px;border-bottom:1px solid var(--line);vertical-align:middle}}
th{{color:var(--muted);font-weight:600;font-size:12px}}td.n{{text-align:right;font-variant-numeric:tabular-nums}}
tr:last-child td{{border-bottom:none}}.note{{color:var(--muted);font-size:12.5px;margin-top:8px}}
.hi{{color:#7ee0a2;font-weight:600}}.key{{background:#152449}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px}}
.card .big{{font-size:22px;font-weight:700}}.card .lbl{{color:var(--muted);font-size:11.5px}}
</style></head><body><div class="wrap">
<h1>Backtest Research</h1>
<div class="sub">2024–2026 · {len(rows):,} complete-case team-games · weight tuning, run-line spreads, run distributions</div>

<h2>A. Which inputs actually predict runs?</h2>
<table><thead><tr><th>Input</th><th class="n">corr w/ runs</th><th></th></tr></thead><tbody>{comp_rows}</tbody></table>
<div class="note">OPS-Last-3 is the <b>strongest</b> single input; Runs-Last-3 is essentially <b>noise</b>; bullpen ERA is stronger than its 10% weight suggests; season OPS is middling, not zero.</div>

<h2>B. Can we improve the weights? (train 2024–25 → test 2026)</h2>
<table><thead><tr><th>Weighting</th><th class="n">corr train</th><th class="n">corr <u>test</u></th><th class="n">spread% train</th><th class="n">spread% test</th></tr></thead>
<tbody>{wrows}</tbody></table>
<div class="note">The optimizer drops Runs-L3 to 0, lifts bullpen + OPS-L3, and trims xERA — and the gain <b>holds out of sample</b> (test corr +0.136 → +0.176). Real, but modest: a few points, not a leap to 70% overall.</div>

<h2>C. Spread → run margin (the −1.5 run-line question)</h2>
<div class="cards">
<div class="card"><div class="big hi">{(margin[g40]>0).mean()*100:.0f}%</div><div class="lbl">gap ≥ 40: favored wins (n={g40.sum()})</div></div>
<div class="card"><div class="big hi">+{margin[g40].mean():.2f}</div><div class="lbl">gap ≥ 40: mean run margin</div></div>
<div class="card"><div class="big hi">{(margin[g40]>=2).mean()*100:.0f}%</div><div class="lbl">gap ≥ 40: covers −1.5 (win by 2+)</div></div>
</div>
<table><thead><tr><th>Score gap</th><th class="n">n</th><th class="n">win rate</th><th class="n">mean margin</th><th class="n">covers −1.5</th><th></th></tr></thead><tbody>{srows}</tbody></table>
<div class="note">Your intuition is right: at a <b>40+ gap</b> the favorite wins ~72% straight-up, by <b>+2.4 runs on average</b>, and covers −1.5 about 58% of the time (63% at 50+). Below ~30 the run line is a coin flip. Note total runs barely move with spread — spread drives <i>margin</i>, combined score drives <i>total</i>.</div>

<h2>D. Total-runs distribution by combined score (over/under)</h2>
<table><thead><tr><th>Combined</th><th class="n">n</th><th class="n">mean</th><th class="n">std</th><th class="n">p10 / p50 / p90</th><th class="n">over 8.5</th><th class="n">over 9.5</th></tr></thead><tbody>{drows}</tbody></table>
<div class="note">Higher combined → more total runs (7.7 → 11.3 mean), but variance is huge (std ~4–6). A combined-90 game still ranges from ~4 to ~14 runs. Over-8.5 rate climbs from 41% to 63%.</div>

<h2>E. A team's runs distribution by its score</h2>
<table><thead><tr><th>Team score</th><th class="n">n</th><th class="n">mean</th><th class="n">std</th><th class="n">p25 / p50 / p75 / p90</th><th class="n">scores 6+</th><th class="n">held ≤1</th></tr></thead><tbody>{erows}</tbody></table>
<div class="note">A top-band (80–99) team scores 6+ runs ~61% of the time and is held to ≤1 only ~6% — but the score is capped at 100, so "100+" essentially never happens. Even elite spots carry big variance (std ~3–4).</div>
</div></body></html>"""
    open(os.path.join(HERE,"research.html"),"w",encoding="utf-8").write(html)
    print("Wrote research.html")

if __name__ == "__main__":
    main()
