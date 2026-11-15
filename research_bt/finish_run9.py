"""Finish the interrupted Run 9 on a bounded set of already-specified cells.

The Nov 8 attempt was still downloading when the session died. Its code and
partial files were not committed, so there was no verified result to resume.
This command does not reopen that download grid.
"""

from __future__ import annotations

import csv
import hashlib
import json
import traceback
from datetime import UTC, datetime
from pathlib import Path

from research_bt.coinbase import fetch_candles
from research_bt.engine import Bar, run_backtest
from research_bt.indicators import ema
from research_bt.metrics import summarize
from research_bt.pine_breakout import run_pine, summarize_pine
from research_bt.strategies import build

FAMILIES = ("donchian_breakout", "breakout_retest", "atr_trend")
MARKETS = ("BTC-USD", "ETH-USD", "SOL-USD")
COST = 0.0065
TV_REFERENCE = {
    "BTC-USD": {"trades": 32, "net_usd": -8.76, "max_dd_usd": 8.76, "profit_factor": 0.068, "win_rate": 0.0313},
    "ETH-USD": {"trades": 40, "net_usd": -12.94, "max_dd_usd": 12.94, "profit_factor": 0.11, "win_rate": 0.05},
    "SOL-USD": {"trades": 40, "net_usd": -14.14, "max_dd_usd": 14.14, "profit_factor": 0.053, "win_rate": 0.025},
}


def run(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    failures = []
    (out_dir / "specification.json").write_text(json.dumps({
        "run": 9,
        "started_utc": started.isoformat(),
        "continues_from": "b297279",
        "prior_attempt": "Interrupted on 2026-11-08 while fetching SOL-USD 15-minute candles. No scored result was committed.",
        "families": list(FAMILIES),
        "window_status": "inspected",
        "capital_usd": 100,
        "leverage": 1,
        "side": "long_only",
        "planned_loss_usd": 0.50,
        "cumulative_loss_usd": 2.0,
        "loss_resets": False,
        "cost_per_side": COST,
        "cost_note": "0.65 percent per side is the whole modeled cost. Slippage and spread are not added again.",
        "regimes": "Lagged close versus EMA20 at the signal bar. trend_down longs are reversal attempts, not shorts.",
        "cells": [
            "1d reused from research_bt/output, 2024-01-01 through 2026-11-07",
            "15m reused from research_bt/correction_output, about 2026-04-22 through 2026-11-08",
            "1h Coinbase fetch 2024-01-01 through the last closed hour before retrieval",
            "5m Coinbase fetch 2026-10-25 through the last closed 5-minute bar, for the Pine comparison and the same three families",
        ],
    }, indent=2), encoding="utf-8")
    series = {}
    series.update(_reuse("1d", Path("research_bt/output"), ""))
    series.update(_reuse("15m", Path("research_bt/correction_output"), "-15m"))
    try:
        series.update(_fetch("1h", 3600, datetime(2024, 1, 1, tzinfo=UTC), datetime(2026, 11, 15, tzinfo=UTC), out_dir))
    except Exception as exc:
        failures.append({"cell": "1h", "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()})
    try:
        series.update(_fetch("5m", 300, datetime(2026, 10, 25, tzinfo=UTC), datetime(2026, 11, 15, tzinfo=UTC), out_dir))
    except Exception as exc:
        failures.append({"cell": "5m", "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()})
    matrix = []
    ledgers = []
    for key, rows in series.items():
        market, timeframe = key.rsplit("-", 1)
        if len(rows) < 100:
            matrix.append(_unavailable(market, timeframe, "insufficient_bars", len(rows)))
            continue
        labels = _regimes(rows)
        bars = [Bar(row["time"], row["open"], row["high"], row["low"], row["close"], row["volume"]) for row in rows]
        for family in FAMILIES:
            signals, stops = build(family, rows)
            result = run_backtest(
                bars, signals, stops, symbol=market, step=0.00000001, min_notional=1.0,
                commission_rate=COST, slippage_rate=0.0, loss_mode="cumulative",
                start_cash=100.0, risk_per_trade=0.50, session_loss=2.0,
            )
            stats = summarize(result, 100.0, len(bars))
            scenario = f"{family}|{market}|{timeframe}|inspected|cost_65bps_per_side|cumulative_no_reset"
            matrix.append({
                "scenario_id": scenario, "family": family, "market": market, "timeframe": timeframe,
                "book": "one_100_usd_book", "window_status": "inspected", "regime": "all",
                "cost_per_side": COST, "loss_mode": "cumulative_no_reset",
                "loss_consumed": round(result.loss_consumed, 6), "cutoff_hit": result.cutoff_hit,
                "bars": len(rows), **{name: _num(value) for name, value in stats.items() if name != "session_resets"},
            })
            _regime_rows(matrix, scenario, family, market, timeframe, result, labels, rows)
            for trade in result.trades:
                ledgers.append({"scenario_id": scenario, "family": family, "market": market, "timeframe": timeframe, **trade})
        _references(matrix, bars, market, timeframe)
    pine = _pine(series, failures)
    _write_csv(out_dir / "results_matrix.csv", matrix)
    _write_csv(out_dir / "trade_ledger.csv", ledgers)
    manifest = _hashes(out_dir)
    decision = {
        "label": "NO_VALIDATED_STRATEGY",
        "reason": "These books are inspected in-sample comparisons. A positive cell with a small trade count is not validation.",
    }
    report = {
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(UTC).isoformat(),
        "decision": decision,
        "failures": failures,
        "pine_vs_tradingview": pine,
        "coverage": {key: {"bars": len(rows), "first": rows[0]["time"] if rows else None, "last": rows[-1]["time"] if rows else None} for key, rows in series.items()},
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "hash_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _evidence(out_dir, report, matrix, pine)
    return report


def _reuse(timeframe: str, folder: Path, suffix: str) -> dict[str, list[dict]]:
    out = {}
    for market in MARKETS:
        path = folder / f"{market}{suffix}.csv"
        out[f"{market}-{timeframe}"] = _read_csv(path) if path.exists() else []
    return out


def _fetch(timeframe: str, granularity: int, start: datetime, end: datetime, out_dir: Path) -> dict[str, list[dict]]:
    retrieved = datetime.now(UTC)
    out = {}
    for market in MARKETS:
        rows = fetch_candles(market, start, end, granularity=granularity)
        cutoff = int(retrieved.timestamp()) - granularity
        closed = [row for row in rows if row["time"] + granularity <= cutoff]
        _write_rows(out_dir / f"{market}-{timeframe}.csv", closed)
        out[f"{market}-{timeframe}"] = closed
        (out_dir / f"{market}-{timeframe}.meta.json").write_text(json.dumps({
            "source": f"https://api.exchange.coinbase.com/products/{market}/candles",
            "granularity": granularity,
            "retrieved_utc": retrieved.isoformat(),
            "quote": "USD",
            "venue": "Coinbase Exchange spot",
            "tail_rule": "Drop a bucket that ends after retrieval minus one interval.",
            "bars": len(closed),
        }, indent=2), encoding="utf-8")
    return out


def _regimes(rows: list[dict]) -> list[str]:
    closes = [row["close"] for row in rows]
    trend = ema(closes, 20)
    labels = []
    for i, close in enumerate(closes):
        if trend[i] is None:
            labels.append("undefined")
        elif close > trend[i]:
            labels.append("trend_up")
        else:
            labels.append("trend_down")
    return labels


def _regime_rows(matrix, scenario, family, market, timeframe, result, labels, rows):
    index = {row["time"]: i for i, row in enumerate(rows)}
    grouped = {"trend_up": [], "trend_down": []}
    pending = None
    for trade in result.trades:
        if trade["side"] == "buy":
            signal_i = index.get(trade["time"], 1) - 1
            pending = labels[signal_i] if signal_i >= 0 else "undefined"
        elif trade["side"] == "sell" and pending in grouped and trade.get("pnl") is not None:
            grouped[pending].append(trade["pnl"])
            pending = None
    for regime, pnls in grouped.items():
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        gross_loss = -sum(losses)
        matrix.append({
            "scenario_id": scenario + f"|{regime}",
            "family": family, "market": market, "timeframe": timeframe,
            "book": "trade_subset_not_a_separate_account",
            "window_status": "inspected",
            "regime": regime if regime == "trend_up" else "trend_down_long_reversal_not_a_short",
            "cost_per_side": COST, "loss_mode": "cumulative_no_reset",
            "completed_trades": len(pnls),
            "net_pnl_usd": _num(sum(pnls)) if pnls else None,
            "profit_factor": _num(sum(wins) / gross_loss) if gross_loss else None,
            "win_rate": _num(len(wins) / len(pnls)) if pnls else None,
            "expectancy": _num(sum(pnls) / len(pnls)) if pnls else None,
            "note": "Subset of the one shared book. Drawdown of the subset is not a second equity curve.",
        })


def _references(matrix, bars, market, timeframe):
    for family, signals, risk in (
        ("buy_and_hold_unconstrained", ["enter"] + ["hold"] * (len(bars) - 1), False),
        ("cash", ["hold"] * len(bars), False),
    ):
        result = run_backtest(
            bars, signals, [None] * len(bars), symbol=market, step=0.00000001, min_notional=0,
            commission_rate=COST, slippage_rate=0.0, loss_mode="off", size_by_risk=risk,
        )
        stats = summarize(result, 100.0, len(bars))
        matrix.append({
            "scenario_id": f"{family}|{market}|{timeframe}|inspected|cost_65bps_per_side|unconstrained_reference",
            "family": family, "market": market, "timeframe": timeframe, "regime": "all",
            "window_status": "inspected", "book": "reference_not_the_risk_budget",
            "cost_per_side": COST, "loss_mode": "off",
            **{name: _num(value) for name, value in stats.items() if name != "session_resets"},
        })


def _pine(series, failures) -> dict:
    out = {"source": "Coinbase USD spot 5-minute candles", "tradingview_inspected": TV_REFERENCE, "replica": {}}
    for market in MARKETS:
        rows = series.get(f"{market}-5m") or []
        if len(rows) < 100:
            out["replica"][market] = {"status": "unavailable", "bars": len(rows)}
            continue
        try:
            result = run_pine(rows)
            stats = summarize_pine(result)
            tv = TV_REFERENCE[market]
            out["replica"][market] = {
                "status": "ran",
                "bars": len(rows),
                "first": rows[0]["time"],
                "last": rows[-1]["time"],
                **{key: _num(value) for key, value in stats.items()},
                "trade_count_minus_tradingview": stats["trades"] - tv["trades"],
                "net_usd_minus_tradingview": _num(stats["net_usd"] - tv["net_usd"]),
            }
        except Exception as exc:
            failures.append({"cell": f"pine-{market}", "error": f"{type(exc).__name__}: {exc}"})
            out["replica"][market] = {"status": "failed", "error": str(exc)}
    out["difference_note"] = (
        "TradingView used its own 5-minute BTCUSD/ETHUSD/SOLUSD feed. This replica uses Coinbase USD spot. "
        "Indicator warmup, the UTC-day intraday guard, and stop-before-limit when both are touched in one bar "
        "can change the trade count. The attached Strategy Tester numbers are inspected, not a fresh test."
    )
    return out


def _unavailable(market, timeframe, reason, bars):
    return {
        "scenario_id": f"unavailable|{market}|{timeframe}",
        "family": "not_scored", "market": market, "timeframe": timeframe,
        "window_status": "unavailable", "reason": reason, "bars": bars, "completed_trades": 0,
    }


def _read_csv(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            rows.append({
                "time": int(float(record["time"])), "open": float(record["open"]),
                "high": float(record["high"]), "low": float(record["low"]),
                "close": float(record["close"]), "volume": float(record["volume"]),
            })
    return rows


def _write_rows(path: Path, rows: list[dict]) -> None:
    lines = ["time,open,high,low,close,volume"]
    for row in rows:
        lines.append(f"{row['time']},{row['open']},{row['high']},{row['low']},{row['close']},{row['volume']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _hashes(folder: Path) -> dict:
    out = {}
    for path in sorted(folder.glob("*")):
        if path.is_file() and path.name != "hash_manifest.json":
            out[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _num(value):
    if isinstance(value, float):
        return round(value, 6)
    return value


def _evidence(path: Path, report: dict, matrix: list[dict], pine: dict) -> None:
    lines = [
        "# Run 9 completion",
        "",
        f"Started {report['started_utc']}. Finished {report['finished_utc']}. No order was sent.",
        "",
        "The 2026-11-08 Run 9 process was interrupted during the SOL-USD 15-minute download. That attempt produced no committed score. This file is the bounded completion.",
        "",
        f"Label: {report['decision']['label']}. {report['decision']['reason']}",
        "",
        "Every scored clock here was already inspected, either in Run 8 or in the attached TradingView test. Nothing is called unseen.",
        "",
        "Cost is 0.65 percent per side and is not combined with a second slippage or spread. Each family book starts at 100 USD, buys only, plans at most 0.50 USD of loss including that cost, and stops new entries after 2 USD of cumulative realized loss. Profits do not restore the 2 USD.",
        "",
        "## Family books",
        "",
        "| family | market | tf | trades | net pnl USD | max DD USD | PF | win rate | expectancy | cutoff |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in matrix:
        if row.get("regime") == "all" and row.get("family") in FAMILIES:
            net = row.get("ending_equity")
            pnl = None if net is None else round(net - 100.0, 6)
            lines.append(
                f"| {row['family']} | {row['market']} | {row['timeframe']} | {row.get('completed_trades')} | {pnl} | "
                f"{row.get('max_drawdown_usd')} | {row.get('profit_factor')} | {row.get('win_rate')} | {row.get('expectancy')} | {row.get('cutoff_hit')} |"
            )
    lines.extend(["", "## Regime subsets of those same books", ""])
    lines.append("| family | market | tf | regime | trades | pnl USD | PF | win rate | expectancy |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in matrix:
        if row.get("book") == "trade_subset_not_a_separate_account":
            lines.append(
                f"| {row['family']} | {row['market']} | {row['timeframe']} | {row['regime']} | {row['completed_trades']} | "
                f"{row.get('net_pnl_usd')} | {row.get('profit_factor')} | {row.get('win_rate')} | {row.get('expectancy')} |"
            )
    lines.extend(["", "## Pine replica versus the inspected TradingView result", ""])
    for market, item in pine.get("replica", {}).items():
        tv = TV_REFERENCE[market]
        lines.append(
            f"- {market}: replica {item}. TradingView inspected trades {tv['trades']}, net {tv['net_usd']} USD."
        )
    lines.append("")
    lines.append(pine.get("difference_note", ""))
    if report["failures"]:
        lines.extend(["", "## Failures", ""])
        for item in report["failures"]:
            lines.append(f"- {item['cell']}: {item['error']}")
    lines.append("")
    (path / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import sys
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "research_bt/run9_output")
    print(json.dumps(run(destination)["decision"], indent=2))
