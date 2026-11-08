"""Cash long-only backtest. A closed bar can signal. The fill is a later bar."""

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
class Position:
    qty: float
    entry_time: int
    entry_fill: float
    cash_out: float
    stop: float
    target: float
    entry_index: int


@dataclass
class Result:
    trades: list[dict] = field(default_factory=list)
    equity: list[dict] = field(default_factory=list)
    blocked_entries: int = 0
    session_resets: list[str] = field(default_factory=list)
    loss_consumed: float = 0.0
    cutoff_hit: bool = False


def _floor_step(qty: float, step: float) -> float:
    if step <= 0 or qty <= 0:
        return 0.0
    units = (Decimal(str(qty)) / Decimal(str(step))).to_integral_value(ROUND_DOWN)
    return float(units * Decimal(str(step)))


def _session_id(ts: int, loss_mode: str) -> str:
    if loss_mode == "monthly":
        return datetime.fromtimestamp(int(ts), UTC).strftime("%Y-%m")
    if loss_mode == "two_hour":
        return str(int(ts) // 7200)
    return "book"


def _adverse_plan(open_price: float, stop: float, commission: float, slip: float) -> float | None:
    """Loss of one unit if the exit is the stop. No future price is used."""
    if not (0 < stop < open_price):
        return None
    entry_fill = open_price * (1.0 + slip)
    exit_fill = stop * (1.0 - slip)
    fee_in = entry_fill * commission
    fee_out = exit_fill * commission
    planned = (entry_fill - exit_fill) + fee_in + fee_out
    if planned <= 0:
        return None
    return planned


def run_backtest(
    bars: list[Bar],
    signals: list[str],
    stops: list[float | None],
    *,
    symbol: str,
    step: float,
    min_notional: float,
    commission_rate: float = 0.0,
    slippage_rate: float = 0.0,
    spread_rate: float = 0.0,
    start_cash: float = 100.0,
    risk_per_trade: float = 0.50,
    session_loss: float = 2.0,
    loss_mode: str = "cumulative",
    max_positions: int = 2,
    size_by_risk: bool = True,
    prior_signal: str | None = None,
    prior_stop: float | None = None,
    cost_rate: float | None = None,
) -> Result:
    """Fill a signal at the next open. Stop is filled before target on the same bar.

    ``spread_rate`` stays zero when the candle is a trade print and slippage is
    already the allowance for crossing the spread. Adding both would count it twice.
    ``loss_mode`` ``cumulative`` does not give the 2 USD budget back after a profit
    and does not reset on a calendar boundary. ``monthly`` and ``two_hour`` are
    separate research scenarios and record every reset. A gap can lose more than
    the planned amount.
    """
    if spread_rate != 0.0:
        raise ValueError("spread is not added on top of slippage for trade-print candles")
    if cost_rate is not None:
        commission_rate = cost_rate
        slippage_rate = 0.0
    if loss_mode not in {"cumulative", "monthly", "two_hour", "off"}:
        raise ValueError(loss_mode)
    if len(signals) != len(bars) or len(stops) != len(bars):
        raise ValueError("signals and stops must align with bars")
    cash = start_cash
    pos: Position | None = None
    pending = 0
    result = Result()
    session = None
    month_equity = start_cash
    loss_total = 0.0
    session_used = 0.0
    peak = start_cash

    def mark(price: float) -> float:
        held = 0.0 if pos is None else pos.qty * price * (1.0 - slippage_rate) * (1.0 - commission_rate)
        return cash + held

    def consume(pnl: float) -> None:
        nonlocal loss_total, session_used
        if pnl < 0:
            loss_total += -pnl
            session_used += -pnl
            result.loss_consumed = loss_total
            if _budget_exhausted(loss_mode, loss_total, session_used, session_loss):
                result.cutoff_hit = True

    for i, bar in enumerate(bars):
        current = _session_id(bar.time, loss_mode)
        if current != session:
            session = current
            if loss_mode == "monthly":
                month_equity = mark(bars[i - 1].close) if i else start_cash
                result.session_resets.append(current)
            elif loss_mode == "two_hour":
                session_used = 0.0
                result.session_resets.append(current)
            elif i == 0:
                result.session_resets.append(current)
        if pos is not None and i > pos.entry_index:
            exit_raw = None
            reason = ""
            if bar.open <= pos.stop:
                exit_raw = bar.open
                reason = "gap_stop"
            elif bar.low <= pos.stop:
                exit_raw = pos.stop
                reason = "stop"
            elif bar.high >= pos.target:
                exit_raw = pos.target
                reason = "target"
            elif (prior_signal if i == 0 else signals[i - 1]) == "exit":
                exit_raw = bar.open
                reason = "exit_next_open"
            if exit_raw is not None:
                _close(result, pos, exit_raw, bar.time, reason, session, symbol,
                       commission_rate, slippage_rate, consume)
                cash += result.trades[-1]["cash_delta"]
                pos = None
                pending = 0
        signal = prior_signal if i == 0 else signals[i - 1]
        stop = prior_stop if i == 0 else stops[i - 1]
        if pos is None and signal == "enter":
            risk_cap = _risk_cap(
                loss_mode, loss_total, session_used, session_loss, cash, month_equity, risk_per_trade,
            )
            if (
                _blocked(loss_mode, loss_total, session_used, session_loss, cash, month_equity, pending, max_positions)
                or (size_by_risk and risk_cap <= 0)
            ):
                result.blocked_entries += 1
                if _budget_exhausted(loss_mode, loss_total, session_used, session_loss) or risk_cap <= 0:
                    result.cutoff_hit = True
            else:
                opened = _try_open(
                    result, bar, stop, session, symbol, step, min_notional, cash,
                    commission_rate, slippage_rate, risk_cap, size_by_risk, i,
                )
                if opened is None:
                    result.blocked_entries += 1
                else:
                    pos, cash = opened
                    pending = 1
                    if size_by_risk and bar.open <= (stop or 0):
                        _close(result, pos, bar.open, bar.time, "gap_stop", session, symbol,
                               commission_rate, slippage_rate, consume)
                        cash += result.trades[-1]["cash_delta"]
                        pos = None
                        pending = 0
                    elif size_by_risk and stop is not None and bar.low <= stop:
                        _close(result, pos, stop, bar.time, "stop", session, symbol,
                               commission_rate, slippage_rate, consume)
                        cash += result.trades[-1]["cash_delta"]
                        pos = None
                        pending = 0
                    elif size_by_risk and bar.high >= pos.target:
                        _close(result, pos, pos.target, bar.time, "target", session, symbol,
                               commission_rate, slippage_rate, consume)
                        cash += result.trades[-1]["cash_delta"]
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
            "in_position": pos is not None,
        })
    if pos is not None:
        last = bars[-1]
        _close(result, pos, last.close, last.time, "mark_to_close_end", session or "book",
               symbol, commission_rate, slippage_rate, consume)
        cash += result.trades[-1]["cash_delta"]
        result.equity[-1]["equity"] = cash
        result.equity[-1]["cash"] = cash
        result.equity[-1]["in_position"] = False
    result.loss_consumed = loss_total
    return result


def _risk_cap(loss_mode, loss_total, session_used, session_loss, cash_now, month_equity, risk_per_trade) -> float:
    """Largest planned loss still inside the active budget. A gap can exceed it."""
    if loss_mode == "off":
        return risk_per_trade
    if loss_mode == "monthly":
        remaining = session_loss - (month_equity - cash_now)
    elif loss_mode == "two_hour":
        remaining = session_loss - session_used
    else:
        remaining = session_loss - loss_total
    return min(risk_per_trade, max(0.0, remaining))


def _budget_exhausted(loss_mode, loss_total, session_used, session_loss) -> bool:
    if loss_mode == "two_hour":
        return session_used >= session_loss
    if loss_mode == "cumulative":
        return loss_total >= session_loss
    return False


def _blocked(loss_mode, loss_total, session_used, session_loss, cash_now, month_equity, pending, max_positions) -> bool:
    if pending >= max_positions:
        return True
    if loss_mode == "off":
        return False
    if loss_mode == "monthly":
        return cash_now - month_equity <= -session_loss
    if loss_mode == "two_hour":
        return session_used >= session_loss
    return loss_total >= session_loss


def _try_open(result, bar, stop, session, symbol, step, min_notional, cash,
              commission, slip, risk_per_trade, size_by_risk, index):
    entry_fill = bar.open * (1.0 + slip)
    fee_per = entry_fill * commission
    cash_per = entry_fill + fee_per
    if cash_per <= 0:
        return None
    if size_by_risk:
        planned = _adverse_plan(bar.open, stop or 0.0, commission, slip)
        if planned is None:
            return None
        raw_qty = min(risk_per_trade / planned, cash / cash_per)
    else:
        planned = None
        raw_qty = cash / cash_per
    qty = _floor_step(raw_qty, step)
    if size_by_risk:
        while qty > 0 and qty * planned > risk_per_trade + 1e-9:
            qty = _floor_step(qty - step, step)
    notional = qty * bar.open
    if qty <= 0 or qty * cash_per > cash + 1e-9 or notional + 1e-9 < min_notional:
        return None
    fee = qty * fee_per
    cash_out = qty * cash_per
    cash -= cash_out
    target = bar.open + 2.0 * (bar.open - (stop or 0.0)) if size_by_risk else float("inf")
    pos = Position(qty, bar.time, entry_fill, cash_out, stop or 0.0, target, index)
    result.trades.append({
        "symbol": symbol,
        "side": "buy",
        "time": bar.time,
        "price": entry_fill,
        "raw_price": bar.open,
        "qty": qty,
        "notional": notional,
        "fee": fee,
        "slip_cash": qty * (entry_fill - bar.open),
        "spread_cash": 0.0,
        "cash_delta": -cash_out,
        "reason": "enter_next_open",
        "session_id": session,
        "entry_time": bar.time,
        "planned_loss": None if planned is None else qty * planned,
    })
    return pos, cash


def _close(result, pos, raw_price, when, reason, session, symbol, commission, slip, consume):
    fill = raw_price * (1.0 - slip)
    fee = pos.qty * fill * commission
    cash_in = pos.qty * fill - fee
    pnl = cash_in - pos.cash_out
    consume(pnl)
    result.trades.append({
        "symbol": symbol,
        "side": "sell",
        "time": when,
        "price": fill,
        "raw_price": raw_price,
        "qty": pos.qty,
        "notional": pos.qty * raw_price,
        "fee": fee,
        "slip_cash": pos.qty * (raw_price - fill),
        "spread_cash": 0.0,
        "cash_delta": cash_in,
        "reason": reason,
        "session_id": session,
        "entry_time": pos.entry_time,
        "pnl": pnl,
    })
