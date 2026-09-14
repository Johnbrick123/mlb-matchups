# Bullpen research scripts

Not used by the site build. Kept so the numbers in `../BULLPEN_FINDINGS.md`
can be reproduced.

```
python bullpen_core.py harvest 2024      # ~1 min/season, caches to bp_cache/
python bullpen_core.py harvest 2025
python bullpen_core.py harvest 2026
python bullpen_core.py show 2026-09-12   # per-team layer table for one date
python bullpen_backtest.py 2024 2025 2026
python stage_b.py                        # reads bt_rows.json from the step above
python rescore.py ../data.js             # old vs new scores for a slate
```

`bp_cache/` is gitignored — it is ~6 MB of box-score derivatives and rebuilds
in about three minutes.
