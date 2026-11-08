"""Eight families. Rules are frozen approximations, not copied upstream code.

Parameters below were chosen before any unseen slice was scored and are not
searched. See docs/STRATEGY_SOURCE_MAP.md for the files that were read.
"""

from __future__ import annotations

from research_bt.indicators import (
    atr,
    bollinger,
    donchian_prior,
    ema,
    macd,
    rsi_wilder,
    utc_day_vwap,
)

# Frozen. Not fit on the unseen slice.
EMA_FAST = 12
EMA_SLOW = 26
RSI_PERIOD = 14
RSI_LOW = 30.0
RSI_HIGH = 70.0
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BB_PERIOD = 20
DONCHIAN = 20
DONCHIAN_EXIT = 10
ATR_PERIOD = 14
BREAKOUT = 20
RETEST_BARS = 5
STOP_ATR = 1.5


def _stops_from_atr(highs, lows, closes) -> list[float | None]:
    values = atr(highs, lows, closes, ATR_PERIOD)
    out = [None] * len(closes)
    for i, value in enumerate(values):
        if value is not None and value > 0:
            out[i] = closes[i] - STOP_ATR * value
    return out


def build(family: str, bars: list[dict]) -> tuple[list[str], list[float | None]]:
    closes = [bar["close"] for bar in bars]
    highs = [bar["high"] for bar in bars]
    lows = [bar["low"] for bar in bars]
    volumes = [bar["volume"] for bar in bars]
    times = [bar["time"] for bar in bars]
    n = len(bars)
    signals = ["hold"] * n
    stops = _stops_from_atr(highs, lows, closes)
    if family == "ema_cross":
        fast = ema(closes, EMA_FAST)
        slow = ema(closes, EMA_SLOW)
        for i in range(1, n):
            if None in (fast[i], slow[i], fast[i - 1], slow[i - 1]):
                continue
            if fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]:
                signals[i] = "enter"
            elif fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]:
                signals[i] = "exit"
    elif family == "rsi_mean":
        values = rsi_wilder(closes, RSI_PERIOD)
        for i in range(1, n):
            if values[i] is None or values[i - 1] is None:
                continue
            if values[i - 1] >= RSI_LOW and values[i] < RSI_LOW:
                signals[i] = "enter"
            elif values[i - 1] <= RSI_HIGH and values[i] > RSI_HIGH:
                signals[i] = "exit"
    elif family == "macd_momentum":
        _line, _signal, hist = macd(closes, MACD_FAST, MACD_SLOW, MACD_SIGNAL)
        for i in range(1, n):
            if hist[i] is None or hist[i - 1] is None:
                continue
            if hist[i - 1] <= 0 < hist[i]:
                signals[i] = "enter"
            elif hist[i - 1] >= 0 > hist[i]:
                signals[i] = "exit"
    elif family == "vwap_pullback":
        vwap = utc_day_vwap(times, highs, lows, closes, volumes)
        for i in range(1, n):
            if vwap[i] is None or vwap[i - 1] is None:
                continue
            if closes[i - 1] < vwap[i - 1] and closes[i] > vwap[i]:
                signals[i] = "enter"
            elif closes[i - 1] > vwap[i - 1] and closes[i] < vwap[i]:
                signals[i] = "exit"
    elif family == "bollinger_mean":
        _mid, _upper, lower = bollinger(closes, BB_PERIOD, 2.0)
        mid, _u, _l = bollinger(closes, BB_PERIOD, 2.0)
        for i in range(n):
            if lower[i] is None:
                continue
            if closes[i] < lower[i]:
                signals[i] = "enter"
            elif mid[i] is not None and closes[i] > mid[i]:
                signals[i] = "exit"
    elif family == "breakout_retest":
        upper, _lower = donchian_prior(highs, lows, BREAKOUT)
        armed_level = None
        armed_left = 0
        for i in range(n):
            if armed_level is not None:
                armed_left -= 1
                if lows[i] <= armed_level <= closes[i]:
                    signals[i] = "enter"
                    armed_level = None
                elif armed_left <= 0 or closes[i] < armed_level:
                    armed_level = None
            if upper[i] is not None and closes[i] > upper[i] and armed_level is None:
                armed_level = upper[i]
                armed_left = RETEST_BARS
    elif family == "donchian_breakout":
        upper, _lower = donchian_prior(highs, lows, DONCHIAN)
        _u, lower_exit = donchian_prior(highs, lows, DONCHIAN_EXIT)
        for i in range(n):
            if upper[i] is not None and closes[i] > upper[i]:
                signals[i] = "enter"
            elif lower_exit[i] is not None and closes[i] < lower_exit[i]:
                signals[i] = "exit"
    elif family == "atr_trend":
        trend = ema(closes, 20)
        ranges = atr(highs, lows, closes, ATR_PERIOD)
        for i in range(n):
            if trend[i] is None or ranges[i] is None:
                continue
            if closes[i] > trend[i] and (closes[i] - trend[i]) > ranges[i]:
                signals[i] = "enter"
            elif closes[i] < trend[i]:
                signals[i] = "exit"
    else:
        raise ValueError(family)
    return signals, stops
