@echo off
REM Windows 每日运行入口（供任务计划程序调用）。
REM 前提：已在项目根目录跑过 `uv sync` 建好 .venv；已设环境变量 SLACK_WEBHOOK_URL；代理已开在 127.0.0.1:7890。
REM 任务计划程序：程序/脚本填此 .bat 的完整路径即可。

REM 定位到项目根目录（本 bat 在 scripts\ 下）
cd /d "%~dp0.."

REM 用 venv 的 python 直接跑（不经 uv，启动快、不碰网络做依赖解析）
".venv\Scripts\python.exe" -m exchange_monitor >> "%USERPROFILE%\exchange_monitor_daily.log" 2>&1

REM 退出码透传：全部交易所失败时为 1，可让任务计划程序据此重试
exit /b %ERRORLEVEL%
