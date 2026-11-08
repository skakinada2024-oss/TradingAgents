"""Fail-closed preflight for a possible xAI research call.

Prices are copied from xAI's public docs at the retrieval time below. The
repository model catalog is not treated as proof that an id is sold or that
this account can call it. This module never contacts api.x.ai.

A dollar figure computed here is not a provider-enforced cap. grok-4.5,
grok-4.6, and grok-4.7 bill reasoning tokens at the output rate, reasoning
cannot be disabled, and the docs say ``max_output_tokens`` does not limit
reasoning tokens. No published reasoning-token maximum was found, so
``guaranteed_dollar_cap`` stays false and ``send`` stays false.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# Docs fetched in this session on 2026-11-08, before this module was written.
RETRIEVED_AT = "2026-11-08T03:25:00+00:00"
PRICE_SOURCES = (
    {
        "url": "https://docs.x.ai/developers/pricing",
        "retrieved_at": RETRIEVED_AT,
        "note": "Text rates, tool invocation rates, US 1.1x, priority 2x, reasoning listed as its own billed token type.",
    },
    {
        "url": "https://docs.x.ai/developers/models",
        "retrieved_at": RETRIEVED_AT,
        "note": "Same text rates. Docs recommend grok-4.7. Knowledge cutoff stated there for grok-4.7 is May 2026. Account availability is delegated to the console.",
    },
    {
        "url": "https://docs.x.ai/developers/models/grok-4.6",
        "retrieved_at": RETRIEVED_AT,
        "note": "grok-4.6 context 500000. Short-context input $2 / cached $0.50 / output $6 per 1M. Long context at 200k prompt tokens.",
    },
    {
        "url": "https://docs.x.ai/developers/model-capabilities/text/reasoning",
        "retrieved_at": RETRIEVED_AT,
        "note": "grok-4.7, grok-4.6, and grok-4.5 cannot disable reasoning. Default effort is high. Reasoning tokens are billed.",
    },
    {
        "url": "https://docs.x.ai/developers/model-capabilities/text/best-practices",
        "retrieved_at": RETRIEVED_AT,
        "note": "max_output_tokens caps the visible answer only. Reasoning and function-call tokens do not count toward it. Default max_output_tokens is 128000.",
    },
    {
        "url": "https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing",
        "retrieved_at": RETRIEVED_AT,
        "note": "Reasoning tokens are billed at the full completion-token price. Page says last updated May 10, 2026.",
    },
)

# USD per 1M tokens. Short context is prompt < 200_000. Long context applies
# to every token in the request once the prompt reaches 200_000.
# input, cached input, output. Cached is not used for a worst case.
TEXT_RATES: dict[str, dict[str, tuple[str, str]]] = {
    "grok-4.7": {"short": ("2.00", "6.00"), "long": ("4.00", "12.00")},
    "grok-4.6": {"short": ("2.00", "6.00"), "long": ("4.00", "12.00")},
    "grok-4.5": {"short": ("2.00", "6.00"), "long": ("4.00", "12.00")},
    "grok-4.3": {"short": ("1.25", "2.50"), "long": ("2.50", "5.00")},
    "grok-4.20-0309-reasoning": {"short": ("1.25", "2.50"), "long": ("2.50", "5.00")},
    "grok-4.20-0309-non-reasoning": {"short": ("1.25", "2.50"), "long": ("2.50", "5.00")},
    "grok-build-0.1": {"short": ("1.00", "2.00"), "long": ("2.00", "4.00")},
    "grok-4.20-multi-agent-0309": {"short": ("1.25", "2.50"), "long": ("2.50", "5.00")},
}

# Models the reasoning doc says cannot turn reasoning off.
REASONING_REQUIRED = frozenset({"grok-4.7", "grok-4.6", "grok-4.5"})
LONG_CONTEXT_PROMPT_TOKENS = 200_000
GLOBAL_BASE_URL = "https://api.x.ai/v1"
US_BASE_URL = "https://us.api.x.ai/v1"
US_MULTIPLIER = Decimal("1.1")

# Bounds this research mode is willing to *request*. They are not bills.
MAX_REQUESTS = 2
MAX_INPUT_TOKENS_PER_REQUEST = 4_000
MAX_VISIBLE_OUTPUT_TOKENS = 512
MAX_RETRIES = 0
# Illustrative reasoning sizes. The provider does not enforce either number.
ILLUSTRATIVE_REASONING_TOKENS = (0, 8_000, 128_000)
KEY_ENV = "XAI_API_KEY"
AUTH_ENV = "TRADINGAGENTS_XAI_BOUNDED_RUN"
AUTH_VALUE = "authorize-bounded-xai-research"
# Smallest parent-side ceiling worth mentioning for a short trace, after a 2x
# allowance on the 8_000-reasoning illustration. Not a hard cap.
PROPOSED_PARENT_BUDGET_USD = Decimal("0.25")


class BudgetRejected(RuntimeError):
    """The preflight will not send a paid request."""


def _money(tokens: int, per_million: str) -> Decimal:
    return (Decimal(tokens) * Decimal(per_million)) / Decimal(1_000_000)


def _q(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def illustrative_cost(
    model: str,
    *,
    requests: int,
    input_tokens: int,
    visible_output_tokens: int,
    reasoning_tokens: int,
    long_context: bool,
    us_endpoint: bool,
) -> dict[str, str]:
    """Published-rate arithmetic. Cached tokens are priced as uncached."""
    rates = TEXT_RATES[model]
    input_rate, output_rate = rates["long" if long_context else "short"]
    one = _money(input_tokens, input_rate) + _money(
        visible_output_tokens + reasoning_tokens, output_rate
    )
    total = one * requests
    if us_endpoint:
        total *= US_MULTIPLIER
    return {
        "usd": _q(total),
        "input_rate_per_million": input_rate,
        "output_rate_per_million": output_rate,
        "requests": str(requests),
        "reasoning_tokens_assumed": str(reasoning_tokens),
        "enforced_by_provider": "false",
    }


def preflight(
    *,
    model: str,
    requests: int = MAX_REQUESTS,
    input_tokens: int = MAX_INPUT_TOKENS_PER_REQUEST,
    visible_output_tokens: int = MAX_VISIBLE_OUTPUT_TOKENS,
    retries: int = 0,
    base_url: str | None = None,
    server_side_tools: bool = False,
    key_present: bool = False,
    authorization: str | None = None,
    parent_budget_usd: str | None = None,
) -> dict[str, Any]:
    """Decide whether a paid call may be sent. In this build the answer is no."""
    reasons: list[str] = []
    if model not in TEXT_RATES:
        reasons.append(
            f"{model!r} is not on the xAI text price table retrieved {RETRIEVED_AT}. "
            "The in-repo catalog is not a substitute."
        )
    if requests < 1 or requests > MAX_REQUESTS:
        reasons.append(f"requests must be 1..{MAX_REQUESTS}, got {requests}")
    if input_tokens < 1 or input_tokens > MAX_INPUT_TOKENS_PER_REQUEST:
        reasons.append(
            f"input tokens must be 1..{MAX_INPUT_TOKENS_PER_REQUEST}, got {input_tokens}"
        )
    if visible_output_tokens < 1 or visible_output_tokens > MAX_VISIBLE_OUTPUT_TOKENS:
        reasons.append(
            f"visible output tokens must be 1..{MAX_VISIBLE_OUTPUT_TOKENS}, "
            f"got {visible_output_tokens}"
        )
    if retries != MAX_RETRIES:
        reasons.append(f"retries must be {MAX_RETRIES}, got {retries}")
    if input_tokens >= LONG_CONTEXT_PROMPT_TOKENS:
        reasons.append("prompt ceiling crosses the 200k long-context tier")
    if server_side_tools:
        reasons.append(
            "server-side tools are billed per invocation and the model chooses the count"
        )
    resolved_url = base_url or GLOBAL_BASE_URL
    if resolved_url != GLOBAL_BASE_URL:
        reasons.append(
            f"base URL {resolved_url!r} is not the global endpoint {GLOBAL_BASE_URL}. "
            "The US endpoint bills 1.1x and is refused."
        )
    if not key_present:
        reasons.append(f"{KEY_ENV} is not set. A key alone would still not send.")
    if authorization != AUTH_VALUE:
        reasons.append(
            f"{AUTH_ENV} must equal the explicit bounded-run phrase. "
            "It was not provided."
        )
    reasoning_unbounded = model in REASONING_REQUIRED or model not in TEXT_RATES
    if model in REASONING_REQUIRED:
        reasons.append(
            f"{model} bills reasoning tokens at the output rate, reasoning cannot "
            "be disabled, and max_output_tokens does not limit them. No published "
            "reasoning-token maximum was found, so a dollar hard cap cannot be guaranteed."
        )
    elif model in TEXT_RATES:
        reasons.append(
            "Chat Completions max_tokens is not documented as a billing ceiling "
            "for this client. A pre-call estimate is not a provider-enforced cap."
        )

    rates = None
    if model in TEXT_RATES:
        short_in, short_out = TEXT_RATES[model]["short"]
        long_in, long_out = TEXT_RATES[model]["long"]
        rates = {
            "currency": "USD",
            "unit": "per_1M_tokens",
            "short_context_prompt_below": LONG_CONTEXT_PROMPT_TOKENS,
            "short_input": short_in,
            "short_output": short_out,
            "long_input": long_in,
            "long_output": long_out,
            "cached_input": "not_used_for_worst_case",
            "reasoning_billed_as": "output",
        }
    illustrations: dict[str, dict[str, str]] = {}
    if model in TEXT_RATES and requests >= 1 and input_tokens >= 1 and visible_output_tokens >= 1:
        for assumed in ILLUSTRATIVE_REASONING_TOKENS:
            illustrations[str(assumed)] = illustrative_cost(
                model,
                requests=max(requests, 1),
                input_tokens=input_tokens,
                visible_output_tokens=visible_output_tokens,
                reasoning_tokens=assumed,
                long_context=False,
                us_endpoint=False,
            )
        # Context window is not a documented billing max. Shown so a $0.25
        # proposal is not mistaken for the size of a long trace.
        illustrations["context_window_500000_not_a_billing_max"] = illustrative_cost(
            "grok-4.6" if model not in TEXT_RATES else model,
            requests=max(requests, 1) if requests >= 1 else 1,
            input_tokens=min(max(input_tokens, 1), MAX_INPUT_TOKENS_PER_REQUEST),
            visible_output_tokens=min(max(visible_output_tokens, 1), MAX_VISIBLE_OUTPUT_TOKENS),
            reasoning_tokens=500_000,
            long_context=False,
            us_endpoint=False,
        )

    guaranteed = False
    parent_ok = None
    if parent_budget_usd is not None and illustrations.get("8000"):
        parent_ok = Decimal(parent_budget_usd) >= Decimal(illustrations["8000"]["usd"])
        if not parent_ok:
            reasons.append(
                f"parent budget {parent_budget_usd} is below the illustrative "
                f"8_000-reasoning-token cost {illustrations['8000']['usd']}"
            )

    return {
        "send": False,
        "guaranteed_dollar_cap": guaranteed,
        "reasoning_tokens_bounded": False,
        "reasoning_required_by_docs": reasoning_unbounded and model in REASONING_REQUIRED,
        "model": model,
        "rates": rates,
        "model_on_official_price_table": model in TEXT_RATES,
        "catalog_is_not_availability": True,
        "price_sources": list(PRICE_SOURCES),
        "retrieved_at": RETRIEVED_AT,
        "base_url": resolved_url,
        "retries": retries,
        "server_side_tool_invocations": 0 if not server_side_tools else "unbounded",
        "yahoo_price_tool_usd": "0",
        "requests": requests,
        "input_token_ceiling": input_tokens,
        "visible_output_token_ceiling": visible_output_tokens,
        "illustrative_usd": illustrations,
        "proposed_parent_budget_usd": format(PROPOSED_PARENT_BUDGET_USD, "f"),
        "proposed_budget_is_hard_cap": False,
        "parent_budget_covers_8k_illustration": parent_ok,
        "reasons": reasons,
        "key_env": KEY_ENV,
        "authorization_env": AUTH_ENV,
        "authorization_satisfied": authorization == AUTH_VALUE,
        "key_present": key_present,
    }


def assert_not_sending(report: dict[str, Any]) -> None:
    if report.get("send") or report.get("guaranteed_dollar_cap"):
        raise BudgetRejected("preflight tried to treat an estimate as permission to send")
