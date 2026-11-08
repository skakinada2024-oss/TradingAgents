"""In-process paper ledger. No broker and no network."""

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tradingagents.paper_sim import (
    STARTING_CASH,
    Bar,
    Book,
    Intent,
    LedgerRejected,
    LiveFlagRefused,
    fixture_bars,
    fixture_round_trip,
    main as paper_main,
    run_batch,
)


def _now() -> datetime:
    return datetime(2026, 11, 8, 4, 45, tzinfo=UTC)


def _apply(tmp_path: Path, intents, bars=None, as_of=date(2026, 11, 8), cash=STARTING_CASH):
    book = Book(tmp_path, starting_cash=cash)
    bars = fixture_bars() if bars is None else bars
    rows = [book.apply(intent, bars, as_of, _now()) for intent in intents]
    return book, rows


def test_fixture_round_trip_is_next_bar_and_cash_funded(tmp_path):
    book, rows = _apply(tmp_path, fixture_round_trip())
    assert [row["status"] for row in rows] == ["filled", "filled"]
    assert rows[0]["fill_date"] == "2026-11-03"
    assert rows[0]["signal_date"] == "2026-11-02"
    assert rows[1]["fill_date"] == "2026-11-05"
    assert rows[1]["signal_source"] == "fixture_not_a_model"
    assert book.position == 0
    assert book.cash > 0
    assert Decimal(rows[0]["fill_price"]) > Decimal(rows[0]["raw_open"])
    assert Decimal(rows[1]["fill_price"]) < Decimal(rows[1]["raw_open"])
    assert rows[0]["recorded_at_america_los_angeles"] == "2026-11-07T20:45:00-08:00"


def test_replay_does_not_fill_twice(tmp_path):
    book, first = _apply(tmp_path, fixture_round_trip())
    cash = book.cash
    again = [book.apply(intent, fixture_bars(), date(2026, 11, 8), _now()) for intent in fixture_round_trip()]
    assert [row["status"] for row in again] == ["idempotent_skip", "idempotent_skip"]
    assert book.cash == cash
    assert book.position == 0
    assert [row["status"] for row in first] == ["filled", "filled"]


def test_restart_loads_the_same_book(tmp_path):
    book, _rows = _apply(tmp_path, fixture_round_trip())
    restored = Book(tmp_path)
    assert restored.cash == book.cash
    assert restored.position == 0
    skipped = restored.apply(fixture_round_trip()[0], fixture_bars(), date(2026, 11, 8), _now())
    assert skipped["status"] == "idempotent_skip"


def test_hold_batch_does_not_invent_a_trade(tmp_path):
    audit = run_batch(tmp_path, as_of=date(2026, 11, 8))
    assert audit["simulated_execution"] is True
    assert audit["execution_permitted"] is False
    assert audit["broker_order_submission"] == "absent"
    assert audit["research_signal"]["rating"] == "Hold"
    assert audit["research_signal"]["orders"] == 0
    assert audit["books"]["research_hold"]["fills"] == 0
    assert audit["books"]["research_hold"]["cash"] == "10000.00"
    assert audit["books"]["fixture_round_trip"]["fills"] == 2
    assert audit["fixture_replay_fills_added"] == 0
    assert audit["books"]["deterministic_baseline_not_ai"]["fills"] == 2
    assert audit["market_session"] == "weekend_closed"
    text = Path(audit["books"]["fixture_round_trip"]["ledger_csv"]).read_text(encoding="utf-8")
    assert "fixture_not_a_model" in text
    assert "deterministic_baseline_not_ai" in Path(
        audit["books"]["deterministic_baseline_not_ai"]["ledger_csv"]
    ).read_text(encoding="utf-8")


def test_same_bar_missing_duplicate_order_and_stale_are_refused(tmp_path):
    bars = fixture_bars()
    one = [bars[0]]
    book = Book(tmp_path / "one")
    row = book.apply(
        Intent("only", "AAPL", "buy", bars[0].session, "fixture_not_a_model"),
        one,
        date(2026, 11, 8),
        _now(),
    )
    assert row["status"] == "no_next_bar"
    assert book.position == 0
    with pytest.raises(LedgerRejected) as caught:
        Book(tmp_path / "dup").apply(
            fixture_round_trip()[0],
            [bars[0], Bar(bars[0].session, Decimal("100"), Decimal("101"), "dup")],
            date(2026, 11, 8),
            _now(),
        )
    assert caught.value.code == "duplicate_bar"
    with pytest.raises(LedgerRejected) as caught:
        Book(tmp_path / "order").apply(
            fixture_round_trip()[0],
            [bars[1], bars[0]],
            date(2026, 11, 8),
            _now(),
        )
    assert caught.value.code == "out_of_order"
    with pytest.raises(LedgerRejected) as caught:
        Book(tmp_path / "stale").apply(
            fixture_round_trip()[0],
            bars,
            date(2026, 12, 31),
            _now(),
        )
    assert caught.value.code == "stale_prices"


def test_cash_oversell_and_unsupported_shapes_are_refused(tmp_path):
    bars = fixture_bars()
    as_of = date(2026, 11, 8)
    poor = Book(tmp_path / "poor", starting_cash=Decimal("1.00"))
    row = poor.apply(fixture_round_trip()[0], bars, as_of, _now())
    assert row["status"] == "insufficient_cash"
    assert poor.cash == Decimal("1.00")
    flat = Book(tmp_path / "flat")
    row = flat.apply(fixture_round_trip()[1], bars, as_of, _now())
    assert row["status"] == "oversell"
    assert flat.position == 0
    for intent, code in (
        (Intent("x", "MSFT", "buy", bars[0].session, "fixture_not_a_model"), "unsupported_symbol"),
        (Intent("y", "AAPL", "buy", bars[0].session, "fixture_not_a_model", asset_type="option"), "unsupported_asset"),
        (Intent("z", "AAPL", "buy", bars[0].session, "fixture_not_a_model", leverage=Decimal("2")), "unsupported_leverage"),
        (Intent("s", "AAPL", "short", bars[0].session, "fixture_not_a_model"), "unsupported_side"),
    ):
        with pytest.raises(LedgerRejected) as caught:
            Book(tmp_path / code).apply(intent, bars, as_of, _now())
        assert caught.value.code == code


def test_conflicting_duplicate_id_is_refused(tmp_path):
    book, _rows = _apply(tmp_path, fixture_round_trip()[:1])
    clash = Intent("fixture-buy-2026-11-02", "AAPL", "sell", date(2026, 11, 2), "fixture_not_a_model")
    with pytest.raises(LedgerRejected) as caught:
        book.apply(clash, fixture_bars(), date(2026, 11, 8), _now())
    assert caught.value.code == "duplicate_conflict"


def test_live_flag_is_refused():
    with pytest.raises(LiveFlagRefused):
        paper_main(["--output", "/tmp/unused-paper", "--live"])


def test_module_does_not_call_a_broker_or_model_api():
    source = Path("tradingagents/paper_sim.py").read_text(encoding="utf-8").lower()
    for token in ("alpaca", "ccxt", "paper-api", "api.x.ai", "xai_api_key"):
        assert token not in source
