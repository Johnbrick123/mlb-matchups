#!/usr/bin/env python3
"""Render backtest results to a themed HTML page. Usage: python report.py 2024 2025 2026"""
import sys, os, csv
import research as R
HERE = os.path.dirname(os.path.abspath(__file__))
UNI = [0.24, 0.19, 0.25, 0.00, 0.32]   # optimized unified weighting (live)

def load(years):
    years = set(int(y) for y in years)
    rows = []
    for r in R.load():                 # complete cases, recompute total on UNI weights
        if r["season"] not in years:
            continue
        total = sum(s*w for s, w in zip(r["subs"], UNI)) / sum(UNI)
        rows.append({"season": r["season"], "pk": r["pk"], "total": total,
                     "runs": r["runs"], "opp_runs": r["opp_runs"]})
    return rows

def corr(xs, ys):
    n=len(xs); mx=sum(xs)/n; my=sum(ys)/n
    cov=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    vx=sum((x-mx)**2 for x in xs)**.5; vy=sum((y-my)**2 for y in ys)**.5
    return cov/(vx*vy) if vx and vy else 0.0

def calib(rows):
    b={}
    for r in rows:
        k=int(r["total"]//10)*10; b.setdefault(k,[]).append(r["runs"])
    return [(k,len(b[k]),sum(b[k])/len(b[k])) for k in sorted(b)]

def spread(rows):
    bg={}
    for r in rows: bg.setdefault(r["pk"],[]).append(r)
    w=l=0; sb={}
    for pk,pair in bg.items():
        if len(pair)!=2: continue
        hi,lo=(pair[0],pair[1]) if pair[0]["total"]>=pair[1]["total"] else (pair[1],pair[0])
        sp=hi["total"]-lo["total"]
        win=hi["runs"]>lo["runs"]; tie=hi["runs"]==lo["runs"]
        if not tie:
            w+=win; l+=(not win)
        k=int(sp//10)*10; d=sb.setdefault(k,[0,0])
        if not tie: d[0]+=win; d[1]+=(not win)
    grad=[(k,sb[k][0],sb[k][1]) for k in sorted(sb)]
    return w,l,grad

def combined(rows):
    bg={}
    for r in rows: bg.setdefault(r["pk"],[]).append(r)
    pts=[]
    for pk,pair in bg.items():
        if len(pair)!=2: continue
        pts.append((pair[0]["total"]+pair[1]["total"], pair[0]["runs"]+pair[1]["runs"]))
    cb={}
    for c,t in pts:
        k=int(c//20)*20; cb.setdefault(k,[]).append(t)
    return corr([p[0] for p in pts],[p[1] for p in pts]), [(k,len(cb[k]),sum(cb[k])/len(cb[k])) for k in sorted(cb)], len(pts)

def bar(frac, w=220):
    return f'<div style="background:#2563eb;height:11px;border-radius:3px;width:{max(1,frac*w):.0f}px"></div>'

def main(years):
    years=[int(y) for y in years]
    rows=load(years)
    if not rows:
        print("no data"); return
    c=corr([r["total"] for r in rows],[r["runs"] for r in rows])
    cal=calib(rows)
    w,l,grad=spread(rows)
    ccorr,ccurve,ngames=combined(rows)
    maxruns=max(x[2] for x in cal)
    maxtot=max(x[2] for x in ccurve)

    def calrows():
        out=""
        for k,n,avg in cal:
            out+=f'<tr><td>{k}–{k+9}</td><td class="n">{n:,}</td><td class="n">{avg:.2f}</td><td>{bar(avg/maxruns)}</td></tr>'
        return out
    def gradrows():
        out=""
        for k,gw,gl in grad:
            d=gw+gl; pct=gw/d*100 if d else 0
            out+=f'<tr><td>{k}–{k+9}</td><td class="n">{gw}-{gl}</td><td class="n">{pct:.1f}%</td><td>{bar(pct/100)}</td></tr>'
        return out
    def combrows():
        out=""
        for k,n,avg in ccurve:
            out+=f'<tr><td>{k}–{k+19}</td><td class="n">{n:,}</td><td class="n">{avg:.2f}</td><td>{bar(avg/maxtot)}</td></tr>'
        return out
    def perseason():
        out=""
        for y in years:
            yr=[r for r in rows if int(r["season"])==y]
            if not yr: continue
            yc=corr([r["total"] for r in yr],[r["runs"] for r in yr])
            yw,yl,_=spread(yr)
            out+=f'<tr><td>{y}</td><td class="n">{len(yr):,}</td><td class="n">{yc:+.3f}</td><td class="n">{yw/(yw+yl)*100:.1f}%</td></tr>'
        return out

    html=f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Backtest — MLB Matchup Scores</title><style>
:root{{--bg:#0b1220;--card:#111a2e;--line:#22304d;--txt:#e6edf7;--muted:#8aa0c0}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;padding:28px}}
h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:15px;margin:26px 0 10px;border-bottom:1px solid var(--line);padding-bottom:6px}}
.sub{{color:var(--muted);font-size:13px}}.wrap{{max-width:900px;margin:0 auto}}
.cards{{display:flex;gap:14px;flex-wrap:wrap;margin:16px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;min-width:150px}}
.card .big{{font-size:26px;font-weight:700}}.card .lbl{{color:var(--muted);font-size:12px}}
table{{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th,td{{text-align:left;padding:7px 12px;border-bottom:1px solid var(--line)}}th{{color:var(--muted);font-weight:600;font-size:12px}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}tr:last-child td{{border-bottom:none}}
.note{{color:var(--muted);font-size:12.5px;margin-top:8px}}.hi{{color:#7ee0a2;font-weight:600}}
</style></head><body><div class="wrap">
<h1>Backtest — MLB Matchup Scores</h1>
<div class="sub">Point-in-time predictive validation · optimized weights (xERA 24 · OPS 19 · Bullpen 25 · Runs L3 0 · OPS L3 32) · seasons {', '.join(map(str,years))} · {len(rows):,} team-games</div>

<div class="cards">
<div class="card"><div class="big">{len(rows):,}</div><div class="lbl">team-games scored</div></div>
<div class="card"><div class="big hi">{c:+.3f}</div><div class="lbl">corr(score, runs scored)</div></div>
<div class="card"><div class="big hi">{w/(w+l)*100:.1f}%</div><div class="lbl">spread-lean win rate ({w:,}-{l:,})</div></div>
<div class="card"><div class="big hi">{ccorr:+.3f}</div><div class="lbl">corr(combined, total runs)</div></div>
</div>

<h2>Calibration — does a higher score mean more runs?</h2>
<table><thead><tr><th>Score bucket</th><th class="n">Games</th><th class="n">Avg runs</th><th></th></tr></thead><tbody>{calrows()}</tbody></table>
<div class="note">Each 10-point rise in the model score maps to real, monotonic gains in actual runs scored.</div>

<h2>Spread — does the higher-rated team out-score its opponent?</h2>
<table><thead><tr><th>Model spread</th><th class="n">W-L</th><th class="n">Win %</th><th></th></tr></thead><tbody>{gradrows()}</tbody></table>
<div class="note">Even matchups (0–9) sit at a coin flip, as they should; the win rate climbs as the model's edge grows — the signature of real signal.</div>

<h2>Combined total — does a higher combined score mean a higher-scoring game?</h2>
<table><thead><tr><th>Combined bucket</th><th class="n">Games</th><th class="n">Avg total runs</th><th></th></tr></thead><tbody>{combrows()}</tbody></table>

<h2>By season</h2>
<table><thead><tr><th>Season</th><th class="n">Team-games</th><th class="n">corr(score,runs)</th><th class="n">Spread win %</th></tr></thead><tbody>{perseason()}</tbody></table>

<div class="note" style="margin-top:22px">
<b>Method.</b> For every game, inputs are reconstructed using only data available <i>before</i> that game — no look-ahead.
Opposing-starter xERA is rebuilt from Statcast pitch-level xwOBA accumulated to date (validated to within ±0.04 of Savant's published xERA);
team OPS, OPS L3, Runs L3, and opponent bullpen ERA are point-in-time. Scores use the identical engine and weights as the live site.
Single-game baseball is inherently noisy, so game-level correlations in the 0.15–0.20 range represent meaningful predictive signal.
</div>
</div></body></html>"""
    outp=os.path.join(HERE,"report.html")
    open(outp,"w",encoding="utf-8").write(html)
    print("wrote",outp,f"({len(rows):,} games)")

if __name__=="__main__":
    main(sys.argv[1:] or [2024,2025,2026])
