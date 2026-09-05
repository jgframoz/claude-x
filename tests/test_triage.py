from __future__ import annotations

import pytest

from claude_x import triage

# Real examples, lightly trimmed, from the first live fetch on the account.
# Every one of these arrived within a day on an account with ~100 followers.
REAL_SPAM = [
    "🔥 Тhе ВIGGЕST #Сryрtо #РUМР #Signаl is hеrе! 🚀 Jоin thе аctiоn!",
    "$LINK Аirdrop➡️https://t.co/w0Iv4IXF6M\n\n@ddeonufox03 @LouisConradt @a @b",
    "Stay notified on this Аirdrоp ➡️ https://t.co/LQY9bm2G4Z\n\n@x @y @z",
    "Check this➡️https://t.co/bMqLxkUYhb\n\n@dumanovtolga @limon_kufu @a @b",
    "💧 Vitalik Buterin Presale is Live!  1️⃣ More information: http://x.co/a",
    "Free Mint NFT Nickelodeon 🥳 @Rodrigo11002645 @orkunabiniz @q @w @e",
    "🚨 JUST IN: Rіррlе іѕ рlеаѕеd tо аnnоunсе thаt уоu аrе еlіgіblе",
    "📈#WIF BIG CRYPTO PUMP TODAY and its biggest $WIF PUMP ever",
    "🔥Make strategic arbitrage moves to maximise earnings!➡️ http://x.co/b",
    "Have you heard aboutt this project before? @a @b @c @d @e @f @g",
]

# Things a real person might plausibly send this account.
REAL_MENTIONS = [
    "@JoaoFernandesRa this is neat, does it handle threads?",
    "@JoaoFernandesRa how are you stopping it from posting on its own?",
    "nice work on claude-x, forked it: https://github.com/someone/fork",
    "@JoaoFernandesRa @someone we were just talking about this, see the repo",
    "Interesting approach. Did X actually ban keyword reply bots, or just limit them?",
    "@JoaoFernandesRa the auth flow post was useful, thanks for writing it up",
]


@pytest.mark.parametrize("text", REAL_SPAM)
def test_real_spam_is_caught(text):
    is_spam, reason = triage.classify(text)
    assert is_spam, f"missed: {text[:60]}"
    assert reason


@pytest.mark.parametrize("text", REAL_MENTIONS)
def test_real_mentions_are_not_buried(text):
    """A false positive costs a conversation, so this is the important half."""
    is_spam, reason = triage.classify(text)
    assert not is_spam, f"wrongly buried as {reason}: {text[:60]}"


def test_homoglyph_spelling_does_not_evade_the_phrase_check():
    """Cyrillic А and о in 'Аirdrоp' is precisely the evasion being defeated."""
    is_spam, reason = triage.classify("Claim your Аirdrоp today")

    assert is_spam
    assert "airdrop" in reason


def test_mass_tagging_alone_is_enough():
    is_spam, reason = triage.classify("@a @b @c @d @e take a look")

    assert is_spam
    assert "5 accounts" in reason


def test_a_bare_link_with_no_message_is_spam():
    is_spam, reason = triage.classify("https://t.co/gHo03NEHjf")

    assert is_spam
    assert "no message" in reason


def test_a_link_with_a_real_message_is_kept():
    is_spam, _ = triage.classify(
        "built on top of your thing, here it is https://github.com/a/b what do you think?"
    )

    assert not is_spam


def test_plain_conversation_is_kept():
    assert triage.classify("does this work with threads?") == (False, "")
