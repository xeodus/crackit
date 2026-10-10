"""Explicit measurement definitions for the feasibility lab."""

import math
import re
from decimal import Decimal
from typing import Iterable, List


def percentile(values: Iterable[float], p: float) -> float:
    """Nearest-rank percentile. Reports must include sample count."""
    items = sorted(values)
    if not items or not 0 < p <= 100:
        raise ValueError("Nonempty samples and percentile 0 < p <= 100 required")
    return items[max(0, math.ceil(len(items) * p / 100) - 1)]


def words(text: str) -> List[str]:
    return re.findall(r"[^\W_]+", text.lower(), re.UNICODE)


def word_error_rate(reference: str, hypothesis: str) -> dict:
    ref, hyp = words(reference), words(hypothesis)
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (r != h)))
        previous = current
    edits = previous[-1]
    # Empty reference with insertions has no meaningful finite normalized WER.
    return {"edits": edits, "reference_words": len(ref), "hypothesis_words": len(hyp),
            "wer": edits / len(ref) if ref else (0.0 if not hyp else None),
            "normalization": "Unicode words, lowercase; no spoken-number normalization"}


def token_cost(input_tokens: int, output_tokens: int,
               input_per_million: str, output_per_million: str) -> Decimal:
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Usage must be nonnegative")
    prices = (Decimal(input_per_million), Decimal(output_per_million))
    if any(not v.is_finite() or v < 0 for v in prices):
        raise ValueError("Prices must be finite and nonnegative")
    return (input_tokens * prices[0] + output_tokens * prices[1]) / Decimal(1_000_000)


def audio_cost(billable_seconds: str, stream_multiplier: int, hourly_rate: str) -> Decimal:
    seconds, rate = Decimal(billable_seconds), Decimal(hourly_rate)
    if (not seconds.is_finite() or seconds < 0 or not rate.is_finite()
            or rate < 0 or stream_multiplier < 1):
        raise ValueError("Invalid billable audio usage")
    return seconds * stream_multiplier * rate / Decimal(3600)
