@echo off
REM Run this ONCE as Administrator to register the daily scrape task.
REM Runs every day at 03:00 AM.

schtasks /Create /TN "MemeScavenger_GraduatedScrape" ^
  /TR "\"C:\A 03 SOFTWARE HOUSE PROJECT\meme-scavenger\scripts\scrape_graduated.bat\"" ^
  /SC DAILY /ST 03:00 ^
  /RU SYSTEM ^
  /RL HIGHEST ^
  /F

echo.
echo Task registered. Verify with:
echo   schtasks /Query /TN "MemeScavenger_GraduatedScrape" /FO LIST
pause
