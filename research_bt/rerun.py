"""Methodology correction. Does not place an order and does not refit rules.

The daily holdout in research_bt/output was already inspected. This module
reruns those books with corrected costs and loss accounting and labels that
slice as an inspected holdout. It is not a fresh unseen test.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from research_bt.coinbase import PAIRS, fetch_candles, write_csv
from research_bt.engine import Bar, run_backtest
from research_bt.indicators import atr
from research_bt.metrics import summarize
from research_bt.stocks import whole_share_check
from research_bt.strategies import build, build_intraday_vwap

DAILY_FAMILIES = (
    "ema_cross",
    "rsi_mean",
    "macd_momentum",
    "bollinger_mean",
    "breakout_retest",
    "donchian_breakout",
    "atr_trend",
)
PRIMARY_COSTS = (
    {"name": "primary_65bps_per_side", "role": "primary_stress", "commission": 0.006, "slip": 0.0005},
    {"name": "primary_70bps_per_side", "role": "primary_stress", "commission": 0.006, "slip": 0.001},
)
OPTIMISTIC_COSTS = (
    {"name": "optimistic_10bps_per_side", "role": "optimistic_sensitivity", "commission": 0.001, "slip": 0.0},
    {"name": "optimistic_25bps_per_side", "role": "optimistic_sensitivity", "commission": 0.0025, "slip": 0.0},
)
SPEC = {
    "kind": "posthoc_methodology_correction",
    "fresh_unseen": False,
    "daily_holdout_label": "inspected_holdout",
    "vwap_holdout_label": "first_look_holdout",
    "rejected_proxy": "one-bar UTC HLC3 cross is not a VWAP pullback",
    "vwap_rule": "UTC session VWAP, at least 4 closed bars, prior close above VWAP, signal bar low at or through VWAP and close back above, entry on the next bar",
    "costs": list(PRIMARY_COSTS) + list(OPTIMISTIC_COSTS),
    "spread_rate": 0.0,
    "spread_note": "Candles are trade prints. Slippage is the allowance for crossing the spread. A spread is not added again.",
    "risk_per_trade_usd": 0.50,
    "risk_note": "Size uses the stop as the adverse exit and adds entry and exit commission and slippage. The planned loss is kept at or under 0.50. A gap can lose more. No future exit price is used.",
    "experiment_loss": "cumulative realized losses, not restored by later profits, no calendar reset, per 100 USD book. The next entry is sized to the budget still left, so the plan does not exceed 2 USD. A gap can still lose more.",
    "monthly_loss": "separate research scenario, resets each UTC month",
    "two_hour_loss": "separate intraday research scenario, resets every 7200 seconds and is not the whole-book allowance",
    "trade_count_note": "A 30-trade cutoff in the first run was this study's heuristic. It is not a guarantee and a low count is inconclusive even when the return is positive.",
}


def run(out_dir: Path, daily_dir: Path = Path("research_bt/output")) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "specification.json").write_text(json.dumps(SPEC, indent=2), encoding="utf-8")
    retrieved = datetime.now(UTC).isoformat()
    daily = _load_daily(daily_dir)
    kraken = json.loads((daily_dir / "kraken_minimums.json").read_text(encoding="utf-8"))
    products = json.loads((daily_dir / "products.json").read_text(encoding="utf-8"))
    matrix = []
    ledgers = []
    curves = []
    for product, bars in daily.items():
        _run_daily_product(
            product, bars, products[product], kraken.get(product), matrix, ledgers, curves
        )
    vwap_coverage = _run_vwap(out_dir, products, kraken, matrix, ledgers, curves)
    _attach_exposure_scale(matrix)
    stocks = _stocks(out_dir)
    _write_csv(out_dir / "results_matrix.csv", matrix)
    _write_csv(out_dir / "trade_ledger.csv", ledgers)
    _write_csv(out_dir / "equity_curves.csv", curves)
    decision = {
        "recommendation": "NO_TRADE",
        "reason": (
            "This is a second look at an already inspected daily holdout, plus one "
            "historical intraday VWAP window. Low trade counts are inconclusive. "
            "The 30-trade figure is not a guarantee."
        ),
    }
    report = {
        "retrieved_utc": retrieved,
        "specification": SPEC,
        "decision": decision,
        "daily_source": "research_bt/output candles from the first retrieval; not a new daily download",
        "vwap_coverage": vwap_coverage,
        "stocks": stocks,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_evidence(out_dir, retrieved, decision, matrix, vwap_coverage, stocks)
    return report


def _run_daily_product(product, bars, product_meta, kraken, matrix, ledgers, curves):
    framed = [bar.__dict__ for bar in bars]
    families = {name: build(name, framed) for name in DAILY_FAMILIES}
    families["buy_and_hold_unconstrained"] = (["enter"] + ["hold"] * (len(bars) - 1), [None] * len(bars))
    families["cash"] = (["hold"] * len(bars), [None] * len(bars))
    families["risk_budget_hold"] = _risk_hold(families["atr_trend"][1])
    parts = _parts(bars)
    scenarios = [_scenario("coinbase_increment", float(product_meta["base_increment"]), float(product_meta["min_market_funds"] or 0))]
    if kraken is not None:
        scenarios.append(_scenario("kraken_current_ordermin_on_coinbase_prices", kraken["ordermin"], kraken["costmin"]))
    if product == "BTC-USD":
        scenarios.append(_scenario("tradingview_btc_step_parent_reported", 0.0001, 0.0))
    for family, (signals, stops) in families.items():
        for part_name, part, status in parts:
            offset = _offset(bars, part)
            local_signals = list(signals[offset : offset + len(part)])
            local_stops = list(stops[offset : offset + len(part)])
            prior_signal = signals[offset - 1] if offset else None
            prior_stop = stops[offset - 1] if offset else None
            if family == "buy_and_hold_unconstrained":
                local_signals = ["enter", *["hold"] * (len(part) - 1)]
                prior_signal = None
            if family == "risk_budget_hold":
                local_signals = ["hold"] * len(part)
                prior_signal = None
                for index, stop in enumerate(local_stops):
                    if stop is not None:
                        local_signals[index] = "enter"
                        break
            costs = PRIMARY_COSTS if _primary_only(family, part_name) else (*PRIMARY_COSTS, *OPTIMISTIC_COSTS)
            modes = ("cumulative",) if family in {"buy_and_hold_unconstrained", "cash", "risk_budget_hold"} else ("cumulative", "monthly")
            if part_name.startswith("calendar") or part_name == "whole_sample":
                costs = PRIMARY_COSTS
                modes = ("cumulative",)
            for scenario in scenarios:
                use_costs = costs if scenario["name"] == "coinbase_increment" else PRIMARY_COSTS
                for cost in use_costs:
                    for mode in modes:
                        result = run_backtest(
                            part, local_signals, local_stops,
                            symbol=product, step=scenario["step"], min_notional=scenario["min_notional"],
                            commission_rate=cost["commission"], slippage_rate=cost["slip"],
                            loss_mode="off" if family in {"buy_and_hold_unconstrained", "cash", "risk_budget_hold"} else mode,
                            size_by_risk=family not in {"buy_and_hold_unconstrained", "cash"},
                            prior_signal=prior_signal, prior_stop=prior_stop,
                        )
                        row = _row(family, product, part_name, status, scenario["name"], cost, mode, result, len(part))
                        matrix.append(row)
                        if _keep_detail(part_name, scenario["name"], cost["name"], mode):
                            _store(ledgers, curves, family, product, scenario["name"], result)


def _primary_only(family, part_name) -> bool:
    return family in {"cash", "risk_budget_hold"} or part_name.startswith("calendar")


def _keep_detail(part_name, scenario, cost, mode) -> bool:
    return (
        part_name in {"inspected_holdout", "whole_sample"}
        and scenario == "coinbase_increment"
        and cost == "primary_65bps_per_side"
        and mode == "cumulative"
    )


def _run_vwap(out_dir, products, kraken, matrix, ledgers, curves):
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    start = end - timedelta(days=200)
    coverage = {"granularity_seconds": 900, "requested_start": start.isoformat(), "markets": {}}
    for product in PAIRS:
        print(f"fetch 15m {product}", flush=True)
        rows = fetch_candles(product, start, end, granularity=900)
        digest = write_csv(out_dir / f"{product}-15m.csv", rows)
        bars = [Bar(row["time"], row["open"], row["high"], row["low"], row["close"], row["volume"]) for row in rows]
        holes = _holes(rows, 900)
        days = len({row["time"] // 86400 for row in rows})
        coverage["markets"][product] = {
            "bars": len(rows),
            "utc_days": days,
            "first": rows[0]["time"] if rows else None,
            "last": rows[-1]["time"] if rows else None,
            "missing_15m_slots": holes,
            "sha256": digest,
            "regime_note": "One recent window of about 200 days. Not a multi-regime sample.",
        }
        signals, stops = build_intraday_vwap([bar.__dict__ for bar in bars])
        parts = _vwap_parts(bars)
        meta = products[product]
        scenarios = [_scenario("coinbase_increment", float(meta["base_increment"]), float(meta["min_market_funds"] or 0))]
        if product in kraken:
            scenarios.append(_scenario("kraken_current_ordermin_on_coinbase_prices", kraken[product]["ordermin"], kraken[product]["costmin"]))
        if product == "BTC-USD":
            scenarios.append(_scenario("tradingview_btc_step_parent_reported", 0.0001, 0.0))
        for part_name, part, status in parts:
            offset = _offset(bars, part)
            local_signals = signals[offset : offset + len(part)]
            local_stops = stops[offset : offset + len(part)]
            prior_signal = signals[offset - 1] if offset else None
            prior_stop = stops[offset - 1] if offset else None
            mode_list = ("cumulative", "two_hour") if part_name == "whole_sample" else ("cumulative",)
            cost_list = (*PRIMARY_COSTS, *OPTIMISTIC_COSTS) if part_name != "whole_sample" else PRIMARY_COSTS
            for scenario in scenarios:
                costs = cost_list if scenario["name"] == "coinbase_increment" else PRIMARY_COSTS
                for cost in costs:
                    for mode in mode_list:
                        result = run_backtest(
                            part, local_signals, local_stops, symbol=product,
                            step=scenario["step"], min_notional=scenario["min_notional"],
                            commission_rate=cost["commission"], slippage_rate=cost["slip"],
                            loss_mode=mode, prior_signal=prior_signal, prior_stop=prior_stop,
                        )
                        matrix.append(_row(
                            "vwap_pullback_intraday", product, part_name, status,
                            scenario["name"], cost, mode, result, len(part),
                        ))
                        if part_name == "first_look_holdout" and cost["name"] == "primary_65bps_per_side" and mode == "cumulative" and scenario["name"] == "coinbase_increment":
                            _store(ledgers, curves, "vwap_pullback_intraday", product, scenario["name"], result)
    (out_dir / "vwap_coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    return coverage


def _stocks(out_dir: Path) -> dict:
    cutoff = datetime(2026, 11, 6, tzinfo=UTC).date()
    try:
        from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv
    except Exception as exc:
        payload = {"status": "import_failed", "error": f"{type(exc).__name__}: {exc}"}
        (out_dir / "stocks.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    rows = []
    errors = []
    for symbol in ("SPY", "QQQ", "NVDA", "AMD", "AAPL", "MSFT"):
        try:
            frame = load_ohlcv(symbol, "2026-11-06", fill_gaps=False)
        except Exception as exc:
            errors.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
            continue
        bars = _yahoo_bars(frame, cutoff)
        if not bars or datetime.fromtimestamp(bars[-1].time, UTC).date().isoformat() != "2026-11-06":
            errors.append({"symbol": symbol, "error": "Friday 2026-11-06 close was not the last kept session"})
            continue
        closes = [bar.close for bar in bars]
        highs = [bar.high for bar in bars]
        lows = [bar.low for bar in bars]
        ranges = atr(highs, lows, closes, 14)
        last = bars[-1]
        stop = None if ranges[-1] is None else last.close - 1.5 * ranges[-1]
        check = whole_share_check(last.close, stop, 0.006, 0.0005)
        check.update({
            "symbol": symbol,
            "session": "2026-11-06",
            "sunday_bar": False,
            "note": "Priced at the Friday close. Sunday 2026-11-08 has no bar and no fill was simulated.",
        })
        rows.append(check)
    text = (
        "Whole shares were checked against 100 USD cash and against a 0.50 USD planned loss "
        "using the Friday 2026-11-06 close, a 1.5 ATR stop, 60 bps commission and 5 bps slippage per side. "
        "The earlier 10 USD allocation was not the constraint. Yahoo does not publish a share increment, "
        "so a fractional account is not assumed."
    )
    payload = {"status": "checked" if rows else "unavailable", "summary": text, "rows": rows, "errors": errors}
    (out_dir / "stocks.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _yahoo_bars(frame, cutoff):
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


def _parts(bars: list[Bar]):
    n = len(bars)
    a = int(n * 0.6)
    b = int(n * 0.8)
    out = [
        ("train", bars[:a], "in_sample"),
        ("validation", bars[a:b], "validation_not_a_fresh_test"),
        ("inspected_holdout", bars[b:], "previously_inspected_not_fresh_unseen"),
        ("whole_sample", bars, "one_book_no_split_restart"),
    ]
    groups: dict[str, list[Bar]] = {}
    for bar in bars:
        key = "calendar_" + datetime.fromtimestamp(bar.time, UTC).strftime("%Y") + "_not_a_regime"
        groups.setdefault(key, []).append(bar)
    for key, group in groups.items():
        out.append((key, group, "calendar_slice_not_a_regime"))
    return out


def _vwap_parts(bars: list[Bar]):
    n = len(bars)
    a = int(n * 0.6)
    b = int(n * 0.8)
    return [
        ("train", bars[:a], "in_sample"),
        ("validation", bars[a:b], "validation_not_a_fresh_test"),
        ("first_look_holdout", bars[b:], "historical_first_look_not_prospective"),
        ("whole_sample", bars, "one_book_no_split_restart"),
    ]


def _risk_hold(stops):
    signals = ["hold"] * len(stops)
    for i, stop in enumerate(stops):
        if stop is not None:
            signals[i] = "enter"
            break
    return signals, stops


def _scenario(name, step, minimum):
    return {"name": name, "step": float(step), "min_notional": float(minimum)}


def _offset(bars, part) -> int:
    return bars.index(part[0]) if part else 0


def _row(family, product, part_name, status, scenario, cost, mode, result, n_bars):
    stats = summarize(result, 100.0, n_bars)
    return {
        "family": family,
        "market": product,
        "split": part_name,
        "window_status": status,
        "scenario": scenario,
        "cost_name": cost["name"],
        "cost_role": cost["role"],
        "commission_rate": cost["commission"],
        "slippage_rate": cost["slip"],
        "spread_rate": 0.0,
        "loss_mode": "off" if family in {"buy_and_hold_unconstrained", "cash", "risk_budget_hold"} else mode,
        **{key: _num(value) for key, value in stats.items() if key != "session_resets"},
        "session_reset_count": len(result.session_resets),
        "loss_consumed": _num(result.loss_consumed),
        "cutoff_hit": result.cutoff_hit,
    }


def _store(ledgers, curves, family, product, scenario, result):
    for trade in result.trades:
        ledgers.append({"family": family, "market": product, "scenario": scenario, **trade})
    for point in result.equity:
        curves.append({
            "family": family, "market": product, "time": point["time"],
            "equity": round(point["equity"], 6), "drawdown": round(point["drawdown"], 6),
            "in_position": point["in_position"],
        })


def _attach_exposure_scale(matrix):
    holds = {}
    for row in matrix:
        if row["family"] == "buy_and_hold_unconstrained":
            holds[(row["market"], row["split"], row["cost_name"], row["scenario"])] = row.get("net_return")
    for row in matrix:
        base = holds.get((row["market"], row["split"], row["cost_name"], row["scenario"]))
        exposure = row.get("exposure")
        if base is None or exposure is None or row["family"] == "buy_and_hold_unconstrained":
            row["exposure_scaled_buyhold_return"] = None
        else:
            row["exposure_scaled_buyhold_return"] = _num(base * exposure)


def _load_daily(path: Path) -> dict[str, list[Bar]]:
    out = {}
    for product in PAIRS:
        bars = []
        with (path / f"{product}.csv").open(encoding="utf-8") as handle:
            for record in csv.DictReader(handle):
                bars.append(Bar(
                    int(record["time"]), float(record["open"]), float(record["high"]),
                    float(record["low"]), float(record["close"]), float(record["volume"]),
                ))
        out[product] = bars
    return out


def _holes(rows, step):
    if len(rows) < 2:
        return 0
    missing = 0
    for prev, nxt in zip(rows, rows[1:], strict=False):
        gap = nxt["time"] - prev["time"]
        if gap > step:
            missing += gap // step - 1
    return int(missing)


def _num(value):
    if isinstance(value, float):
        return round(value, 6)
    return value


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    for row in rows[1:]:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_evidence(path, retrieved, decision, matrix, vwap_coverage, stocks):
    lines = [
        "# Methodology correction",
        "",
        f"Run at {retrieved}. No order was sent.",
        "",
        f"Decision: {decision['recommendation']}. {decision['reason']}",
        "",
        "The daily 60/20/20 holdout was already reviewed in the first run. It is labeled inspected_holdout. A prospective unseen window would have to be collected after this specification and left untouched. This file does not claim that.",
        "",
        "Primary costs are 65 and 70 bps per side: 60 bps commission plus 5 or 10 bps slippage. The 10 and 25 bps rows are an optimistic sensitivity from the first run. Spread is not added on top of slippage because these candles are trade prints.",
        "",
        "The experiment loss limit is a cumulative 2 USD of realized losses on a 100 USD book. Later profits do not restore it, and a new month does not restore it. The monthly reset and the 2-hour intraday reset are separate scenarios. Their reset counts are in the matrix. A gap can lose more than 2 USD.",
        "",
        "The one-bar daily VWAP cross is rejected. The intraday rule uses 15-minute Coinbase candles, a UTC-day VWAP of closed bars only, and at least four bars in the day.",
        "",
        "## Inspected daily holdout, cumulative loss, Coinbase step, 65 bps per side",
        "",
        "| family | market | net return | trades | max DD USD | max DD % | exposure | hold hours | expectancy |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in matrix:
        if (
            row["split"] == "inspected_holdout"
            and row["cost_name"] == "primary_65bps_per_side"
            and row["loss_mode"] in {"cumulative", "off"}
            and row["scenario"] == "coinbase_increment"
            and row["family"] != "vwap_pullback_intraday"
        ):
            lines.append(
                f"| {row['family']} | {row['market']} | {row['net_return']} | {row['completed_trades']} | "
                f"{row['max_drawdown_usd']} | {row['max_drawdown_pct']} | {row['exposure']} | "
                f"{row['avg_hold_hours']} | {row['expectancy']} |"
            )
    lines.extend(["", "## Intraday VWAP first look, same primary cost", ""])
    lines.append("| market | split | net return | trades | max DD USD | max DD % | exposure | hold hours | expectancy |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in matrix:
        if row["family"] == "vwap_pullback_intraday" and row["cost_name"] == "primary_65bps_per_side" and row["loss_mode"] == "cumulative" and row["scenario"] == "coinbase_increment" and row["split"] in {"train", "validation", "first_look_holdout", "whole_sample"}:
            lines.append(
                f"| {row['market']} | {row['split']} | {row['net_return']} | {row['completed_trades']} | "
                f"{row['max_drawdown_usd']} | {row['max_drawdown_pct']} | {row['exposure']} | "
                f"{row['avg_hold_hours']} | {row['expectancy']} |"
            )
    lines.extend(["", "## VWAP coverage", ""])
    for product, info in vwap_coverage.get("markets", {}).items():
        first = datetime.fromtimestamp(info["first"], UTC).isoformat() if info["first"] else "none"
        last = datetime.fromtimestamp(info["last"], UTC).isoformat() if info["last"] else "none"
        lines.append(
            f"- {product}: {info['bars']} closed 15-minute bars, {info['utc_days']} UTC days, {first} through {last}, missing slots {info['missing_15m_slots']}. {info['regime_note']}"
        )
    lines.extend(["", "## Separate 2-hour reset", ""])
    lines.append(
        "The 2-hour rows reset the 2 USD budget every 7200 seconds. They are not the one-book allowance. "
        "A reset lets the book keep losing. The cumulative whole-sample book does not reset."
    )
    for row in matrix:
        if (
            row["family"] == "vwap_pullback_intraday"
            and row["split"] == "whole_sample"
            and row["scenario"] == "coinbase_increment"
            and row["cost_name"] == "primary_65bps_per_side"
        ):
            lines.append(
                f"- {row['market']} {row['loss_mode']}: net return {row['net_return']}, "
                f"trades {row['completed_trades']}, loss consumed {row['loss_consumed']}, "
                f"resets {row['session_reset_count']}."
            )
    lines.extend(["", "## Stocks", "", stocks.get("summary", "No stock calculation.")])
    for row in stocks.get("rows", []):
        lines.append(
            f"- {row['symbol']} {row['session']}: close {row['price']}, one-share cash out {row['one_share_cash_out']}, "
            f"planned loss {row['planned_loss_one_share']}, cash rejects {row['cash_rejects_one_share']}, "
            f"risk rejects {row['risk_rejects_one_share']}."
        )
    lines.append("")
    (path / "evidence.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import sys
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "research_bt/correction_output")
    print(json.dumps(run(destination)["decision"], indent=2))
