"""Rules that decide whether something may be published, and what it will cost.

Kept in one module so the constraints are reviewable in a single read rather
than scattered through the posting path.
"""

from __future__ import annotations

import re

from .config import COST_PER_POST_USD, COST_PER_POST_WITH_LINK_USD
from .errors import PolicyError

MAX_WEIGHTED_LENGTH = 280

# Every link is rewritten to a t.co URL, so X counts it as a fixed width no
# matter how long the original is.
TCO_LENGTH = 23

_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def contains_link(text: str) -> bool:
    return _URL_PATTERN.search(text) is not None


def weighted_length(text: str) -> int:
    """Length as X counts it, with URLs charged at their t.co width.

    Simplification: characters outside the Latin ranges actually count double
    in X's own algorithm. We count them as one, so this can under-report for
    CJK text. The API is the final authority — this is here to catch the
    ordinary overrun before spending a request on it.
    """
    without_urls = _URL_PATTERN.sub("", text)
    url_count = len(_URL_PATTERN.findall(text))
    return len(without_urls) + (url_count * TCO_LENGTH)


def estimate_cost(text: str) -> float:
    """What publishing this text will cost, in USD.

    A post containing a link is 13x a plain one under the Feb 2026 pay-per-use
    pricing, which is worth knowing *before* pressing send.
    """
    return COST_PER_POST_WITH_LINK_USD if contains_link(text) else COST_PER_POST_USD


def normalise(text: str) -> str:
    """Canonical form used to decide whether two drafts are the same post."""
    return _WHITESPACE.sub(" ", text).strip().casefold()


def check_length(text: str) -> None:
    # Whitespace has a length but no content — check the stripped text, or a
    # draft of blank lines would sail through to the API.
    if not text.strip():
        raise PolicyError("Refusing to publish an empty post.")

    length = weighted_length(text)
    if length > MAX_WEIGHTED_LENGTH:
        raise PolicyError(
            f"Post is {length} characters, over the {MAX_WEIGHTED_LENGTH} limit. "
            "Split it into a thread with '---' between the parts."
        )


# Em dash and en dash. The user's rule: these read as machine-written, so they
# never go out. Enforced here rather than left to the drafting agent, because
# prose instructions get forgotten and this one is absolute.
_DASHES = {"—": "em dash", "–": "en dash"}


def check_style(text: str) -> None:
    for character, name in _DASHES.items():
        if character in text:
            raise PolicyError(
                f"Draft contains an {name} ({character}), which reads as AI-written. "
                "Use a period, comma, colon, or parentheses instead. "
                "If a sentence needs a dash, it is usually two sentences."
            )


def split_thread(text: str) -> list[str]:
    """Split a draft into thread parts on a line containing only '---'."""
    parts = [part.strip() for part in re.split(r"^\s*---\s*$", text, flags=re.MULTILINE)]
    return [part for part in parts if part]
