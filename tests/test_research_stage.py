"""Stage 1 safety: mock xAI wiring, no live call, no order, isolated memory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tradingagents.research_stage as stage
from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS


@pytest.fixture
def models(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_LLM", "grok-4.6")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "grok-4.6")
    monkeypatch.delenv("TRADINGAGENTS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)


def test_missing_model_env_is_refused(monkeypatch):
    monkeypatch.delenv("TRADINGAGENTS_QUICK_THINK_LLM", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_DEEP_THINK_LLM", raising=False)
    with pytest.raises(SystemExit) as caught:
        stage._require_model_env()
    assert "TRADINGAGENTS_QUICK_THINK_LLM" in str(caught.value)


def test_non_xai_provider_is_refused(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_QUICK_THINK_LLM", "grok-4.6")
    monkeypatch.setenv("TRADINGAGENTS_DEEP_THINK_LLM", "grok-4.6")
    monkeypatch.setenv("TRADINGAGENTS_LLM_PROVIDER", "openai")
    with pytest.raises(SystemExit):
        stage._require_model_env()


def test_config_uses_registry_provider_and_isolates_paths(models, tmp_path):
    config = stage.build_research_config(tmp_path)
    assert config["llm_provider"] == "xai"
    assert config["backend_url"] is None
    assert config["quick_think_llm"] == "grok-4.6"
    assert config["deep_think_llm"] == "grok-4.6"
    assert config["checkpoint_enabled"] is False
    assert config["llm_max_retries"] == 0
    assert config["max_tokens"] <= stage.STAGE_MAX_TOKENS
    assert str(tmp_path) in config["memory_log_path"]
    assert ".tradingagents" not in config["memory_log_path"]
    contract = stage.real_xai_contract(config)
    assert contract["base_url"] == OPENAI_COMPATIBLE_PROVIDERS["xai"].base_url
    assert contract["use_responses_api"] is False
    assert contract["api_key_env"] == "XAI_API_KEY"
    assert contract["paid_inference"] == "not_performed"


def test_retry_and_token_env_are_capped(models, monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGAGENTS_LLM_MAX_RETRIES", "6")
    monkeypatch.setenv("TRADINGAGENTS_MAX_TOKENS", "8192")
    config = stage.build_research_config(tmp_path)
    assert config["llm_max_retries"] == stage.STAGE_MAX_RETRIES
    assert config["max_tokens"] == stage.STAGE_MAX_TOKENS
    assert config["_stage_bounds"]["llm_max_retries_requested"] == 6
    assert config["_stage_bounds"]["max_tokens_requested"] == 8192


def test_live_flag_is_refused():
    with pytest.raises(stage.LiveInferenceRefused):
        stage.main(["--output", "/tmp/unused", "--live"])


def test_gate_ignores_bullish_prose():
    gate = stage.deterministic_gate("Buy")
    assert gate["execution_permitted"] is False
    assert gate["sizing"] == "not_computed"
    assert gate["llm_prose_is_executable_gate"] is False


def test_execution_surface_has_no_broker_module():
    surface = stage.execution_surface()
    assert surface["order_submission"] == "absent"
    assert surface["matching_modules"] == []


@pytest.mark.unit
def test_mock_graph_runs_with_no_api_key(models, monkeypatch, tmp_path):
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    audit = stage.run_stage(tmp_path / "nokey")
    assert audit["real_xai_invoked"] is False
    assert audit["api_key_present_in_environment"] is False
    assert audit["deterministic_gate"]["execution_permitted"] is False
    assert stage.MOCK_PLACEHOLDER not in (tmp_path / "nokey" / "audit.json").read_text(encoding="utf-8")


@pytest.mark.unit
def test_mock_graph_does_not_call_xai_or_submit(models, monkeypatch, tmp_path):
    planted = "super-secret-test-value-do-not-persist"
    monkeypatch.setenv("XAI_API_KEY", planted)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)

    bullish = (
        "**Rating**: Buy\n\n"
        "MOCK INTEGRATION. Buy prose must not become an order.\n\n"
        "FINAL TRANSACTION PROPOSAL: **BUY**"
    )
    audit = stage.run_stage(tmp_path / "run", decision_text=bullish)

    assert audit["mode"] == "mock_integration"
    assert audit["real_xai_invoked"] is False
    assert audit["output_is_mock"] is True
    assert audit["pinned_upstream_sha"] == stage.PINNED_UPSTREAM_SHA
    assert audit["deterministic_gate"]["execution_permitted"] is False
    assert audit["outputs"]["signal"] == "Buy"
    assert audit["network"]["llm_calls"] >= 1
    assert audit["network"]["llm_calls"] <= stage.STAGE_MAX_LLM_CALLS
    assert audit["network"]["blocked_attempts"]
    assert all(item["address"].startswith("('api.x.ai'") or "api.x.ai" in item["address"]
               for item in audit["network"]["blocked_attempts"])
    assert audit["network"]["mock_urls"]
    assert all(url.startswith("https://api.x.ai/v1/chat/completions") for url in audit["network"]["mock_urls"])
    assert audit["memory"]["home_memory_unchanged"] is True
    assert not (home / ".tradingagents" / "memory" / "trading_memory.md").exists()
    blob = (tmp_path / "run" / "audit.json").read_text(encoding="utf-8")
    memory = Path(audit["outputs"]["memory_log_path"]).read_text(encoding="utf-8")
    assert planted not in blob
    assert planted not in memory
    assert stage.MOCK_PLACEHOLDER not in blob
    assert "MOCK INTEGRATION" in blob
    assert audit["execution_surface"]["order_submission"] == "absent"
    assert audit["dependency_manifest"]["langchain-openai"] != "not-installed"
    saved = json.loads(blob)
    assert saved["api_key_persisted"] is False
