"""Cash long-only backtest. Signals use a closed bar. Fills are on a later bar."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal


@dataclass
class Bar:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Fill:
    symbol: str
    side: str
    time: int
    price: float
    qty: float
    notional: float
    cost: float
    reason: str
    session_id: str


@dataclass
class Position:
    qty: float
    entry_time: int
    entry_price: float
    stop: float
    target: float
    entry_index: int


@dataclass
class Result:
    trades: list[dict] = field(default_factory=list)
    equity: list[dict] = field(default_factory=list)
    blocked_entries: int = 0
    session_resets: list[str] = field(default_factory=list)


def _floor_step(qty: float, step: float) -> float:
    if step <= 0:
        return 0.0
    units = (Decimal(str(qty)) / Decimal(str(step))).to_integral_value(ROUND_DOWN)
    return float(units * Decimal(str(step)))


def _month(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), UTC).strftime("%Y-%m")
    return datetime.fromtimestamp(int(ts), UTC).strftime("%Y-%m")


def run_backtest(
    bars: list[Bar],
    signals: list[str],
    stops: list[float | None],
    *,
    symbol: str,
    step: float,
    min_notional: float,
    cost_rate: float,
    start_cash: float = 100.0,
    risk_per_trade: float = 0.50,
    session_loss: float = 2.0,
    max_positions: int = 2,
    allocation: float = 0.10,
    size_by_risk: bool = True,
) -> Result:
    """One symbol book. ``signals[i]`` was computed from bars[: i + 1] only.

    A non-flat signal at i is eligible at the open of i + 1. Same-bar high and
    low of bar i are not used to fill that signal. If stop and target are both
    touched after entry, the stop is filled. A gap through the stop fills at
    the open, not at the stop.
    """
    if len(signals) != len(bars) or len(stops) != len(bars):
        raise ValueError("signals and stops must align with bars")
    cash = start_cash
    pos: Position | None = None
    pending = 0
    result = Result()
    month = None
    month_equity = start_cash
    peak = start_cash

    def mark(price: float) -> float:
        held = 0.0 if pos is None else pos.qty * price
        return cash + held

    for i, bar in enumerate(bars):
        session = _month(bar.time)
        if session != month:
            month = session
            month_equity = mark(bars[i - 1].close) if i else start_cash
            result.session_resets.append(session)
        # Manage an open long using this bar. Entry, if any, already happened
        # at a previous open or will happen below only when flat.
        if pos is not None and i > pos.entry_index:
            exit_price = None
            reason = ""
            if bar.open <= pos.stop:
                exit_price = bar.open
                reason = "gap_stop"
            elif bar.low <= pos.stop:
                exit_price = pos.stop
                reason = "stop"
            elif bar.high >= pos.target:
                exit_price = pos.target
                reason = "target"
            elif i > 0 and signals[i - 1] == "exit":
                exit_price = bar.open
                reason = "exit_next_open"
            if exit_price is not None:
                fill = exit_price * (1.0 - cost_rate)
                proceeds = pos.qty * fill
                cost = pos.qty * exit_price * cost_rate
                cash += proceeds
                result.trades.append({
                    "symbol": symbol,
                    "side": "sell",
                    "time": bar.time,
                    "price": fill,
                    "qty": pos.qty,
                    "notional": pos.qty * exit_price,
                    "cost": cost,
                    "reason": reason,
                    "session_id": session,
                    "entry_time": pos.entry_time,
                    "entry_price": pos.entry_price,
                })
                pos = None
                pending = 0
        # Entry from the prior closed bar.
        if pos is None and i > 0 and signals[i - 1] == "enter":
            equity_now = cash
            if equity_now - month_equity <= -session_loss or pending >= max_positions:
                result.blocked_entries += 1
            else:
                stop = stops[i - 1]
                entry_raw = bar.open
                entry = entry_raw * (1.0 + cost_rate)
                if size_by_risk and (stop is None or not (0 < stop < entry)):
                    result.blocked_entries += 1
                else:
                    distance = (entry - stop) if size_by_risk else entry
                    roundtrip = 2.0 * cost_rate * entry
                    per_unit = distance + roundtrip
                    if per_unit <= 0:
                        result.blocked_entries += 1
                    else:
                        risk_qty = (risk_per_trade / per_unit) if size_by_risk else float("inf")
                        budget = min(cash, equity_now * allocation)
                        cash_qty = budget / entry if entry else 0.0
                        raw_qty = min(risk_qty, cash_qty)
                        qty = _floor_step(raw_qty, step)
                        notional = qty * entry_raw
                        if qty <= 0 or qty * entry > cash + 1e-9 or notional < min_notional:
                            result.blocked_entries += 1
                        else:
                            cash -= qty * entry
                            target = entry + 2.0 * distance if size_by_risk else float("inf")
                            pos = Position(qty, bar.time, entry, stop or 0.0, target, i)
                            pending = 1
                            result.trades.append({
                                "symbol": symbol,
                                "side": "buy",
                                "time": bar.time,
                                "price": entry,
                                "qty": qty,
                                "notional": qty * entry_raw,
                                "cost": qty * entry_raw * cost_rate,
                                "reason": "enter_next_open",
                                "session_id": session,
                                "entry_time": bar.time,
                                "entry_price": entry,
                            })
                            if size_by_risk and bar.open <= stop:
                                fill = bar.open * (1.0 - cost_rate)
                                cash += qty * fill
                                result.trades.append({
                                    "symbol": symbol,
                                    "side": "sell",
                                    "time": bar.time,
                                    "price": fill,
                                    "qty": qty,
                                    "notional": qty * bar.open,
                                    "cost": qty * bar.open * cost_rate,
                                    "reason": "gap_stop",
                                    "session_id": session,
                                    "entry_time": bar.time,
                                    "entry_price": entry,
                                })
                                pos = None
                                pending = 0
                            elif size_by_risk and bar.low <= stop:
                                fill = stop * (1.0 - cost_rate)
                                cash += qty * fill
                                result.trades.append({
                                    "symbol": symbol,
                                    "side": "sell",
                                    "time": bar.time,
                                    "price": fill,
                                    "qty": qty,
                                    "notional": qty * stop,
                                    "cost": qty * stop * cost_rate,
                                    "reason": "stop",
                                    "session_id": session,
                                    "entry_time": bar.time,
                                    "entry_price": entry,
                                })
                                pos = None
                                pending = 0
        equity = mark(bar.close)
        peak = max(peak, equity)
        result.equity.append({
            "time": bar.time,
            "equity": equity,
            "cash": cash,
            "session_id": session,
            "drawdown": peak - equity,
        })
    if pos is not None:
        last = bars[-1]
        fill = last.close * (1.0 - cost_rate)
        cash += pos.qty * fill
        result.trades.append({
            "symbol": symbol,
            "side": "sell",
            "time": last.time,
            "price": fill,
            "qty": pos.qty,
            "notional": pos.qty * last.close,
            "cost": pos.qty * last.close * cost_rate,
            "reason": "mark_to_close_end",
            "session_id": _month(last.time),
            "entry_time": pos.entry_time,
            "entry_price": pos.entry_price,
        })
        result.equity[-1]["equity"] = cash
        result.equity[-1]["cash"] = cash
    return result
