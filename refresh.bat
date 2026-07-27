@echo off
REM Pull fresh MLB data for today and open the site.
cd /d "%~dp0"
python update.py
if errorlevel 1 (
  echo.
  echo Update failed - see the error above. Opening the last saved data.
)
start "" "index.html"
