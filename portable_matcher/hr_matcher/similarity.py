from __future__ import annotations

from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz as _rapidfuzz
except Exception:  # pragma: no cover - exercised when optional dependency is absent.
    _rapidfuzz = None


def token_sort_ratio(left: str, right: str) -> float:
    if _rapidfuzz:
        return float(_rapidfuzz.token_sort_ratio(left, right))
    return _ratio(" ".join(sorted(_tokens(left))), " ".join(sorted(_tokens(right))))


def token_set_ratio(left: str, right: str) -> float:
    if _rapidfuzz:
        return float(_rapidfuzz.token_set_ratio(left, right))
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    common = left_tokens & right_tokens
    left_only = left_tokens - common
    right_only = right_tokens - common
    common_text = " ".join(sorted(common))
    variants = [
        (common_text, " ".join(sorted(common | left_only))),
        (common_text, " ".join(sorted(common | right_only))),
        (" ".join(sorted(common | left_only)), " ".join(sorted(common | right_only))),
    ]
    return max(_ratio(a, b) for a, b in variants if a or b)


def ratio(left: str, right: str) -> float:
    return _ratio(left, right)


def _ratio(left: str, right: str) -> float:
    if not left and not right:
        return 100.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio() * 100


def _tokens(value: str) -> list[str]:
    return [token for token in str(value or "").split() if token]
