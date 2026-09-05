from __future__ import annotations

import pytest

from claude_x import policy
from claude_x.errors import PolicyError


def test_plain_post_costs_the_base_rate():
    assert policy.estimate_cost("shipped a thing today") == 0.015


def test_post_with_a_link_costs_thirteen_times_more():
    """The link premium is the single most expensive surprise in this tool."""
    assert policy.estimate_cost("shipped: https://github.com/jgframoz/claude-x") == 0.20


@pytest.mark.parametrize(
    "text",
    [
        "http://example.com",
        "https://example.com",
        "see HTTPS://EXAMPLE.COM for details",
        "trailing text https://a.io/path?q=1 more",
    ],
)
def test_link_detection(text):
    assert policy.contains_link(text) is True


@pytest.mark.parametrize("text", ["no link here", "not a url: example.com", "a@b.com"])
def test_non_links_are_not_charged_as_links(text):
    assert policy.contains_link(text) is False


def test_urls_count_as_their_tco_width_not_their_real_length():
    short = "x " + "https://a.io"
    long = "x " + "https://example.com/an/extremely/long/path/that/goes/on?and=on&for=ever"

    assert policy.weighted_length(short) == policy.weighted_length(long)
    assert policy.weighted_length(short) == 2 + policy.TCO_LENGTH


def test_length_check_accepts_a_normal_post():
    policy.check_length("a" * 280)


def test_length_check_rejects_an_overrun_and_suggests_a_thread():
    with pytest.raises(PolicyError, match="thread"):
        policy.check_length("a" * 281)


def test_length_check_rejects_empty_and_whitespace():
    with pytest.raises(PolicyError, match="empty"):
        policy.check_length("   \n  ")


def test_a_long_post_can_fit_once_urls_are_counted_properly():
    """A post that looks over the limit but isn't, once t.co is applied."""
    text = "a" * 250 + " https://example.com/" + "b" * 100
    assert policy.weighted_length(text) == 250 + 1 + policy.TCO_LENGTH
    policy.check_length(text)


def test_normalise_makes_whitespace_and_case_irrelevant():
    assert policy.normalise("Hello   World\n") == policy.normalise("hello world")


def test_split_thread_on_dividers():
    draft = "first part\n---\nsecond part\n---\nthird part"
    assert policy.split_thread(draft) == ["first part", "second part", "third part"]


def test_split_thread_ignores_dividers_inside_a_line():
    assert policy.split_thread("a --- b") == ["a --- b"]


def test_split_thread_drops_empty_sections():
    assert policy.split_thread("one\n---\n\n---\ntwo") == ["one", "two"]


def test_split_thread_on_a_single_post_returns_one_part():
    assert policy.split_thread("just one") == ["just one"]


def test_em_dash_is_refused():
    """The user's hardest style rule: dashes read as machine-written."""
    with pytest.raises(PolicyError, match="em dash"):
        policy.check_style("Built a thing — it works well")


def test_en_dash_is_refused():
    with pytest.raises(PolicyError, match="en dash"):
        policy.check_style("Took 3–4 hours")


def test_ordinary_punctuation_passes():
    policy.check_style("Built a thing. It works well, mostly (see the caveats).")


def test_hyphens_are_fine():
    """A hyphen is not a dash. Compound words must still work."""
    policy.check_style("A well-tested, keyword-triggered reply bot is still banned.")
