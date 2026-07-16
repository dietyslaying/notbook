"""SM-2 spaced repetition scheduler for flashcards."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class SRSResult:
    ease: float
    interval_days: float
    repetitions: int
    due_at: float


def sm2_review(
    *,
    quality: int,
    ease: float,
    interval_days: float,
    repetitions: int,
    now: float | None = None,
) -> SRSResult:
    """
    quality: 0=again, 1=hard, 2=good, 3=easy  (mapped to classic SM-2 0-5 scale)
    """
    now = now if now is not None else time.time()
    # Map 0-3 → 1,2,4,5 on classic scale
    q_map = {0: 1, 1: 2, 2: 4, 3: 5}
    q = q_map.get(int(quality), 3)

    ease = max(1.3, float(ease))
    if q < 3:
        # Fail — reset interval, keep slight ease penalty
        repetitions = 0
        interval_days = 0.0
        ease = max(1.3, ease - 0.2)
        due_at = now + 10 * 60  # 10 minutes
        return SRSResult(ease=ease, interval_days=interval_days, repetitions=repetitions, due_at=due_at)

    # Success
    if repetitions == 0:
        interval_days = 1.0
    elif repetitions == 1:
        interval_days = 3.0 if q >= 4 else 2.0
    else:
        interval_days = max(1.0, interval_days * ease)
        if q == 5:
            interval_days *= 1.3
        elif q == 2:
            interval_days *= 0.9

    ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    ease = max(1.3, ease)
    repetitions = repetitions + 1
    due_at = now + interval_days * 86400
    return SRSResult(
        ease=round(ease, 3),
        interval_days=round(interval_days, 3),
        repetitions=repetitions,
        due_at=due_at,
    )
