# Run 9 completion

Started 2026-11-15T00:48:13.593173+00:00. Finished 2026-11-15T00:50:16.541478+00:00. No order was sent.

The 2026-11-08 Run 9 process was interrupted during the SOL-USD 15-minute download. That attempt produced no committed score. This file is the bounded completion.

Label: NO_VALIDATED_STRATEGY. These books are inspected in-sample comparisons. A positive cell with a small trade count is not validation.

Every scored clock here was already inspected, either in Run 8 or in the attached TradingView test. Nothing is called unseen.

Cost is 0.65 percent per side and is not combined with a second slippage or spread. Each family book starts at 100 USD, buys only, plans at most 0.50 USD of loss including that cost, and stops new entries after 2 USD of cumulative realized loss. Profits do not restore the 2 USD.

## Family books

| family | market | tf | trades | net pnl USD | max DD USD | PF | win rate | expectancy | cutoff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| donchian_breakout | BTC-USD | 1d | 10 | 1.382588 | 2.619723 | 1.691296 | 0.5 | 0.138259 | False |
| breakout_retest | BTC-USD | 1d | 5 | -1.314836 | 2.063498 | 0.342539 | 0.2 | -0.262967 | False |
| atr_trend | BTC-USD | 1d | 10 | 2.14669 | 1.85562 | 2.073384 | 0.6 | 0.214669 | False |
| donchian_breakout | ETH-USD | 1d | 9 | 0.794204 | 2.0 | 1.397102 | 0.444444 | 0.088245 | False |
| breakout_retest | ETH-USD | 1d | 6 | -0.535508 | 2.190147 | 0.732245 | 0.333333 | -0.089251 | False |
| atr_trend | ETH-USD | 1d | 10 | 2.276189 | 1.435922 | 2.138098 | 0.6 | 0.227619 | False |
| donchian_breakout | SOL-USD | 1d | 12 | 1.695299 | 1.36341 | 1.84765 | 0.5 | 0.141275 | False |
| breakout_retest | SOL-USD | 1d | 9 | 2.069718 | 1.179236 | 2.034859 | 0.555556 | 0.229969 | False |
| atr_trend | SOL-USD | 1d | 11 | 1.356098 | 1.324491 | 1.678049 | 0.454545 | 0.123282 | False |
| donchian_breakout | BTC-USD | 15m | 4 | -1.999979 | 1.999979 | 0.0 | 0.0 | -0.499995 | False |
| breakout_retest | BTC-USD | 15m | 4 | -1.999978 | 1.999978 | 0.0 | 0.0 | -0.499994 | False |
| atr_trend | BTC-USD | 15m | 5 | -1.999995 | 1.999995 | 0.0 | 0.0 | -0.399999 | False |
| donchian_breakout | ETH-USD | 15m | 5 | -1.986448 | 1.990728 | 0.0 | 0.0 | -0.39729 | False |
| breakout_retest | ETH-USD | 15m | 5 | -2.0 | 2.0 | 0.0 | 0.0 | -0.4 | False |
| atr_trend | ETH-USD | 15m | 5 | -1.997971 | 1.998469 | 0.0 | 0.0 | -0.399594 | False |
| donchian_breakout | SOL-USD | 15m | 4 | -2.0 | 2.0 | 0.0 | 0.0 | -0.5 | False |
| breakout_retest | SOL-USD | 15m | 4 | -2.0 | 2.0 | 0.0 | 0.0 | -0.5 | False |
| atr_trend | SOL-USD | 15m | 5 | -2.0 | 2.0 | 0.0 | 0.0 | -0.4 | False |
| donchian_breakout | BTC-USD | 1h | 9 | -1.324685 | 1.652297 | 0.337655 | 0.444444 | -0.147187 | False |
| breakout_retest | BTC-USD | 1h | 6 | -1.685311 | 1.765357 | 0.157335 | 0.333333 | -0.280885 | False |
| atr_trend | BTC-USD | 1h | 11 | -1.600985 | 1.999111 | 0.199504 | 0.545455 | -0.145544 | False |
| donchian_breakout | ETH-USD | 1h | 6 | -1.666005 | 1.841807 | 0.166997 | 0.333333 | -0.277668 | False |
| breakout_retest | ETH-USD | 1h | 13 | 0.102161 | 0.943062 | 1.051081 | 0.692308 | 0.007859 | False |
| atr_trend | ETH-USD | 1h | 6 | -1.824165 | 2.076072 | 0.087917 | 0.333333 | -0.304028 | False |
| donchian_breakout | SOL-USD | 1h | 6 | -1.00056 | 1.418922 | 0.49972 | 0.333333 | -0.16676 | False |
| breakout_retest | SOL-USD | 1h | 5 | -1.566875 | 2.0 | 0.216563 | 0.2 | -0.313375 | False |
| atr_trend | SOL-USD | 1h | 6 | -0.984244 | 1.896618 | 0.507878 | 0.333333 | -0.164041 | False |
| donchian_breakout | BTC-USD | 5m | 4 | -1.999983 | 1.999983 | 0.0 | 0.0 | -0.499996 | False |
| breakout_retest | BTC-USD | 5m | 4 | -1.99997 | 1.99997 | 0.0 | 0.0 | -0.499993 | False |
| atr_trend | BTC-USD | 5m | 5 | -1.999994 | 1.999994 | 0.0 | 0.0 | -0.399999 | False |
| donchian_breakout | ETH-USD | 5m | 5 | -2.0 | 2.0 | 0.0 | 0.0 | -0.4 | False |
| breakout_retest | ETH-USD | 5m | 4 | -1.999999 | 1.999999 | 0.0 | 0.0 | -0.5 | False |
| atr_trend | ETH-USD | 5m | 5 | -2.0 | 2.0 | 0.0 | 0.0 | -0.4 | False |
| donchian_breakout | SOL-USD | 5m | 5 | -2.0 | 2.0 | 0.0 | 0.0 | -0.4 | False |
| breakout_retest | SOL-USD | 5m | 4 | -2.0 | 2.0 | 0.0 | 0.0 | -0.5 | False |
| atr_trend | SOL-USD | 5m | 5 | -2.0 | 2.0 | 0.0 | 0.0 | -0.4 | False |

## Regime subsets of those same books

| family | market | tf | regime | trades | pnl USD | PF | win rate | expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| donchian_breakout | BTC-USD | 1d | trend_up | 10 | 1.382588 | 1.691296 | 0.5 | 0.138259 |
| donchian_breakout | BTC-USD | 1d | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | BTC-USD | 1d | trend_up | 5 | -1.314836 | 0.342539 | 0.2 | -0.262967 |
| breakout_retest | BTC-USD | 1d | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | BTC-USD | 1d | trend_up | 10 | 2.14669 | 2.073384 | 0.6 | 0.214669 |
| atr_trend | BTC-USD | 1d | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | ETH-USD | 1d | trend_up | 9 | 0.794204 | 1.397102 | 0.444444 | 0.088245 |
| donchian_breakout | ETH-USD | 1d | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | ETH-USD | 1d | trend_up | 6 | -0.535508 | 0.732245 | 0.333333 | -0.089251 |
| breakout_retest | ETH-USD | 1d | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | ETH-USD | 1d | trend_up | 10 | 2.276189 | 2.138098 | 0.6 | 0.227619 |
| atr_trend | ETH-USD | 1d | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | SOL-USD | 1d | trend_up | 12 | 1.695299 | 1.84765 | 0.5 | 0.141275 |
| donchian_breakout | SOL-USD | 1d | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | SOL-USD | 1d | trend_up | 9 | 2.069718 | 2.034859 | 0.555556 | 0.229969 |
| breakout_retest | SOL-USD | 1d | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | SOL-USD | 1d | trend_up | 11 | 1.356098 | 1.678049 | 0.454545 | 0.123282 |
| atr_trend | SOL-USD | 1d | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | BTC-USD | 15m | trend_up | 4 | -1.999979 | 0.0 | 0.0 | -0.499995 |
| donchian_breakout | BTC-USD | 15m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | BTC-USD | 15m | trend_up | 4 | -1.999978 | 0.0 | 0.0 | -0.499994 |
| breakout_retest | BTC-USD | 15m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | BTC-USD | 15m | trend_up | 5 | -1.999995 | 0.0 | 0.0 | -0.399999 |
| atr_trend | BTC-USD | 15m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | ETH-USD | 15m | trend_up | 5 | -1.986448 | 0.0 | 0.0 | -0.39729 |
| donchian_breakout | ETH-USD | 15m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | ETH-USD | 15m | trend_up | 5 | -2.0 | 0.0 | 0.0 | -0.4 |
| breakout_retest | ETH-USD | 15m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | ETH-USD | 15m | trend_up | 5 | -1.997971 | 0.0 | 0.0 | -0.399594 |
| atr_trend | ETH-USD | 15m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | SOL-USD | 15m | trend_up | 4 | -2.0 | 0.0 | 0.0 | -0.5 |
| donchian_breakout | SOL-USD | 15m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | SOL-USD | 15m | trend_up | 4 | -2.0 | 0.0 | 0.0 | -0.5 |
| breakout_retest | SOL-USD | 15m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | SOL-USD | 15m | trend_up | 5 | -2.0 | 0.0 | 0.0 | -0.4 |
| atr_trend | SOL-USD | 15m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | BTC-USD | 1h | trend_up | 9 | -1.324685 | 0.337655 | 0.444444 | -0.147187 |
| donchian_breakout | BTC-USD | 1h | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | BTC-USD | 1h | trend_up | 6 | -1.685311 | 0.157335 | 0.333333 | -0.280885 |
| breakout_retest | BTC-USD | 1h | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | BTC-USD | 1h | trend_up | 11 | -1.600985 | 0.199504 | 0.545455 | -0.145544 |
| atr_trend | BTC-USD | 1h | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | ETH-USD | 1h | trend_up | 6 | -1.666005 | 0.166997 | 0.333333 | -0.277668 |
| donchian_breakout | ETH-USD | 1h | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | ETH-USD | 1h | trend_up | 13 | 0.102161 | 1.051081 | 0.692308 | 0.007859 |
| breakout_retest | ETH-USD | 1h | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | ETH-USD | 1h | trend_up | 6 | -1.824165 | 0.087917 | 0.333333 | -0.304028 |
| atr_trend | ETH-USD | 1h | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | SOL-USD | 1h | trend_up | 6 | -1.00056 | 0.49972 | 0.333333 | -0.16676 |
| donchian_breakout | SOL-USD | 1h | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | SOL-USD | 1h | trend_up | 5 | -1.566875 | 0.216563 | 0.2 | -0.313375 |
| breakout_retest | SOL-USD | 1h | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | SOL-USD | 1h | trend_up | 6 | -0.984244 | 0.507878 | 0.333333 | -0.164041 |
| atr_trend | SOL-USD | 1h | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | BTC-USD | 5m | trend_up | 4 | -1.999983 | 0.0 | 0.0 | -0.499996 |
| donchian_breakout | BTC-USD | 5m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | BTC-USD | 5m | trend_up | 4 | -1.99997 | 0.0 | 0.0 | -0.499993 |
| breakout_retest | BTC-USD | 5m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | BTC-USD | 5m | trend_up | 5 | -1.999994 | 0.0 | 0.0 | -0.399999 |
| atr_trend | BTC-USD | 5m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | ETH-USD | 5m | trend_up | 5 | -2.0 | 0.0 | 0.0 | -0.4 |
| donchian_breakout | ETH-USD | 5m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | ETH-USD | 5m | trend_up | 4 | -1.999999 | 0.0 | 0.0 | -0.5 |
| breakout_retest | ETH-USD | 5m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | ETH-USD | 5m | trend_up | 5 | -2.0 | 0.0 | 0.0 | -0.4 |
| atr_trend | ETH-USD | 5m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| donchian_breakout | SOL-USD | 5m | trend_up | 5 | -2.0 | 0.0 | 0.0 | -0.4 |
| donchian_breakout | SOL-USD | 5m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| breakout_retest | SOL-USD | 5m | trend_up | 4 | -2.0 | 0.0 | 0.0 | -0.5 |
| breakout_retest | SOL-USD | 5m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |
| atr_trend | SOL-USD | 5m | trend_up | 5 | -2.0 | 0.0 | 0.0 | -0.4 |
| atr_trend | SOL-USD | 5m | trend_down_long_reversal_not_a_short | 0 | None | None | None | None |

## Pine replica versus the inspected TradingView result

- BTC-USD: replica {'status': 'ran', 'bars': 6049, 'first': 1792886400, 'last': 1794700800, 'trades': 33, 'net_usd': -9.18051, 'ending_equity': 90.81949, 'max_dd_usd': 9.18051, 'profit_factor': 0.064676, 'win_rate': 0.030303, 'expectancy': -0.278197, 'gross_profit': 0.634815, 'gross_loss': 9.815325, 'trade_count_minus_tradingview': 1, 'net_usd_minus_tradingview': -0.42051}. TradingView inspected trades 32, net -8.76 USD.
- ETH-USD: replica {'status': 'ran', 'bars': 6049, 'first': 1792886400, 'last': 1794700800, 'trades': 39, 'net_usd': -12.802317, 'ending_equity': 87.197683, 'max_dd_usd': 12.802317, 'profit_factor': 0.110124, 'win_rate': 0.051282, 'expectancy': -0.328265, 'gross_profit': 1.584312, 'gross_loss': 14.386629, 'trade_count_minus_tradingview': -1, 'net_usd_minus_tradingview': 0.137683}. TradingView inspected trades 40, net -12.94 USD.
- SOL-USD: replica {'status': 'ran', 'bars': 6049, 'first': 1792886400, 'last': 1794700800, 'trades': 42, 'net_usd': -14.939761, 'ending_equity': 85.060239, 'max_dd_usd': 14.939761, 'profit_factor': 0.049655, 'win_rate': 0.02381, 'expectancy': -0.355709, 'gross_profit': 0.780587, 'gross_loss': 15.720348, 'trade_count_minus_tradingview': 2, 'net_usd_minus_tradingview': -0.799761}. TradingView inspected trades 40, net -14.14 USD.

TradingView used its own 5-minute BTCUSD/ETHUSD/SOLUSD feed. This replica uses Coinbase USD spot. Indicator warmup, the UTC-day intraday guard, and stop-before-limit when both are touched in one bar can change the trade count. The attached Strategy Tester numbers are inspected, not a fresh test.

