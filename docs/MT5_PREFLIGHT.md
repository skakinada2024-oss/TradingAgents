# MetaTrader 5 read-only preflight

Official API: https://www.mql5.com/en/docs/python_metatrader5

`initialize` attaches to a MetaTrader 5 terminal on the same Windows machine. This command does not call `login` and does not send an order. A password, a server name, and an account number are not arguments.

This cloud VM is Linux. It has no desktop terminal and no private Windows worker. The command here refuses to connect. A real Windows check has not been run.

## On the Windows machine, after the terminal is already open and logged in

```bash
pip install MetaTrader5
python -m tradingagents.mt5_preflight --symbol EURUSD
```

`--terminal-path` may point at an already installed `terminal64.exe`. It is optional when the terminal is already running. `--live` exits 2.

The process prints a JSON report and exits. `execution_enabled` is false. `eligible` is false unless every check below passes. A false result is still a completed read. It is not a started session.

## What the check reads

- `account_info` twice, so a changed account fails closed
- `terminal_info`: `connected`, `trade_allowed`, `tradeapi_disabled`, name, build
- `symbol_info` and `symbol_info_tick` for the symbol you named
- `positions_total`

Demo only (`ACCOUNT_TRADE_MODE_DEMO`). Contest, real, and any other mode fail. Currency must be USD. Leverage must be 1, because gross leverage stays refused. The minimum-volume gross notional is `volume_min * trade_contract_size * ask` from the official symbol fields. If that exceeds cash, the check fails and does not treat the contract as a share. Profit currency other than USD is not converted. A quote older than 30 seconds is stale. A quote older than 15 minutes, or a disabled or close-only symbol, is not an open session. An open position fails closed because this check will not close it.

Login, name, server, company, and terminal paths are not printed.

## Proposed limits, not armed

5 USD equity-loss cutoff, one position, 12 hours maximum, stop earlier if a future process checks the cutoff. The cutoff cannot make the realized loss exactly 5 USD: a gap or a closed market can move through that level before the next read. None of these limits start a loop. `order_send` is not in this module.

## What is still missing for a 12 hour run

A Windows desktop with the official terminal already logged into the demo account, this command run there, and a result that is eligible. Chat-stop cannot be verified from this VM because there is no remote Windows session to interrupt. Forex being closed, or a minimum lot whose gross notional is above the demo cash, keeps `eligible` false. That is a blocker, not a prompt to raise the cap.
