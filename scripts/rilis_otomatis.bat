@echo off
rem Seranta - rilis satu klik. Klik dua kali, atau dari CMD: scripts\rilis_otomatis.bat [--coba] [--kunci PATH]
cd /d "%~dp0\.."
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 scripts\rilis_otomatis.py %*
) else (
  python scripts\rilis_otomatis.py %*
)
echo.
pause
