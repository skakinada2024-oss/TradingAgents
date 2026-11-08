# Methodology correction

Run at 2026-11-08T22:56:02.359135+00:00. No order was sent.

Decision: NO_TRADE. This is a second look at an already inspected daily holdout, plus one historical intraday VWAP window. Low trade counts are inconclusive. The 30-trade figure is not a guarantee.

The daily 60/20/20 holdout was already reviewed in the first run. It is labeled inspected_holdout. A prospective unseen window would have to be collected after this specification and left untouched. This file does not claim that.

Primary costs are 65 and 70 bps per side: 60 bps commission plus 5 or 10 bps slippage. The 10 and 25 bps rows are an optimistic sensitivity from the first run. Spread is not added on top of slippage because these candles are trade prints.

The experiment loss limit is a cumulative 2 USD of realized losses on a 100 USD book. Later profits do not restore it, and a new month does not restore it. The monthly reset and the 2-hour intraday reset are separate scenarios. Their reset counts are in the matrix. A gap can lose more than 2 USD.

The one-bar daily VWAP cross is rejected. The intraday rule uses 15-minute Coinbase candles, a UTC-day VWAP of closed bars only, and at least four bars in the day.

## Inspected daily holdout, cumulative loss, Coinbase step, 65 bps per side

| family | market | net return | trades | max DD USD | max DD % | exposure | hold hours | expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ema_cross | BTC-USD | -0.005441 | 4.0 | 0.756453 | 0.007555 | 0.129187 | 162.0 | -0.13602 |
| rsi_mean | BTC-USD | -0.005 | 1.0 | 0.499978 | 0.005 | 0.004785 | 24.0 | -0.499978 |
| macd_momentum | BTC-USD | -0.007062 | 8.0 | 0.991795 | 0.009903 | 0.215311 | 135.0 | -0.08828 |
| bollinger_mean | BTC-USD | -0.019999 | 4.0 | 2.101623 | 0.020995 | 0.038278 | 48.0 | -0.499981 |
| breakout_retest | BTC-USD | 0.008629 | 3.0 | 0.99664 | 0.009885 | 0.30622 | 512.0 | 0.287641 |
| donchian_breakout | BTC-USD | 0.010752 | 7.0 | 1.225813 | 0.011982 | 0.454545 | 325.714286 | 0.153597 |
| atr_trend | BTC-USD | 0.007108 | 7.0 | 1.026984 | 0.010196 | 0.354067 | 253.714286 | 0.101539 |
| buy_and_hold_unconstrained | BTC-USD | 0.004399 | 1.0 | 31.391366 | 0.28803 | 0.990431 | 4968.0 | 0.439933 |
| cash | BTC-USD | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | None | None |
| risk_budget_hold | BTC-USD | 0.007015 | 1.0 | 0.334534 | 0.00334 | 0.105263 | 528.0 | 0.701451 |
| ema_cross | ETH-USD | 0.007466 | 1.0 | 0.394509 | 0.003926 | 0.186603 | 936.0 | 0.746609 |
| rsi_mean | ETH-USD | -0.005 | 1.0 | 0.5 | 0.005 | 0.004785 | 24.0 | -0.5 |
| macd_momentum | ETH-USD | 0.004876 | 5.0 | 0.878452 | 0.00877 | 0.15311 | 153.6 | 0.097525 |
| bollinger_mean | ETH-USD | -0.02 | 4.0 | 1.999997 | 0.02 | 0.038278 | 48.0 | -0.499999 |
| breakout_retest | ETH-USD | -0.005 | 1.0 | 0.519666 | 0.005196 | 0.066986 | 336.0 | -0.499998 |
| donchian_breakout | ETH-USD | -0.009349 | 5.0 | 0.999997 | 0.009993 | 0.244019 | 244.8 | -0.18699 |
| atr_trend | ETH-USD | 0.001546 | 7.0 | 1.067176 | 0.010543 | 0.421053 | 301.714286 | 0.022087 |
| buy_and_hold_unconstrained | ETH-USD | -0.068603 | 1.0 | 35.590109 | 0.353176 | 0.990431 | 4968.0 | -6.860285 |
| cash | ETH-USD | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | None | None |
| risk_budget_hold | ETH-USD | -0.005 | 1.0 | 0.545347 | 0.005451 | 0.15311 | 768.0 | -0.5 |
| ema_cross | SOL-USD | 0.003631 | 4.0 | 0.762243 | 0.007605 | 0.167464 | 210.0 | 0.090772 |
| rsi_mean | SOL-USD | -0.010418 | 3.0 | 1.04182 | 0.010418 | 0.038278 | 64.0 | -0.347273 |
| macd_momentum | SOL-USD | 0.011932 | 4.0 | 0.883802 | 0.008766 | 0.167464 | 210.0 | 0.298295 |
| bollinger_mean | SOL-USD | -0.004049 | 6.0 | 1.66829 | 0.016683 | 0.08134 | 68.0 | -0.067479 |
| breakout_retest | SOL-USD | -0.02 | 4.0 | 2.0 | 0.02 | 0.248804 | 312.0 | -0.5 |
| donchian_breakout | SOL-USD | -0.00649 | 7.0 | 1.229146 | 0.012291 | 0.167464 | 120.0 | -0.092721 |
| atr_trend | SOL-USD | -0.000647 | 8.0 | 1.081089 | 0.010786 | 0.110048 | 69.0 | -0.008091 |
| buy_and_hold_unconstrained | SOL-USD | 0.022667 | 1.0 | 40.156242 | 0.361647 | 0.990431 | 4968.0 | 2.266692 |
| cash | SOL-USD | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | None | None |
| risk_budget_hold | SOL-USD | -0.005 | 1.0 | 1.132288 | 0.011252 | 0.210526 | 1056.0 | -0.5 |

## Intraday VWAP first look, same primary cost

| market | split | net return | trades | max DD USD | max DD % | exposure | hold hours | expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BTC-USD | train | -0.019867 | 7.0 | 1.986653 | 0.019867 | 0.002782 | 1.142857 | -0.283808 |
| BTC-USD | validation | -0.019158 | 10.0 | 2.107498 | 0.021035 | 0.029987 | 2.875 | -0.191578 |
| BTC-USD | first_look_holdout | -0.02 | 5.0 | 1.999996 | 0.02 | 0.003129 | 0.6 | -0.399999 |
| BTC-USD | whole_sample | -0.019867 | 7.0 | 1.986653 | 0.019867 | 0.001669 | 1.142857 | -0.283808 |
| ETH-USD | train | -0.02 | 6.0 | 2.0 | 0.02 | 0.000608 | 0.291667 | -0.333333 |
| ETH-USD | validation | -0.017167 | 9.0 | 1.716658 | 0.017167 | 0.016949 | 1.805556 | -0.19074 |
| ETH-USD | first_look_holdout | -0.02 | 5.0 | 2.0 | 0.02 | 0.002086 | 0.4 | -0.4 |
| ETH-USD | whole_sample | -0.02 | 6.0 | 2.0 | 0.02 | 0.000365 | 0.291667 | -0.333333 |
| SOL-USD | train | -0.019913 | 6.0 | 1.991293 | 0.019913 | 0.001391 | 0.666667 | -0.331882 |
| SOL-USD | validation | -0.013999 | 9.0 | 1.817861 | 0.018103 | 0.030248 | 3.222222 | -0.155545 |
| SOL-USD | first_look_holdout | -0.019953 | 6.0 | 1.995311 | 0.019953 | 0.009126 | 1.458333 | -0.332552 |
| SOL-USD | whole_sample | -0.019913 | 6.0 | 1.991293 | 0.019913 | 0.000834 | 0.666667 | -0.331882 |

## VWAP coverage

- BTC-USD: 19174 closed 15-minute bars, 201 UTC days, 2026-04-22T23:00:00+00:00 through 2026-11-08T22:30:00+00:00, missing slots 25. One recent window of about 200 days. Not a multi-regime sample.
- ETH-USD: 19174 closed 15-minute bars, 201 UTC days, 2026-04-22T23:00:00+00:00 through 2026-11-08T22:30:00+00:00, missing slots 25. One recent window of about 200 days. Not a multi-regime sample.
- SOL-USD: 19174 closed 15-minute bars, 201 UTC days, 2026-04-22T23:00:00+00:00 through 2026-11-08T22:30:00+00:00, missing slots 25. One recent window of about 200 days. Not a multi-regime sample.

## Separate 2-hour reset

The 2-hour rows reset the 2 USD budget every 7200 seconds. They are not the one-book allowance. A reset lets the book keep losing. The cumulative whole-sample book does not reset.
- BTC-USD cumulative: net return -0.019867, trades 7.0, loss consumed 1.986653, resets 1.
- BTC-USD two_hour: net return -0.989962, trades 414.0, loss consumed 99.249395, resets 2399.
- ETH-USD cumulative: net return -0.02, trades 6.0, loss consumed 2.0, resets 1.
- ETH-USD two_hour: net return -0.98995, trades 429.0, loss consumed 99.455986, resets 2399.
- SOL-USD cumulative: net return -0.019913, trades 6.0, loss consumed 1.991293, resets 1.
- SOL-USD two_hour: net return -0.990025, trades 446.0, loss consumed 100.367623, resets 2399.

## Stocks

Whole shares were checked against 100 USD cash and against a 0.50 USD planned loss using the Friday 2026-11-06 close, a 1.5 ATR stop, 60 bps commission and 5 bps slippage per side. The earlier 10 USD allocation was not the constraint. Yahoo does not publish a share increment, so a fractional account is not assumed.
- SPY 2026-11-06: close 735.2899780273438, one-share cash out 740.0715687544556, planned loss 25.197483389967495, cash rejects True, risk rejects True.
- QQQ 2026-11-06: close 656.0999755859375, one-share cash out 660.3665937271728, planned loss 31.55584000307769, cash rejects True, risk rejects True.
- NVDA 2026-11-06: close 186.63999938964844, one-share cash out 187.8537193056793, planned loss 14.00317435109451, cash rejects True, risk rejects True.
- AMD 2026-11-06: close 449.0400085449219, one-share cash out 451.9601157204895, planned loss 60.393044172944606, cash rejects True, risk rejects True.
- AAPL 2026-11-06: close 342.3699951171875, one-share cash out 344.59642719543456, planned loss 17.521168264036447, cash rejects True, risk rejects True.
- MSFT 2026-11-06: close 530.6099853515625, one-share cash out 534.0605420863037, planned loss 29.90458625823193, cash rejects True, risk rejects True.

