#!/usr/bin/env python3
"""Scan for high-confidence over/under alert rules keyed on combined score."""
import os, csv, json
import numpy as np
import research as R

HERE=os.path.dirname(os.path.abspath(__file__))
BASE=np.array([0.40,0.30,0.10,0.10,0.10])
OPT =np.array([0.25,0.17,0.29,0.00,0.28])  # recommended optimized (max-corr)

def build(weights):
    rows=R.load()
    S=np.array([r["subs"] for r in rows]); runs=np.array([r["runs"] for r in rows])
    seas=np.array([r["season"] for r in rows])
    tot=S@(weights/weights.sum())
    by={}
    for i,r in enumerate(rows): by.setdefault(r["pk"],[]).append(i)
    comb=[];tr=[];sea=[]
    for pk,idx in by.items():
        if len(idx)==2:
            comb.append(tot[idx[0]]+tot[idx[1]]); tr.append(runs[idx[0]]+runs[idx[1]]); sea.append(seas[idx[0]])
    return np.array(comb),np.array(tr),np.array(sea)

def wilson_lo(k,n,z=1.96):
    if n==0: return 0
    p=k/n; d=1+z*z/n
    return (p+z*z/(2*n)-z*np.sqrt((p*(1-p)+z*z/(4*n))/n))/d

comb,tr,sea=build(BASE)
combO,_,_=build(OPT)
N=len(comb)
print(f"Games (both sides scored): {N}")
print(f"combined->total corr: baseline {np.corrcoef(comb,tr)[0,1]:+.3f} | optimized {np.corrcoef(combO,tr)[0,1]:+.3f}")
print(f"overall total runs: mean {tr.mean():.2f}  median {np.median(tr):.0f}\n")

LINES=[6.5,7.5,8.5,9.5]
print("BASE RATES (all games):")
for L in LINES:
    print(f"  over {L}: {(tr>L).mean()*100:4.1f}%   under {L}: {(tr<L).mean()*100:4.1f}%")

def scan(direction, thresholds, lines):
    print(f"\n{'='*72}\n{direction.upper()} SCAN\n{'='*72}")
    hdr="thresh     n   " + "".join(f"{('o' if direction=='over' else 'u')}{L:<7}" for L in lines)
    print(hdr)
    for T in thresholds:
        m = comb>=T if direction=="over" else comb<=T
        n=m.sum()
        if n<40: continue
        cells=""
        for L in lines:
            hit=(tr[m]>L).mean() if direction=="over" else (tr[m]<L).mean()
            cells+=f"{hit*100:4.0f}%   "
        print(f"{('>=' if direction=='over' else '<=')}{T:<6}{n:>5}   {cells}")

scan("over", range(95,150,5), LINES)
scan("under", range(85,45,-5), LINES)

# ---- pick candidate rules, validate on 2026 holdout ----
print(f"\n{'='*72}\nRULE VALIDATION  (train 2024-25  vs  test 2026)\n{'='*72}")
def rule_stats(mask_fn, line, over=True, label=""):
    def hit(m):
        t=tr[m]
        return ((t>line).mean() if over else (t<line).mean()), m.sum()
    tr_mask = mask_fn(comb) & (sea<2026)
    te_mask = mask_fn(comb) & (sea==2026)
    all_mask= mask_fn(comb)
    ph,na=hit(all_mask); pt,_=hit(tr_mask); pe,ne=hit(te_mask)
    lo=wilson_lo(int(round(ph*na)),na)
    print(f"  {label:34} ALL {ph*100:4.1f}% (n={na:4d}, 95%floor {lo*100:4.1f}%) | train {pt*100:4.1f}% | test {pe*100:4.1f}% (n={ne})")
    return {"label":label,"line":line,"over":over,"hit":round(ph*100,1),"n":int(na),"floor":round(lo*100,1)}

rules=[]
rules.append(rule_stats(lambda c:c>=120, 8.5, True,  "OVER 8.5  when combined >= 120"))
rules.append(rule_stats(lambda c:c>=115, 7.5, True,  "OVER 7.5  when combined >= 115"))
rules.append(rule_stats(lambda c:c>=110, 6.5, True,  "OVER 6.5  when combined >= 110"))
rules.append(rule_stats(lambda c:c>=130, 9.5, True,  "OVER 9.5  when combined >= 130"))
rules.append(rule_stats(lambda c:c<=65,  7.5, False, "UNDER 7.5 when combined <= 65"))
rules.append(rule_stats(lambda c:c<=70,  8.5, False, "UNDER 8.5 when combined <= 70"))
rules.append(rule_stats(lambda c:c<=60,  6.5, False, "UNDER 6.5 when combined <= 60"))

# user's specific claims
print(f"\n{'='*72}\nYOUR EXAMPLE CLAIMS\n{'='*72}")
m=comb>=100; print(f"  combined>=100 -> over 6 (7+ runs): {(tr[m]>6).mean()*100:.1f}%  (n={m.sum()})  [you guessed 80%]")
m=comb<=70;  print(f"  combined<=70  -> under 8 (<=7 runs): {(tr[m]<8).mean()*100:.1f}%  (n={m.sum()})  [you guessed 80%]")

json.dump(rules, open(os.path.join(HERE,"alert_rules.json"),"w"), indent=1)
print("\nSaved alert_rules.json")
