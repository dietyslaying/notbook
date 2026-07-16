"""Safety + library framing.

Notbook is a compiled textbook library, not a clinician.
For emergency-sounding language we still surface matching textbook material
(for medical students who ask about those topics) but always lead with
emergency guidance and library framing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from config import config


# Self-harm / active crisis — stronger redirect
_CRISIS = re.compile(
    r"\b("
    r"kill myself|suicide|suicidal|end my life|want to die|"
    r"self[\s-]?harm|cut myself|overdose on purpose"
    r")\b",
    re.I,
)

# Acute emergency symptoms / situations
_EMERGENCY = re.compile(
    r"\b("
    r"can't breathe|cannot breathe|not breathing|"
    r"crushing chest pain|chest pain now|heart attack|"
    r"stroke symptoms|face droop|severe bleeding|"
    r"unconscious|anaphylaxis|seizure now|"
    r"overdose|poisoned|choking|"
    r"call (an )?ambulance|emergency room right now"
    r")\b",
    re.I,
)


@dataclass
class SafetyResult:
    is_crisis: bool
    is_emergency: bool
    banner: str
    framing: str
    still_answer_from_books: bool


def assess(text: str) -> SafetyResult:
    bot = config.raw_config.get("bot") or {}
    framing = " ".join(str(bot.get("library_framing") or "").split())
    emergency_banner = " ".join(str(bot.get("emergency_banner") or "").split())

    is_crisis = bool(_CRISIS.search(text or ""))
    is_emergency = bool(_EMERGENCY.search(text or "")) or is_crisis

    if is_crisis:
        banner = (
            "If you are in immediate danger or thinking of harming yourself, "
            "contact local emergency services or a crisis line right now. "
            + emergency_banner
        )
    elif is_emergency:
        banner = emergency_banner
    else:
        banner = ""

    return SafetyResult(
        is_crisis=is_crisis,
        is_emergency=is_emergency,
        banner=banner.strip(),
        framing=framing,
        # Always allow textbook retrieval for study topics, including emergency topics
        still_answer_from_books=True,
    )


def compose_disclaimer(safety: SafetyResult, extra: str = "") -> str:
    parts = [p for p in [safety.framing, extra, safety.banner] if p]
    # Deduplicate near-identical lines
    seen: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.append(p)
    return "\n".join(seen)
