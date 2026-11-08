# EURUSD demo agent

This is a local Windows program. It is not running on the machine that built
this archive. It does not ask for a password. Log in through the MetaTrader 5
desktop terminal first, then leave that terminal open.

Installed on the target PC when this was requested: Python 3.14 64-bit,
MetaTrader5 5.0.6231, NumPy 2.5.4, python-dotenv 1.2.4.

## Commands

Dry-run, one pass, no order:

```bat
Run demo dry.cmd
```

Bounded demo execution, EURUSD only, at most 12 hours, stop earlier on the
5 USD equity-loss check, Ctrl+C, or `Stop demo.cmd`:

```bat
Run demo execute.cmd
```

```bat
Stop demo.cmd
```

`Stop demo.cmd` writes a STOP file next to the run. It cannot be pressed from
the parent chat. There is no remote Windows worker.

`--live` is refused. A paid model API is not called.

## What it does

Closed M1 bars are read with `copy_rates_from_pos`. The newest, still-forming
bar is dropped. A NumPy logistic fit uses only earlier bars to predict the
next closed bar's direction, then the later bars are a chronological holdout.
If the history is too short, the labels are one class, or the holdout is not
better than a constant baseline, the signal is HOLD. That comparison is not a
profit claim.

A LONG entry is a buy of whole min-lot steps whose gross USD notional fits in
10 percent of the smaller of balance and equity. Volume is floored to the
step and is never rounded up through that cap. The broker leverage setting,
including 1:100, is not used as the position size. Selling is only a close of
a long this process opened. An existing position at start is left alone and
the process exits.

Stops are the tightest distance the symbol allows. If that distance risks more
than 1 USD, there is no entry. A 5 USD session equity drop stops new entries
and attempts one close. A gap can lose more than 5 USD. Swap is whatever the
terminal reports in equity; it is not assumed to be zero.

If the market is closed, the execute loop logs WAITING and does not invent a
price. It keeps checking until the deadline or STOP. The deadline is the
original start time plus 43200 seconds and does not reset if the terminal
reconnects.

## Dependencies

```text
python-dotenv
numpy
MetaTrader5
```

`python-dotenv` is required because the package import loads a `.env` if one
is present. Do not put a key file in this folder.
