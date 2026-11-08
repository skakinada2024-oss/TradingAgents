"""In-process simulated ledger. It does not call a broker or a model.

``simulated_execution`` is true only for this accounting book.
``execution_permitted`` stays false: nothing is submitted to a broker.
``--live`` is refused. One batch writes its files and returns.

Fills use the next bar's open. The signal bar is not the fill bar.
Prices and signals in the fixture book are synthetic. They are not a
Grok result and not a live weekend fill.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tradingagents.agents.rating import parse_rating
from tradingagents.research_stage import MOCK_DECISION, deterministic_gate

PACIFIC = ZoneInfo("America/Los_Angeles")
CENT = Decimal("0.01")
PRICE_QUANTUM = Decimal("0.0001")
STARTING_CASH = Decimal("10000.00")
MAX_ALLOCATION = Decimal("0.10")
FEE_RATE = Decimal("0.0001")  # 1 bp of notional, example assumption
SLIPPAGE_RATE = Decimal("0.0005")  # 5 bp adverse, example assumption
ALLOWED_SYMBOLS = frozenset({"AAPL"})
STALE_CALENDAR_DAYS = 10


class LiveFlagRefused(RuntimeError):
    """``--live`` is refused. This ledger is not a broker session."""


class LedgerRejected(Exception):
    """One input was not applied. The book is unchanged for that input."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _price(value: Decimal) -> Decimal:
    return value.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def _d(value: Decimal | str | int) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class Bar:
    session: date
    open: Decimal
    close: Decimal
    source_id: str


@dataclass(frozen=True)
class Intent:
    client_order_id: str
    symbol: str
    side: str
    signal_date: date
    source: str
    asset_type: str = "stock"
    leverage: Decimal = Decimal("1")


def validate_bars(bars: list[Bar], as_of: date) -> None:
    if not bars:
        raise LedgerRejected("missing_prices", "no bars")
    previous: date | None = None
    seen: set[date] = set()
    for bar in bars:
        if bar.session in seen:
            raise LedgerRejected("duplicate_bar", bar.session.isoformat())
        seen.add(bar.session)
        if previous is not None and bar.session <= previous:
            raise LedgerRejected("out_of_order", bar.session.isoformat())
        previous = bar.session
        if bar.open <= 0 or bar.close <= 0:
            raise LedgerRejected("missing_price", bar.session.isoformat())
    last = bars[-1].session
    if (as_of - last).days > STALE_CALENDAR_DAYS:
        raise LedgerRejected(
            "stale_prices",
            f"last bar {last.isoformat()} is more than {STALE_CALENDAR_DAYS} days before {as_of.isoformat()}",
        )
    if last > as_of:
        raise LedgerRejected("future_bar", last.isoformat())


def _index(bars: list[Bar]) -> dict[date, int]:
    return {bar.session: index for index, bar in enumerate(bars)}


def _fill_price(side: str, open_price: Decimal) -> Decimal:
    if side == "buy":
        return _price(open_price * (Decimal("1") + SLIPPAGE_RATE))
    if side == "sell":
        return _price(open_price * (Decimal("1") - SLIPPAGE_RATE))
    raise LedgerRejected("unsupported_side", side)


class Book:
    """Cash and whole shares. State is rewritten after every applied event."""

    def __init__(self, path: Path, starting_cash: Decimal = STARTING_CASH):
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)
        self.state_path = path / "state.json"
        self.csv_path = path / "ledger.csv"
        self.cash = _money(starting_cash)
        self.position = 0
        self.symbol: str | None = None
        self.applied: dict[str, dict[str, Any]] = {}
        self.rows: list[dict[str, str]] = []
        if self.state_path.exists():
            self._load()

    def _load(self) -> None:
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.cash = Decimal(payload["cash"])
        self.position = int(payload["position"])
        self.symbol = payload.get("symbol")
        self.applied = payload.get("applied", {})
        if self.csv_path.exists():
            with self.csv_path.open(encoding="utf-8", newline="") as handle:
                self.rows = list(csv.DictReader(handle))

    def _save(self) -> None:
        payload = {
            "cash": format(self.cash, "f"),
            "position": self.position,
            "symbol": self.symbol,
            "applied": self.applied,
            "simulated_execution": True,
            "execution_permitted": False,
        }
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.state_path)
        with self.csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=list(CSV_FIELDS),
            )
            writer.writeheader()
            writer.writerows(self.rows)

    def equity(self, mark: Decimal) -> Decimal:
        return _money(self.cash + (Decimal(self.position) * mark))

    def persist(self) -> None:
        self._save()

    def apply(self, intent: Intent, bars: list[Bar], as_of: date, recorded_at: datetime) -> dict[str, str]:
        validate_bars(bars, as_of)
        self._reject_unsupported(intent)
        if intent.client_order_id in self.applied:
            previous = self.applied[intent.client_order_id]
            if previous.get("fingerprint") != _fingerprint(intent):
                raise LedgerRejected("duplicate_conflict", intent.client_order_id)
            return {"status": "idempotent_skip", "client_order_id": intent.client_order_id}
        try:
            row = self._fill(intent, bars, recorded_at)
        except LedgerRejected as exc:
            row = self._row(intent, recorded_at, status=exc.code, note=exc.detail)
            self.rows.append(row)
            self.applied[intent.client_order_id] = {
                "fingerprint": _fingerprint(intent),
                "status": exc.code,
            }
            self._save()
            return row
        self.rows.append(row)
        self.applied[intent.client_order_id] = {
            "fingerprint": _fingerprint(intent),
            "status": "filled",
        }
        self._save()
        return row

    def _reject_unsupported(self, intent: Intent) -> None:
        if intent.asset_type != "stock":
            raise LedgerRejected("unsupported_asset", intent.asset_type)
        if intent.symbol not in ALLOWED_SYMBOLS:
            raise LedgerRejected("unsupported_symbol", intent.symbol)
        if intent.side not in {"buy", "sell"}:
            raise LedgerRejected("unsupported_side", intent.side)
        if intent.leverage != Decimal("1"):
            raise LedgerRejected("unsupported_leverage", str(intent.leverage))

    def _fill(self, intent: Intent, bars: list[Bar], recorded_at: datetime) -> dict[str, str]:
        located = _index(bars)
        if intent.signal_date not in located:
            raise LedgerRejected("missing_signal_bar", intent.signal_date.isoformat())
        index = located[intent.signal_date]
        if index + 1 >= len(bars):
            raise LedgerRejected("no_next_bar", "same-bar and end-of-series fills are refused")
        signal_bar = bars[index]
        fill_bar = bars[index + 1]
        if fill_bar.session <= signal_bar.session:
            raise LedgerRejected("same_bar", fill_bar.session.isoformat())
        fill = _fill_price(intent.side, fill_bar.open)
        mark = signal_bar.close
        equity = self.equity(mark)
        if intent.side == "buy":
            budget = _money(min(self.cash, equity * MAX_ALLOCATION))
            quantity = int((budget / fill).to_integral_value(rounding=ROUND_DOWN))
            if quantity < 1:
                raise LedgerRejected("insufficient_cash", f"budget {budget} cannot buy one share at {fill}")
            notional = _money(Decimal(quantity) * fill)
            fee = _money(notional * FEE_RATE)
            cost = notional + fee
            if cost > self.cash:
                raise LedgerRejected("insufficient_cash", f"cost {cost} exceeds cash {self.cash}")
            self.cash = _money(self.cash - cost)
            self.position += quantity
            self.symbol = intent.symbol
        else:
            quantity = self.position
            if quantity < 1:
                raise LedgerRejected("oversell", "no long shares to sell")
            notional = _money(Decimal(quantity) * fill)
            fee = _money(notional * FEE_RATE)
            self.cash = _money(self.cash + notional - fee)
            self.position = 0
        return self._row(
            intent,
            recorded_at,
            status="filled",
            note="next-bar open; example fee and slippage; not a broker fill",
            quantity=quantity,
            raw_open=fill_bar.open,
            fill_price=fill,
            fee=fee,
            fill_date=fill_bar.session,
            price_source=fill_bar.source_id,
            equity=self.equity(fill_bar.close),
        )

    def _row(
        self,
        intent: Intent,
        recorded_at: datetime,
        *,
        status: str,
        note: str,
        quantity: int = 0,
        raw_open: Decimal | None = None,
        fill_price: Decimal | None = None,
        fee: Decimal | None = None,
        fill_date: date | None = None,
        price_source: str = "",
        equity: Decimal | None = None,
    ) -> dict[str, str]:
        local = recorded_at.astimezone(PACIFIC)
        marked = equity if equity is not None else self.cash
        return {
            "recorded_at_utc": recorded_at.astimezone(UTC).isoformat(),
            "recorded_at_america_los_angeles": local.isoformat(),
            "client_order_id": intent.client_order_id,
            "symbol": intent.symbol,
            "side": intent.side,
            "status": status,
            "signal_date": intent.signal_date.isoformat(),
            "fill_date": "" if fill_date is None else fill_date.isoformat(),
            "signal_source": intent.source,
            "price_source": price_source,
            "quantity": str(quantity),
            "raw_open": "" if raw_open is None else format(raw_open, "f"),
            "fill_price": "" if fill_price is None else format(fill_price, "f"),
            "fee_usd": "" if fee is None else format(fee, "f"),
            "slippage_rate": format(SLIPPAGE_RATE, "f"),
            "fee_rate": format(FEE_RATE, "f"),
            "cash_after": format(self.cash, "f"),
            "position_after": str(self.position),
            "equity_after": format(marked, "f"),
            "note": note,
        }


CSV_FIELDS = (
    "recorded_at_utc",
    "recorded_at_america_los_angeles",
    "client_order_id",
    "symbol",
    "side",
    "status",
    "signal_date",
    "fill_date",
    "signal_source",
    "price_source",
    "quantity",
    "raw_open",
    "fill_price",
    "fee_usd",
    "slippage_rate",
    "fee_rate",
    "cash_after",
    "position_after",
    "equity_after",
    "note",
)


def _fingerprint(intent: Intent) -> str:
    return "|".join([
        intent.symbol,
        intent.side,
        intent.signal_date.isoformat(),
        intent.source,
        intent.asset_type,
        format(intent.leverage, "f"),
    ])


def fixture_bars() -> list[Bar]:
    """Synthetic weekday bars. Not vendor prices and not a model forecast."""
    raw = (
        (date(2026, 11, 2), "100", "101"),
        (date(2026, 11, 3), "102", "103"),
        (date(2026, 11, 4), "104", "105"),
        (date(2026, 11, 5), "106", "107"),
        (date(2026, 11, 6), "108", "109"),
    )
    return [
        Bar(session, Decimal(open_), Decimal(close), f"fixture:AAPL:{session.isoformat()}")
        for session, open_, close in raw
    ]


def fixture_round_trip() -> list[Intent]:
    return [
        Intent("fixture-buy-2026-11-02", "AAPL", "buy", date(2026, 11, 2), "fixture_not_a_model"),
        Intent("fixture-sell-2026-11-04", "AAPL", "sell", date(2026, 11, 4), "fixture_not_a_model"),
    ]


def baseline_intents() -> list[Intent]:
    """One buy and one later sell. The rule is the script, not a model."""
    return [
        Intent("baseline-buy-2026-11-02", "AAPL", "buy", date(2026, 11, 2), "deterministic_baseline_not_ai"),
        Intent("baseline-sell-2026-11-05", "AAPL", "sell", date(2026, 11, 5), "deterministic_baseline_not_ai"),
    ]


def research_hold_intents() -> tuple[str, list[Intent]]:
    """The stage-1 mock completion. Hold does not create an order."""
    rating = parse_rating(MOCK_DECISION)
    if rating not in {"Buy", "Sell"}:
        return rating, []
    side = "buy" if rating == "Buy" else "sell"
    return rating, [
        Intent(
            f"research-{side}-mock",
            "AAPL",
            side,
            date(2026, 11, 6),
            "stage1_mock_completion",
        )
    ]


def _git_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip()


def _run_book(path: Path, intents: list[Intent], bars: list[Bar], as_of: date, now: datetime) -> dict[str, Any]:
    book = Book(path)
    results = [book.apply(intent, bars, as_of, now) for intent in intents]
    book.persist()
    fills = [row for row in results if row.get("status") == "filled"]
    return {
        "cash": format(book.cash, "f"),
        "position": book.position,
        "equity": format(book.equity(bars[-1].close), "f"),
        "orders": len(intents),
        "fills": len(fills),
        "results": results,
        "ledger_csv": str(book.csv_path),
        "state_json": str(book.state_path),
    }


def run_batch(output_dir: Path | str, as_of: date | None = None) -> dict[str, Any]:
    """One bounded batch. Weekend as-of does not create a live session fill."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    session_as_of = as_of or now.astimezone(PACIFIC).date()
    bars = fixture_bars()
    rating, hold_intents = research_hold_intents()
    gate = deterministic_gate(rating)
    books = {
        "research_hold": _run_book(output / "research_hold", hold_intents, bars, session_as_of, now),
        "fixture_round_trip": _run_book(
            output / "fixture_round_trip", fixture_round_trip(), bars, session_as_of, now
        ),
        "deterministic_baseline_not_ai": _run_book(
            output / "deterministic_baseline_not_ai", baseline_intents(), bars, session_as_of, now
        ),
    }
    # Replay the fixture book once. A second apply must not add fills.
    replay = _run_book(output / "fixture_round_trip", fixture_round_trip(), bars, session_as_of, now)
    audit = {
        "mode": "in_process_paper_simulation",
        "simulated_execution": True,
        "execution_permitted": gate["execution_permitted"],
        "broker_order_submission": "absent",
        "market_session": "weekend_closed" if session_as_of.weekday() >= 5 else "not_a_live_session",
        "fills_are": "simulated_on_fixture_bars_not_a_live_or_broker_fill",
        "as_of": session_as_of.isoformat(),
        "recorded_at_utc": now.isoformat(),
        "recorded_at_america_los_angeles": now.astimezone(PACIFIC).isoformat(),
        "git_head": _git_head(),
        "starting_cash_usd": format(STARTING_CASH, "f"),
        "max_allocation": format(MAX_ALLOCATION, "f"),
        "fee_rate": format(FEE_RATE, "f"),
        "slippage_rate": format(SLIPPAGE_RATE, "f"),
        "fill_rule": "next bar open; same-bar fills refused",
        "price_source": "fixture synthetic AAPL bars 2026-11-02 through 2026-11-06",
        "research_signal": {
            "source": "tradingagents.research_stage.MOCK_DECISION",
            "rating": rating,
            "orders": len(hold_intents),
            "label": "mock_completion_not_a_vendor_or_model_call",
        },
        "books": {
            name: {key: value for key, value in book.items() if key != "results"}
            for name, book in books.items()
        },
        "fixture_replay_fills_added": replay["fills"],
        "known_limits": [
            "Example fee of 1 bp and slippage of 5 bp are assumptions, not a broker schedule.",
            "Fixture prices are synthetic. Equity in that book is not a strategy profit.",
            "The deterministic baseline is a scripted buy then sell, not a model and not AI.",
            "The stage-1 mock signal is Hold, so that book does not trade.",
            "No Yahoo fetch and no live session in this batch. The week of 2026-11-08 is a weekend as of Sunday.",
            "Long-only whole shares of AAPL. Shorts, options, leverage, and other symbols are refused.",
            "Broker execution_permitted remains false.",
        ],
    }
    # Attach the fixture fill rows for the evidence file, without a second ledger.
    audit["fixture_results"] = books["fixture_round_trip"]["results"]
    audit["research_results"] = books["research_hold"]["results"]
    audit["baseline_results"] = books["deterministic_baseline_not_ai"]["results"]
    path = output / "audit.json"
    path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One in-process paper batch. No broker.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD. Default is the current Pacific date.")
    parser.add_argument("--live", action="store_true", help="Refused. Not a broker session.")
    args = parser.parse_args(argv)
    if args.live:
        raise LiveFlagRefused("Refusing --live. This ledger does not submit orders.")
    as_of = None if args.as_of is None else datetime.strptime(args.as_of, "%Y-%m-%d").date()
    audit = run_batch(args.output, as_of)
    print(json.dumps({
        "mode": audit["mode"],
        "simulated_execution": audit["simulated_execution"],
        "execution_permitted": audit["execution_permitted"],
        "recorded_at_america_los_angeles": audit["recorded_at_america_los_angeles"],
        "research_rating": audit["research_signal"]["rating"],
        "research_orders": audit["research_signal"]["orders"],
        "fixture_fills": audit["books"]["fixture_round_trip"]["fills"],
        "fixture_cash": audit["books"]["fixture_round_trip"]["cash"],
        "fixture_equity": audit["books"]["fixture_round_trip"]["equity"],
        "baseline_fills": audit["books"]["deterministic_baseline_not_ai"]["fills"],
        "audit": str(Path(args.output) / "audit.json"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LiveFlagRefused as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
