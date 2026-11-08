# Paper research evidence

Retrieved 2026-11-08T22:44:30.628731+00:00. Closed Coinbase daily candles only. No order was sent.

Decision: NO_TRADE. Unseen net return > 0, profit factor > 1, and at least 30 completed trades on every listed cost rate.

Session: one UTC month. A new month records a reset and starts the 2 USD loss budget from equity at the prior close. The budget is not a guaranteed loss.

Starting cash is 100 USD, long only, one name per book. Cost rates are labeled stresses, not a venue fee schedule.

TradingView BTC step 0.0001 is parent-reported. ETH and SOL are not claimed TradingView-feasible.

The eight families are original approximations. GPL files were read and were not copied. Parameters were frozen before the unseen slice: EMA 12/26, RSI 14 at 30/70, MACD 12/26/9 histogram cross, 20-day Bollinger on close, 20-bar breakout with a 5-bar retest, Donchian 20/10, ATR 14 with a 20 EMA trend filter. The daily VWAP rule is a UTC-day typical-price cross, not an intraday session VWAP.

Signals use a closed bar. An entry fills at the next bar's open. If stop and target are both touched, the stop fills. A gap through the stop fills at the open. Splits are 60/20/20 in time, each starts flat, and a position is not carried across a boundary. The 2 USD figure stops new entries after that session drawdown. It is not a guaranteed realized loss.

## Coverage

- BTC-USD: 1042 bars, 2024-01-01 through 2026-11-07, gaps over 36h: 0, sha256 ca97f9ad003c6451390da1a72a9c788a769c7c62a3b0dfe75aebde5a9d921800
- ETH-USD: 1042 bars, 2024-01-01 through 2026-11-07, gaps over 36h: 0, sha256 e5b9132f25a35a1bc77b673b0777dc2ea13d7c0e29078eff5607266b0835ad05
- SOL-USD: 1042 bars, 2024-01-01 through 2026-11-07, gaps over 36h: 0, sha256 e7353a2d318f7a69c41f186aa29b169f85a3ce87a86fb9adf61c9b56a9d88cc2

## Unseen net return, Coinbase increment, 10 bps per side

| family | market | net return | trades | profit factor | max DD USD |
| --- | --- | --- | --- | --- | --- |
| ema_cross | BTC-USD | -0.001775 | 4 | 0.796796 | 0.74123 |
| rsi_mean | BTC-USD | -0.004899 | 1 | 0.0 | 0.489919 |
| macd_momentum | BTC-USD | -0.004975 | 8 | 0.697048 | 0.980429 |
| vwap_pullback | BTC-USD | -0.011921 | 54 | 0.764035 | 2.048877 |
| bollinger_mean | BTC-USD | -0.012612 | 8 | 0.456011 | 2.577607 |
| breakout_retest | BTC-USD | 0.014598 | 3 | 4.382225 | 1.010473 |
| donchian_breakout | BTC-USD | 0.020416 | 7 | 2.525809 | 1.286812 |
| atr_trend | BTC-USD | 0.015817 | 7 | 2.427455 | 1.007263 |
| buy_and_hold | BTC-USD | 0.001551 | 1 | N/A | 3.176854 |
| cash | BTC-USD | 0.0 | 0 | N/A | 0.0 |
| ema_cross | ETH-USD | 0.009619 | 1 | N/A | 0.453547 |
| rsi_mean | ETH-USD | -0.004919 | 1 | 0.0 | 0.491949 |
| macd_momentum | ETH-USD | 0.010533 | 5 | 2.070309 | 0.923325 |
| vwap_pullback | ETH-USD | -0.035416 | 55 | 0.456715 | 3.608397 |
| bollinger_mean | ETH-USD | -0.021352 | 9 | 0.379304 | 2.753692 |
| breakout_retest | ETH-USD | -0.004915 | 1 | 0.0 | 0.610907 |
| donchian_breakout | ETH-USD | -0.0058 | 5 | 0.6212 | 0.981796 |
| atr_trend | ETH-USD | 0.009848 | 6 | 1.806831 | 1.004534 |
| buy_and_hold | ETH-USD | -0.00583 | 1 | 0.0 | 3.601975 |
| cash | ETH-USD | 0.0 | 0 | N/A | 0.0 |
| ema_cross | SOL-USD | -0.005602 | 4 | 0.620725 | 1.966015 |
| rsi_mean | SOL-USD | -0.009669 | 3 | 0.018873 | 0.985526 |
| macd_momentum | SOL-USD | 0.004023 | 4 | 1.408834 | 2.01315 |
| vwap_pullback | SOL-USD | -0.007085 | 55 | 0.891709 | 2.062395 |
| bollinger_mean | SOL-USD | -0.009987 | 9 | 0.662335 | 1.603447 |
| breakout_retest | SOL-USD | -0.0197 | 4 | 0.0 | 1.969967 |
| donchian_breakout | SOL-USD | -0.000669 | 8 | 0.968997 | 1.204996 |
| atr_trend | SOL-USD | 0.018282 | 9 | 2.485726 | 0.913867 |
| buy_and_hold | SOL-USD | 0.003398 | 1 | N/A | 4.064104 |
| cash | SOL-USD | 0.0 | 0 | N/A | 0.0 |

Buy-and-hold buys the 10 percent cash allocation on the next open and holds to the last close. It does not use a protective stop. Cash stays in cash. Both pay the same per-side stress rate when a fill exists.
The Kraken rows apply current Kraken order minimums to these Coinbase candles. They are not Kraken historical trades and not a historical minimum.
TradingView fees were not published in this run, so they are not entered as zero. The 10 bps and 25 bps rates are stresses.
This window is 2024-01-01 through 2026-11-07. Year rows are calendar slices of that one sample, not named market regimes.

## Stocks

Yahoo history was filtered through the Friday 2026-11-06 session. Sunday 2026-11-08 was not given a bar. A whole share costs more than the 10 USD allocation on every checked name, so the cash book completed no stock trade.
