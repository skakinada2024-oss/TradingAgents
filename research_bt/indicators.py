"""Closed-bar indicators. Each value at index i uses bars up to and including i."""

from __future__ import annotations


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period < 1 or len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    alpha = 2.0 / (period + 1.0)
    prev = seed
    for i in range(period, len(values)):
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def wilder(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period < 1 or len(values) < period:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def rsi_wilder(closes: list[float], period: int = 14) -> list[float | None]:
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = wilder(gains, period)
    avg_loss = wilder(losses, period)
    out: list[float | None] = [None] * len(closes)
    for i in range(len(closes)):
        if avg_gain[i] is None or avg_loss[i] is None:
            continue
        if avg_loss[i] == 0:
            out[i] = 100.0
        else:
            rs = avg_gain[i] / avg_loss[i]
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    line: list[float | None] = [None] * len(closes)
    ready = []
    for i in range(len(closes)):
        if fast_ema[i] is None or slow_ema[i] is None:
            ready.append(None)
            continue
        line[i] = fast_ema[i] - slow_ema[i]
        ready.append(line[i])
    # signal EMA only over defined MACD values, aligned back to the full index
    defined = [(i, value) for i, value in enumerate(line) if value is not None]
    signal_line = [None] * len(closes)
    if len(defined) >= signal:
        series = [value for _, value in defined]
        smoothed = ema(series, signal)
        for (idx, _), value in zip(defined, smoothed, strict=True):
            signal_line[idx] = value
    hist = [
        None if line[i] is None or signal_line[i] is None else line[i] - signal_line[i]
        for i in range(len(closes))
    ]
    return line, signal_line, hist


def bollinger(closes: list[float], period: int = 20, dev: float = 2.0):
    mid: list[float | None] = [None] * len(closes)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mean = sum(window) / period
        var = sum((value - mean) ** 2 for value in window) / period
        sigma = var ** 0.5
        mid[i] = mean
        upper[i] = mean + dev * sigma
        lower[i] = mean - dev * sigma
    return mid, upper, lower


def true_ranges(highs, lows, closes) -> list[float]:
    out = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        out.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    return out


def atr(highs, lows, closes, period: int = 14) -> list[float | None]:
    return wilder(true_ranges(highs, lows, closes), period)


def donchian_prior(highs, lows, period: int):
    """Prior channel, excluding the current bar."""
    upper = [None] * len(highs)
    lower = [None] * len(lows)
    for i in range(period, len(highs)):
        upper[i] = max(highs[i - period : i])
        lower[i] = min(lows[i - period : i])
    return upper, lower


def utc_day_vwap(times, highs, lows, closes, volumes):
    """One value per bar. A daily series makes this a single HLC3 print, not a pullback."""
    out = [None] * len(closes)
    bucket = None
    pv = 0.0
    vol = 0.0
    for i, ts in enumerate(times):
        day = int(ts) // 86400
        if day != bucket:
            bucket = day
            pv = 0.0
            vol = 0.0
        typical = (highs[i] + lows[i] + closes[i]) / 3.0
        vol += volumes[i]
        pv += typical * volumes[i]
        if vol > 0:
            out[i] = pv / vol
    return out


def anchored_session_vwap(times, highs, lows, closes, volumes):
    """UTC-day VWAP from closed bars only. The value at i ignores later bars."""
    out: list[float | None] = [None] * len(closes)
    count = [0] * len(closes)
    bucket = None
    pv = 0.0
    vol = 0.0
    seen = 0
    for i, ts in enumerate(times):
        day = int(ts) // 86400
        if day != bucket:
            bucket = day
            pv = 0.0
            vol = 0.0
            seen = 0
        typical = (highs[i] + lows[i] + closes[i]) / 3.0
        vol += volumes[i]
        pv += typical * volumes[i]
        seen += 1
        count[i] = seen
        if vol > 0:
            out[i] = pv / vol
    return out, count
