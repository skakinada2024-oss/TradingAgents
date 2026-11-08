"""Coinbase Exchange public candles. No key. Closed daily bars only."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

URL = "https://api.exchange.coinbase.com/products/{product}/candles"
PRODUCTS = "https://api.exchange.coinbase.com/products/{product}"
PAIRS = ("BTC-USD", "ETH-USD", "SOL-USD")
GRANULARITY = 86400
USER_AGENT = "paper-research-backtest/1.0"


def _get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def fetch_product(product: str) -> dict:
    return _get(PRODUCTS.format(product=product))


def fetch_candles(product: str, start: datetime, end: datetime) -> list[dict]:
    """Paginate at most 300 daily candles per request. Drop an unfinished day."""
    retrieved = int(datetime.now(UTC).timestamp())
    cursor = int(start.timestamp())
    stop = int(end.timestamp())
    rows = {}
    while cursor < stop:
        chunk_end = min(stop, cursor + 300 * GRANULARITY)
        url = (
            f"{URL.format(product=product)}?granularity={GRANULARITY}"
            f"&start={datetime.fromtimestamp(cursor, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}"
            f"&end={datetime.fromtimestamp(chunk_end, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        payload = _get(url)
        for item in payload:
            ts, low, high, open_, close, volume = item
            ts = int(ts)
            if ts + GRANULARITY > retrieved:
                continue
            rows[ts] = {
                "time": ts,
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
            }
        cursor = chunk_end
        time.sleep(0.2)
    return [rows[key] for key in sorted(rows)]


def write_csv(path: Path, rows: list[dict]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["time,open,high,low,close,volume"]
    for row in rows:
        lines.append(
            f"{row['time']},{row['open']},{row['high']},{row['low']},{row['close']},{row['volume']}"
        )
    text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()
