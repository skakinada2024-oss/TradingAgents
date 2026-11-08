"""NumPy logistic fit on closed bars. A failed or weak holdout returns HOLD.

Samples use only bars strictly before the target bar. The newest bar is
dropped when the caller says the series still contains the forming bar.
Nothing here is a claim that the fit will make money.
"""

from __future__ import annotations

from typing import Any

import numpy as np

MIN_TRAIN = 40
MIN_TEST = 20
PROBABILITY_LONG = 0.55


def drop_forming_bar(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the newest bar. copy_rates position 0 is the bar still forming."""
    if not bars:
        return []
    ordered = sorted(bars, key=lambda bar: int(bar["time"]))
    return ordered[:-1]


def _features(ordered: list[dict[str, Any]], index: int) -> np.ndarray:
    now = ordered[index]
    close = float(now["close"])
    return np.array([
        np.log(close / float(ordered[index - 1]["close"])),
        np.log(close / float(ordered[index - 5]["close"])),
        (float(now["high"]) - float(now["low"])) / close,
    ], dtype=np.float64)


def _samples(closed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(closed, key=lambda bar: int(bar["time"]))
    out = []
    for index in range(5, len(ordered) - 1):
        now = ordered[index]
        nxt = ordered[index + 1]
        close = float(now["close"])
        if int(nxt["time"]) <= int(now["time"]) or close <= 0 or float(nxt["close"]) <= 0:
            continue
        out.append({
            "feature_time": int(now["time"]),
            "target_time": int(nxt["time"]),
            "feature_close": close,
            "x": _features(ordered, index),
            "y": 1.0 if float(nxt["close"]) > close else 0.0,
        })
    return out


def _fit(x_train: np.ndarray, y_train: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std = np.where(std < 1e-12, 1.0, std)
    scaled = (x_train - mean) / std
    weights = np.zeros(scaled.shape[1] + 1, dtype=np.float64)
    for _ in range(400):
        scores = scaled @ weights[1:] + weights[0]
        probs = 1.0 / (1.0 + np.exp(-np.clip(scores, -30, 30)))
        error = probs - y_train
        grad = np.concatenate([[error.mean()], scaled.T @ error / len(y_train)])
        grad[1:] += 1e-3 * weights[1:]
        weights -= 0.2 * grad
    return weights, mean, std


def _log_loss(y_true: np.ndarray, probs: np.ndarray) -> float:
    clipped = np.clip(probs, 1e-6, 1 - 1e-6)
    return float(-(y_true * np.log(clipped) + (1 - y_true) * np.log(1 - clipped)).mean())


def _predict_row(row: np.ndarray, weights: np.ndarray, mean: np.ndarray, std: np.ndarray) -> float:
    scaled = (row - mean) / std
    score = float(scaled @ weights[1:] + weights[0])
    return float(1.0 / (1.0 + np.exp(-np.clip(score, -30, 30))))


def fit_closed_bars(closed_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Fit on the earlier samples and score the later ones. HOLD if that is not honest."""
    samples = _samples(closed_bars)
    result: dict[str, Any] = {
        "signal": "HOLD",
        "probability": None,
        "reason": "",
        "n_samples": len(samples),
        "n_train": 0,
        "n_test": 0,
        "holdout_log_loss": None,
        "baseline_log_loss": None,
        "feature_times_before_targets": all(
            sample["feature_time"] < sample["target_time"] for sample in samples
        ),
    }
    if len(samples) < MIN_TRAIN + MIN_TEST:
        result["reason"] = "insufficient_closed_history"
        return result
    split = int(len(samples) * 0.7)
    if split < MIN_TRAIN or len(samples) - split < MIN_TEST:
        result["reason"] = "insufficient_closed_history"
        return result
    train = samples[:split]
    test = samples[split + 1:]
    if len(train) < MIN_TRAIN or len(test) < MIN_TEST:
        result["reason"] = "insufficient_closed_history"
        return result
    if train[-1]["target_time"] >= test[0]["feature_time"]:
        result["reason"] = "holdout_not_chronological"
        return result
    y_train = np.array([sample["y"] for sample in train], dtype=np.float64)
    if y_train.min() == y_train.max():
        result["reason"] = "training_labels_are_a_single_class"
        return result
    weights, mean, std = _fit(
        np.vstack([sample["x"] for sample in train]),
        y_train,
    )
    test_x = np.vstack([sample["x"] for sample in test])
    test_y = np.array([sample["y"] for sample in test], dtype=np.float64)
    test_probs = np.array([
        _predict_row(row, weights, mean, std) for row in test_x
    ])
    base_rate = float(np.clip(y_train.mean(), 1e-6, 1 - 1e-6))
    model_loss = _log_loss(test_y, test_probs)
    base_loss = _log_loss(test_y, np.full(len(test_y), base_rate))
    result.update({
        "n_train": len(train),
        "n_test": len(test),
        "holdout_log_loss": model_loss,
        "baseline_log_loss": base_loss,
        "coefficients": [float(value) for value in weights],
    })
    if not np.isfinite(model_loss) or not np.isfinite(base_loss) or model_loss >= base_loss:
        result["reason"] = "holdout_not_better_than_baseline"
        return result
    live_x = _features(sorted(closed_bars, key=lambda bar: int(bar["time"])), len(closed_bars) - 1)
    probability = _predict_row(live_x, weights, mean, std)
    result["probability"] = probability
    result["live_feature_time"] = int(sorted(closed_bars, key=lambda bar: int(bar["time"]))[-1]["time"])
    result["signal"] = "LONG" if probability >= PROBABILITY_LONG else "HOLD"
    result["reason"] = "holdout_beat_baseline"
    return result
