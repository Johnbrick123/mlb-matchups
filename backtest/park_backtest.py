#!/usr/bin/env python3
"""Does a given combined score mean different totals at different parks? (park conditions the O/U rule)"""
import os, csv
import numpy as np
import test_features as T

HERE=os.path.dirname(os.path.abspath(__file__))
S={y:T.build(y) for y in T.SEASONS}
PF=T.park_factors(S)                 # leave-one-season-out park factor by team/season
UNI=T.UNI; sub=T.sub

csvrows={}
for y in T.SEASONS:
    for r in csv.DictReader(open(os.path.join(HERE,f"games_{y}.csv"),encoding="utf-8")):
        csvrows[(r["pk"],int(r["team_id"]))]=r

def score(r):
    p={k:sub(float(r[c]) if r[c] not in ("",None) else None,k)
       for k,c in [("xERA","oppXERA"),("ops","ops"),("bullpen","oppBullpenERA"),("runsL3","runsL3"),("opsL3","opsL3")]}
    if p["xERA"] is None: return None
    return sum((p[k] or 0)*UNI[k] for k in UNI)/sum(UNI.values())

games=[]
for y in T.SEASONS:
    for g in S[y]["games"]:
        rh=csvrows.get((str(g["pk"]),g["home_id"])); ra=csvrows.get((str(g["pk"]),g["away_id"]))
        if not rh or not ra: continue
        sh=score(rh); sa=score(ra); pf=PF[y].get(g["home_id"])
        if sh is None or sa is None or pf is None: continue
        games.append((sh+sa, g["home_score"]+g["away_score"], pf))
comb=np.array([x[0] for x in games]); tot=np.array([x[1] for x in games],float); pf=np.array([x[2] for x in games])
print(f"{len(games)} games\n")

# park tiers by tercile
lo,hi=np.quantile(pf,[1/3,2/3])
tier=np.where(pf>=hi,"hitter",np.where(pf<=lo,"pitcher","neutral"))
names={"pitcher":f"pitcher parks (PF<={lo:.0f})","neutral":"neutral parks","hitter":f"hitter parks (PF>={hi:.0f})"}

print("="*70)
print("THE TEST: hold combined score ~constant (100-120), vary the park")
print("="*70)
band=(comb>=100)&(comb<120)
print(f"  games with combined 100-120: {band.sum()}")
print(f"  {'park tier':26}{'n':>5}{'avg total':>11}{'over 8.5':>10}{'over 9.5':>10}")
for t in ("pitcher","neutral","hitter"):
    m=band&(tier==t)
    print(f"  {names[t]:26}{m.sum():>5}{tot[m].mean():>11.2f}{(tot[m]>8.5).mean()*100:>9.0f}%{(tot[m]>9.5).mean()*100:>9.0f}%")

print("\n"+"="*70)
print("FULL GRID: over-8.5 rate by combined tier x park tier")
print("="*70)
cbands=[("combined <90",comb<90),("combined 90-105",(comb>=90)&(comb<105)),
        ("combined 105-120",(comb>=105)&(comb<120)),("combined >=120",comb>=120)]
print(f"  {'':18}{'pitcher pk':>12}{'neutral':>10}{'hitter pk':>11}   (n per cell)")
for lab,cm in cbands:
    cells=""
    for t in ("pitcher","neutral","hitter"):
        m=cm&(tier==t)
        cells+=f"{(tot[m]>8.5).mean()*100:>8.0f}% ({m.sum():>3})" if m.sum() else f"{'--':>12}"
    print(f"  {lab:18}{cells}")

print("\n"+"="*70)
print("PUNCHLINE: park swing at a FIXED combined score")
print("="*70)
for lab,cm in cbands[1:]:
    h=tot[cm&(tier=='hitter')]; p=tot[cm&(tier=='pitcher')]
    if len(h)>20 and len(p)>20:
        print(f"  {lab:18}: hitter park {h.mean():.2f} total vs pitcher park {p.mean():.2f}  = {h.mean()-p.mean():+.2f} runs from PARK alone")
