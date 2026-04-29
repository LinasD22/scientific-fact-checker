"""Shared enums for API and persistence."""

from enum import Enum


class FactCheckResult(str, Enum):
    """Verdict values produced by the fact-check pipeline (matches AI JSON + DB)."""

    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    FALSE = "false"
    UNVERIFIABLE = "unverifiable"
    CONFLICTING = "conflicting"
