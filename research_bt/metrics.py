"""Summaries. Missing trades are N/A, never an infinite profit factor."""

from __future__ import annotations


def _completed(trades: list[dict]) -> list[dict]:
    buys = {}
    done = []
    for trade in trades:
        if trade["side"] == "buy":
            buys[trade["time"]] = trade
        elif trade["side"] == "sell":
            entry = buys.get(trade["entry_time"])
            if entry is None:
                continue
            pnl = trade.get("pnl")
            if pnl is None:
                pnl = trade["cash_delta"] + entry["cash_delta"]
            done.append({
                "pnl": pnl,
                "hold_hours": (trade["time"] - entry["time"]) / 3600,
            })
    return done


def summarize(result, start_cash: float, bars: int) -> dict:
    done = _completed(result.trades)
    end = result.equity[-1]["equity"] if result.equity else start_cash
    peak = start_cash
    max_dd = 0.0
    max_dd_pct = 0.0
    in_market = 0
    for point in result.equity:
        peak = max(peak, point["equity"])
        drawdown = peak - point["equity"]
        max_dd = max(max_dd, drawdown)
        if peak > 0:
            max_dd_pct = max(max_dd_pct, drawdown / peak)
        if point.get("in_position"):
            in_market += 1
    wins = [row["pnl"] for row in done if row["pnl"] > 0]
    losses = [row["pnl"] for row in done if row["pnl"] < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "net_return": (end / start_cash - 1.0) if start_cash else None,
        "ending_equity": end,
        "max_drawdown_usd": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "win_rate": (len(wins) / len(done)) if done else None,
        "avg_win": (sum(wins) / len(wins)) if wins else None,
        "avg_loss": (sum(losses) / len(losses)) if losses else None,
        "expectancy": (sum(row["pnl"] for row in done) / len(done)) if done else None,
        "completed_trades": len(done),
        "exposure": (in_market / bars) if bars else None,
        "avg_hold_hours": (sum(row["hold_hours"] for row in done) / len(done)) if done else None,
        "blocked_entries": result.blocked_entries,
        "session_resets": list(result.session_resets),
    }
