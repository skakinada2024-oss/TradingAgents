"""Run the eight families. Writes artifacts. Does not place an order."""

from __future__ import annotations

import csv
import json
import shutil
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from research_bt import FAMILIES
from research_bt.coinbase import PAIRS, fetch_candles, fetch_product, write_csv
from research_bt.engine import Bar, run_backtest
from research_bt.metrics import summarize
from research_bt.strategies import build

START = datetime(2024, 1, 1, tzinfo=UTC)
END = datetime(2026, 11, 8, tzinfo=UTC)
COST_RATES = (0.001, 0.0025)
TV_BTC_STEP = 0.0001


def _split(bars: list[Bar]):
    n = len(bars)
    a = int(n * 0.6)
    b = int(n * 0.8)
    return {"train": bars[:a], "validation": bars[a:b], "unseen": bars[b:]}


def _scenario(name: str, step: float, min_notional: float) -> dict:
    return {"name": name, "step": step, "min_notional": min_notional}


def run(out_dir: Path) -> dict:
    raise RuntimeError(
        "research_bt/output is the first run and is left in place. "
        "The methodology correction is python -m research_bt.rerun."
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.now(UTC).isoformat()
    meta = {}
    coverage = {}
    for product in PAIRS:
        info = fetch_product(product)
        meta[product] = {
            "id": info.get("id"),
            "base_increment": info.get("base_increment"),
            "quote_increment": info.get("quote_increment"),
            "min_market_funds": info.get("min_market_funds"),
            "status": info.get("status"),
            "source": "https://api.exchange.coinbase.com/products/" + product,
        }
        rows = fetch_candles(product, START, END)
        digest = write_csv(out_dir / f"{product}.csv", rows)
        coverage[product] = {
            "bars": len(rows),
            "first": rows[0]["time"] if rows else None,
            "last": rows[-1]["time"] if rows else None,
            "sha256": digest,
            "gaps_over_36h": _gaps(rows),
        }
    (out_dir / "products.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out_dir / "coverage.json").write_text(json.dumps({"retrieved_utc": retrieved, **coverage}, indent=2), encoding="utf-8")
    kraken = _kraken_minimums()
    (out_dir / "kraken_minimums.json").write_text(json.dumps(kraken, indent=2), encoding="utf-8")
    matrix = []
    ledgers = []
    curves = []
    for product in coverage:
        bars = _load(out_dir / f"{product}.csv")
        parts = _split(bars)
        increment = float(meta[product]["base_increment"])
        scenarios = [
            _scenario("coinbase_increment", increment, float(meta[product]["min_market_funds"] or 0)),
        ]
        if product == "BTC-USD":
            scenarios.append(_scenario("tradingview_btc_step_parent_reported", TV_BTC_STEP, 0.0))
        families = {family: build(family, [bar.__dict__ for bar in bars]) for family in FAMILIES}
        families["buy_and_hold"] = (["enter"] + ["hold"] * (len(bars) - 1), [None] * len(bars))
        families["cash"] = (["hold"] * len(bars), [None] * len(bars))
        kraken_rule = kraken.get(product)
        if kraken_rule is not None:
            scenarios.append(_scenario(
                "kraken_current_ordermin_on_coinbase_prices",
                kraken_rule["ordermin"],
                kraken_rule["costmin"],
            ))
        for family, (signals, stops) in families.items():
            for part_name, part in {**parts, **_years(bars)}.items():
                offset = bars.index(part[0]) if part else 0
                local_signals = signals[offset : offset + len(part)]
                local_stops = stops[offset : offset + len(part)]
                if family == "buy_and_hold" and local_signals:
                    local_signals = ["enter", *["hold"] * (len(local_signals) - 1)]
                for scenario in scenarios:
                    for rate in COST_RATES:
                        result = run_backtest(
                            part, local_signals, local_stops,
                            symbol=product, step=scenario["step"],
                            min_notional=scenario["min_notional"], cost_rate=rate,
                            size_by_risk=family != "buy_and_hold",
                        )
                        stats = summarize(result, 100.0, len(part))
                        row = {
                            "family": family,
                            "market": product,
                            "split": part_name,
                            "scenario": scenario["name"],
                            "cost_rate_per_side": rate,
                            "recommendation_input": part_name == "unseen",
                            **{key: _num(value) for key, value in stats.items() if key != "session_resets"},
                            "session_resets": "|".join(stats["session_resets"]),
                        }
                        matrix.append(row)
                        if (
                            part_name == "unseen"
                            and rate == COST_RATES[0]
                            and scenario["name"] == "coinbase_increment"
                        ):
                            for trade in result.trades:
                                ledgers.append({"family": family, "scenario": scenario["name"], **trade})
                            for point in result.equity:
                                curves.append({
                                    "family": family,
                                    "market": product,
                                    "time": point["time"],
                                    "equity": round(point["equity"], 6),
                                    "cash": round(point["cash"], 6),
                                    "drawdown": round(point["drawdown"], 6),
                                    "session_id": point["session_id"],
                                })
    _write_csv(out_dir / "results_matrix.csv", matrix)
    _write_csv(out_dir / "trade_ledger.csv", ledgers)
    _write_csv(out_dir / "equity_curves.csv", curves)
    decision = _decide(matrix)
    stocks = _stocks(out_dir)
    shutil.copy(Path(__file__).with_name("source_map.csv"), out_dir / "source_map.csv")
    _write_evidence(out_dir, retrieved, coverage, meta, decision, matrix, stocks)
    (out_dir / "report.json").write_text(json.dumps({
        "retrieved_utc": retrieved,
        "decision": decision,
        "coverage": coverage,
        "products": meta,
        "stocks": stocks,
        "cost_rates_per_side": list(COST_RATES),
        "cost_note": "Each rate is a labeled stress, not an exchange or TradingView fee schedule.",
        "tv_note": "ETH-USD and SOL-USD are not claimed TradingView-feasible. BTC step 0.0001 is parent-reported.",
    }, indent=2), encoding="utf-8")
    return {"decision": decision, "coverage": coverage}


def _kraken_minimums() -> dict[str, dict]:
    """Current public Kraken minimums. They are not historical and not Coinbase rules."""
    url = "https://api.kraken.com/0/public/AssetPairs?pair=XBTUSD,ETHUSD,SOLUSD"
    request = urllib.request.Request(url, headers={"User-Agent": "paper-research-backtest/1.0"})
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = json.load(response)
    mapping = {"XXBTZUSD": "BTC-USD", "XETHZUSD": "ETH-USD", "SOLUSD": "SOL-USD"}
    out = {}
    for key, info in payload.get("result", {}).items():
        product = mapping.get(key)
        if product is None:
            continue
        out[product] = {
            "ordermin": float(info["ordermin"]),
            "costmin": float(info["costmin"]),
            "source": url,
        }
    return out


def _stocks(out_dir: Path) -> dict:
    """US names only through the last verified weekday close. Sunday is not filled in."""
    symbols = ("SPY", "QQQ", "NVDA", "AMD", "AAPL", "MSFT")
    cutoff = datetime(2026, 11, 6, tzinfo=UTC).date()
    try:
        from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv
    except Exception as exc:
        payload = {"status": "import_failed", "error": f"{type(exc).__name__}: {exc}",
                   "summary": "Stock history was not loaded. No stock result is claimed."}
        (out_dir / "stocks.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    rows = []
    errors = []
    for symbol in symbols:
        try:
            frame = load_ohlcv(symbol, "2026-11-06", fill_gaps=False)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if frame is None or frame.empty:
            errors.append({"symbol": symbol, "error": "empty frame"})
            continue
        last = None
        kept = 0
        for record in frame.to_dict("records"):
            stamp = record.get("Date")
            day = stamp.date() if hasattr(stamp, "date") else datetime.fromisoformat(str(stamp)[:10]).date()
            if day > cutoff or day.weekday() >= 5:
                continue
            close = record.get("Close")
            if close is None or close != close:
                continue
            kept += 1
            last = day.isoformat()
        if last != "2026-11-06":
            errors.append({"symbol": symbol, "error": f"last kept session was {last}, expected 2026-11-06"})
            continue
        bars = _stock_bars(frame, cutoff)
        result = run_backtest(
            bars, ["enter"] + ["hold"] * (len(bars) - 1), [None] * len(bars),
            symbol=symbol, step=1, min_notional=0, cost_rate=0.001,
            size_by_risk=False, allocation=0.10,
        )
        stats = summarize(result, 100.0, len(bars))
        rows.append({
            "symbol": symbol,
            "bars": kept,
            "last_session": last,
            "completed_trades": stats["completed_trades"],
            "blocked_entries": stats["blocked_entries"],
            "net_return": stats["net_return"],
            "note": "Whole shares and a 10 percent cap. One share above 10 USD cannot be bought.",
        })
    payload = {
        "status": "checked" if rows else "unavailable",
        "as_of_session": "2026-11-06",
        "source": "tradingagents yahoo load_ohlcv, fill_gaps false, rows after 2026-11-06 and weekend rows dropped",
        "rows": rows,
        "errors": errors,
        "summary": _stock_summary(rows, errors),
    }
    (out_dir / "stocks.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def _stock_bars(frame, cutoff):
    bars = []
    for record in frame.to_dict("records"):
        stamp = record.get("Date")
        day = stamp.date() if hasattr(stamp, "date") else datetime.fromisoformat(str(stamp)[:10]).date()
        if day > cutoff or day.weekday() >= 5:
            continue
        values = [record.get(name) for name in ("Open", "High", "Low", "Close")]
        if any(value is None or value != value for value in values):
            continue
        bars.append(Bar(
            int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp()),
            float(values[0]), float(values[1]), float(values[2]), float(values[3]),
            float(record.get("Volume") or 0),
        ))
    return bars


def _stock_summary(rows, errors) -> str:
    if errors and not rows:
        return "Stock history could not be verified for a complete last session of 2026-11-06. No stock backtest is claimed. " + "; ".join(
            f"{item['symbol']}: {item['error']}" for item in errors
        )
    if not rows:
        return "No stock rows were verified."
    blocked = all(row["completed_trades"] == 0 for row in rows)
    text = (
        "Yahoo history was filtered through the Friday 2026-11-06 session. "
        "Sunday 2026-11-08 was not given a bar. "
    )
    if blocked:
        text += "A whole share costs more than the 10 USD allocation on every checked name, so the cash book completed no stock trade."
    return text


def _years(bars: list[Bar]) -> dict[str, list[Bar]]:
    groups: dict[str, list[Bar]] = {}
    for bar in bars:
        key = "year_" + datetime.fromtimestamp(bar.time, UTC).strftime("%Y")
        groups.setdefault(key, []).append(bar)
    return groups


def _gaps(rows: list[dict]) -> int:
    count = 0
    for prev, nxt in zip(rows, rows[1:], strict=False):
        if nxt["time"] - prev["time"] > 36 * 3600:
            count += 1
    return count


def _load(path: Path) -> list[Bar]:
    bars = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            bars.append(Bar(
                int(row["time"]), float(row["open"]), float(row["high"]),
                float(row["low"]), float(row["close"]), float(row["volume"]),
            ))
    return bars


def _num(value):
    if isinstance(value, float):
        return round(value, 6)
    return value


def _decide(matrix: list[dict]) -> dict:
    """NO TRADE unless unseen net return is positive with at least 30 completed trades on both cost rates."""
    grouped = {}
    for row in matrix:
        if row["split"] != "unseen" or row["scenario"] != "coinbase_increment":
            continue
        grouped.setdefault((row["family"], row["market"]), []).append(row)
    passed = []
    for key, rows in grouped.items():
        if len(rows) < 2:
            continue
        if all(
            (row["net_return"] or 0) > 0
            and (row["completed_trades"] or 0) >= 30
            and (row["profit_factor"] or 0) > 1
            for row in rows
        ):
            passed.append(key)
    return {
        "recommendation": "NO_TRADE" if not passed else "REVIEW_ONLY",
        "passed_unseen_keys": [list(key) for key in passed],
        "rule": "Unseen net return > 0, profit factor > 1, and at least 30 completed trades on every listed cost rate.",
    }


def _write_evidence(path: Path, retrieved, coverage, meta, decision, matrix, stocks) -> None:
    lines = [
        "# Paper research evidence",
        "",
        f"Retrieved {retrieved}. Closed Coinbase daily candles only. No order was sent.",
        "",
        f"Decision: {decision['recommendation']}. {decision['rule']}",
        "",
        "Session: one UTC month. A new month records a reset and starts the 2 USD loss budget from equity at the prior close. The budget is not a guaranteed loss.",
        "",
        "Starting cash is 100 USD, long only, one name per book. Cost rates are labeled stresses, not a venue fee schedule.",
        "",
        "TradingView BTC step 0.0001 is parent-reported. ETH and SOL are not claimed TradingView-feasible.",
        "",
        "The eight families are original approximations. GPL files were read and were not copied. Parameters were frozen before the unseen slice: EMA 12/26, RSI 14 at 30/70, MACD 12/26/9 histogram cross, 20-day Bollinger on close, 20-bar breakout with a 5-bar retest, Donchian 20/10, ATR 14 with a 20 EMA trend filter. The daily VWAP rule is a UTC-day typical-price cross, not an intraday session VWAP.",
        "",
        "Signals use a closed bar. An entry fills at the next bar's open. If stop and target are both touched, the stop fills. A gap through the stop fills at the open. Splits are 60/20/20 in time, each starts flat, and a position is not carried across a boundary. The 2 USD figure stops new entries after that session drawdown. It is not a guaranteed realized loss.",
        "",
        "## Coverage",
        "",
    ]
    for product, info in coverage.items():
        first = datetime.fromtimestamp(info["first"], UTC).date().isoformat() if info["first"] else "none"
        last = datetime.fromtimestamp(info["last"], UTC).date().isoformat() if info["last"] else "none"
        lines.append(
            f"- {product}: {info['bars']} bars, {first} through {last}, gaps over 36h: {info['gaps_over_36h']}, sha256 {info['sha256']}"
        )
    lines.extend(["", "## Unseen net return, Coinbase increment, 10 bps per side", ""])
    lines.append("| family | market | net return | trades | profit factor | max DD USD |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in matrix:
        if row["split"] == "unseen" and row["scenario"] == "coinbase_increment" and row["cost_rate_per_side"] == 0.001:
            pf = row["profit_factor"] if row["profit_factor"] is not None else "N/A"
            lines.append(
                f"| {row['family']} | {row['market']} | {row['net_return']} | {row['completed_trades']} | {pf} | {row['max_drawdown_usd']} |"
            )
    lines.append("")
    lines.append("Buy-and-hold buys the 10 percent cash allocation on the next open and holds to the last close. It does not use a protective stop. Cash stays in cash. Both pay the same per-side stress rate when a fill exists.")
    lines.append("The Kraken rows apply current Kraken order minimums to these Coinbase candles. They are not Kraken historical trades and not a historical minimum.")
    lines.append("TradingView fees were not published in this run, so they are not entered as zero. The 10 bps and 25 bps rates are stresses.")
    lines.append("This window is 2024-01-01 through 2026-11-07. Year rows are calendar slices of that one sample, not named market regimes.")
    lines.append("")
    lines.append("## Stocks")
    lines.append("")
    lines.append(stocks.get("summary", "No stock result."))
    (path / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    import sys
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "research_bt_output")
    print(json.dumps(run(destination), indent=2))
