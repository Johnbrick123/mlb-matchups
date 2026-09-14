# MLB Matchup Scores

A site that scores every pitcher/game matchup on the slate and ranks each team's
offensive spot using your model. Data is pulled automatically from the MLB API and
Baseball Savant — no manual entry. It refreshes itself in the cloud four times a
day (see `.github/workflows/refresh.yml`) and is served by GitHub Pages.

## Daily use
The site updates itself. To force a refresh on your laptop, double-click
**`refresh.bat`** — it runs `update.py`, then `verify.py`, and opens the site.

`index.html` runs entirely in your browser and reads `data.js` next to it.

## What you see
- **Slate tab** — one row per team's offense vs the opposing starter + bullpen.
  - Click any column header to **sort**; click again to reverse (defaults to Score, high→low).
  - **Filter** box searches team / pitcher / game; plus Home/Away and Min-score filters.
  - Score cells are **color-coded** red→green (green = better spot for that offense).
  - **Show raw inputs** reveals the underlying numbers.
  - **Adjust weights** — live sliders re-weight the model and recompute instantly.
    The **Effective bullpen input** checkbox (on by default) switches the bullpen
    slot between the effective number and plain season ERA so you can compare.
  - A `*` after a score means one input was missing for that row and its weight was
    redistributed across the others. A TBD opposing starter shows no score at all.
- **Matchups tab** — game-level rankings, recomputed live with the weight sliders:
  - **Largest spreads** — the gap between the two offenses' scores per game
    (e.g. 70 vs 40 = 30), most lopsided first. "Lean" = the better offensive spot.
  - **Highest combined totals** — both teams' scores added, biggest "over" leans first.
- **Runs / Game, Team OPS** tabs — sortable reference tables.
- **Bullpens tab** — every club's pen in three layers: **Talent** (season relief
  line), **Form** (last 14 / last 7 days), **Tonight** (3-day workload, arms likely
  down), plus the **Effective** quality that feeds the model. Workload and arms-down
  are display only and carry zero weight — see `BULLPEN_FINDINGS.md` for why.

## The scoring model
Each sub-score rescales a stat to 0–100 (clamped):

| Sub-score | Formula |
|---|---|
| xERA    | (oppXERA − 2.5) / 4 × 100 |
| Bullpen | (oppBullpenEff − 2.5) / 4 × 100 — falls back to season ERA if the effective number is unavailable |
| OPS     | (OPS − 0.625) / 0.175 × 100 |
| OPS L3  | (opsL3 − 0.5) / 0.4 × 100 |
| Runs L3 | (runsL3 − 2) / 6 × 100 |

**Live weights: 24% xERA · 19% OPS · 25% Bullpen · 0% Runs L3 · 32% OPS L3**
(backtest-optimised; the weight sliders default to these). Edit `scales` and
`weights` in `write_js()` in `update.py` to change the model permanently.

### The effective bullpen input
The 25% bullpen slot is fed by **Effective Bullpen Quality** rather than raw
season relief ERA: 50% season + 30% last-14 + 20% last-7, each layer scored on
ERA (40%) + WHIP (25%) + K-BB% (25%) + HR/9 (10%), then mapped back onto the same
2.50–6.50 axis so the slot's weight and scale are unchanged. Weights were chosen by
backtest over 2024–26 (`BULLPEN_FINDINGS.md`); the improvement is real but small
(r vs runs 0.089 → 0.122) and has **not** been tested against a betting line.
`bullpen_live.py` computes it; if it cannot, `update.py` uses season ERA for every
club that run (never a mix) and says so in the log.

## Where each number comes from (`update.py`)
| Column | Source |
|---|---|
| Schedule, probable pitchers + MLB ids | MLB StatsAPI (`statsapi.mlb.com`) |
| Opposing-starter **xERA** | Baseball Savant expected-stats leaderboard |
| Team **OPS** / **OPS L3** and **Runs L3** | MLB StatsAPI team hitting (season + lastXGames) |
| Opponent **bullpen ERA** and **BB/SO%** | MLB StatsAPI relief-only split (`sitCodes=rp`) |
| Opponent **effective bullpen** (`oppBullpenEff`) | `bullpen_live.py`: relief split + last 14 days of box scores |
| Bullpens tab three-layer table (`bullpenEff`) | same |

Note: "Bullpen SO%" in your sheet is the bullpen's **walk-to-strikeout ratio**
(BB ÷ SO), computed here from live reliever totals.

```
python update.py                 # today
python update.py 2026-07-25      # a specific date
python update.py 2026-07-25 out.js   # write elsewhere, leaving data.js untouched
```

`update.py` refuses to overwrite `data.js` (and exits non-zero) if the schedule
had games but no rows were built, a game is missing a side, any playing club has
no relief-split ERA, the 30-team tables are short, or every named starter is
missing xERA. Better a stale board than a wrong one.

## Verify the data against the sources
```
python verify.py            # schema checks + re-pull every source and diff, field by field
python verify.py --offline  # schema checks only
```
Prints OK/BAD counts per field and lists every mismatch; exits 1 if anything is
off. The cloud refresh runs this between "regenerate" and "commit", so a `data.js`
that disagrees with its sources is never published — the run fails, GitHub emails
you, and the previous data stays live until the next scheduled run succeeds.
Small day-of drift in bullpen numbers between runs is normal.

## Backtest (backtest/ folder)
Point-in-time predictive validation of the scoring model over 2024, 2025, and 2026-to-date
(~12,300 team-games). Every game's inputs are reconstructed using only data available
*before* that game — no look-ahead. Opposing-starter xERA is rebuilt from Statcast
pitch-level xwOBA (validated to within ±0.04 of Savant's published xERA); OPS, OPS L3,
Runs L3, and bullpen ERA are point-in-time; scores use the identical site engine.
```
python backtest/bt.py fetch 2024      # cache raw data (resumable)
python backtest/bt.py build 2024      # -> games_2024.csv (one row per team-game + actual runs)
python backtest/bt.py analyze 2024 2025 2026
python backtest/report.py 2024 2025 2026   # -> backtest/report.html
```
Result: score→runs correlation +0.18, and spread-lean win rate climbs monotonically
50%→70% as the model's edge grows — real predictive signal.

**Known issue:** the backtest's bullpen column is built as team pitching minus the
probable starter, not from the relief-only split the site uses, and it leaks some
starter quality into the bullpen slot (`BULLPEN_FINDINGS.md`, last section). The
26.8% bullpen weight it produced should be re-fit once that column is rebuilt.

The bullpen-specific research (`research/`) is separate and reproducible; see
`research/README.md`.

## Files
- `index.html` — the site (open this)
- `data.js` — current slate + reference tables (regenerated by update.py)
- `update.py` — the importer
- `bullpen_live.py` — effective bullpen quality for one slate (used by update.py)
- `verify.py` — cross-checks data.js against the live sources; gates the cloud refresh
- `refresh.bat` — one click: update + verify + open
- `BULLPEN_FINDINGS.md` — what was tested for the bullpen input and what shipped
- `research/` — scripts that reproduce the bullpen findings (not used by the site)
- `backtest/` — model backtest
- `data_snapshot_2026-07-25.js` — your original pasted slate, kept for reference
