"""Telling real mentions apart from the spam that arrives with them.

Written after the first live fetch on a 100-follower account returned 25
mentions, all of them crypto spam. Without this the drafting agent would compose
considered replies to airdrop bots, which is a waste of attention and, if any
were ever sent, a good way to look like a bot yourself.

The heuristics are deliberately high-precision rather than exhaustive. A missed
spam mention costs a second of the user's attention. A real mention wrongly
buried costs a conversation, so nothing here is deleted: it is only sorted, and
`--spam` shows what was set aside.
"""

from __future__ import annotations

import re

# Mass-tagging strangers is the clearest structural signal. Real replies address
# one or two people.
MASS_TAG_THRESHOLD = 5

_HANDLE = re.compile(r"@\w+")

_SPAM_PHRASES = (
    "airdrop",
    "air drop",
    "presale",
    "pre-sale",
    "pump",
    "giveaway",
    "givêaway",
    "free mint",
    "claim now",
    "claim your",
    "whitelist",
    "token sale",
    "arbitrage",
    "eligible to claim",
    "join the action",
    "big crypto",
    "biggest crypto",
)

# Spammers swap Latin letters for Cyrillic lookalikes to dodge keyword filters.
# Legitimate English posts do not contain these characters at all.
_CYRILLIC_HOMOGLYPHS = set("аеорсухАЕОРСХіІ")


# Fold lookalikes back to Latin before matching phrases. Otherwise "Аirdrоp"
# with a Cyrillic А and о sails past a check for "airdrop", which is the entire
# point of writing it that way.
_FOLD = str.maketrans(
    {
        "а": "a",
        "А": "A",
        "е": "e",
        "Е": "E",
        "о": "o",
        "О": "O",
        "р": "p",
        "Р": "P",
        "с": "c",
        "С": "C",
        "у": "y",
        "У": "Y",
        "х": "x",
        "Х": "X",
        "і": "i",
        "І": "I",
        "ѕ": "s",
        "Ѕ": "S",
        "ј": "j",
        "Ј": "J",
        "һ": "h",
        "ԁ": "d",
        "ɡ": "g",
        "ν": "v",
        "Ь": "b",
        "м": "m",
        "М": "M",
        "к": "k",
        "К": "K",
        "т": "t",
        "Т": "T",
        "в": "b",
        "В": "B",
        "н": "h",
        "Н": "H",
    }
)


def _homoglyph_count(text: str) -> int:
    return sum(1 for character in text if character in _CYRILLIC_HOMOGLYPHS)


def _fold(text: str) -> str:
    return text.translate(_FOLD)


def classify(text: str) -> tuple[bool, str]:
    """Return (is_likely_spam, reason).

    The reason is shown to the user, so it has to be specific enough to argue
    with when the call is wrong.
    """
    lowered = _fold(text).casefold()

    handles = len(_HANDLE.findall(text))
    if handles >= MASS_TAG_THRESHOLD:
        return True, f"tags {handles} accounts"

    # Check phrases against the folded text, so evasion spelling is caught too.
    for phrase in _SPAM_PHRASES:
        if phrase in lowered:
            return True, f"crypto spam phrase ({phrase!r})"

    # Mixing scripts inside otherwise-English text is itself the tell, even when
    # no known phrase matched.
    homoglyphs = _homoglyph_count(text)
    if homoglyphs >= 2:
        return True, "uses Cyrillic lookalike characters to evade filters"

    # Measure the actual message: strip links, handles, emoji and punctuation,
    # and see how many letters are left. "Check this➡️" looks long enough by
    # character count while saying nothing.
    without_links = re.sub(r"https?://\S+", "", text)
    message = _HANDLE.sub("", without_links)
    letters = sum(1 for character in message if character.isalpha())

    if "http" in text:
        if letters < 12:
            return True, "link with no message"
        # A link, several strangers tagged, and barely any words is a drop, not
        # a conversation.
        if handles >= 3 and letters < 25:
            return True, f"link, {handles} accounts tagged, almost no message"

    return False, ""
