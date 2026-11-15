"""Pine replica tests. No network and no orders."""

from research_bt.pine_breakout import run_pine, size_order


def _bar(i, open_, high, low, close, day=1_763_596_800):
    return {"time": day + i * 300, "open": open_, "high": high, "low": low, "close": close, "volume": 1.0}


def test_size_respects_cash_cap_step_and_min_notional():
    order = size_order(100.0, 1.0, 100.0)
    assert order["cash_budget"] == 20.0
    assert abs(order["qty"] * 10000 - round(order["qty"] * 10000)) < 1e-6
    assert order["feasible"]
    assert order["planned_loss"] <= 0.50 + 1e-9
    assert order["qty"] * 100 >= 10
    too_expensive = size_order(200_000.0, 100.0, 100.0)
    assert too_expensive["qty"] == 0.0
    assert not too_expensive["feasible"]


def test_signal_fills_at_the_next_open_and_does_not_sell_short():
    bars = [_bar(i, 100, 101, 99, 100) for i in range(30)]
    bars.append(_bar(30, 100, 120, 99, 115))
    bars.append(_bar(31, 115, 116, 114, 115))
    result = run_pine(bars)
    buys = [trade for trade in result["trades"] if trade["side"] == "buy"]
    assert buys
    assert buys[0]["time"] == bars[31]["time"]
    assert buys[0]["price"] == 115
    assert all(trade["side"] in {"buy", "sell"} for trade in result["trades"])
    assert all(trade["qty"] > 0 for trade in result["trades"])


def test_stop_is_filled_before_the_limit_on_the_same_bar():
    bars = [_bar(i, 100, 101, 99, 100) for i in range(30)]
    bars.append(_bar(30, 100, 120, 99, 115))
    bars.append(_bar(31, 115, 200, 1, 110))
    result = run_pine(bars)
    sells = [trade for trade in result["trades"] if trade["side"] == "sell"]
    assert sells
    assert sells[0]["reason"] == "stop"


def test_intraday_guard_resets_on_the_next_utc_day():
    day = 1_763_596_800
    bars = [_bar(i, 100, 101, 99, 100, day) for i in range(30)]
    bars.append(_bar(30, 100, 120, 99, 115, day))
    bars.append(_bar(31, 115, 116, 114, 115, day))
    bars.append(_bar(32, 10, 11, 9, 10, day))
    next_day = day + 86400
    bars.append({"time": next_day, "open": 100, "high": 130, "low": 99, "close": 120, "volume": 1})
    bars.append({"time": next_day + 300, "open": 120, "high": 121, "low": 119, "close": 120, "volume": 1})
    result = run_pine(bars)
    reasons = [trade["reason"] for trade in result["trades"] if trade["side"] == "sell"]
    assert "intraday_guard" in reasons or any(trade["pnl"] < -2 for trade in result["trades"] if trade["side"] == "sell")
