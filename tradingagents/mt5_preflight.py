"""Read-only eligibility check for a MetaTrader 5 terminal that is already logged in.

The official API is the MetaTrader5 package documented at
https://www.mql5.com/en/docs/python_metatrader5 . ``initialize`` attaches to
a local terminal. This module does not call ``login`` and does not send an
order. On this cloud VM it does not open a terminal at all.

Trade-mode integers match the documented enumeration order and the official
examples: ``account_info`` printed ``trade_mode=0`` for a demo server, and
``symbol_info`` printed ``trade_mode=4`` for a tradable symbol.
https://www.mql5.com/en/docs/constants/environment_state/accountinformation
https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

# ENUM_ACCOUNT_TRADE_MODE, documented order DEMO, CONTEST, REAL.
ACCOUNT_TRADE_MODE_DEMO = 0
ACCOUNT_TRADE_MODE_CONTEST = 1
ACCOUNT_TRADE_MODE_REAL = 2
# ENUM_SYMBOL_TRADE_MODE. The symbol_info example printed 4 for a tradable name.
SYMBOL_TRADE_MODE_DISABLED = 0
SYMBOL_TRADE_MODE_LONGONLY = 1
SYMBOL_TRADE_MODE_SHORTONLY = 2
SYMBOL_TRADE_MODE_CLOSEONLY = 3
SYMBOL_TRADE_MODE_FULL = 4

ALLOCATION_CAP = Decimal("0.10")
EQUITY_LOSS_CUTOFF_USD = Decimal("5")
MAX_POSITIONS = 1
MAX_ELAPSED_SECONDS = 12 * 60 * 60
STALE_QUOTE_SECONDS = 30
CLOSED_QUOTE_SECONDS = 15 * 60

_PRIVATE_KEYS = {
    "login",
    "name",
    "server",
    "company",
    "path",
    "data_path",
    "commondata_path",
    "password",
}


class PreflightRefused(RuntimeError):
    """The process will not attach or will not continue."""


def proposed_limits() -> dict[str, Any]:
    """Limits for a later run. This preflight does not arm them."""
    return {
        "execution_enabled": False,
        "send_order": False,
        "equity_loss_cutoff_usd": format(EQUITY_LOSS_CUTOFF_USD, "f"),
        "max_positions": MAX_POSITIONS,
        "max_elapsed_seconds": MAX_ELAPSED_SECONDS,
        "cutoff_note": (
            "A 5 USD equity-loss cutoff cannot stop a fill at exactly 5 USD. "
            "A gap, a weekend reopen, or a missed quote can realize a larger loss "
            "before any later check runs. The 12 hour bound is a hard elapsed cap "
            "for a future process and can also stop earlier. Neither cap is active."
        ),
    }


def _mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    as_dict = getattr(value, "_asdict", None)
    if callable(as_dict):
        return dict(as_dict())
    return None


def _decimal(value: Any, label: str) -> Decimal:
    if value is None or value == "":
        raise ValueError(label)
    return Decimal(str(value))


def allocation_budget_usd(balance: Decimal, equity: Decimal) -> Decimal:
    """Ten percent of the smaller of cash and equity, rounded down."""
    base = min(balance, equity)
    return (base * ALLOCATION_CAP).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def public_view(report: dict[str, Any]) -> dict[str, Any]:
    """Drop account identifiers. Balance stays because the gross check uses it."""
    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items() if key not in _PRIVATE_KEYS}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return scrub(report)


def evaluate(
    client: Any,
    symbol: str,
    now: datetime,
    *,
    source: str,
) -> dict[str, Any]:
    """Read one client and decide eligibility. ``source`` is ``fake_client`` or ``terminal``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    reasons: list[str] = []
    first = _mapping(client.account_info())
    second = _mapping(client.account_info())
    terminal = _mapping(client.terminal_info())
    symbol_info = _mapping(client.symbol_info(symbol)) if symbol else None
    tick = _mapping(client.symbol_info_tick(symbol)) if symbol else None
    positions = client.positions_total()

    if not symbol:
        reasons.append("symbol is required; this preflight does not choose one")
    if first is None or second is None:
        reasons.append("account_info is missing")
    elif first.get("login") != second.get("login") or first.get("server") != second.get("server"):
        reasons.append("account identity changed between reads")
    if terminal is None:
        reasons.append("terminal_info is missing")
    else:
        if terminal.get("connected") is not True:
            reasons.append("terminal is not connected")
        if terminal.get("trade_allowed") is not True:
            reasons.append("terminal trade_allowed is not true")
        if terminal.get("tradeapi_disabled") is True:
            reasons.append("terminal trade API is disabled")
    if positions is None:
        reasons.append("positions_total is missing")
    elif int(positions) != 0:
        reasons.append("a position is already open; this check does not close it")

    mode = None if first is None else first.get("trade_mode")
    if first is not None:
        if mode == ACCOUNT_TRADE_MODE_REAL:
            reasons.append("account trade mode is real")
        elif mode == ACCOUNT_TRADE_MODE_CONTEST:
            reasons.append("account trade mode is contest")
        elif mode != ACCOUNT_TRADE_MODE_DEMO:
            reasons.append("account trade mode is not demo")
        if first.get("currency") != "USD":
            reasons.append("account currency is not USD")
        if first.get("trade_allowed") is not True:
            reasons.append("account trade_allowed is not true")
        # account.leverage is the broker maximum (for example 100). It is not
        # the exposure this check will take. Exposure is capped in cash terms.

    notional = None
    budget = None
    if symbol and symbol_info is None:
        reasons.append("symbol_info is missing")
    elif symbol_info is not None:
        trade_mode = symbol_info.get("trade_mode")
        if trade_mode == SYMBOL_TRADE_MODE_DISABLED:
            reasons.append("symbol trade mode is disabled")
        elif trade_mode == SYMBOL_TRADE_MODE_CLOSEONLY:
            reasons.append("symbol is close-only")
        elif trade_mode == SYMBOL_TRADE_MODE_SHORTONLY:
            reasons.append("symbol is short-only; shorts stay refused")
        elif trade_mode != SYMBOL_TRADE_MODE_FULL and trade_mode != SYMBOL_TRADE_MODE_LONGONLY:
            reasons.append("symbol trade mode is missing or unknown")
        profit_ccy = symbol_info.get("currency_profit")
        if profit_ccy != "USD":
            reasons.append("symbol profit currency is not USD; no conversion is applied")
        if tick is None or tick.get("time") is None or tick.get("ask") in (None, 0):
            reasons.append("symbol tick is missing")
        else:
            age = int(now.timestamp()) - int(tick["time"])
            if age < 0 or age > CLOSED_QUOTE_SECONDS:
                reasons.append("quote is not from an open session")
            elif age > STALE_QUOTE_SECONDS:
                reasons.append("quote is stale")
            try:
                volume_min = _decimal(symbol_info.get("volume_min"), "volume_min")
                contract = _decimal(symbol_info.get("trade_contract_size"), "trade_contract_size")
                ask = _decimal(tick.get("ask"), "ask")
                notional = (volume_min * contract * ask).quantize(Decimal("0.01"))
            except (ValueError, ArithmeticError):
                reasons.append("min-lot metadata is missing")
            else:
                if volume_min <= 0 or contract <= 0 or ask <= 0:
                    reasons.append("min-lot metadata is missing")
                elif first is None or first.get("balance") is None or first.get("equity") is None:
                    reasons.append("balance or equity is missing")
                else:
                    balance = _decimal(first["balance"], "balance")
                    equity = _decimal(first["equity"], "equity")
                    budget = allocation_budget_usd(balance, equity)
                    if notional > min(balance, equity):
                        reasons.append("minimum volume gross notional exceeds cash and equity")
                    if notional > budget:
                        reasons.append(
                            "minimum volume gross notional exceeds the 10 percent "
                            "allocation of cash and equity; the contract is not resized"
                        )

    eligible = not reasons
    report = {
        "source": source,
        "eligible": eligible,
        "execution_enabled": False,
        "reasons": reasons,
        "symbol": symbol,
        "account_currency": None if first is None else first.get("currency"),
        "account_trade_mode": mode,
        "account_leverage": None if first is None else first.get("leverage"),
        "balance": None if first is None else first.get("balance"),
        "equity": None if first is None else first.get("equity"),
        "login_present": bool(first and first.get("login") not in (None, "")),
        "server_present": bool(first and first.get("server")),
        "terminal_connected": None if terminal is None else terminal.get("connected"),
        "terminal_name": None if terminal is None else terminal.get("name"),
        "terminal_build": None if terminal is None else terminal.get("build"),
        "positions_total": positions,
        "min_lot_gross_usd": None if notional is None else format(notional, "f"),
        "allocation_budget_usd": None if budget is None else format(budget, "f"),
        "allocation_cap": format(ALLOCATION_CAP, "f"),
        "leverage_note": (
            "account.leverage is the broker maximum, not the gross exposure used here"
        ),
        "limits": proposed_limits(),
        "checked_at": now.astimezone(UTC).isoformat(),
    }
    return public_view(report)


def attach_and_read(symbol: str, terminal_path: str | None, now: datetime) -> dict[str, Any]:
    """Attach on Windows with ``initialize`` only. Never call ``login``."""
    if sys.platform != "win32":
        raise PreflightRefused(
            "This process is not Windows. The MetaTrader5 package talks to a "
            "local terminal. No connection was opened."
        )
    import MetaTrader5 as mt5

    if mt5.ACCOUNT_TRADE_MODE_DEMO != ACCOUNT_TRADE_MODE_DEMO:
        raise PreflightRefused("installed package demo constant differs from the documented value")
    ok = mt5.initialize(terminal_path) if terminal_path else mt5.initialize()
    if not ok:
        code = mt5.last_error()
        raise PreflightRefused(f"initialize failed: {code[0] if isinstance(code, tuple) else 'unknown'}")

    class _Client:
        def account_info(self):
            return mt5.account_info()

        def terminal_info(self):
            return mt5.terminal_info()

        def symbol_info(self, name):
            return mt5.symbol_info(name)

        def symbol_info_tick(self, name):
            return mt5.symbol_info_tick(name)

        def positions_total(self):
            return mt5.positions_total()

    try:
        return evaluate(_Client(), symbol, now, source="terminal")
    finally:
        mt5.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only MetaTrader 5 demo preflight. Does not send an order."
    )
    parser.add_argument("--symbol", required=True, help="Symbol already visible in the terminal.")
    parser.add_argument(
        "--terminal-path",
        default=None,
        help="Optional path to an already installed terminal64.exe. No server and no password.",
    )
    parser.add_argument("--live", action="store_true", help="Refused.")
    args = parser.parse_args(argv)
    if args.live:
        print("Refusing --live. This preflight does not enable execution.", file=sys.stderr)
        return 2
    try:
        report = attach_and_read(args.symbol, args.terminal_path, datetime.now(UTC))
    except PreflightRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(public_view(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
