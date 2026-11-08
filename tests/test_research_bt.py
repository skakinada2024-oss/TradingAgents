"""Engine tests. No network and no orders."""

import pytest

from research_bt.engine import Bar, run_backtest
from research_bt.indicators import ema
from research_bt.strategies import build, build_intraday_vwap


def _bar(i, open_, high, low, close):
    return Bar(1_700_000_000 + i * 86400, open_, high, low, close, 10.0)


def test_entry_uses_the_next_bar_not_the_signal_bar():
    bars = [_bar(i, 100, 101, 99, 100) for i in range(4)]
    signals = ["enter", "hold", "hold", "hold"]
    stops = [90, None, None, None]
    result = run_backtest(
        bars, signals, stops, symbol="BTC-USD", step=0.0001, min_notional=1, cost_rate=0
    )
    buys = [trade for trade in result.trades if trade["side"] == "buy"]
    assert len(buys) == 1
    assert buys[0]["time"] == bars[1].time


def test_signal_on_the_final_bar_does_not_fill():
    bars = [_bar(i, 100, 101, 99, 100) for i in range(3)]
    signals = ["hold", "hold", "enter"]
    result = run_backtest(
        bars, signals, [None, None, 90], symbol="BTC-USD", step=0.0001, min_notional=1, cost_rate=0
    )
    assert result.trades == []


def test_gap_through_stop_fills_at_the_open():
    bars = [
        _bar(0, 100, 100, 100, 100),
        _bar(1, 100, 101, 99, 100),
        _bar(2, 90, 91, 89, 90),
    ]
    result = run_backtest(
        bars, ["enter", "hold", "hold"], [95, None, None],
        symbol="BTC-USD", step=0.0001, min_notional=1, cost_rate=0,
    )
    sells = [trade for trade in result.trades if trade["side"] == "sell"]
    assert sells[0]["reason"] == "gap_stop"
    assert sells[0]["price"] == 90


def test_stop_wins_when_stop_and_target_are_both_touched():
    bars = [
        _bar(0, 100, 100, 100, 100),
        _bar(1, 100, 130, 90, 110),
    ]
    result = run_backtest(
        bars, ["enter", "hold"], [95, None],
        symbol="BTC-USD", step=0.0001, min_notional=1, cost_rate=0,
    )
    sells = [trade for trade in result.trades if trade["side"] == "sell"]
    assert sells[0]["reason"] == "stop"
    assert sells[0]["price"] == 95


def test_quantity_floors_and_refuses_an_unsupported_step():
    bars = [_bar(0, 50, 50, 50, 50), _bar(1, 50, 51, 49, 50)]
    result = run_backtest(
        bars, ["enter", "hold"], [40, None],
        symbol="BTC-USD", step=1, min_notional=1,
    )
    assert result.trades == []
    assert result.blocked_entries == 1


def test_fee_and_slip_are_separate_and_spread_is_not_added():
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 101, 99, 100), _bar(2, 110, 111, 109, 110)]
    result = run_backtest(
        bars, ["enter", "exit", "hold"], [50, None, None],
        symbol="BTC-USD", step=0.0001, min_notional=0,
        commission_rate=0.006, slippage_rate=0.0005,
    )
    buy, sell = result.trades
    assert buy["price"] == 100 * 1.0005
    assert buy["fee"] == buy["qty"] * buy["price"] * 0.006
    assert buy["spread_cash"] == 0.0
    assert sell["reason"] == "exit_next_open"
    assert sell["price"] == 110 * 0.9995
    assert sell["spread_cash"] == 0.0
    try:
        run_backtest(
            bars, ["enter", "hold", "hold"], [50, None, None],
            symbol="BTC-USD", step=0.0001, min_notional=0, spread_rate=0.001,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("spread must not be added on top of slippage")


def test_planned_risk_uses_the_stop_not_a_future_close():
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 100, 100, 1000)]
    result = run_backtest(
        bars, ["enter", "hold"], [90, None],
        symbol="BTC-USD", step=0.0001, min_notional=0,
    )
    buy = result.trades[0]
    assert buy["planned_loss"] <= 0.50 + 1e-9
    assert buy["qty"] * 10 <= 0.50 + 1e-6


def test_cumulative_loss_is_not_restored_by_a_profit():
    bars = [
        _bar(0, 100, 100, 100, 100),
        _bar(1, 100, 101, 90, 100),
        _bar(2, 100, 101, 99, 100),
        _bar(3, 100, 140, 95, 130),
        _bar(4, 130, 131, 129, 130),
    ]
    result = run_backtest(
        bars, ["enter", "hold", "enter", "hold", "hold"], [95, None, 90, None, None],
        symbol="BTC-USD", step=0.0001, min_notional=0, loss_mode="cumulative",
    )
    first_loss = next(trade["pnl"] for trade in result.trades if trade["side"] == "sell")
    assert first_loss < 0
    assert abs(result.loss_consumed - (-first_loss)) < 1e-9
    assert any(trade["pnl"] > 0 for trade in result.trades if trade["side"] == "sell")


def test_the_next_trade_is_sized_to_the_budget_that_remains():
    bars = [
        _bar(0, 100, 100, 100, 100),
        _bar(1, 100, 101, 99, 100),
        _bar(2, 83, 84, 82, 83),
        _bar(3, 100, 101, 99, 100),
    ]
    result = run_backtest(
        bars, ["enter", "hold", "enter", "hold"], [95, None, 90, None],
        symbol="BTC-USD", step=0.0001, min_notional=0,
    )
    buys = [trade for trade in result.trades if trade["side"] == "buy"]
    assert buys[0]["planned_loss"] <= 0.50 + 1e-9
    assert buys[1]["planned_loss"] <= 0.30 + 1e-6


def test_a_gap_can_exceed_the_two_dollar_budget_and_then_block():
    bars = [
        _bar(0, 100, 100, 100, 100),
        _bar(1, 100, 101, 99, 100),
        _bar(2, 50, 51, 49, 50),
        _bar(3, 100, 101, 99, 100),
    ]
    result = run_backtest(
        bars, ["enter", "hold", "enter", "hold"], [95, None, 90, None],
        symbol="BTC-USD", step=0.0001, min_notional=0,
    )
    sells = [trade for trade in result.trades if trade["side"] == "sell"]
    assert sells[0]["reason"] == "gap_stop"
    assert sells[0]["pnl"] < -2
    assert result.cutoff_hit
    assert len([trade for trade in result.trades if trade["side"] == "buy"]) == 1


def test_monthly_reset_is_separate_from_the_cumulative_budget():
    base = 1_704_067_200
    later = base + 32 * 86400
    bars = [
        Bar(base, 100, 100, 100, 100, 1),
        Bar(base + 86400, 100, 101, 99, 100, 1),
        Bar(base + 2 * 86400, 50, 51, 49, 50, 1),
        Bar(later, 100, 101, 99, 100, 1),
        Bar(later + 86400, 100, 101, 99, 100, 1),
    ]
    signals = ["enter", "hold", "enter", "hold", "hold"]
    stops = [95, None, 90, None, None]
    monthly = run_backtest(
        bars, signals, stops, symbol="BTC-USD", step=0.0001, min_notional=0, loss_mode="monthly",
    )
    cumulative = run_backtest(
        bars, signals, stops, symbol="BTC-USD", step=0.0001, min_notional=0, loss_mode="cumulative",
    )
    assert len(monthly.session_resets) == 2
    assert len([trade for trade in monthly.trades if trade["side"] == "buy"]) == 2
    assert len([trade for trade in cumulative.trades if trade["side"] == "buy"]) == 1


def test_boundary_signal_fills_at_the_next_open_and_ignores_that_bar():
    bars = [_bar(0, 123, 130, 90, 1)]
    result = run_backtest(
        bars, ["hold"], [None], symbol="BTC-USD", step=0.0001, min_notional=0,
        prior_signal="enter", prior_stop=90,
    )
    assert result.trades[0]["price"] == 123
    assert result.trades[0]["time"] == bars[0].time


def test_cash_does_not_go_negative():
    bars = [_bar(0, 40, 40, 40, 40), _bar(1, 40, 41, 39, 40)]
    result = run_backtest(
        bars, ["enter", "hold"], [20, None],
        symbol="BTC-USD", step=0.00000001, min_notional=0, commission_rate=0.001,
        risk_per_trade=1000,
    )
    assert result.equity[-1]["cash"] >= -1e-8
    assert all(point["equity"] >= -1e-8 for point in result.equity)


def test_family_signal_matches_a_prefix_only_rebuild():
    bars = [{"time": 1_700_000_000 + i * 86400, "open": 100+i, "high": 102+i,
             "low": 99+i, "close": 100+i*0.5, "volume": 5} for i in range(80)]
    full, _stops = build("ema_cross", bars)
    prefix, _stops = build("ema_cross", bars[:40])
    assert full[39] == prefix[39]


def test_ema_prefix_matches_the_full_series():
    values = [float(i) for i in range(30)]
    assert ema(values, 5)[:10] == ema(values[:10], 5)


def test_unconstrained_buy_and_hold_uses_the_full_cash():
    bars = [_bar(0, 20, 20, 20, 20), _bar(1, 20, 21, 19, 22), _bar(2, 22, 23, 21, 24)]
    result = run_backtest(
        bars, ["enter", "hold", "hold"], [None, None, None],
        symbol="BTC-USD", step=0.0001, min_notional=1,
        size_by_risk=False, loss_mode="off",
    )
    buys = [trade for trade in result.trades if trade["side"] == "buy"]
    assert buys[0]["qty"] == 5
    assert result.trades[-1]["reason"] == "mark_to_close_end"


def test_split_names_do_not_call_the_inspected_slice_unseen():
    from research_bt.rerun import _parts
    bars = [_bar(i, 1, 1, 1, 1) for i in range(100)]
    parts = _parts(bars)
    names = [name for name, _part, _status in parts]
    assert "unseen" not in names
    assert "inspected_holdout" in names
    train = next(part for name, part, _status in parts if name == "train")
    holdout = next(part for name, part, _status in parts if name == "inspected_holdout")
    assert train[-1].time < holdout[0].time


def test_daily_vwap_proxy_is_rejected_and_intraday_ignores_later_bars():
    day = 1_704_067_200
    one = [{"time": day, "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 5}]
    with pytest.raises(ValueError):
        build("vwap_pullback", one)
    signals, _stops = build_intraday_vwap(one)
    assert signals == ["hold"]
    bars = []
    for i in range(6):
        bars.append({
            "time": day + i * 900, "open": 100, "high": 101, "low": 99, "close": 100.5, "volume": 10,
        })
    bars[4]["low"] = 90
    bars[4]["close"] = 100.2
    signals, _stops = build_intraday_vwap(bars)
    extended = [*bars, {
        "time": day + 6 * 900, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 100000,
    }]
    later, _stops = build_intraday_vwap(extended)
    assert signals[4] == later[4]


def test_whole_share_rejection_is_cash_or_risk_not_a_ten_percent_cap():
    from research_bt.stocks import whole_share_check
    expensive = whole_share_check(250, 240, 0.006, 0.0005)
    assert expensive["cash_rejects_one_share"]
    assert expensive["risk_rejects_one_share"]
    assert expensive["allocation_cap_used"] is False
    affordable = whole_share_check(40, 20, 0.0, 0.0)
    assert affordable["cash_rejects_one_share"] is False
    assert affordable["risk_rejects_one_share"] is True
