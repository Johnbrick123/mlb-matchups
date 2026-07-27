#!/usr/bin/env python3
"""Team OFFENSIVE xwOBA, point-in-time, via Statcast (monthly chunks to dodge the 25k-row cap).
Usage: python bt_xwoba.py fetch 2024      # cache team batting statcast
       python bt_xwoba.py test  2024      # does as-of team xwOBA predict runs / add to OPS?
"""
import sys, os, io, csv, time, calendar
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import bt

HERE=os.path.dirname(os.path.abspath(__file__))
CACHE=os.path.join(HERE,"cache","xwoba")
UA={"User-Agent":"Mozilla/5.0 (backtest research; jhnbrick@gmail.com)"}

SAVANT={108:"LAA",109:"AZ",110:"BAL",111:"BOS",112:"CHC",113:"CIN",114:"CLE",115:"COL",
        116:"DET",117:"HOU",118:"KC",119:"LAD",120:"WSH",121:"NYM",133:"OAK",134:"PIT",
        135:"SD",136:"SEA",137:"SF",138:"STL",139:"TB",140:"TEX",141:"TOR",142:"MIN",
        143:"PHI",144:"ATL",145:"CWS",146:"MIA",147:"NYY",158:"MIL"}

def months(year):
    return [3,4,5,6,7,8,9,10] if year!=2026 else [3,4,5,6,7]

def fetch_chunk(code, year, m):
    os.makedirs(CACHE, exist_ok=True)
    p=os.path.join(CACHE,f"{code}_{year}_{m:02d}.csv")
    if os.path.exists(p) and os.path.getsize(p)>0:
        return open(p,encoding="utf-8").read()
    last=calendar.monthrange(year,m)[1]
    url=(f"https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfGT=R%7C&hfTeam={code}%7C"
         f"&player_type=batter&game_date_gt={year}-{m:02d}-01&game_date_lt={year}-{m:02d}-{last}&type=details")
    for i in range(4):
        try:
            txt=urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=120).read().decode("utf-8-sig","replace")
            open(p,"w",encoding="utf-8").write(txt); return txt
        except Exception as e:
            time.sleep(2*(i+1)); err=e
    raise RuntimeError(f"{code} {year}-{m}: {err}")

def team_PAs(team_id, year):
    """Return sorted [(date, contrib, denom)] terminal PAs for a team's hitters."""
    code=SAVANT[team_id]; pas=[]
    for m in months(year):
        txt=fetch_chunk(code,year,m)
        rows=list(csv.DictReader(io.StringIO(txt)))
        if len(rows)>=25000:
            print(f"  WARN {code} {year}-{m}: hit 25k cap ({len(rows)}) — chunk finer")
        for x in rows:
            if not x.get("events") or not x.get("woba_denom"): continue
            est=x.get("estimated_woba_using_speedangle")
            c=float(est) if est not in ("","null",None) else (float(x["woba_value"]) if x.get("woba_value") not in ("","null",None) else 0.0)
            pas.append((x["game_date"], c, float(x["woba_denom"])))
    pas.sort()
    return pas

def cmd_fetch(year):
    year=int(year)
    games=bt.get_schedule(year)
    tids=sorted({g["away_id"] for g in games}|{g["home_id"] for g in games})
    jobs=[(t,m) for t in tids for m in months(year)]
    print(f"[{year}] {len(tids)} teams x {len(months(year))} months = {len(jobs)} chunks")
    done=0; errs=[]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(fetch_chunk,SAVANT[t],year,m):(t,m) for t,m in jobs}
        for f in as_completed(futs):
            try: f.result()
            except Exception as e: errs.append(str(e))
            done+=1
            if done%40==0: print(f"[{year}] {done}/{len(jobs)}")
    print(f"[{year}] done, {len(errs)} errors")
    for e in errs[:10]: print("  ERR",e)

def xwoba_asof(pas, date):
    num=den=0.0
    for d,c,w in pas:
        if d>=date: break
        num+=c; den+=w
    return (num/den, den) if den>0 else (None,0)

def cmd_test(year):
    import numpy as np, research as R
    year=int(year)
    # cache team PAs
    games=bt.get_schedule(year)
    tids=sorted({g["away_id"] for g in games}|{g["home_id"] for g in games})
    print(f"[{year}] loading team PAs…")
    PAS={t:team_PAs(t,year) for t in tids}
    # validate one team full-season vs Savant-style
    for t in (147,):
        xw,pa=xwoba_asof(PAS[t], f"{year}-12-01")
        print(f"  validate {SAVANT[t]} {year} full-season xwOBA={xw:.4f} (PA {pa:.0f})")
    # join to games_YEAR.csv (has team_id,date,ops,opsL3,runsL3,runs,pk)
    p=os.path.join(HERE,f"games_{year}.csv")
    rows=[r for r in csv.DictReader(open(p,encoding="utf-8"))]
    xs_xw=[]; xs_ops=[]; ys=[]
    perpk={}
    for r in rows:
        tid=int(r["team_id"]); date=r["date"]
        xw,den=xwoba_asof(PAS.get(tid,[]), date)
        if xw is None or den<50: continue
        try: ops=float(r["ops"])
        except: continue
        runs=int(r["runs"])
        xs_xw.append(xw); xs_ops.append(ops); ys.append(runs)
        perpk.setdefault(r["pk"],[]).append((xw,runs))
    xw=np.array(xs_xw); ops=np.array(xs_ops); y=np.array(ys,float)
    def corr(a,b): return float(np.corrcoef(a,b)[0,1])
    print(f"\n[{year}] team-games with xwOBA: {len(y)}")
    print(f"  corr(team xwOBA , runs scored) = {corr(xw,y):+.3f}")
    print(f"  corr(team OPS   , runs scored) = {corr(ops,y):+.3f}   <- current model input")
    print(f"  corr(xwOBA , OPS)              = {corr(xw,ops):+.3f}")
    # does xwOBA add beyond OPS? partial via residual
    b=np.polyfit(ops,xw,1); xw_resid=xw-np.polyval(b,ops)
    print(f"  corr(xwOBA-residual-after-OPS , runs) = {corr(xw_resid,y):+.3f}  (signal xwOBA adds ON TOP of OPS)")
    # combined (game total)
    comb=[]; tot=[]
    for pk,v in perpk.items():
        if len(v)==2: comb.append(v[0][0]+v[1][0]); tot.append(v[0][1]+v[1][1])
    if comb:
        print(f"  corr(combined team xwOBA , game total runs) = {corr(np.array(comb),np.array(tot)):+.3f}  (n={len(comb)})")

if __name__=="__main__":
    {"fetch":cmd_fetch,"test":cmd_test}[sys.argv[1]](sys.argv[2])
