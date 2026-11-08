@echo off
setlocal
cd /d "%~dp0"
echo This starts the bounded EURUSD demo loop. It is not a remote start.
py -3.14 -m tradingagents.mt5_demo --execute-demo --state-dir "%~dp0run_state"
