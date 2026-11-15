"""Python replica of the owner's Pine v6 script. Not part of the TradingAgents graph.

Rules follow original.pine: confirmed-bar signals, next-bar-open fills, stop and
limit taken from the signal close, and the script's sizing formula. The $2
figure is the script's intraday guard. It resets each UTC day, so a multi-day
loss can exceed $2. That is not the Run 9 cumulative ledger.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal

from research_bt.indicators import atr, ema, rsi_wilder

FEE_RATE = 0.0065
MAX_CASH = 20.0
MAX_RISK = 0.50
MIN_NOTIONAL = 10.0
QTY_STEP = 0.0001
INTRADAY_LOSS = 2.0


def _floor_step(qty: float, step: float) -> float:
    if qty <= 0 or step <= 0:
        return 0.0
    units = (Decimal(str(qty)) / Decimal(str(step))).to_integral_value(ROUND_DOWN)
    return float(units * Decimal(str(step)))


def size_order(close: float, atr_value: float, equity: float) -> dict:
    """Sizing from the signal close. The next bar's open is not used."""
    stop_distance = max(atr_value * 1.2, close * 0.008)
    cash_budget = min(MAX_CASH, equity * 0.20)
    qty_cash = cash_budget / (close * (1.0 + FEE_RATE))
    qty_risk = MAX_RISK / (stop_distance + close * 2.0 * FEE_RATE)
    qty = _floor_step(min(qty_cash, qty_risk), QTY_STEP)
    planned = qty * (stop_distance + 2.0 * FEE_RATE * close)
    feasible = qty > 0 and qty * close + 1e-9 >= MIN_NOTIONAL and planned <= MAX_RISK + 1e-9
    target_distance = 2.0 * stop_distance + 6.0 * FEE_RATE * close
    return {
        "qty": qty if feasible else 0.0,
        "feasible": feasible,
        "stop_distance": stop_distance,
        "target_distance": target_distance,
        "planned_loss": planned,
        "cash_budget": cash_budget,
    }


def _day(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), UTC).strftime("%Y-%m-%d")


def run_pine(bars: list[dict]) -> dict:
    """One long-only book. No shorts, no added size, no same-bar signal fill."""
    closes = [bar["close"] for bar in bars]
    opens = [bar["open"] for bar in bars]
    highs = [bar["high"] for bar in bars]
    lows = [bar["low"] for bar in bars]
    trend = ema(closes, 20)
    rsi = rsi_wilder(closes, 14)
    ranges = atr(highs, lows, closes, 14)
    cash = 100.0
    pos = None
    trades = []
    equity = []
    day = None
    day_start = 100.0
    blocked_guard = 0

    def mark(price: float) -> float:
        if pos is None or pos.get("armed"):
            return cash
        return cash + pos["qty"] * price * (1.0 - FEE_RATE)

    for i, bar in enumerate(bars):
        current = _day(bar["time"])
        if current != day:
            day = current
            day_start = mark(bars[i - 1]["close"]) if i else 100.0
        if pos is not None and i > pos["entry_index"]:
            exit_raw = None
            reason = ""
            if bar["open"] <= pos["stop"]:
                exit_raw, reason = bar["open"], "gap_stop"
            elif bar["low"] <= pos["stop"]:
                exit_raw, reason = pos["stop"], "stop"
            elif bar["high"] >= pos["limit"]:
                exit_raw, reason = pos["limit"], "limit"
            if exit_raw is not None:
                _close(trades, pos, exit_raw, bar["time"], reason)
                cash += trades[-1]["cash_delta"]
                pos = None
        guard = mark(bar["open"]) <= day_start - INTRADAY_LOSS
        signal = _signal(i, closes, opens, highs, trend, rsi)
        if pos is None and signal and not guard and ranges[i] is not None:
            order = size_order(closes[i], ranges[i], cash)
            if i + 1 < len(bars) and order["feasible"]:
                pos = {
                    "armed": True,
                    "qty": order["qty"],
                    "stop": closes[i] - order["stop_distance"],
                    "limit": closes[i] + order["target_distance"],
                    "signal_index": i,
                    "entry_index": i + 1,
                    "signal_time": bar["time"],
                }
            elif not order["feasible"]:
                pass
        elif pos is not None and pos.get("armed") and i == pos["entry_index"]:
            fill = bar["open"]
            fee = pos["qty"] * fill * FEE_RATE
            cash_out = pos["qty"] * fill + fee
            if cash_out <= cash + 1e-9:
                cash -= cash_out
                pos["entry_fill"] = fill
                pos["cash_out"] = cash_out
                pos["entry_time"] = bar["time"]
                pos["armed"] = False
                trades.append({
                    "side": "buy", "time": bar["time"], "price": fill, "qty": pos["qty"],
                    "fee": fee, "cash_delta": -cash_out, "reason": "next_open",
                    "stop": pos["stop"], "limit": pos["limit"],
                })
                if bar["open"] <= pos["stop"]:
                    _close(trades, pos, bar["open"], bar["time"], "gap_stop")
                    cash += trades[-1]["cash_delta"]
                    pos = None
                elif bar["low"] <= pos["stop"]:
                    _close(trades, pos, pos["stop"], bar["time"], "stop")
                    cash += trades[-1]["cash_delta"]
                    pos = None
                elif bar["high"] >= pos["limit"]:
                    _close(trades, pos, pos["limit"], bar["time"], "limit")
                    cash += trades[-1]["cash_delta"]
                    pos = None
            else:
                pos = None
        if pos is not None and not pos.get("armed") and mark(bar["close"]) <= day_start - INTRADAY_LOSS:
            _close(trades, pos, bar["close"], bar["time"], "intraday_guard")
            cash += trades[-1]["cash_delta"]
            pos = None
            blocked_guard += 1
        equity.append({"time": bar["time"], "equity": mark(bar["close"]) if pos is None or not pos.get("armed") else cash, "cash": cash})
    if pos is not None and not pos.get("armed"):
        last = bars[-1]
        _close(trades, pos, last["close"], last["time"], "mark_to_close_end")
        cash += trades[-1]["cash_delta"]
        equity[-1]["equity"] = cash
        equity[-1]["cash"] = cash
    return {"trades": trades, "equity": equity, "cash": cash, "guard_exits": blocked_guard}


def _signal(i, closes, opens, highs, trend, rsi) -> bool:
    breakout = False
    if i >= 12 and trend[i] is not None and rsi[i] is not None:
        prior = max(highs[i - 12:i])
        breakout = closes[i] > prior and closes[i] > trend[i] and rsi[i] > 55
    rebound = False
    if i >= 1 and rsi[i] is not None and rsi[i - 1] is not None:
        rebound = rsi[i - 1] <= 35 < rsi[i] and closes[i] > opens[i] and closes[i] > closes[i - 1]
    return breakout or rebound


def _close(trades, pos, raw, when, reason):
    fee = pos["qty"] * raw * FEE_RATE
    cash_in = pos["qty"] * raw - fee
    trades.append({
        "side": "sell", "time": when, "price": raw, "qty": pos["qty"], "fee": fee,
        "cash_delta": cash_in, "reason": reason, "entry_time": pos.get("entry_time", when),
        "pnl": cash_in - pos.get("cash_out", 0.0),
    })


def summarize_pine(result: dict) -> dict:
    sells = [trade for trade in result["trades"] if trade["side"] == "sell"]
    wins = [trade["pnl"] for trade in sells if trade["pnl"] > 0]
    losses = [trade["pnl"] for trade in sells if trade["pnl"] < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    peak = 100.0
    max_dd = 0.0
    for point in result["equity"]:
        peak = max(peak, point["equity"])
        max_dd = max(max_dd, peak - point["equity"])
    end = result["equity"][-1]["equity"] if result["equity"] else 100.0
    return {
        "trades": len(sells),
        "net_usd": end - 100.0,
        "ending_equity": end,
        "max_dd_usd": max_dd,
        "profit_factor": (gross_win / gross_loss) if gross_loss else None,
        "win_rate": (len(wins) / len(sells)) if sells else None,
        "expectancy": (sum(trade["pnl"] for trade in sells) / len(sells)) if sells else None,
        "gross_profit": gross_win,
        "gross_loss": gross_loss,
    }
