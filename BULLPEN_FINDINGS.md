# Bullpen enhancement — what was tested and what shipped

Built and measured 2026-09-12. Everything below is reproducible from
`bullpen_live.py` (live) and the research scripts named at the end.

## The proposal

Replace the 25% bullpen input — today the opponent's **full-season team relief
ERA** — with an "Effective Bullpen Quality" score built from five layers:
current-roster quality (45%), last-14 (20%), last-7 (10%), tonight's available
arms (15%), and fatigue (10%), with each layer scored on ERA + WHIP + K-BB% +
HR/9 rather than ERA alone.

## Data: no scraping needed

All five layers come from MLB StatsAPI, free and keyless, the same source
`update.py` already uses:

| layer | source |
|---|---|
| season relief line | `/teams/{id}/stats?stats=statSplits&sitCodes=rp` — the official relief split |
| current-roster line | `/teams/{id}/roster?rosterType=active` × per-pitcher `sitCodes=rp` split |
| L14 / L7, workload, arms down | `/game/{pk}/boxscore`, relief = every pitcher with `gamesStarted == 0` |

Validation: rebuilding the season relief line from 14,456 box-score relief
appearances reproduces `data.js`'s `bullpen` table **exactly** for all 30 clubs.
Two independent code paths (roster API and box-score rebuild) agree on the
current-roster line to within 0.01 ERA.

Against the Covers figures quoted in the ChatGPT chat:

| club | Covers "current bullpen" | rebuilt here | season |
|---|---|---|---|
| MIN | 3.97 | **3.98** | 4.85 |
| CLE | 3.05 | **3.13** | 3.60 |
| NYY | 2.87 | **2.74** | 3.06 |
| BOS | 2.76 | **2.63** | 3.13 |

So the premise is real and reproducible: **season ERA and current-roster ERA are
different numbers**, by up to ~0.9 of ERA.

## The headline claim does not replicate

The chat concluded CLE 61.9 vs MIN 22.9 — "the largest matchup gap on the
board, roughly 39 points" — because it put Minnesota's effective bullpen at
**15.6/100**.

Minnesota's layers on 2026-09-12: roster 3.98, L14 4.50, L7 6.66, available
3.98. Under the formula the chat itself specified (45/20/10/15/10), those
produce **36–50/100**, not 15.6. The 15.6 can only come from letting Covers'
**"Last 3" ERA of 9.22** dominate — three games, roughly 8 relief innings, in
which one blown inning moves the number by two runs. The stated weights and the
stated output are inconsistent, and the conclusion drawn from them is an
artifact of an 8-inning sample.

On the shipped version, CLE–MIN is a 29-point gap and the fourth-largest on the
board, not the largest.

## Backtest — 8,703 team-games, 2024 / 2025 / 2026

Point-in-time by construction: every measure for a team-game is built only from
relief appearances dated strictly before that game. Correlation with the runs
the offense actually scored (sign flipped so bigger = more predictive):

| bullpen measure | 2024 | 2025 | 2026 |
|---|---|---|---|
| season relief ERA (today's input) | 0.074 | 0.102 | 0.093 |
| current-roster ERA | 0.081 | 0.111 | 0.085 |
| last-14 ERA | 0.094 | 0.110 | 0.085 |
| **last-7 ERA** | **0.101** | **0.117** | **0.102** |
| available-arms ERA | 0.073 | 0.105 | 0.082 |
| **3-day fatigue** | **0.057** | **0.023** | **0.029** |

SE of r at n≈2,200 is about 0.021 — treat anything under ~0.04 as a tie.

Weight variants, same three seasons:

| variant | 2024 | 2025 | 2026 | mean |
|---|---|---|---|---|
| season relief ERA (baseline) | 0.074 | 0.102 | 0.093 | 0.089 |
| ChatGPT's 45/20/10/15/10 | 0.117 | 0.138 | 0.107 | 0.121 |
| same, minus availability + fatigue | 0.117 | 0.138 | 0.106 | 0.121 |
| **50% season / 30% L14 / 20% L7** | **0.119** | **0.135** | **0.111** | **0.122** |
| season blend only (no time windows) | 0.076 | 0.110 | 0.098 | 0.095 |
| L7 alone | 0.121 | 0.116 | 0.099 | 0.112 |

### What that says

1. **The enhancement is real but small.** Every multi-window variant beats
   season ERA alone in all three seasons, r 0.089 → 0.122. That is ~1.5% of the
   variance in runs against ~0.8%. Better, and still almost nothing.
2. **Mixing time windows is what carries it**, not the roster work. Scoring the
   season population on four stats instead of ERA alone adds a little
   (0.089 → 0.095); adding L14 and L7 adds the rest.
3. **Availability adds nothing measurable.** Dropping it changes the mean by
   0.000. Its regression coefficient flips sign between the fit and holdout
   periods (−0.002 → +0.011) — the signature of noise.
4. **Fatigue adds nothing**, again. This is now the third independent
   confirmation, alongside the 4-season workload study and the tail test.
5. **Fitting the weights overfits.** A least-squares fit on 2024-25 scores 0.141
   in-sample and 0.115 out-of-sample, worse than not fitting at all. Its
   coefficients on roster (−0.075) and availability (+0.068) nearly cancel —
   two collinear columns chasing noise. The chosen weights are round numbers
   picked for stability, not fitted.
6. **Priority order is nearly the reverse of the chat's.** It proposed
   current-roster → availability/fatigue → K-BB%/WHIP → L14 → L7. What survives
   is L7 and L14 → the multi-stat blend → roster (marginal) → availability and
   fatigue (nothing).

### Caveats, stated plainly

- **Eight variants were screened.** The top three are within noise of each
  other; 50/30/20 was chosen for being the simplest, not the highest.
- **Stage B was not run.** `backtest/games_*.csv` carries no closing lines —
  its `total` column is the model score, not a betting total. Nothing here has
  been tested against a price, so none of it is a betting edge. Given the effect
  at Stage A is ~1.5% of variance, it is unlikely to survive one.
- **Availability rules are conventions, not measurements.** Three straight days,
  back-to-back with 35+ pitches, 45+ pitches yesterday. They flag 0–2 arms per
  club and they do not know about injuries, reported unavailability, or a
  manager's plan. Covers knows those; this does not. That is exactly why the
  column ships as display-only.

## Separate finding: the backtest's bullpen column is not the site's

`backtest/bt.py` builds `oppBullpenERA` as *team pitching minus the listed
probable starter's line*, keyed by date. The site builds it from MLB's official
relief split. They are not the same quantity:

- they correlate 0.93, mean difference 0.024 ERA, sd 0.311;
- the difference correlates **+0.139 with the opposing starter's xERA** — the
  backtest column drifts upward exactly when the opposing starter is bad, i.e.
  it is partly measuring starters;
- causes: a probable who is scratched, an actual starter never listed as a
  probable (his whole start counts as relief), and doubleheader dates where the
  team total covers two games but only one starter is subtracted.

Consequence worth checking: `backtest/final_weights.txt` puts **26.8%** on the
bullpen slot. If the optimiser was partly rewarding smuggled-in starter quality,
that weight is too high for the clean input the site actually feeds it.
Re-running the weight fit with a clean relief column is the obvious next job.

## What shipped

`bullpen_live.py` → **50% season + 30% L14 + 20% L7**, each layer scored on
ERA (40%) + WHIP (25%) + K-BB% (25%) + HR/9 (10%), mapped back onto the site's
existing 2.50–6.50 axis so it drops into the current scale and weight machinery
untouched. Roster, availability and workload are computed and displayed on the
Bullpens tab, and carry **zero weight**.

The Slate tab has an "Effective bullpen input" checkbox — on by default, uncheck
to score with season ERA — so the two can be compared on a live board.

Cost: one stats call per club plus ~15 days of box scores, about 10 seconds,
keyless. If it fails, `update.py` prints a warning and falls back to season ERA.

## Scripts

| file | what it does |
|---|---|
| `bullpen_live.py` | production module, one slate (in repo) |
| `research/bullpen_core.py` | full-season relief harvester + all five layers as-of any date |
| `research/bullpen_backtest.py` | joins to `backtest/games_*.csv`, Stage A + incremental value |
| `research/stage_b.py` | fitted-composite fit/holdout comparison |
| `research/rescore.py` | rescores a slate under old vs new input |
