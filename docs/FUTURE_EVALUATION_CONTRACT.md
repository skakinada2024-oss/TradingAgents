# Future evaluation contract

This document is a contract for a later evaluation. Stage 1 does not run it,
and it does not score a strategy.

The current repository's `run_backtest` scores settled decision ratings. It is
not a portfolio simulator. `tradingagents/backtest.py` states that turning a
rating into a filled order needs a quantity, a fill price, and a cash ledger,
and that inventing those would put an execution model behind an evaluation
tool. An evaluation that reports returns has to be built as its own explicit
simulator, with the rules below fixed before any run is looked at.

## Comparisons

- A deterministic baseline, specified in code, including buy-and-hold of the
  same symbol over the same dates.
- The research system's non-binding ratings, mapped to positions by the
  deterministic simulator only. Model prose does not size trades and does not
  approve them.

## Splits

- Train, tune, and test windows are dated before the run.
- One walk-forward or other untouched out-of-sample window is held out of
  every tuning choice.
- The final test is not used to pick a prompt, a model, a threshold, or a
  symbol. A result that was selected after seeing the test is reported as
  post-test selection, not as confirmation.

## Costs and fills

- Commission and slippage are explicit numbers or an explicit zero, written
  down before the run. "Not modeled" is a reported fact, not a silent default.
- Fills follow a next-bar rule. A decision whose inputs were available only
  after the close of day *d* cannot trade the close of day *d*.
- Adjusted and unadjusted prices are not mixed inside one return. The series
  used for signals and the series used for fills are named.

## Language-model repeats

- The same date is run more than once when a language model produces the
  rating. The report keeps the spread, not a single chosen run.
- Each run gets its own memory log. Lessons from one run are not visible to
  the next unless the protocol says that memory is part of the system under
  test.
- A timestamp on a retrieved article does not remove events that were in the
  model's training data. The write-up says that historical knowledge can
  remain.

## Data that is not on disk

- If a point-in-time news or filing record is missing, the evaluation uses
  prices only, or it moves to a forward period where the data is collected as
  it is published. Historical news is not filled in after the fact.
- Negative and inconclusive windows stay in the report. They are not dropped
  because the system lost money or the model disagreed with itself.

## What this contract does not authorize

It does not authorize a paper or live order, a paid model call, or a claim
that a published TradingAgents or FinRL-X number has been reproduced.
