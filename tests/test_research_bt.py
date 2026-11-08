"""Engine tests. No network and no orders."""

from research_bt.engine import Bar, run_backtest
from research_bt.indicators import ema
from research_bt.strategies import build


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
        symbol="BTC-USD", step=1, min_notional=1, cost_rate=0, allocation=0.10,
    )
    assert result.trades == []
    assert result.blocked_entries == 1


def test_cost_is_applied_once_per_side():
    bars = [_bar(0, 100, 100, 100, 100), _bar(1, 100, 101, 99, 100), _bar(2, 110, 111, 109, 110)]
    result = run_backtest(
        bars, ["enter", "exit", "hold"], [50, None, None],
        symbol="BTC-USD", step=0.0001, min_notional=0, cost_rate=0.01,
    )
    buy, sell = result.trades
    assert buy["price"] == 100 * 1.01
    assert sell["reason"] == "exit_next_open"
    assert sell["price"] == 110 * 0.99
    assert buy["cost"] == buy["notional"] * 0.01
    assert sell["cost"] == sell["notional"] * 0.01


def test_session_loss_blocks_a_new_entry_and_records_the_reset():
    base = 1_704_067_200
    bars = [
        Bar(base, 100, 100, 100, 100, 1),
        Bar(base + 86400, 100, 101, 90, 90, 1),
        Bar(base + 2 * 86400, 100, 101, 99, 100, 1),
        Bar(base + 3 * 86400, 100, 101, 99, 100, 1),
    ]
    result = run_backtest(
        bars, ["enter", "hold", "enter", "hold"], [95, None, 95, None],
        symbol="BTC-USD", step=0.0001, min_notional=1, cost_rate=0,
        risk_per_trade=50, allocation=1,
    )
    assert result.session_resets == ["2024-01"]
    assert result.blocked_entries >= 1
    assert len([trade for trade in result.trades if trade["side"] == "buy"]) == 1


def test_cash_does_not_go_negative():
    bars = [_bar(0, 40, 40, 40, 40), _bar(1, 40, 41, 39, 40)]
    result = run_backtest(
        bars, ["enter", "hold"], [20, None],
        symbol="BTC-USD", step=0.00000001, min_notional=0, cost_rate=0.001, allocation=1,
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


def test_buy_and_hold_uses_the_cash_allocation():
    bars = [_bar(0, 20, 20, 20, 20), _bar(1, 20, 21, 19, 22), _bar(2, 22, 23, 21, 24)]
    result = run_backtest(
        bars, ["enter", "hold", "hold"], [None, None, None],
        symbol="BTC-USD", step=0.0001, min_notional=1, cost_rate=0,
        size_by_risk=False, allocation=0.10,
    )
    buys = [trade for trade in result.trades if trade["side"] == "buy"]
    assert buys[0]["qty"] == 0.5
    assert result.trades[-1]["reason"] == "mark_to_close_end"


def test_split_boundaries_do_not_overlap():
    from research_bt.run_research import _split
    bars = [_bar(i, 1, 1, 1, 1) for i in range(100)]
    parts = _split(bars)
    assert parts["train"][-1].time < parts["validation"][0].time
    assert parts["validation"][-1].time < parts["unseen"][0].time
    assert len(parts["train"]) + len(parts["validation"]) + len(parts["unseen"]) == 100
