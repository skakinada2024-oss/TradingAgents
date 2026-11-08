@echo off
setlocal
cd /d "%~dp0"
py -3.14 -m tradingagents.mt5_demo --state-dir "%~dp0run_state"
echo Dry-run finished. No order is sent by this file.
