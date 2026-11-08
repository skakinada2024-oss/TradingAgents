"""EURUSD demo agent. Dry-run unless --execute-demo. No orders from a non-Windows process.

The fit uses closed bars only. A closed market logs WAITING and does not
invent a tick. Selling is only a close of a long this process opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any

from tradingagents.mt5_preflight import (
    ACCOUNT_TRADE_MODE_DEMO,
    SYMBOL_TRADE_MODE_CLOSEONLY,
    SYMBOL_TRADE_MODE_DISABLED,
    allocation_budget_usd,
)

SYMBOL = "EURUSD"
MAGIC = 20261108
MAX_ELAPSED = timedelta(seconds=12 * 60 * 60)
LOSS_CUTOFF = Decimal("5")
MAX_TRADE_RISK = Decimal("1")
MAX_SPREAD_POINTS = Decimal("30")
TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_DONE_PARTIAL = 10010
TRADE_RETCODE_MARKET_CLOSED = 10018
TRADE_RETCODE_TRADE_DISABLED = 10017
TRADE_RETCODE_PRICE_OFF = 10021
TRADE_RETCODE_CLOSE_ONLY = 10044
ORDER_CHECK_OK = 0
MARKET_CLOSED_RETCODES = {
    TRADE_RETCODE_MARKET_CLOSED,
    TRADE_RETCODE_TRADE_DISABLED,
    TRADE_RETCODE_PRICE_OFF,
    TRADE_RETCODE_CLOSE_ONLY,
}


class DemoRefused(RuntimeError):
    pass


def identity_hash(login: Any, server: Any) -> str:
    raw = f"{login}|{server}".encode()
    return hashlib.sha256(raw).hexdigest()


def floor_volume(raw: Decimal, step: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal | None:
    """Largest step multiple that is at least the minimum and not above the budget."""
    if step <= 0 or minimum <= 0 or raw < minimum:
        return None
    steps = (raw / step).to_integral_value(rounding=ROUND_DOWN)
    volume = steps * step
    if volume < minimum or volume > maximum:
        return None
    return volume


def gross_usd(volume: Decimal, contract: Decimal, price: Decimal) -> Decimal:
    return (volume * contract * price).quantize(Decimal("0.01"))


def size_entry(symbol: dict[str, Any], tick: dict[str, Any], balance: Decimal, equity: Decimal) -> dict[str, Any]:
    """Floor volume to the step. Never round up through the 10 percent cap or the 1 USD stop."""
    if symbol.get("currency_profit") != "USD":
        return {"ok": False, "reason": "profit currency is not USD; no conversion is applied"}
    point = Decimal(str(symbol["point"]))
    tick_size = Decimal(str(symbol["trade_tick_size"]))
    tick_value = Decimal(str(symbol["trade_tick_value"]))
    step = Decimal(str(symbol["volume_step"]))
    minimum = Decimal(str(symbol["volume_min"]))
    maximum = Decimal(str(symbol.get("volume_max") or minimum))
    ask = Decimal(str(tick["ask"]))
    bid = Decimal(str(tick["bid"]))
    if point <= 0 or tick_size <= 0 or ask <= 0 or bid <= 0 or ask < bid:
        return {"ok": False, "reason": "price metadata is missing"}
    spread_points = (ask - bid) / point
    if spread_points > MAX_SPREAD_POINTS:
        return {"ok": False, "reason": "spread is wider than the bound"}
    budget = allocation_budget_usd(balance, equity)
    unit = gross_usd(Decimal("1"), Decimal(str(symbol["trade_contract_size"])), ask)
    if unit <= 0:
        return {"ok": False, "reason": "contract metadata is missing"}
    raw = budget / unit
    volume = floor_volume(raw, step, minimum, maximum)
    if volume is None:
        return {"ok": False, "reason": "minimum volume does not fit the allocation cap"}
    notional = gross_usd(volume, Decimal(str(symbol["trade_contract_size"])), ask)
    if notional > budget or notional > min(balance, equity):
        return {"ok": False, "reason": "volume would exceed cash exposure"}
    stops = Decimal(str(symbol.get("trade_stops_level") or 0))
    distance = max(stops, Decimal("1")) * point
    risk = (distance / tick_size) * tick_value * volume
    if risk > MAX_TRADE_RISK:
        return {"ok": False, "reason": "tightest valid stop risks more than 1 USD"}
    filling = _filling(int(symbol.get("filling_mode") or 0))
    if filling is None:
        return {"ok": False, "reason": "symbol filling mode has no documented match"}
    sl = ask - distance
    tp = ask + distance
    return {
        "ok": True,
        "volume": format(volume, "f"),
        "notional": format(notional, "f"),
        "sl": format(sl, "f"),
        "tp": format(tp, "f"),
        "risk_usd": format(risk.quantize(Decimal("0.01")), "f"),
        "filling": filling,
        "price": format(ask, "f"),
    }


def _filling(mask: int) -> int | None:
    # SYMBOL_FILLING_FOK = 1 maps to ORDER_FILLING_FOK = 0.
    # SYMBOL_FILLING_IOC = 2 maps to ORDER_FILLING_IOC = 1.
    if mask & 1:
        return 0
    if mask & 2:
        return 1
    return None


def session_pnl(start_equity: Decimal, equity: Decimal) -> Decimal:
    return (equity - start_equity).quantize(Decimal("0.01"))


def loss_reached(start_equity: Decimal, equity: Decimal) -> bool:
    return session_pnl(start_equity, equity) <= -LOSS_CUTOFF


def deadline_reached(started_at: datetime, now: datetime) -> bool:
    if started_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("times must be timezone-aware")
    return now - started_at >= MAX_ELAPSED


def load_started_at(path: Path, now: datetime) -> datetime:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        return datetime.fromisoformat(text)
    path.write_text(now.isoformat(), encoding="utf-8")
    return now


def pin_identity(path: Path, login: Any, server: Any) -> dict[str, Any]:
    digest = identity_hash(login, server)
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        saved["changed"] = saved.get("hash") != digest
        return saved
    payload = {"hash": digest, "changed": False}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def acquire_lock(path: Path, pid: int, alive) -> bool:
    if path.exists():
        try:
            other = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            other = -1
        if alive(other):
            return False
        path.unlink()
    path.write_text(str(pid), encoding="utf-8")
    return True


def _demo_account(account: dict[str, Any] | None) -> str | None:
    if account is None:
        return "account_info is missing"
    if account.get("trade_mode") != ACCOUNT_TRADE_MODE_DEMO:
        return "account is not a USD demo"
    if account.get("currency") != "USD":
        return "account is not a USD demo"
    if account.get("trade_allowed") is not True:
        return "account trade_allowed is not true"
    return None


def train_signal(rates: list[dict[str, Any]] | None) -> dict[str, Any]:
    if not rates:
        return {"signal": "HOLD", "reason": "no_closed_bars"}
    from tradingagents.mt5_model import drop_forming_bar, fit_closed_bars

    closed = drop_forming_bar(rates)
    if len(closed) < 2:
        return {"signal": "HOLD", "reason": "no_closed_bars"}
    try:
        fitted = fit_closed_bars(closed)
    except Exception as exc:  # noqa: BLE001 — a failed fit must not become a trade
        return {"signal": "HOLD", "reason": f"fit_failed:{type(exc).__name__}"}
    return fitted


def cycle(client: Any, state: dict[str, Any], now: datetime, *, execute: bool) -> dict[str, Any]:
    """One pass. ``execute`` false never sends. Market-closed does not invent a price."""
    account = client.account_info()
    terminal = client.terminal_info()
    problem = _demo_account(account)
    if problem:
        return {"action": "STOP", "detail": problem, "sent": False}
    if terminal is None or terminal.get("connected") is not True:
        return {"action": "WAITING", "detail": "terminal disconnected", "sent": False}
    digest = identity_hash(account.get("login"), account.get("server"))
    if digest != state["identity_hash"]:
        return {"action": "STOP", "detail": "account identity changed", "sent": False}
    if deadline_reached(state["started_at"], now):
        return _exit(client, state, now, execute, "deadline")
    equity = Decimal(str(account["equity"]))
    balance = Decimal(str(account["balance"]))
    if loss_reached(state["start_equity"], equity):
        return _exit(client, state, now, execute, "equity_loss_cutoff")
    if state.get("stop"):
        return _exit(client, state, now, execute, "stop_requested")
    positions = client.positions_get(SYMBOL) or []
    foreign = [item for item in positions if item.get("ticket") != state.get("owned_ticket")]
    if state.get("owned_ticket") is None and positions:
        return {"action": "STOP", "detail": "existing position will not be managed", "sent": False}
    if foreign:
        return {"action": "STOP", "detail": "foreign position will not be managed", "sent": False}
    if state.get("owned_ticket") is not None:
        return {"action": "HOLD", "detail": "one position is already open", "sent": False}
    symbol = client.symbol_info(SYMBOL)
    tick = client.symbol_info_tick(SYMBOL)
    if symbol is None or tick is None or not tick.get("ask") or not tick.get("bid"):
        return {"action": "WAITING", "detail": "quote metadata is missing", "sent": False}
    if symbol.get("trade_mode") in {SYMBOL_TRADE_MODE_DISABLED, SYMBOL_TRADE_MODE_CLOSEONLY}:
        return {"action": "WAITING", "detail": "market closed", "sent": False}
    fitted = train_signal(client.copy_rates(SYMBOL))
    if fitted.get("signal") != "LONG":
        return {"action": "HOLD", "detail": fitted.get("reason") or "model_hold", "sent": False, "fit": _public_fit(fitted)}
    sized = size_entry(symbol, tick, balance, equity)
    if not sized["ok"]:
        return {"action": "HOLD", "detail": sized["reason"], "sent": False, "fit": _public_fit(fitted)}
    request = {
        "symbol": SYMBOL,
        "volume": sized["volume"],
        "sl": sized["sl"],
        "tp": sized["tp"],
        "type": "buy",
        "magic": MAGIC,
        "type_filling": sized["filling"],
    }
    checked = client.order_check(request)
    retcode = None if checked is None else checked.get("retcode")
    if retcode in MARKET_CLOSED_RETCODES:
        return {"action": "WAITING", "detail": f"order_check retcode {retcode}", "sent": False}
    if retcode != ORDER_CHECK_OK:
        return {"action": "HOLD", "detail": f"order_check refused {retcode}", "sent": False}
    if not execute:
        return {"action": "HOLD", "detail": "dry_run", "sent": False, "would_send": request, "fit": _public_fit(fitted)}
    if client.orders_get(SYMBOL):
        return {"action": "HOLD", "detail": "an order is already working", "sent": False}
    result = client.order_send(dict(request))
    code = None if result is None else result.get("retcode")
    if code in MARKET_CLOSED_RETCODES:
        return {"action": "WAITING", "detail": f"send retcode {code}", "sent": False}
    if code not in {TRADE_RETCODE_DONE, TRADE_RETCODE_DONE_PARTIAL}:
        return {"action": "HOLD", "detail": f"send refused {code}", "sent": True}
    filled = Decimal(str(result.get("volume") or sized["volume"]))
    state["owned_ticket"] = result.get("order")
    state["owned_volume"] = format(filled, "f")
    state["partial"] = code == TRADE_RETCODE_DONE_PARTIAL
    return {"action": "BUY", "detail": "filled" if code == TRADE_RETCODE_DONE else "partial", "sent": True, "volume": format(filled, "f")}


def _exit(client: Any, state: dict[str, Any], now: datetime, execute: bool, why: str) -> dict[str, Any]:
    account = client.account_info()
    if _demo_account(account) or identity_hash(account.get("login"), account.get("server")) != state["identity_hash"]:
        return {"action": "STOP", "detail": f"{why}; close skipped because the account no longer matches", "sent": False, "flattened": False}
    ticket = state.get("owned_ticket")
    if ticket is None:
        return {"action": "STOP", "detail": why, "sent": False, "flattened": True}
    symbol = client.symbol_info(SYMBOL)
    if symbol is None or symbol.get("trade_mode") in {SYMBOL_TRADE_MODE_DISABLED}:
        return {"action": "STOP", "detail": f"{why}; position still open because the market is closed", "sent": False, "flattened": False}
    if not execute:
        return {"action": "STOP", "detail": f"{why}; dry_run did not close", "sent": False, "flattened": False}
    close = {"symbol": SYMBOL, "volume": state.get("owned_volume"), "type": "sell", "position": ticket, "magic": MAGIC}
    checked = client.order_check(close)
    if checked is None or checked.get("retcode") in MARKET_CLOSED_RETCODES or checked.get("retcode") != ORDER_CHECK_OK:
        return {"action": "STOP", "detail": f"{why}; close check did not pass", "sent": False, "flattened": False}
    result = client.order_send(close)
    if result and result.get("retcode") == TRADE_RETCODE_DONE:
        state["owned_ticket"] = None
        return {"action": "CLOSE", "detail": why, "sent": True, "flattened": True}
    return {"action": "STOP", "detail": f"{why}; close was not confirmed", "sent": True, "flattened": False}


def _public_fit(fitted: dict[str, Any]) -> dict[str, Any]:
    return {key: fitted.get(key) for key in (
        "signal", "reason", "probability", "n_train", "n_test",
        "holdout_log_loss", "baseline_log_loss",
    )}


def run_session(client: Any, state_dir: Path, *, execute: bool, now_fn, sleep_fn, stop_fn, max_cycles: int | None = None) -> list[dict[str, Any]]:
    state_dir.mkdir(parents=True, exist_ok=True)
    if not acquire_lock(state_dir / "LOCK", os.getpid(), _pid_alive):
        return [{"action": "STOP", "detail": "another process holds the lock", "sent": False}]
    account = client.account_info()
    problem = _demo_account(account)
    if problem:
        return [{"action": "STOP", "detail": problem, "sent": False}]
    if (client.positions_get(SYMBOL) or []):
        return [{"action": "STOP", "detail": "existing position will not be managed", "sent": False}]
    identity = pin_identity(state_dir / "identity.json", account.get("login"), account.get("server"))
    if identity.get("changed"):
        return [{"action": "STOP", "detail": "account identity changed", "sent": False}]
    started = load_started_at(state_dir / "started_at.txt", now_fn())
    state = {
        "identity_hash": identity["hash"],
        "started_at": started,
        "start_equity": Decimal(str(account["equity"])),
        "owned_ticket": None,
        "owned_volume": None,
        "stop": False,
    }
    events = []
    cycles = 0
    while True:
        now = now_fn()
        state["stop"] = stop_fn()
        event = cycle(client, state, now, execute=execute)
        events.append(event)
        _append_event(state_dir / "events.log", now, event)
        cycles += 1
        if event["action"] == "STOP" or (max_cycles is not None and cycles >= max_cycles):
            break
        if event["action"] != "WAITING" and not execute:
            break
        sleep_fn(30)
    (state_dir / "journal.json").write_text(json.dumps({
        "flattened": events[-1].get("flattened"),
        "owned_ticket_set": state.get("owned_ticket") is not None,
        "partial": state.get("partial", False),
        "started_at": started.isoformat(),
    }), encoding="utf-8")
    lock = state_dir / "LOCK"
    if lock.exists():
        lock.unlink()
    return events


def _append_event(path: Path, now: datetime, event: dict[str, Any]) -> None:
    line = json.dumps({
        "at": now.isoformat(),
        "action": event.get("action"),
        "detail": event.get("detail"),
        "sent": event.get("sent"),
    })
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def write_stop(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "STOP").write_text("stop\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD demo agent. Dry-run unless --execute-demo.")
    parser.add_argument("--execute-demo", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--state-dir", default="run_state")
    parser.add_argument("--terminal-path", default=None)
    args = parser.parse_args(argv)
    if args.live:
        print("Refusing --live. Demo execution is only --execute-demo, and only on Windows.", file=sys.stderr)
        return 2
    state_dir = Path(args.state_dir)
    if args.stop:
        write_stop(state_dir)
        print(f"STOP written in {state_dir}")
        return 0
    if sys.platform != "win32":
        print("This process is not Windows. No terminal was opened and no order was sent.", file=sys.stderr)
        return 2
    import MetaTrader5 as mt5

    ok = mt5.initialize(args.terminal_path) if args.terminal_path else mt5.initialize()
    if not ok:
        print("initialize failed. No order was sent.", file=sys.stderr)
        return 2
    client = _WindowsClient(mt5)
    stop = {"flag": False}

    def now_fn():
        return datetime.now(UTC)

    def sleep_fn(seconds: float):
        import time
        time.sleep(seconds)

    def stop_fn():
        return stop["flag"] or (state_dir / "STOP").exists()

    try:
        events = run_session(
            client, state_dir, execute=args.execute_demo,
            now_fn=now_fn, sleep_fn=sleep_fn, stop_fn=stop_fn,
            max_cycles=1 if not args.execute_demo else None,
        )
    except KeyboardInterrupt:
        stop["flag"] = True
        events = [{"action": "STOP", "detail": "keyboard_interrupt", "sent": False}]
    finally:
        mt5.shutdown()
    print(json.dumps(events[-1], default=str))
    return 0


class _WindowsClient:
    def __init__(self, mt5: Any):
        self._mt5 = mt5

    def account_info(self):
        info = self._mt5.account_info()
        return None if info is None else info._asdict()

    def terminal_info(self):
        info = self._mt5.terminal_info()
        return None if info is None else info._asdict()

    def symbol_info(self, symbol):
        info = self._mt5.symbol_info(symbol)
        return None if info is None else info._asdict()

    def symbol_info_tick(self, symbol):
        info = self._mt5.symbol_info_tick(symbol)
        return None if info is None else info._asdict()

    def positions_get(self, symbol):
        rows = self._mt5.positions_get(symbol=symbol)
        if rows is None:
            return []
        return [row._asdict() for row in rows]

    def orders_get(self, symbol):
        rows = self._mt5.orders_get(symbol=symbol)
        if not rows:
            return []
        return [row._asdict() for row in rows if row.magic == MAGIC]

    def copy_rates(self, symbol):
        rates = self._mt5.copy_rates_from_pos(symbol, self._mt5.TIMEFRAME_M1, 0, 800)
        if rates is None:
            return None
        return [{
            "time": int(row["time"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        } for row in rates]

    def order_check(self, request):
        checked = self._mt5.order_check(_wire(self._mt5, request))
        return None if checked is None else checked._asdict()

    def order_send(self, request):
        result = self._mt5.order_send(_wire(self._mt5, request))
        return None if result is None else result._asdict()


def _wire(mt5: Any, request: dict[str, Any]) -> dict[str, Any]:
    side = mt5.ORDER_TYPE_BUY if request["type"] == "buy" else mt5.ORDER_TYPE_SELL
    payload = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": request["symbol"],
        "volume": float(request["volume"]),
        "type": side,
        "magic": request.get("magic", MAGIC),
        "deviation": 20,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": request.get("type_filling", mt5.ORDER_FILLING_IOC),
    }
    if request["type"] == "buy":
        tick = mt5.symbol_info_tick(request["symbol"])
        payload["price"] = tick.ask
        payload["sl"] = float(request["sl"])
        payload["tp"] = float(request["tp"])
    else:
        tick = mt5.symbol_info_tick(request["symbol"])
        payload["price"] = tick.bid
        payload["position"] = request.get("position")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
