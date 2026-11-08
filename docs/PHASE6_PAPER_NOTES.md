# Phase 6 paper-execution notes

Phase 6 is not implemented. This fork does not import a broker SDK, does not
read broker credentials, and does not submit an order. Stage 1's
deterministic gate sets `execution_permitted` to false for every rating.

## What was verified elsewhere, for comparison only

In AI4Finance-Foundation/FinRL-Trading at
`4409abe925c904e570be78ebfb5e77ac3491dff8`:

- `.env.example` sets `APCA_USE_PAPER_TRADING=true` and
  `APCA_BASE_URL=https://paper-api.alpaca.markets`.
- `src/trading/alpaca_manager.py` defaults `AlpacaAccount.base_url` to
  `https://paper-api.alpaca.markets`. `is_paper` is `"paper" in self.base_url`.
  A constructor argument named `paper=True` was not in that file.

Those lines are not wired into this repository. The default here is that
nothing is submitted.

## Requirements that would have to be true before any later paper path

These are notes, not code.

- Submission stays disabled unless a person turns it on for that process.
- The endpoint is checked to be a paper endpoint before a client is built.
  A live endpoint is a hard stop.
- A human approves the exact order, and the order is revalidated after
  approval against the current quote, buying power, and the original limits.
- Stale orders and duplicate orders are rejected.
- Pending exposure, including orders that are not yet filled, counts before
  another order is allowed.
- `client_order_id` is stable across retries so a timeout cannot create a
  second order.
- The order record is persisted before the request is sent.
- An ambiguous timeout is reconciled with the broker before any retry.
- Partial fills are recorded as partial. The remainder is an explicit new
  decision, not an automatic resend.
- After a restart, open orders and positions are reconciled before anything
  new is sent.
- Exit orders are allowed to run when new entries are halted.
- Monitoring keeps running when entries are halted.
- No leverage, shorts, options, crypto, or extended-hours orders.

Until those controls exist as code and tests, paper trading is out of scope.
