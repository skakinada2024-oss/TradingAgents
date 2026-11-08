"""Linux fakes for the demo agent. No terminal and no orders leave this process."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradingagents.mt5_demo import (
    MAGIC,
    TRADE_RETCODE_DONE,
    TRADE_RETCODE_DONE_PARTIAL,
    TRADE_RETCODE_MARKET_CLOSED,
    acquire_lock,
    cycle,
    deadline_reached,
    floor_volume,
    identity_hash,
    load_started_at,
    main,
    run_session,
    size_entry,
    write_stop,
)
from tradingagents.mt5_model import drop_forming_bar, fit_closed_bars
from tradingagents.mt5_preflight import ALLOCATION_CAP
from tradingagents.paper_sim import MAX_ALLOCATION

NOW = datetime(2026, 11, 8, 5, 54, tzinfo=UTC)


def _bars(count=120, start=1_700_000_000):
    rows = []
    price = 1.10
    for index in range(count):
        price += 0.0001 if index % 2 == 0 else -0.00005
        rows.append({
            "time": start + index * 60,
            "open": price,
            "high": price + 0.0002,
            "low": price - 0.0002,
            "close": price,
        })
    return rows


def test_samples_do_not_use_the_target_bar_or_the_forming_bar():
    raw = _bars(30)
    forming = raw[-1]
    closed = drop_forming_bar(raw)
    assert forming not in closed
    fitted = fit_closed_bars(closed)
    assert fitted["signal"] == "HOLD"
    assert fitted["reason"] == "insufficient_closed_history"
    longer = drop_forming_bar(_bars(200))
    from tradingagents.mt5_model import _samples
    samples = _samples(longer)
    assert samples
    assert all(sample["feature_time"] < sample["target_time"] for sample in samples)
    assert samples[-1]["feature_close"] != longer[-1]["close"] or samples[-1]["feature_time"] != longer[-1]["time"]
    result = fit_closed_bars(longer)
    assert result["feature_times_before_targets"] is True
    assert result["n_train"] >= 40
    assert result["live_feature_time"] == longer[-1]["time"]
    assert result["signal"] in {"HOLD", "LONG"}


def test_volume_floors_and_min_lot_is_not_rounded_up():
    assert floor_volume(Decimal("0.019"), Decimal("0.01"), Decimal("0.01"), Decimal("1")) == Decimal("0.01")
    assert floor_volume(Decimal("0.009"), Decimal("0.01"), Decimal("0.01"), Decimal("1")) is None
    assert ALLOCATION_CAP == MAX_ALLOCATION
    symbol = {
        "currency_profit": "USD", "point": "0.00001", "trade_tick_size": "0.00001",
        "trade_tick_value": "1", "volume_step": "0.01", "volume_min": "0.01",
        "volume_max": "50", "trade_contract_size": "100000", "trade_stops_level": "10",
        "filling_mode": 1,
    }
    tick = {"bid": "1.11400", "ask": "1.11416"}
    sized = size_entry(symbol, tick, Decimal("100000"), Decimal("100000"))
    assert sized["ok"] is True
    assert Decimal(sized["volume"]) == Decimal("0.08")
    assert Decimal(sized["notional"]) <= Decimal("10000")
    assert Decimal(sized["risk_usd"]) <= Decimal("1")
    tiny = size_entry(symbol, tick, Decimal("100"), Decimal("100"))
    assert tiny["ok"] is False
    costly = dict(symbol, trade_tick_value="100")
    refused = size_entry(costly, tick, Decimal("100000"), Decimal("100000"))
    assert refused["ok"] is False
    assert "1 USD" in refused["reason"]
    foreign = size_entry(dict(symbol, currency_profit="JPY"), tick, Decimal("100000"), Decimal("100000"))
    assert foreign["ok"] is False
    assert "no conversion" in foreign["reason"]


class Client:
    def __init__(self, account, rates=None, check=0, send=None, positions=None, orders=None):
        self.account = account
        self.rates = rates if rates is not None else _bars(5)
        self.check = check
        self.send = send or {"retcode": TRADE_RETCODE_DONE, "volume": "0.01", "order": 7}
        self.positions = positions or []
        self.orders = orders or []
        self.sent = []

    def account_info(self):
        return self.account

    def terminal_info(self):
        return {"connected": True, "trade_allowed": True}

    def symbol_info(self, symbol):
        return {
            "trade_mode": 4, "currency_profit": "USD", "point": "0.00001",
            "trade_tick_size": "0.00001", "trade_tick_value": "1",
            "volume_step": "0.01", "volume_min": "0.01", "volume_max": "50",
            "trade_contract_size": "100000", "trade_stops_level": "10", "filling_mode": 1,
        }

    def symbol_info_tick(self, symbol):
        return {"time": int(NOW.timestamp()), "bid": "1.11400", "ask": "1.11416"}

    def positions_get(self, symbol):
        return list(self.positions)

    def orders_get(self, symbol):
        return list(self.orders)

    def copy_rates(self, symbol):
        return self.rates

    def order_check(self, request):
        return {"retcode": self.check}

    def order_send(self, request):
        self.sent.append(request)
        return self.send


def _account(**kwargs):
    base = {
        "login": 555001, "server": "Demo-Server", "trade_mode": 0, "currency": "USD",
        "trade_allowed": True, "balance": "100000", "equity": "100000", "leverage": 100,
    }
    base.update(kwargs)
    return base


def test_dry_run_and_market_closed_do_not_send(tmp_path, monkeypatch):
    monkeypatch.setattr("tradingagents.mt5_demo.train_signal", lambda rates: {"signal": "LONG", "reason": "test"})
    client = Client(_account())
    state = {
        "identity_hash": identity_hash(555001, "Demo-Server"),
        "started_at": NOW,
        "start_equity": Decimal("100000"),
        "owned_ticket": None,
    }
    dry = cycle(client, state, NOW, execute=False)
    assert dry["sent"] is False
    assert dry["detail"] == "dry_run"
    assert client.sent == []
    client.check = TRADE_RETCODE_MARKET_CLOSED
    waiting = cycle(client, state, NOW, execute=True)
    assert waiting["action"] == "WAITING"
    assert client.sent == []


def test_real_account_switch_deadline_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr("tradingagents.mt5_demo.train_signal", lambda rates: {"signal": "HOLD", "reason": "test"})
    real = Client(_account(trade_mode=2))
    events = run_session(real, tmp_path / "real", execute=True, now_fn=lambda: NOW, sleep_fn=lambda _s: None, stop_fn=lambda: False, max_cycles=1)
    assert events[0]["action"] == "STOP"
    assert real.sent == []
    first = Client(_account())
    run_session(first, tmp_path / "pin", execute=False, now_fn=lambda: NOW, sleep_fn=lambda _s: None, stop_fn=lambda: False, max_cycles=1)
    assert "555001" not in (tmp_path / "pin" / "events.log").read_text(encoding="utf-8")
    assert "555001" not in (tmp_path / "pin" / "identity.json").read_text(encoding="utf-8")
    started = NOW - timedelta(seconds=43201)
    (tmp_path / "late").mkdir()
    (tmp_path / "late" / "started_at.txt").write_text(started.isoformat(), encoding="utf-8")
    (tmp_path / "late" / "identity.json").write_text(
        json.dumps({"hash": identity_hash(555001, "Demo-Server"), "changed": False}),
        encoding="utf-8",
    )
    late = Client(_account())
    # lock must be free; run_session writes started_at only if missing, so the old stamp remains
    events = run_session(late, tmp_path / "late", execute=True, now_fn=lambda: NOW, sleep_fn=lambda _s: None, stop_fn=lambda: False, max_cycles=3)
    assert any(event["detail"] == "deadline" or "deadline" in str(event.get("detail")) for event in events)
    assert late.sent == []
    assert deadline_reached(load_started_at(tmp_path / "late" / "started_at.txt", NOW), NOW)


def test_existing_position_partial_fill_and_stop_file(tmp_path, monkeypatch):
    monkeypatch.setattr("tradingagents.mt5_demo.train_signal", lambda rates: {"signal": "LONG", "reason": "test"})
    existing = Client(_account(), positions=[{"ticket": 9, "symbol": "EURUSD", "volume": 0.01, "magic": 1}])
    events = run_session(existing, tmp_path / "exist", execute=True, now_fn=lambda: NOW, sleep_fn=lambda _s: None, stop_fn=lambda: False, max_cycles=1)
    assert "will not be managed" in events[0]["detail"]
    assert existing.sent == []
    partial = Client(_account(), send={"retcode": TRADE_RETCODE_DONE_PARTIAL, "volume": "0.01", "order": 77})
    state = {
        "identity_hash": identity_hash(555001, "Demo-Server"),
        "started_at": NOW, "start_equity": Decimal("100000"), "owned_ticket": None,
    }
    first = cycle(partial, state, NOW, execute=True)
    assert first["detail"] == "partial"
    assert len(partial.sent) == 1
    second = cycle(partial, state, NOW, execute=True)
    assert second["detail"] == "one position is already open"
    assert len(partial.sent) == 1
    write_stop(tmp_path / "halt")
    stopped = run_session(
        Client(_account()), tmp_path / "halt", execute=True,
        now_fn=lambda: NOW, sleep_fn=lambda _s: None, stop_fn=lambda: (tmp_path / "halt" / "STOP").exists(),
        max_cycles=2,
    )
    assert stopped[-1]["action"] == "STOP"
    assert "stop_requested" in stopped[-1]["detail"]


def test_lock_and_linux_commands(tmp_path, monkeypatch):
    assert acquire_lock(tmp_path / "LOCK", 4242, lambda pid: pid == 4242)
    assert acquire_lock(tmp_path / "LOCK", 7, lambda pid: pid == 4242) is False
    monkeypatch.setattr("tradingagents.mt5_demo.sys.platform", "linux")
    assert main(["--execute-demo", "--state-dir", str(tmp_path / "nope")]) == 2
    assert main(["--live"]) == 2
    assert main(["--stop", "--state-dir", str(tmp_path / "stopme")]) == 0
    assert (tmp_path / "stopme" / "STOP").is_file()


def test_pending_order_is_not_replayed(monkeypatch):
    monkeypatch.setattr("tradingagents.mt5_demo.train_signal", lambda rates: {"signal": "LONG", "reason": "test"})
    client = Client(_account(), orders=[{"magic": MAGIC}])
    state = {
        "identity_hash": identity_hash(555001, "Demo-Server"),
        "started_at": NOW, "start_equity": Decimal("100000"), "owned_ticket": None,
    }
    event = cycle(client, state, NOW, execute=True)
    assert event["detail"] == "an order is already working"
    assert client.sent == []
