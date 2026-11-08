@echo off
setlocal
cd /d "%~dp0"
py -3.14 -m tradingagents.mt5_demo --stop --state-dir "%~dp0run_state"
echo STOP file written. The running window exits on its next check. Ctrl+C also stops it.
