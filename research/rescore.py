#!/usr/bin/env python3
"""Rescore a slate swapping the 25% bullpen input for Effective Bullpen Quality."""
import json, re, sys, os
import bullpen_core as bc

HERE = os.path.dirname(os.path.abspath(__file__))


def load_slate(path):
    txt = open(path).read()
    txt = txt[txt.index("window.SLATE"):]
    txt = txt[txt.index("{"):txt.rindex("};") + 1]
    txt = re.sub(r"(\{|,)\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', txt)
    return json.loads(txt.rstrip(";"))


def sub(v, lo, hi):
    return None if v is None else max(0.0, min(100.0, (v - lo) / (hi - lo) * 100))


def score(row, slate, bull_era):
    s, w = slate["scales"], slate["weights"]
    parts = {
        "xERA": sub(row.get("oppXERA"), s["xERA"]["min"], s["xERA"]["max"]),
        "bullpen": sub(bull_era, s["bullpen"]["min"], s["bullpen"]["max"]),
        "ops": sub(row.get("ops"), s["ops"]["min"], s["ops"]["max"]),
        "opsL3": sub(row.get("opsL3"), s["opsL3"]["min"], s["opsL3"]["max"]),
        "runsL3": sub(row.get("runsL3"), s["runsL3"]["min"], s["runsL3"]["max"]),
    }
    if parts["xERA"] is None:
        return None, parts
    tot = sum((parts[k] or 0.0) * w[k] for k in w) / sum(w.values())
    return round(tot, 1), parts


def main():
    slate = load_slate(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "../data.js"))
    date = slate["date"]
    eff = bc.build(date[:4], date)

    # opponent abbr for each row
    abbr_of = {}
    for r in slate["rows"]:
        abbr_of[r["team"]] = r["abbr"]

    out = []
    for r in slate["rows"]:
        opp_ab = abbr_of.get(r["opp"])
        e = eff.get(opp_ab, {})
        new_era = e.get("effective_era")
        old, po = score(r, slate, r.get("oppBullpenERA"))
        new, pn = score(r, slate, new_era)
        out.append(dict(game=r["game"], ab=r["abbr"], ha=r["ha"], opp=opp_ab,
                        old=old, new=new,
                        old_bp=round(po["bullpen"], 1) if po["bullpen"] is not None else None,
                        new_bp=round(pn["bullpen"], 1) if pn["bullpen"] is not None else None,
                        opp_eff=e.get("effective"), opp_season=r.get("oppBullpenERA"),
                        opp_eff_era=new_era))

    print(f"slate {date}   weights {slate['weights']}\n")
    print(f"{'game':<12}{'tm':<5}{'oppSznERA':>10}{'oppEffERA':>10}"
          f"{'oldBP':>7}{'newBP':>7}{'OLD':>7}{'NEW':>7}{'Δ':>7}")
    for o in out:
        d = "" if o["old"] is None or o["new"] is None else f"{o['new']-o['old']:+.1f}"
        print(f"{o['game']:<12}{o['ab']:<5}{str(o['opp_season']):>10}{str(o['opp_eff_era']):>10}"
              f"{str(o['old_bp']):>7}{str(o['new_bp']):>7}{str(o['old']):>7}{str(o['new']):>7}{d:>7}")

    print("\n--- games sorted by NEW score gap ---")
    games = {}
    for o in out:
        games.setdefault(o["game"], []).append(o)
    rows = []
    for g, pair in games.items():
        if len(pair) != 2 or any(p["new"] is None for p in pair):
            continue
        a = pair[0] if pair[0]["ha"] == "Away" else pair[1]
        h = pair[1] if pair[0]["ha"] == "Away" else pair[0]
        rows.append((g, a, h, abs(a["new"] - h["new"]), a["new"] + h["new"]))
    for g, a, h, gap, comb in sorted(rows, key=lambda x: -x[3]):
        lean = a["ab"] if a["new"] > h["new"] else h["ab"]
        print(f"{g:<12} {a['ab']} {a['new']:>5}  {h['ab']} {h['new']:>5}   gap {gap:>5.1f}  lean {lean:<4} comb {comb:>6.1f}")

    print("\n--- games sorted by COMBINED (new) ---")
    for g, a, h, gap, comb in sorted(rows, key=lambda x: -x[4]):
        print(f"{g:<12} {a['ab']} {a['new']:>5}  {h['ab']} {h['new']:>5}   comb {comb:>6.1f}")

    json.dump(out, open(os.path.join(HERE, "rescore_out.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
