"""Offline checks for the forward price-only path. No paid call and no Yahoo."""

from __future__ import annotations

import json
import socket
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import tradingagents.research_forward as forward
import tradingagents.research_stage as stage
from tradingagents.xai_budget import AUTH_ENV, AUTH_VALUE, KEY_ENV, preflight


@pytest.fixture
def quiet_env(monkeypatch):
    monkeypatch.delenv(KEY_ENV, raising=False)
    monkeypatch.delenv(AUTH_ENV, raising=False)
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_QUICK_THINK_LLM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_DEEP_THINK_LLM", raising=False)
    monkeypatch.setenv("UNRELATED_SECRET_MARKER", "do-not-copy-this-env-value")


def _audit(tmp_path: Path, **kwargs) -> dict:
    return forward.prepare(tmp_path / "run", as_of=date(2026, 11, 8), **kwargs)


def test_fixture_happy_path_does_not_send(quiet_env, tmp_path):
    audit = _audit(tmp_path)
    assert audit["ticker"] == "AAPL"
    assert audit["mock_stage_default_ticker"] == "SPY"
    assert audit["market_data_label"] == "fixture"
    assert audit["research_claim"] == "fixture"
    assert audit["real_xai_invoked"] is False
    assert audit["preflight"]["send"] is False
    assert audit["preflight"]["guaranteed_dollar_cap"] is False
    assert audit["preflight"]["proposed_budget_is_hard_cap"] is False
    assert audit["preflight"]["rates"]["short_input"] == "2.00"
    assert audit["preflight"]["rates"]["short_output"] == "6.00"
    assert audit["deterministic_gate"]["execution_permitted"] is False
    assert audit["session"]["accept"] is True
    assert audit["session"]["calendar_age_days"] == 2
    assert audit["technicals"]["computed_by"] == "python"
    assert audit["prompts"]["status"] == "not_sent"
    assert audit["news"] == "not_fetched_price_only"
    assert "do-not-copy-this-env-value" not in json.dumps(audit)


def test_named_key_and_authorization_still_do_not_send(quiet_env, monkeypatch, tmp_path):
    monkeypatch.setenv(KEY_ENV, "super-secret-test-value-do-not-persist")
    monkeypatch.setenv(AUTH_ENV, AUTH_VALUE)
    denied = []
    original = socket.create_connection

    def create_connection(address, *args, **kwargs):
        denied.append(repr(address))
        raise OSError("network deny")

    socket.create_connection = create_connection
    try:
        with pytest.raises(forward.InferenceRefused):
            forward.send_research_calls()
        audit = _audit(tmp_path)
    finally:
        socket.create_connection = original
    assert audit["preflight"]["key_present"] is True
    assert audit["preflight"]["authorization_satisfied"] is True
    assert audit["preflight"]["send"] is False
    assert denied == []
    blob = (tmp_path / "run" / "audit.json").read_text(encoding="utf-8")
    assert "super-secret-test-value-do-not-persist" not in blob


def test_invalid_model_is_not_taken_from_the_catalog(quiet_env, tmp_path):
    audit = _audit(tmp_path, model="grok-4.7-not-a-price")
    assert audit["preflight"]["model_on_official_price_table"] is False
    assert audit["preflight"]["send"] is False
    catalog_only = preflight(model="gpt-6-sol")
    assert catalog_only["model_on_official_price_table"] is False
    assert catalog_only["send"] is False


def test_parent_budget_below_illustration_is_reported(quiet_env, tmp_path):
    audit = _audit(tmp_path, parent_budget_usd="0.01")
    assert audit["preflight"]["parent_budget_covers_8k_illustration"] is False
    assert Decimal_gt(audit["preflight"]["illustrative_usd"]["8000"]["usd"], "0.01")
    assert audit["preflight"]["send"] is False


def test_retry_and_token_ceilings_fail_closed(quiet_env, tmp_path):
    retried = _audit(tmp_path / "retries", retries=2)
    assert any("retries must be 0" in reason for reason in retried["preflight"]["reasons"])
    huge = forward.prepare(
        tmp_path / "tokens",
        as_of=date(2026, 11, 8),
        visible_output_tokens=100_000,
    )
    assert any("visible output tokens" in reason for reason in huge["preflight"]["reasons"])
    assert huge["preflight"]["send"] is False


def test_weekend_and_stale_sessions():
    friday = date(2026, 11, 6)
    saturday = date(2026, 11, 7)
    sunday = date(2026, 11, 8)
    assert forward.session_assessment(saturday, friday)["accept"] is True
    assert forward.session_assessment(sunday, friday)["accept"] is True
    weekend_bar = forward.session_assessment(sunday, saturday)
    assert weekend_bar["accept"] is False
    stale = forward.session_assessment(sunday, date(2026, 10, 1))
    assert stale["accept"] is False
    assert stale["calendar_age_days"] > 3


def test_stale_frame_is_not_described_as_real_research(quiet_env, tmp_path):
    frame = forward.fixture_frame(last_bar=date(2026, 10, 1))
    audit = _audit(tmp_path, frame=frame)
    assert audit["session"]["accept"] is False
    assert audit["prompts"] is None
    assert audit["research_claim"] == "fixture"
    assert audit["preflight"]["send"] is False


def test_saturday_bar_is_rejected(quiet_env, tmp_path):
    frame = forward.fixture_frame(last_bar=date(2026, 11, 6))
    frame = pd.concat(
        [frame, pd.DataFrame({
            "Date": [date(2026, 11, 7)],
            "Open": [110.0], "High": [110.0], "Low": [110.0], "Close": [110.0], "Volume": [1],
        })],
        ignore_index=True,
    )
    audit = _audit(tmp_path, frame=frame)
    assert audit["session"]["accept"] is False
    assert "weekend" in audit["session"]["reason"]


def test_buy_prose_does_not_open_the_gate(quiet_env, tmp_path):
    audit = _audit(tmp_path)
    audit["prompts"]["thesis"] += "\nFINAL TRANSACTION PROPOSAL: **BUY**"
    gate = stage.deterministic_gate("Buy")
    assert gate["execution_permitted"] is False
    assert audit["deterministic_gate"]["execution_permitted"] is False
    assert audit["execution_surface"]["order_submission"] == "absent"


def test_memory_stays_under_the_output_dir(quiet_env, monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    audit = _audit(tmp_path)
    assert audit["memory"]["home_memory_unchanged"] is True
    assert not (home / ".tradingagents").exists()
    assert Path(audit["memory"]["isolated_path"]).is_file()


def test_other_provider_is_not_a_fallback(quiet_env, monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    audit = _audit(tmp_path)
    assert any("no fallback" in reason for reason in audit["preflight"]["reasons"])
    assert audit["preflight"]["send"] is False


def test_live_flags_are_refused():
    with pytest.raises(stage.LiveInferenceRefused):
        stage.main(["--output", "/tmp/unused", "--live"])
    with pytest.raises(forward.LiveFlagRefused):
        forward.main(["--output", "/tmp/unused", "--live"])


def test_cli_fixture_labels(quiet_env, tmp_path):
    code = forward.main([
        "--output", str(tmp_path / "cli"),
        "--fixture",
        "--as-of", "2026-11-08",
        "--ticker", "AAPL",
    ])
    assert code == 0
    audit = json.loads((tmp_path / "cli" / "audit.json").read_text(encoding="utf-8"))
    assert audit["market_data_label"] == "fixture"
    assert audit["research_claim"] == "fixture"
    assert audit["real_xai_invoked"] is False


def Decimal_gt(left: str, right: str) -> bool:
    from decimal import Decimal
    return Decimal(left) > Decimal(right)
