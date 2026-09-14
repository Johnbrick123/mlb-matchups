@echo off
REM Pull fresh MLB data for today, verify it against the sources, and open the site.
cd /d "%~dp0"
python update.py
if errorlevel 1 (
  echo.
  echo Update failed - see the error above. Opening the last saved data.
  goto open
)
python verify.py
if errorlevel 1 (
  echo.
  echo WARNING: verify.py found mismatches between data.js and the live sources - see above.
)
:open
start "" "index.html"
