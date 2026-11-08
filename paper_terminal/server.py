"""Localhost UI for the in-process paper ledger.

Accounting stays in ``tradingagents.paper_sim``. This process only starts a
bounded batch, reads the files that batch wrote, and serves them. It does not
accept filesystem paths or shell commands from the browser.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from tradingagents.paper_sim import (
    BOOK_NAMES,
    FEE_RATE,
    MAX_ALLOCATION,
    SLIPPAGE_RATE,
    STARTING_CASH,
    run_batch,
)

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
RUN_ID = re.compile(r"^[a-f0-9]{32}$")
INDEX = Path(__file__).resolve().parent / "index.html"
MAX_BODY = 4096

BOOK_LABELS = {
    "research_hold": "Research Hold",
    "fixture_round_trip": "Fixture round trip",
    "deterministic_baseline_not_ai": "Scripted baseline",
}


class TerminalError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def assert_loopback(host: str) -> str:
    if host != HOST:
        raise TerminalError(400, "the terminal binds to 127.0.0.1 only")
    return host


def _run_dir(root: Path, run_id: str) -> Path:
    if not RUN_ID.fullmatch(run_id or ""):
        raise TerminalError(404, "unknown run")
    path = (root / run_id).resolve()
    if path.parent != root.resolve() or not path.is_dir():
        raise TerminalError(404, "unknown run")
    return path


def _read_audit(path: Path) -> dict[str, Any]:
    audit_path = path / "audit.json"
    if not audit_path.is_file():
        raise TerminalError(404, "unknown run")
    return json.loads(audit_path.read_text(encoding="utf-8"))


def _ledger_rows(path: Path, book: str) -> list[dict[str, str]]:
    csv_path = path / book / "ledger.csv"
    if not csv_path.is_file():
        return []
    import csv

    with csv_path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _equity_points(starting: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    points = [{"label": "start", "equity": starting, "status": "starting_cash"}]
    for row in rows:
        if row.get("status") == "filled" and row.get("equity_after"):
            points.append({
                "label": row.get("fill_date") or row.get("signal_date") or "",
                "equity": row["equity_after"],
                "status": "filled",
            })
    return points


def _stages(audit: dict[str, Any], book: str) -> list[dict[str, str]]:
    info = audit["books"][book]
    fills = int(info["fills"])
    source = ""
    if book == "research_hold":
        signal_state = "mock"
        signal_detail = (
            f"Mock completion rating {audit['research_signal']['rating']}. "
            "No model was called."
        )
    elif book == "fixture_round_trip":
        signal_state = "synthetic"
        signal_detail = "Fixture buy and sell. Not a model and not a market forecast."
        source = "fixture_not_a_model"
    else:
        signal_state = "scripted"
        signal_detail = "Scripted buy then sell. Not AI."
        source = "deterministic_baseline_not_ai"
    executor_state = "executed" if fills else "no_orders"
    executor_detail = (
        f"{fills} simulated fill(s)." if fills else "No order was created."
    )
    return [
        {
            "id": "scout",
            "title": "Scout",
            "state": "disabled",
            "detail": "This simulator does not scan a market.",
        },
        {
            "id": "filter",
            "title": "Filter",
            "state": "rule",
            "detail": "Ledger allowlist is AAPL stock, long-only, whole shares. Other assets are refused.",
        },
        {
            "id": "signal",
            "title": "Signal",
            "state": signal_state,
            "detail": signal_detail if not source else f"{signal_detail} Source {source}.",
        },
        {
            "id": "executor",
            "title": "Executor",
            "state": executor_state,
            "detail": executor_detail + " Fills stay inside this process.",
        },
        {
            "id": "risk",
            "title": "Risk",
            "state": "rule",
            "detail": (
                "execution_permitted is false. "
                f"Max allocation {audit['max_allocation']}. "
                f"Fee rate {audit['fee_rate']}. Slippage rate {audit['slippage_rate']}."
            ),
        },
        {
            "id": "logger",
            "title": "Logger",
            "state": "executed",
            "detail": "The ledger CSV and audit.json are the files this run wrote.",
        },
    ]


def view_run(root: Path, run_id: str) -> dict[str, Any]:
    path = _run_dir(root, run_id)
    audit = _read_audit(path)
    selected = audit.get("selected_books") or list(audit["books"])
    book = selected[0]
    rows = _ledger_rows(path, book)
    info = audit["books"][book]
    return {
        "id": run_id,
        "book": book,
        "book_label": BOOK_LABELS.get(book, book),
        "simulated_execution": audit["simulated_execution"],
        "execution_permitted": audit["execution_permitted"],
        "market_session": audit["market_session"],
        "fills_are": audit["fills_are"],
        "as_of": audit["as_of"],
        "recorded_at_utc": audit["recorded_at_utc"],
        "recorded_at_america_los_angeles": audit["recorded_at_america_los_angeles"],
        "starting_cash_usd": audit["starting_cash_usd"],
        "cash": info["cash"],
        "position": info["position"],
        "equity": info["equity"],
        "orders": info["orders"],
        "fills": info["fills"],
        "fee_rate": audit["fee_rate"],
        "slippage_rate": audit["slippage_rate"],
        "max_allocation": audit["max_allocation"],
        "fill_rule": audit["fill_rule"],
        "price_source": audit["price_source"],
        "research_signal": audit["research_signal"],
        "known_limits": audit["known_limits"],
        "stages": _stages(audit, book),
        "equity_points": _equity_points(audit["starting_cash_usd"], rows),
        "ledger": rows,
        "git_head": audit.get("git_head"),
    }


def list_runs(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    found = []
    for path in sorted(root.iterdir()):
        if not RUN_ID.fullmatch(path.name) or not (path / "audit.json").is_file():
            continue
        view = view_run(root, path.name)
        found.append({
            "id": view["id"],
            "book": view["book"],
            "book_label": view["book_label"],
            "cash": view["cash"],
            "equity": view["equity"],
            "fills": view["fills"],
            "recorded_at_america_los_angeles": view["recorded_at_america_los_angeles"],
        })
    return found


def create_run(root: Path, book: str) -> dict[str, Any]:
    if book not in BOOK_NAMES:
        raise TerminalError(400, "choose a known simulation book")
    import uuid

    root.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    run_batch(root / run_id, books=(book,))
    return view_run(root, run_id)


def reset_run(root: Path, run_id: str) -> None:
    path = _run_dir(root, run_id)
    shutil.rmtree(path)


def meta() -> dict[str, Any]:
    return {
        "name": "Paper Trading Terminal",
        "symbol": "AAPL",
        "currency": "USD",
        "simulated_execution": True,
        "execution_permitted": False,
        "broker_order_submission": "absent",
        "starting_cash_usd": format(STARTING_CASH, "f"),
        "max_allocation": format(MAX_ALLOCATION, "f"),
        "fee_rate": format(FEE_RATE, "f"),
        "slippage_rate": format(SLIPPAGE_RATE, "f"),
        "fill_rule": "next bar open; same-bar fills refused",
        "price_source": "fixture synthetic AAPL bars 2026-11-02 through 2026-11-06",
        "books": [
            {"id": name, "label": BOOK_LABELS[name]} for name in BOOK_NAMES
        ],
        "labels": [
            "virtual dollars",
            "simulated fills",
            "mock or synthetic signals",
            "not a broker",
            "not a live session",
        ],
    }


def dispatch(method: str, path: str, body: bytes, root: Path, lock: threading.Lock) -> tuple[int, str, bytes, str | None]:
    """Return status, content type, body, and optional download name."""
    parsed = urlparse(path)
    parts = [part for part in parsed.path.split("/") if part]
    try:
        if method == "GET" and parsed.path in {"/", "/index.html"}:
            return 200, "text/html; charset=utf-8", INDEX.read_bytes(), None
        if method == "GET" and parsed.path == "/api/meta":
            return 200, "application/json; charset=utf-8", json.dumps(meta()).encode(), None
        if method == "GET" and parsed.path == "/api/runs":
            payload = {"runs": list_runs(root)}
            return 200, "application/json; charset=utf-8", json.dumps(payload).encode(), None
        if method == "GET" and len(parts) == 3 and parts[:2] == ["api", "runs"]:
            return 200, "application/json; charset=utf-8", json.dumps(view_run(root, parts[2])).encode(), None
        if method == "GET" and len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] in {"ledger.csv", "audit.json"}:
            folder = _run_dir(root, parts[2])
            audit = _read_audit(folder)
            book = (audit.get("selected_books") or list(audit["books"]))[0]
            target = folder / "audit.json" if parts[3] == "audit.json" else folder / book / "ledger.csv"
            resolved = target.resolve()
            resolved.relative_to(folder.resolve())
            if not resolved.is_file():
                raise TerminalError(404, "file is not in this run")
            kind = "text/csv; charset=utf-8" if parts[3].endswith(".csv") else "application/json; charset=utf-8"
            return 200, kind, resolved.read_bytes(), parts[3]
        if method == "POST" and parsed.path == "/api/runs":
            if len(body) > MAX_BODY:
                raise TerminalError(400, "request body is too large")
            try:
                payload = json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise TerminalError(400, "send a JSON object with a book name") from exc
            if not isinstance(payload, dict):
                raise TerminalError(400, "send a JSON object with a book name")
            book = payload.get("book")
            if not isinstance(book, str) or set(payload) - {"book"}:
                raise TerminalError(400, "send only a book name")
            with lock:
                view = create_run(root, book)
            return 200, "application/json; charset=utf-8", json.dumps(view).encode(), None
        if method == "DELETE" and len(parts) == 3 and parts[:2] == ["api", "runs"]:
            with lock:
                reset_run(root, parts[2])
            return 200, "application/json; charset=utf-8", json.dumps({"reset": True}).encode(), None
        if method == "GET":
            raise TerminalError(404, "not found")
        raise TerminalError(404, "not found")
    except TerminalError as exc:
        return exc.status, "application/json; charset=utf-8", json.dumps({"error": exc.message}).encode(), None
    except ValueError:
        return 404, "application/json; charset=utf-8", json.dumps({"error": "file is not in this run"}).encode(), None


def _handler(root: Path, lock: threading.Lock):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            detail = fmt % args if args else fmt
            sys.stderr.write(f"{self.address_string()} - {detail}\n")

        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length < 0 or length > MAX_BODY:
                status, content_type, body, filename = 400, "application/json; charset=utf-8", b'{"error":"request body is too large"}', None
            else:
                raw = self.rfile.read(length) if length else b""
                status, content_type, body, filename = dispatch(self.command, self.path, raw, root, lock)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; connect-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'",
            )
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            self._serve()

        def do_POST(self) -> None:  # noqa: N802
            self._serve()

        def do_DELETE(self) -> None:  # noqa: N802
            self._serve()

    return Handler


def serve(host: str, port: int, runs_dir: Path) -> ThreadingHTTPServer:
    host = assert_loopback(host)
    if port != 0 and not 1 <= port <= 65535:
        raise TerminalError(400, "port is out of range")
    runs_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), _handler(runs_dir.resolve(), threading.Lock()))
    return server


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Paper Trading Terminal on localhost.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Directory this process creates for runs. The browser cannot choose it.",
    )
    args = parser.parse_args(argv)
    runs = Path(args.runs_dir) if args.runs_dir else Path.cwd() / "paper_terminal_runs"
    try:
        server = serve(HOST, args.port, runs)
    except TerminalError as exc:
        print(exc.message, file=sys.stderr)
        return 2
    print(f"Paper Trading Terminal at http://{HOST}:{server.server_address[1]}/", flush=True)
    print("Virtual dollars only. No broker. Ctrl-C stops the process.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        server.server_close()
    return 0
