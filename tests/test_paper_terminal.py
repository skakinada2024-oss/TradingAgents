"""Terminal request handling. Numbers are read back from paper_sim files."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from paper_terminal.server import TerminalError, assert_loopback, dispatch
from tradingagents.paper_sim import run_batch

LOCK = threading.Lock()


def _call(root: Path, method: str, path: str, payload: dict | None = None) -> tuple[int, dict | str]:
    body = b"" if payload is None else json.dumps(payload).encode()
    status, content_type, raw, _name = dispatch(method, path, body, root, LOCK)
    text = raw.decode()
    if "json" in content_type:
        return status, json.loads(text)
    return status, text


def test_loopback_only():
    assert assert_loopback("127.0.0.1") == "127.0.0.1"
    with pytest.raises(TerminalError):
        assert_loopback("0.0.0.0")


def test_page_and_meta_are_labeled_simulation(tmp_path: Path):
    status, page = _call(tmp_path, "GET", "/")
    assert status == 200
    assert "Paper Trading Terminal" in page
    assert "NOT A BROKER" in page
    assert "Grok Bot" not in page
    status, meta = _call(tmp_path, "GET", "/api/meta")
    assert status == 200
    assert meta["execution_permitted"] is False
    assert meta["simulated_execution"] is True
    assert meta["symbol"] == "AAPL"
    assert meta["starting_cash_usd"] == "10000.00"


def test_fixture_run_matches_the_simulator_and_resets(tmp_path: Path):
    direct = run_batch(tmp_path / "direct", books=("fixture_round_trip",))
    status, view = _call(tmp_path, "POST", "/api/runs", {"book": "fixture_round_trip"})
    assert status == 200
    assert view["execution_permitted"] is False
    assert view["simulated_execution"] is True
    assert view["fills"] == direct["books"]["fixture_round_trip"]["fills"] == 2
    assert view["cash"] == direct["books"]["fixture_round_trip"]["cash"]
    assert view["equity"] == direct["books"]["fixture_round_trip"]["equity"]
    assert view["ledger"][0]["signal_source"] == "fixture_not_a_model"
    assert view["stages"][0]["state"] == "disabled"
    assert any(stage["state"] == "synthetic" for stage in view["stages"])
    status, csv_text = _call(tmp_path, "GET", f"/api/runs/{view['id']}/ledger.csv")
    assert status == 200 and "fixture_not_a_model" in csv_text
    status, listed = _call(tmp_path, "GET", "/api/runs")
    assert listed["runs"][0]["id"] == view["id"]
    status, body = _call(tmp_path, "DELETE", f"/api/runs/{view['id']}")
    assert status == 200 and body["reset"] is True
    status, missing = _call(tmp_path, "GET", f"/api/runs/{view['id']}")
    assert status == 404 and missing["error"] == "unknown run"


def test_hold_creates_no_order_and_bad_input_is_refused(tmp_path: Path):
    status, view = _call(tmp_path, "POST", "/api/runs", {"book": "research_hold"})
    assert status == 200
    assert view["orders"] == 0
    assert view["fills"] == 0
    assert view["cash"] == "10000.00"
    assert any(stage["state"] == "mock" for stage in view["stages"])
    assert any(stage["state"] == "no_orders" for stage in view["stages"])
    status, _error = _call(tmp_path, "POST", "/api/runs", {"book": "BTC-USD", "path": "/tmp"})
    assert status == 400
    status, _error = _call(tmp_path, "POST", "/api/runs", {"book": "../etc"})
    assert status == 400
    status, missing = _call(tmp_path, "GET", "/api/runs/not-a-run/ledger.csv")
    assert status == 404
    status, missing = _call(tmp_path, "DELETE", "/api/runs/../../etc")
    assert status == 404


def test_two_runs_stay_isolated(tmp_path: Path):
    _, hold = _call(tmp_path, "POST", "/api/runs", {"book": "research_hold"})
    _, trip = _call(tmp_path, "POST", "/api/runs", {"book": "fixture_round_trip"})
    assert hold["id"] != trip["id"]
    _, again = _call(tmp_path, "GET", f"/api/runs/{hold['id']}")
    assert again["cash"] == "10000.00"
    assert trip["cash"] != hold["cash"]
