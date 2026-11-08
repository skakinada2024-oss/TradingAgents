"""Fake-client checks. No MetaTrader terminal is installed on this VM."""

from datetime import UTC, datetime, timedelta

import pytest

from tradingagents.mt5_preflight import (
    ACCOUNT_TRADE_MODE_CONTEST,
    ACCOUNT_TRADE_MODE_DEMO,
    ACCOUNT_TRADE_MODE_REAL,
    SYMBOL_TRADE_MODE_CLOSEONLY,
    SYMBOL_TRADE_MODE_FULL,
    attach_and_read,
    evaluate,
    main,
    public_view,
)

NOW = datetime(2026, 11, 8, 5, 32, tzinfo=UTC)


class Fake:
    def __init__(self, account, terminal, symbol, tick, positions=0, accounts=None):
        self.accounts = list(accounts or [account, account])
        self.reads = 0
        self.terminal = terminal
        self.symbol = symbol
        self.tick = tick
        self.positions = positions
        self.calls = []

    def account_info(self):
        self.calls.append("account_info")
        item = self.accounts[min(self.reads, len(self.accounts) - 1)]
        self.reads += 1
        return item

    def terminal_info(self):
        self.calls.append("terminal_info")
        return self.terminal

    def symbol_info(self, name):
        self.calls.append("symbol_info")
        return None if self.symbol is None else {**self.symbol, "name": name}

    def symbol_info_tick(self, name):
        self.calls.append("symbol_info_tick")
        return self.tick

    def positions_total(self):
        self.calls.append("positions_total")
        return self.positions


def _account(**kwargs):
    base = {
        "login": 111,
        "server": "Demo-Server",
        "name": "Example",
        "company": "Example Co",
        "trade_mode": ACCOUNT_TRADE_MODE_DEMO,
        "currency": "USD",
        "leverage": 1,
        "balance": "100",
        "equity": "100",
        "trade_allowed": True,
    }
    base.update(kwargs)
    return base


def _terminal(**kwargs):
    base = {
        "connected": True,
        "trade_allowed": True,
        "tradeapi_disabled": False,
        "name": "MetaTrader 5",
        "build": 5000,
        "path": r"C:\Users\secret\terminal64.exe",
        "company": "MetaQuotes Software Corp.",
    }
    base.update(kwargs)
    return base


def _symbol(**kwargs):
    base = {
        "trade_mode": SYMBOL_TRADE_MODE_FULL,
        "volume_min": "0.01",
        "trade_contract_size": "100000",
        "currency_profit": "USD",
        "ask": "1.10",
    }
    base.update(kwargs)
    return base


def _tick(age_seconds=1, ask="1.10"):
    return {"time": int((NOW - timedelta(seconds=age_seconds)).timestamp()), "bid": "1.09", "ask": ask}


def _report(fake, symbol="EURUSD"):
    return evaluate(fake, symbol, NOW, source="fake_client")


def test_defaults_stay_disabled_and_private_fields_drop():
    report = _report(Fake(_account(), _terminal(), _symbol(volume_min="1", trade_contract_size="1", ask="10"), _tick(ask="10")))
    assert report["source"] == "fake_client"
    assert report["eligible"] is True
    assert report["execution_enabled"] is False
    assert report["limits"]["equity_loss_cutoff_usd"] == "5"
    assert report["limits"]["max_positions"] == 1
    assert report["limits"]["max_elapsed_seconds"] == 12 * 60 * 60
    assert report["limits"]["send_order"] is False
    assert report["login_present"] is True
    assert report["server_present"] is True
    text = str(public_view(report))
    assert "111" not in text
    assert "Demo-Server" not in text
    assert "secret" not in text
    assert "Example Co" not in text


def test_real_contest_and_unknown_modes_fail():
    for mode, needle in (
        (ACCOUNT_TRADE_MODE_REAL, "real"),
        (ACCOUNT_TRADE_MODE_CONTEST, "contest"),
        (9, "not demo"),
    ):
        report = _report(Fake(_account(trade_mode=mode), _terminal(), _symbol(), _tick()))
        assert report["eligible"] is False
        assert any(needle in reason for reason in report["reasons"])


def test_missing_account_and_account_switch_fail():
    missing = _report(Fake(None, _terminal(), _symbol(), _tick(), accounts=[None, None]))
    assert any("account_info is missing" in reason for reason in missing["reasons"])
    switched = Fake(
        _account(),
        _terminal(),
        _symbol(),
        _tick(),
        accounts=[_account(login=111), _account(login=222)],
    )
    report = _report(switched)
    assert any("account identity changed" in reason for reason in report["reasons"])
    assert "222" not in str(report)


def test_disconnected_stale_and_closed_quotes_fail():
    down = _report(Fake(_account(), _terminal(connected=False), _symbol(), _tick()))
    assert any("not connected" in reason for reason in down["reasons"])
    stale = _report(Fake(_account(leverage=1), _terminal(), _symbol(volume_min="1", trade_contract_size="1"), _tick(age_seconds=45, ask="10")))
    assert any("stale" in reason for reason in stale["reasons"])
    closed = _report(Fake(_account(), _terminal(), _symbol(trade_mode=SYMBOL_TRADE_MODE_CLOSEONLY), _tick(age_seconds=1)))
    assert any("close-only" in reason for reason in closed["reasons"])
    weekend = _report(Fake(_account(), _terminal(), _symbol(), _tick(age_seconds=3 * 60 * 60)))
    assert any("not from an open session" in reason for reason in weekend["reasons"])


def test_missing_symbol_and_min_lot_gross_are_refused():
    missing = _report(Fake(_account(), _terminal(), None, None))
    assert any("symbol_info is missing" in reason for reason in missing["reasons"])
    fx = _report(Fake(_account(balance="100", equity="100", leverage=100), _terminal(), _symbol(), _tick()))
    assert fx["eligible"] is False
    assert fx["account_leverage"] == 100
    assert fx["min_lot_gross_usd"] == "1100.00"
    assert not any("leverage is not 1" in reason for reason in fx["reasons"])
    assert any("10 percent" in reason for reason in fx["reasons"])
    large = _report(Fake(
        _account(balance="100000", equity="100000", leverage=100),
        _terminal(),
        _symbol(),
        _tick(ask="1.11416"),
    ))
    assert large["eligible"] is True
    assert large["min_lot_gross_usd"] == "1114.16"
    assert large["account_leverage"] == 100
    jpy = _report(Fake(
        _account(balance="100000", equity="100000", leverage=100),
        _terminal(),
        _symbol(currency_profit="JPY"),
        _tick(ask="1.11416"),
    ))
    assert jpy["eligible"] is False
    assert any("no conversion" in reason for reason in jpy["reasons"])


def test_linux_launcher_does_not_attach(monkeypatch):
    monkeypatch.setattr("tradingagents.mt5_preflight.sys.platform", "linux")
    with pytest.raises(Exception) as caught:
        attach_and_read("EURUSD", None, NOW)
    assert "not Windows" in str(caught.value)
    assert main(["--symbol", "EURUSD", "--live"]) == 2
    assert main(["--symbol", "EURUSD"]) == 2


def test_module_does_not_send_or_log_in():
    from pathlib import Path
    text = Path("tradingagents/mt5_preflight.py").read_text(encoding="utf-8")
    assert "order_send" not in text
    assert ".login(" not in text
