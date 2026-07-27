#!/usr/bin/env python3
"""Compare baseline vs unified-optimized vs totals-optimized weights for the totals system."""
import os, json
import numpy as np
import research as R

HERE=os.path.dirname(os.path.abspath(__file__))
COMPS=["xERA","ops","bullpen","runsL3","opsL3"]
BASE=np.array([0.40,0.30,0.10,0.10,0.10])

rows=R.load()
S=np.array([r["subs"] for r in rows]); runs=np.array([r["runs"] for r in rows])
seas=np.array([r["season"] for r in rows])
by={}
for i,r in enumerate(rows): by.setdefault(r["pk"],[]).append(i)
pairs=[(idx[0],idx[1]) for idx in by.values() if len(idx)==2]
ii=np.array([a for a,_ in pairs]); jj=np.array([b for _,b in pairs])
pair_sea=seas[ii]

def corr(a,b):
    if np.std(a)==0 or np.std(b)==0: return 0.0
    return float(np.corrcoef(a,b)[0,1])

# ---- derive weightings ----
rng=np.random.default_rng(0)
W=rng.dirichlet(np.ones(5),size=60000)
tr_team=seas<2026
# unified: maximize corr(team_score, team_runs) on train
tot_all=S@W.T
rc_team=np.array([corr(tot_all[tr_team,m],runs[tr_team]) for m in range(W.shape[0])])
UNI=W[int(rc_team.argmax())]
# totals: maximize corr(combined, total_runs) on train
comb_all=tot_all[ii]+tot_all[jj]; total=runs[ii]+runs[jj]
trp=pair_sea<2026
rc_tot=np.array([corr(comb_all[trp,m],total[trp]) for m in range(W.shape[0])])
TOT=W[int(rc_tot.argmax())]

def wstr(w): return " ".join(f"{c}={w[k]*100:.0f}" for k,c in enumerate(COMPS))
print("WEIGHTS (%):")
print("  baseline :",wstr(BASE))
print("  unified  :",wstr(UNI/UNI.sum()))
print("  totals   :",wstr(TOT/TOT.sum()))

def combined_total(w):
    t=S@(w/w.sum()); return t[ii]+t[jj], runs[ii]+runs[jj]

print("\ncombined -> total-runs correlation:")
for name,w in [("baseline",BASE),("unified",UNI),("totals",TOT)]:
    c,tt=combined_total(w)
    ctest=corr(c[pair_sea==2026],tt[pair_sea==2026])
    print(f"  {name:9} all {corr(c,tt):+.3f} | test2026 {ctest:+.3f}")

# ---- equal-coverage over/under comparison ----
LINES=[7.5,8.5,9.5]
def cover_rates(w, q, over=True):
    c,tt=combined_total(w)
    thr=np.quantile(c, 1-q if over else q)
    m = c>=thr if over else c<=thr
    return {L:(tt[m]>L).mean() if over else (tt[m]<L).mean() for L in LINES}, m.sum()

for over in (True,False):
    side="OVER" if over else "UNDER"
    print(f"\n{'='*66}\n{side}  rates at equal coverage (higher = sharper)\n{'='*66}")
    for q in (0.10,0.20,0.30):
        print(f"  --- top {int(q*100)}% {'highest' if over else 'lowest'} combined ---")
        print(f"    {'weighting':10}" + "".join(f"{side[0].lower()}{L:<6}" for L in LINES) + " n")
        for name,w in [("baseline",BASE),("unified",UNI),("totals",TOT)]:
            r,n=cover_rates(w,q,over)
            print(f"    {name:10}" + "".join(f"{r[L]*100:4.0f}%  " for L in LINES) + f" {n}")

# ---- concrete validated rules under UNIFIED (the live weighting) ----
def wilson_lo(k,n,z=1.96):
    if n==0: return 0
    p=k/n; d=1+z*z/n
    return (p+z*z/(2*n)-z*np.sqrt((p*(1-p)+z*z/(4*n))/n))/d

print(f"\n{'='*66}\nCONCRETE ALERT RULES — UNIFIED optimized (live) — train/test\n{'='*66}")
cU,ttU=combined_total(UNI)
def rule(thr, line, over=True):
    m = cU>=thr if over else cU<=thr
    def h(mask):
        t=ttU[mask]; return (t>line).mean() if over else (t<line).mean(), mask.sum()
    ph,na=h(m); ptr,_=h(m&(pair_sea<2026)); pte,ne=h(m&(pair_sea==2026))
    lo=wilson_lo(int(round(ph*na)),na)
    d="OVER" if over else "UNDER"
    print(f"  {d} {line} @ combined {'>=' if over else '<='}{thr:5.0f}: {ph*100:4.1f}% (n={na:4d}, floor {lo*100:4.1f}%) tr {ptr*100:4.1f} te {pte*100:4.1f} (n={ne})")
# choose thresholds by unified combined quantiles
qs=lambda p: float(np.quantile(cU,p))
for line,p in [(7.5,0.80),(8.5,0.85),(9.5,0.90)]:
    rule(qs(p),line,True)
for line,p in [(8.5,0.20),(7.5,0.15),(9.5,0.30)]:
    rule(qs(p),line,False)

json.dump({"unified":list(UNI/UNI.sum()),"totals":list(TOT/TOT.sum())},
          open(os.path.join(HERE,"weights_opt.json"),"w"),indent=1)
print("\ncombined-score range (unified): %.0f to %.0f"%(cU.min(),cU.max()))
print("saved weights_opt.json")
