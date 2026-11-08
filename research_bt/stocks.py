"""Whole-share check at a dated price. Yahoo does not publish a share increment."""

from __future__ import annotations


def whole_share_check(
    price: float,
    stop: float | None,
    commission: float,
    slip: float,
    cash: float = 100.0,
    risk: float = 0.50,
) -> dict:
    """One share against cash and against the planned stop, including both cost sides.

    A 10 percent allocation is not used. Fractional size is not assumed: this source
    has no share-increment field.
    """
    entry = price * (1.0 + slip)
    fee_in = entry * commission
    one_share_cash = entry + fee_in
    planned = None
    if stop is not None and 0 < stop < price:
        exit_fill = stop * (1.0 - slip)
        planned = (entry - exit_fill) + fee_in + exit_fill * commission
    return {
        "price": price,
        "stop": stop,
        "one_share_cash_out": one_share_cash,
        "planned_loss_one_share": planned,
        "cash_rejects_one_share": one_share_cash > cash + 1e-9,
        "risk_rejects_one_share": planned is None or planned > risk + 1e-9,
        "fractional_share_metadata": "absent_from_price_source",
        "allocation_cap_used": False,
    }
