# Forward research preflight

This path prepares one current price-only read. It does not call xAI. The
stage-1 command remains the mock, still defaults to `SPY`, and still refuses
`--live`. `--live` on the forward command is refused as well. That word is
not the name of a model call.

## Command

```bash
export TRADINGAGENTS_QUICK_THINK_LLM=grok-4.6
export TRADINGAGENTS_DEEP_THINK_LLM=grok-4.6
unset XAI_API_KEY TRADINGAGENTS_XAI_BOUNDED_RUN
.venv/bin/python -m tradingagents.research_forward \
  --output /tmp/forward-aapl --ticker AAPL --as-of 2026-11-08
```

`--fixture` skips Yahoo and labels the bars `fixture`. A fixture run is not
real research, and the audit says so. A vendor run is still not a model call.

## Prices used for the preflight

Retrieved `2026-11-08T03:25:00+00:00` from:

- https://docs.x.ai/developers/pricing
- https://docs.x.ai/developers/models
- https://docs.x.ai/developers/models/grok-4.6
- https://docs.x.ai/developers/model-capabilities/text/reasoning
- https://docs.x.ai/developers/model-capabilities/text/best-practices
- https://docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing

`grok-4.6` and `grok-4.7` short-context rates on those pages are $2.00 input
and $6.00 output per 1M tokens, cached input $0.50. At 200k prompt tokens the
whole request moves to $4.00 / $12.00. Reasoning tokens are billed at the
output rate. For `grok-4.7`, `grok-4.6`, and `grok-4.5`, reasoning cannot be
disabled and defaults to `high`. The best-practices page says
`max_output_tokens` limits the visible answer only. No reasoning-token maximum
was stated. The in-repo catalog does not list `grok-4.7`. The docs recommend
`grok-4.7` and say account availability is on the xAI console, which was not
opened. A catalog id is not proof the account can call it. `grok-4.7`'s
knowledge cutoff on the models page is May 2026.

Server-side tools on the pricing page cost $5 per 1,000 calls for web search
and code execution, and the model chooses how many. This path does not enable
them. Yahoo through `load_ohlcv` is treated as $0.

## Why this is not a hard cap

Two calls, 4,000 uncached input tokens, 512 visible output tokens, and a
hypothetical 8,000 reasoning tokens at the short-context `grok-4.6` rates come
to $0.118144. A 2× allowance on that picture is $0.25. That is the smallest
practical parent-side ceiling to mention. It is not enforced. The same two
calls priced as if reasoning used 500,000 tokens come to $6.022144, and the
500,000 figure is the context window, not a documented billing maximum. The US
endpoint is a further 1.1× and is refused. Priority processing is 2× and is
not requested. Retries are required to be 0; a retry inside the provider would
not be visible here.

`guaranteed_dollar_cap` is false. `send` is false. Setting `XAI_API_KEY` and
`TRADINGAGENTS_XAI_BOUNDED_RUN=authorize-bounded-xai-research` does not send.
No credits are purchased.

## Market data

The vendor read uses `load_ohlcv`, which sets `auto_adjust=True` and
`fill_gaps=False` for this path. An unadjusted series was not fetched, so
adjusted and unadjusted prices were not compared. News is not fetched. The
Python SMA and last close are the only calculations. They are not a forecast
and not a reason to send an order. The execution gate stays false.
