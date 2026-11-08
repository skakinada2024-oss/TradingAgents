"""Stage 1: one-symbol, research-only run on the real xAI client and graph.

This is a mock integration. It constructs the provider with
``create_tier_client`` / ``OpenAIClient`` and compiles the real LangGraph
workflow, then serves ``/v1/chat/completions`` from an in-process httpx
transport. It does not call api.x.ai, and it does not submit an order.

A real xAI call is a different mode. It would read ``XAI_API_KEY`` and use
the registry endpoint ``OPENAI_COMPATIBLE_PROVIDERS["xai"].base_url``
(``https://api.x.ai/v1``) with Chat Completions, because that provider's
``use_responses_api`` is false. This stage refuses ``--live``.

Upstream pin: ``9fa1196fffbcfd9de5146d2dd2869df84ab99838``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PINNED_UPSTREAM_SHA = "9fa1196fffbcfd9de5146d2dd2869df84ab99838"
STAGE = "1"
# In-process stand-in so client construction can finish without a real key.
# Never written to the audit, the memory log, or a report.
MOCK_PLACEHOLDER = "mock-xai-not-a-credential"
STAGE_MAX_LLM_CALLS = 24
STAGE_MAX_SECONDS = 60
STAGE_MAX_TOKENS = 512
STAGE_DEFAULT_TOKENS = 256
STAGE_MAX_RETRIES = 2
DEFAULT_TICKER = "SPY"
DEFAULT_TRADE_DATE = "2024-01-02"
DEFAULT_ANALYSTS = ("market",)

MOCK_DECISION = (
    "**Rating**: Hold\n\n"
    "MOCK INTEGRATION. This text was produced inside the process. "
    "It is not an xAI response, not a market call, and not an order.\n\n"
    "FINAL TRANSACTION PROPOSAL: **HOLD**"
)


class LiveInferenceRefused(RuntimeError):
    """Stage 1 does not perform paid or live model calls."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _require_model_env() -> tuple[str, str]:
    """Model ids come from the existing tier env vars. No default model is assumed."""
    quick = os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", "").strip()
    deep = os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "").strip()
    missing = [
        name
        for name, value in (
            ("TRADINGAGENTS_QUICK_THINK_LLM", quick),
            ("TRADINGAGENTS_DEEP_THINK_LLM", deep),
        )
        if not value
    ]
    if missing:
        raise SystemExit(
            "Stage 1 needs model ids in "
            + " and ".join(missing)
            + ". Catalog ids for provider xai at the pinned SHA are in "
            "tradingagents/llm_clients/model_catalog.py; this stage does not pick one."
        )
    provider = os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "").strip().lower()
    if provider and provider != "xai":
        raise SystemExit(
            f"TRADINGAGENTS_LLM_PROVIDER={provider!r} is not this stage. "
            "Stage 1 builds provider 'xai' only."
        )
    return quick, deep


def _bounded_int(env_name: str, default: int, ceiling: int) -> tuple[int, int | None]:
    raw = os.environ.get(env_name)
    requested: int | None = None
    if raw is not None and raw.strip() != "":
        requested = int(raw)
        if requested < 0:
            raise SystemExit(f"{env_name} must be >= 0, got {requested}")
        applied = min(requested, ceiling)
    else:
        applied = default
    return applied, requested


def build_research_config(output_dir: Path) -> dict[str, Any]:
    """Shallow research settings on top of the upstream config object.

    The upstream default provider is ``openai`` and the default models are
    ``gpt-6-sol`` / ``gpt-6-luna``. This stage replaces both. Memory, results
    and the cache are a new directory for this run, not ``~/.tradingagents``.
    """
    from tradingagents.default_config import build_default_config

    quick, deep = _require_model_env()
    config = build_default_config()
    output_dir.mkdir(parents=True, exist_ok=True)
    max_tokens, requested_tokens = _bounded_int(
        "TRADINGAGENTS_MAX_TOKENS", STAGE_DEFAULT_TOKENS, STAGE_MAX_TOKENS
    )
    max_retries, requested_retries = _bounded_int(
        "TRADINGAGENTS_LLM_MAX_RETRIES", 0, STAGE_MAX_RETRIES
    )
    temperature_raw = os.environ.get("TRADINGAGENTS_TEMPERATURE")
    temperature = 0.0 if temperature_raw in (None, "") else float(temperature_raw)

    config.update(
        llm_provider="xai",
        quick_think_provider=None,
        deep_think_provider=None,
        quick_think_backend_url=None,
        deep_think_backend_url=None,
        # None selects the provider registry endpoint. Do not substitute a URL.
        backend_url=None,
        quick_think_llm=quick,
        deep_think_llm=deep,
        max_debate_rounds=1,
        max_risk_discuss_rounds=1,
        max_tool_rounds=1,
        checkpoint_enabled=False,
        temperature=temperature,
        llm_max_retries=max_retries,
        max_tokens=max_tokens,
        results_dir=str(output_dir / "results"),
        data_cache_dir=str(output_dir / "cache"),
        memory_log_path=str(output_dir / "memory" / "trading_memory.md"),
        memory_log_max_entries=None,
    )
    config["_stage_bounds"] = {
        "max_tokens_requested": requested_tokens,
        "max_tokens_applied": max_tokens,
        "llm_max_retries_requested": requested_retries,
        "llm_max_retries_applied": max_retries,
        "debate_rounds_applied": 1,
        "risk_rounds_applied": 1,
        "tool_rounds_applied": 1,
        "checkpoint_enabled_applied": False,
        "memory_isolated": True,
    }
    return config


def deterministic_gate(rating: str | None) -> dict[str, Any]:
    """Python permission check. The model's prose is not an executable gate.

    Research text may say Buy or Sell. This stage never sizes a position and
    never permits submission. There is no broker client to call.
    """
    return {
        "execution_permitted": False,
        "order_submission": "disabled",
        "sizing": "not_computed",
        "account_check": "not_applicable_no_account",
        "llm_prose_is_executable_gate": False,
        "research_rating_nonbinding": rating,
        "checks": [
            "stage flag execution_permitted is false",
            "no quantity, limit, or client_order_id is computed",
            "no broker module is invoked",
        ],
    }


def real_xai_contract(config: dict[str, Any]) -> dict[str, Any]:
    """What a real call would use. Reading this does not contact xAI."""
    from tradingagents.llm_clients.api_key_env import get_api_key_env
    from tradingagents.llm_clients.openai_client import OPENAI_COMPATIBLE_PROVIDERS
    from tradingagents.llm_clients.validators import validate_model

    spec = OPENAI_COMPATIBLE_PROVIDERS["xai"]
    key_env = get_api_key_env("xai")
    return {
        "mode": "real_xai_not_invoked",
        "provider": "xai",
        "api_key_env": key_env,
        "api_key_present": bool(os.environ.get(key_env or "")),
        "base_url": spec.base_url,
        "use_responses_api": spec.use_responses_api,
        "wire": "chat.completions",
        "quick_think_llm": config["quick_think_llm"],
        "deep_think_llm": config["deep_think_llm"],
        "quick_in_catalog": validate_model("xai", config["quick_think_llm"]),
        "deep_in_catalog": validate_model("xai", config["deep_think_llm"]),
        "paid_inference": "not_performed",
    }


def execution_surface() -> dict[str, Any]:
    """Package modules whose names look like a broker adapter."""
    import pkgutil

    import tradingagents

    names = [
        module.name
        for module in pkgutil.walk_packages(tradingagents.__path__, "tradingagents.")
    ]
    hits = [
        name
        for name in names
        if any(token in name.lower() for token in ("alpaca", "broker", "ccxt"))
    ]
    return {
        "order_submission": "absent" if not hits else "present",
        "matching_modules": hits,
    }


def _decision_text(override: str | None) -> str:
    return override if override is not None else MOCK_DECISION


def _mock_clients(model: str, decision_text: str, deadline: float, counter: dict[str, Any]):
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        counter["calls"] += 1
        counter["urls"].append(str(request.url))
        if time.monotonic() > deadline:
            raise RuntimeError(f"stage1 runtime cap of {STAGE_MAX_SECONDS}s exceeded")
        if counter["calls"] > STAGE_MAX_LLM_CALLS:
            raise RuntimeError(f"stage1 LLM call cap of {STAGE_MAX_LLM_CALLS} exceeded")
        if request.url.host != "api.x.ai":
            raise RuntimeError(f"stage1 mock refused host {request.url.host}")
        body = {
            "id": "mock-stage1",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": decision_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        return httpx.Response(200, json=body)

    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport), httpx.AsyncClient(transport=transport)


@contextmanager
def _placeholder_key():
    """Present a non-credential so ``get_llm`` can construct, then restore the env."""
    key_name = "XAI_API_KEY"
    previous = os.environ.get(key_name)
    os.environ[key_name] = MOCK_PLACEHOLDER
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key_name, None)
        else:
            os.environ[key_name] = previous


@contextmanager
def _network_deny():
    attempts: list[dict[str, str]] = []
    original_connect = socket.socket.connect
    original_create = socket.create_connection

    def connect(self, address):  # noqa: ANN001
        attempts.append({"via": "socket.connect", "address": repr(address)})
        raise OSError("stage1 network deny: socket.connect")

    def create_connection(address, *args, **kwargs):  # noqa: ANN001
        attempts.append({"via": "socket.create_connection", "address": repr(address)})
        raise OSError("stage1 network deny: socket.create_connection")

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.create_connection = create_connection
    try:
        yield attempts
    finally:
        socket.socket.connect = original_connect  # type: ignore[method-assign]
        socket.create_connection = original_create


@contextmanager
def _offline_data():
    """Vendors and the identity lookup return fixtures. They do not fetch."""
    import tradingagents.dataflows.router as router
    from tradingagents.agents import context as context_mod

    saved: list[tuple[dict, str, Any]] = []
    for method, vendors in router.VENDOR_METHODS.items():
        for name in list(vendors):
            saved.append((vendors, name, vendors[name]))

            def _fixture(*_args, _method=method, **_kwargs):
                return f"offline fixture for {_method}; no vendor request was made"

            vendors[name] = _fixture
    original_profile = context_mod.get_company_profile

    def _profile(_ticker: str) -> dict[str, str]:
        return {"longName": "Offline fixture", "quoteType": "EQUITY"}

    context_mod.get_company_profile = _profile
    context_mod._identity.cache_clear()
    try:
        yield
    finally:
        for vendors, name, function in saved:
            vendors[name] = function
        context_mod.get_company_profile = original_profile
        context_mod._identity.cache_clear()


def _dependency_manifest() -> dict[str, str]:
    import importlib.metadata as metadata

    names = (
        "tradingagents",
        "langchain-core",
        "langchain-openai",
        "langgraph",
        "openai",
        "httpx",
        "pandas",
        "yfinance",
        "python-dotenv",
        "requests",
    )
    found: dict[str, str] = {}
    for name in names:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = "not-installed"
    return found


def _redact(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _probe_deny() -> str:
    try:
        socket.create_connection(("api.x.ai", 443), timeout=1)
    except OSError as exc:
        return str(exc)
    raise RuntimeError("stage1 network deny did not block api.x.ai:443")


def run_stage(
    output_dir: Path | str,
    ticker: str = DEFAULT_TICKER,
    trade_date: str = DEFAULT_TRADE_DATE,
    decision_text: str | None = None,
) -> dict[str, Any]:
    """Run one mocked research graph and write an audit file under ``output_dir``.

    ``decision_text`` replaces the mock completion. Tests use it to show that
    bullish prose still cannot submit an order.
    """
    from tradingagents.graph import trading_graph as trading_graph_module
    from tradingagents.llm_clients.factory import create_tier_client

    output = Path(output_dir)
    config = build_research_config(output)
    bounds = config.pop("_stage_bounds")
    contract = real_xai_contract(config)
    text = _decision_text(decision_text)
    counter: dict[str, Any] = {"calls": 0, "urls": []}
    deadline = time.monotonic() + STAGE_MAX_SECONDS
    sync_client, async_client = _mock_clients(
        config["deep_think_llm"], text, deadline, counter
    )
    started = _utc_now()
    home_memory = Path.home() / ".tradingagents" / "memory" / "trading_memory.md"
    home_existed = home_memory.exists()
    home_before = home_memory.read_text(encoding="utf-8") if home_existed else None

    def patched(tier_config, tier, **extra):
        extra["http_client"] = sync_client
        extra["http_async_client"] = async_client
        extra["api_key"] = MOCK_PLACEHOLDER
        extra.setdefault("timeout", 20)
        return create_tier_client(tier_config, tier, **extra)

    original_factory = trading_graph_module.create_tier_client
    trading_graph_module.create_tier_client = patched
    try:
        # get_llm reads XAI_API_KEY before it applies the placeholder kwarg.
        # Hold a non-credential only while the clients are constructed.
        with _placeholder_key():
            graph = trading_graph_module.TradingAgentsGraph(
                selected_analysts=list(DEFAULT_ANALYSTS),
                debug=False,
                config=config,
            )
        quick = graph.quick_thinking_llm
        deep = graph.deep_thinking_llm
        if quick.openai_api_key.get_secret_value() != MOCK_PLACEHOLDER:
            raise RuntimeError("mock client retained a non-placeholder API key")
        if deep.openai_api_key.get_secret_value() != MOCK_PLACEHOLDER:
            raise RuntimeError("mock client retained a non-placeholder API key")
        resolved_base = quick.openai_api_base
        if resolved_base != contract["base_url"]:
            raise RuntimeError(
                f"client base {resolved_base!r} != registry {contract['base_url']!r}"
            )
        if getattr(quick, "use_responses_api", None) not in (None, False):
            raise RuntimeError("xAI client enabled the OpenAI Responses API")

        with _network_deny() as denied, _offline_data():
            probe = _probe_deny()
            state, signal = graph.propagate(ticker, trade_date)
    finally:
        trading_graph_module.create_tier_client = original_factory
        sync_client.close()
        asyncio.run(async_client.aclose())

    gate = deterministic_gate(signal)
    report_dir = graph.save_reports(state, ticker, html=False)
    finished = _utc_now()
    secrets = [MOCK_PLACEHOLDER]
    live_key = os.environ.get("XAI_API_KEY")
    if live_key:
        secrets.append(live_key)

    audit = {
        "stage": STAGE,
        "mode": "mock_integration",
        "real_xai_invoked": False,
        "output_is_mock": True,
        "pinned_upstream_sha": PINNED_UPSTREAM_SHA,
        "run_id": uuid.uuid4().hex,
        "started_at": started,
        "finished_at": finished,
        "python": sys.version.split()[0],
        "inputs": {
            "ticker": ticker,
            "trade_date": trade_date,
            "analysts": list(DEFAULT_ANALYSTS),
            "as_of_clock": finished,
        },
        "source_ids": {
            "upstream_commit": PINNED_UPSTREAM_SHA,
            "upstream_permalink": (
                "https://github.com/TauricResearch/TradingAgents/commit/"
                + PINNED_UPSTREAM_SHA
            ),
            "provider_registry": "tradingagents/llm_clients/openai_client.py",
            "mock_completion_id": "mock-stage1",
            "market_data": "offline fixture; no vendor fetch",
            "news": "not requested; news analyst not selected",
        },
        "model_settings": {
            "llm_provider": "xai",
            "quick_think_llm": config["quick_think_llm"],
            "deep_think_llm": config["deep_think_llm"],
            "base_url": resolved_base,
            "use_responses_api": False,
            "temperature": config["temperature"],
            "bounds": bounds,
            "catalog": {
                "quick_in_catalog": contract["quick_in_catalog"],
                "deep_in_catalog": contract["deep_in_catalog"],
            },
        },
        "real_xai_contract": {
            key: value for key, value in contract.items() if key != "api_key_present"
        },
        "api_key_present_in_environment": contract["api_key_present"],
        "api_key_persisted": False,
        "outputs": {
            "signal": signal,
            "final_rating": state.get("final_rating"),
            "decision_excerpt": _redact(str(state.get("final_trade_decision") or ""), secrets)[:2000],
            "report_dir": str(report_dir),
            "memory_log_path": config["memory_log_path"],
        },
        "deterministic_gate": gate,
        "execution_surface": execution_surface(),
        "network": {
            "deny_installed": True,
            "probe": probe,
            "blocked_attempts": denied,
            "mock_urls": counter["urls"],
            "llm_calls": counter["calls"],
            "llm_call_cap": STAGE_MAX_LLM_CALLS,
            "runtime_cap_seconds": STAGE_MAX_SECONDS,
        },
        "memory": {
            "isolated_path": config["memory_log_path"],
            "home_memory_unchanged": (
                (home_memory.read_text(encoding="utf-8") if home_memory.exists() else None)
                == home_before
            ),
        },
        "dependency_manifest": _dependency_manifest(),
        "roles": {
            "data_and_validation": "offline fixture at the vendor router; identity lookup stubbed",
            "deterministic_technicals": "market-analyst tools exist; this mock does not call them",
            "news": "news analyst not selected",
            "thesis": "bull, bear, and research manager on mock text",
            "independent_critic": "bear researcher on mock text",
            "deterministic_risk_gate": "deterministic_gate; risk-debater prose is not executable",
            "paper_execution": "absent",
            "audit": "this file plus the per-run memory log",
        },
    }
    encoded = _redact(json.dumps(audit, indent=2, sort_keys=True), secrets)
    audit_path = output / "audit.json"
    audit_path.write_text(encoded + "\n", encoding="utf-8")
    for path in report_dir.rglob("*"):
        if path.is_file():
            path.write_text(_redact(path.read_text(encoding="utf-8"), secrets), encoding="utf-8")
    memory_path = Path(config["memory_log_path"])
    if memory_path.exists():
        memory_path.write_text(
            _redact(memory_path.read_text(encoding="utf-8"), secrets), encoding="utf-8"
        )
    if MOCK_PLACEHOLDER in audit_path.read_text(encoding="utf-8"):
        raise RuntimeError("audit.json retained the mock placeholder")
    return json.loads(audit_path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage 1 mock research run. Refuses live xAI and broker submission."
    )
    parser.add_argument("--output", required=True, help="Directory for the audit and memory log")
    parser.add_argument("--ticker", default=DEFAULT_TICKER)
    parser.add_argument("--date", default=DEFAULT_TRADE_DATE)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Refused. Stage 1 does not call xAI or a broker.",
    )
    args = parser.parse_args(argv)
    if args.live:
        raise LiveInferenceRefused(
            "Stage 1 refuses --live. A real xAI call needs XAI_API_KEY and the "
            "registry endpoint, and this stage does not make one."
        )
    audit = run_stage(args.output, ticker=args.ticker, trade_date=args.date)
    print(
        json.dumps(
            {
                "mode": audit["mode"],
                "real_xai_invoked": audit["real_xai_invoked"],
                "signal": audit["outputs"]["signal"],
                "execution_permitted": audit["deterministic_gate"]["execution_permitted"],
                "llm_calls": audit["network"]["llm_calls"],
                "audit": str(Path(args.output) / "audit.json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LiveInferenceRefused as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
