@echo off
REM Daily runner for Windows Task Scheduler.
REM Prereqs: run `uv sync` once to build .venv; set SLACK_WEBHOOK_URL; proxy on 127.0.0.1:7890.
REM In Task Scheduler, point "Program/script" to the full path of this .bat.

REM cd to project root (this bat lives in scripts\)
cd /d "%~dp0.."

REM Run with the venv python directly (no uv, fast start, no network dependency resolution)
".venv\Scripts\python.exe" -m exchange_monitor >> "%USERPROFILE%\exchange_monitor_daily.log" 2>&1

REM Propagate exit code: 1 when all exchanges fail, so Task Scheduler can retry
exit /b %ERRORLEVEL%
