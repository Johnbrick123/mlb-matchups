#!/usr/bin/env python3
"""Test three candidate features (home/away OPS, park factor, bullpen fatigue) for added signal."""
import os, csv
from datetime import date as _date
from collections import defaultdict
import numpy as np
import bt

HERE=os.path.dirname(os.path.abspath(__file__))
SEASONS=[2024,2025,2026]
SCALES=bt.SCALES
UNI={"xERA":0.24,"ops":0.19,"bullpen":0.25,"runsL3":0.00,"opsL3":0.32}

def sub(v,k):
    if v is None: return None
    lo,hi=SCALES[k]; return max(0,min(100,(v-lo)/(hi-lo)*100))
def d(s): y,m,dd=s.split("-"); return _date(int(y),int(m),int(dd))
def corr(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float)
    return 0.0 if a.std()==0 or b.std()==0 else float(np.corrcoef(a,b)[0,1])
def resid_corr(feat,base,y):
    """signal 'feat' adds beyond 'base' for predicting y."""
    feat=np.asarray(feat,float); base=np.asarray(base,float)
    bcoef=np.polyfit(base,feat,1); r=feat-np.polyval(bcoef,base)
    return corr(r,y)

def ops_from(c):
    obp_den=c["ab"]+c["bb"]+c["hbp"]+c["sf"]
    if c["ab"]==0 or obp_den==0: return None
    return (c["h"]+c["bb"]+c["hbp"])/obp_den + c["tb"]/c["ab"]

def build(year):
    games=bt.get_schedule(year)
    tg=defaultdict(list)   # team -> [(date,is_home,rs,ra)]
    for g in games:
        tg[g["away_id"]].append((g["date"],False,g["away_score"],g["home_score"]))
        tg[g["home_id"]].append((g["date"],True,g["home_score"],g["away_score"]))
    homedates={t:{d for d,ih,_,_ in gl if ih} for t,gl in tg.items()}
    # hitting split
    hit=defaultdict(list)
    for t in tg:
        for r in bt.get_team_gamelog(t,year,"hitting"):
            dt=r["date"]; ih=dt in homedates[t]
            hit[t].append((dt,ih,dict(ab=int(r.get("atBats",0) or 0),h=int(r.get("hits",0) or 0),
                tb=int(r.get("totalBases",0) or 0),bb=int(r.get("baseOnBalls",0) or 0),
                hbp=int(r.get("hitByPitch",0) or 0),sf=int(r.get("sacFlies",0) or 0))))
        hit[t].sort(key=lambda x: x[0])
    # bullpen outs by date (team total - starter)
    teampit=defaultdict(lambda: defaultdict(lambda:[0,0]))
    for t in tg:
        for r in bt.get_team_gamelog(t,year,"pitching"):
            teampit[t][r["date"]][0]+=int(r.get("earnedRuns",0) or 0)
            teampit[t][r["date"]][1]+=bt.ip_to_outs(r.get("inningsPitched"))
    prob=sorted({g[k] for g in games for k in ("away_prob","home_prob") if g[k]})
    plog={p:bt.get_pitcher_gamelog(p,year) for p in prob}
    st_outs=defaultdict(dict)
    for g in games:
        for tid,pid in ((g["away_id"],g["away_prob"]),(g["home_id"],g["home_prob"])):
            if pid:
                for r in plog[pid]:
                    if r["date"]==g["date"]: st_outs[tid][g["date"]]=r["outs"]; break
    bull=defaultdict(dict)
    for t in tg:
        for dt,(er,outs) in teampit[t].items():
            bull[t][dt]=max(0,outs-st_outs[t].get(dt,0))/3.0   # relief innings
    return dict(games=games,tg=tg,homedates=homedates,hit=hit,bull=bull)

# park factor per team per season (home/road run ratio), then leave-one-season-out
def park_factors(S):
    pf={}
    for y in SEASONS:
        ratios={}
        for t,gl in S[y]["tg"].items():
            h=[rs+ra for _,ih,rs,ra in gl if ih]; r=[rs+ra for _,ih,rs,ra in gl if not ih]
            if len(h)>=20 and len(r)>=20 and sum(r): ratios[t]=(sum(h)/len(h))/(sum(r)/len(r))
        mean=np.mean(list(ratios.values()))
        pf[y]={t:100*v/mean for t,v in ratios.items()}
    # LOO: park factor for (team,season) = mean of that team's PF in OTHER seasons (fallback: own)
    loo={}
    for y in SEASONS:
        loo[y]={}
        for t in pf[y]:
            others=[pf[o][t] for o in SEASONS if o!=y and t in pf[o]]
            loo[y][t]=np.mean(others) if others else pf[y][t]
    return loo

def ops_split_asof(hitlist,date,is_home):
    c=dict(ab=0,h=0,tb=0,bb=0,hbp=0,sf=0)
    for dt,ih,comp in hitlist:
        if dt>=date: break
        if ih==is_home:
            for k in c: c[k]+=comp[k]
    return ops_from(c)

def bull_fatigue(bulld,date,days=3):
    D=d(date); tot=0.0
    for dt,ip in bulld.items():
        delta=(D-d(dt)).days
        if 1<=delta<=days: tot+=ip
    return tot

def main():
    S={y:build(y) for y in SEASONS}
    PF=park_factors(S)
    # load current-model inputs + outcomes from games csv, key (pk,team_id)
    csvrows={}
    for y in SEASONS:
        for r in csv.DictReader(open(os.path.join(HERE,f"games_{y}.csv"),encoding="utf-8")):
            csvrows[(r["pk"],int(r["team_id"]))]=r
    recs=[]
    for y in SEASONS:
        for g in S[y]["games"]:
            for side,tid,oid in (("Away",g["away_id"],g["home_id"]),("Home",g["home_id"],g["away_id"])):
                cr=csvrows.get((str(g["pk"]),tid))
                if not cr: continue
                try:
                    ops=float(cr["ops"]); oppbull=float(cr["oppBullpenERA"])
                except: continue
                is_home=(side=="Home")
                cops=ops_split_asof(S[y]["hit"][tid],g["date"],is_home)
                if cops is None: continue
                # team score (optimized) for residual baselines
                parts={k:sub(float(cr[c]) if cr[c] not in ("",None) else None,k)
                       for k,c in [("xERA","oppXERA"),("ops","ops"),("bullpen","oppBullpenERA"),("runsL3","runsL3"),("opsL3","opsL3")]}
                if parts["xERA"] is None: continue
                tscore=sum((parts[k] or 0)*UNI[k] for k in UNI)/sum(UNI.values())
                recs.append(dict(y=y,pk=str(g["pk"]),tid=tid,is_home=is_home,
                    runs=g["away_score"] if side=="Away" else g["home_score"],
                    ops=ops, cops=cops, tscore=tscore,
                    pf=PF[y].get(g["home_id"],100.0),
                    oppbull_era=oppbull,
                    opp_fatigue=bull_fatigue(S[y]["bull"][oid],g["date"])))
    print(f"records: {len(recs)}\n")
    R=lambda k:[r[k] for r in recs]
    runs=R("runs")

    print("="*60)
    print("1) HOME/AWAY OPS SPLIT")
    print("="*60)
    print(f"  corr(overall OPS , runs)      = {corr(R('ops'),runs):+.3f}")
    print(f"  corr(home/away OPS , runs)    = {corr(R('cops'),runs):+.3f}")
    print(f"  signal split adds beyond OPS  = {resid_corr(R('cops'),R('ops'),runs):+.3f}")

    print("\n"+"="*60)
    print("2) PARK FACTOR")
    print("="*60)
    print(f"  corr(park factor , team runs)          = {corr(R('pf'),runs):+.3f}")
    print(f"  signal PF adds beyond team score       = {resid_corr(R('pf'),R('tscore'),runs):+.3f}")
    # totals: combined score & total runs per game
    byg=defaultdict(list)
    for r in recs: byg[r["pk"]].append(r)
    comb=[];tot=[];pfg=[]
    for pk,v in byg.items():
        if len(v)==2:
            comb.append(v[0]["tscore"]+v[1]["tscore"]); tot.append(v[0]["runs"]+v[1]["runs"]); pfg.append(v[0]["pf"])
    print(f"  corr(park factor , GAME TOTAL runs)    = {corr(pfg,tot):+.3f}")
    print(f"  signal PF adds beyond combined score   = {resid_corr(pfg,comb,tot):+.3f}   (n={len(tot)} games)")

    print("\n"+"="*60)
    print("3) BULLPEN FATIGUE  (opponent relief IP last 3 days)")
    print("="*60)
    fat=R("opp_fatigue")
    print(f"  mean opp fatigue: {np.mean(fat):.1f} relief IP/last-3-days")
    print(f"  corr(opp bullpen fatigue , team runs)  = {corr(fat,runs):+.3f}")
    print(f"  signal beyond opp bullpen ERA          = {resid_corr(fat,R('oppbull_era'),runs):+.3f}")
    # split: rested vs gassed
    fa=np.array(fat); ru=np.array(runs,float)
    for lab,mask in [("rested (bottom 25% fatigue)",fa<=np.quantile(fa,.25)),
                     ("gassed (top 25% fatigue)",fa>=np.quantile(fa,.75))]:
        print(f"    {lab:32} avg runs vs them = {ru[mask].mean():.2f}  (n={mask.sum()})")

if __name__=="__main__":
    main()
