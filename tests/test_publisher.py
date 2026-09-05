from __future__ import annotations

import time

import pytest

from claude_x import auth
from claude_x.auth import Tokens, TokenStore
from claude_x.client import API_BASE
from claude_x.config import load_config
from claude_x.errors import PolicyError
from claude_x.publisher import PostLog, Publisher


@pytest.fixture(autouse=True)
def no_keyring(monkeypatch):
    from keyring.errors import KeyringError

    def unavailable(*args, **kwargs):
        raise KeyringError("no backend in tests")

    monkeypatch.setattr(auth.keyring, "set_password", unavailable)
    monkeypatch.setattr(auth.keyring, "get_password", unavailable)
    monkeypatch.setattr(auth.keyring, "delete_password", unavailable)


@pytest.fixture
def live_config(monkeypatch):
    monkeypatch.setenv("X_CLIENT_ID", "test-client-id")
    config = load_config(dry_run=False)
    TokenStore(config).save(Tokens("test-access-token", "r", expires_at=time.time() + 3600))
    return config


@pytest.fixture
def dry_config(monkeypatch):
    monkeypatch.setenv("X_CLIENT_ID", "test-client-id")
    return load_config(dry_run=True)


def tweet_response(tweet_id: str, text: str = "ok"):
    return {"data": {"id": tweet_id, "text": text}}


# --- Publishing ---------------------------------------------------------


def test_publish_records_the_post_and_its_url(live_config, httpx_mock):
    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("55"))

    with Publisher(live_config) as publisher:
        post = publisher.publish("shipped something")

    assert post.id == "55"
    assert post.url == "https://x.com/i/web/status/55"
    assert post.cost_usd == 0.015

    logged = PostLog(live_config).all()
    assert len(logged) == 1
    assert logged[0]["text"] == "shipped something"


def test_link_posts_record_the_higher_cost(live_config, httpx_mock):
    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("56"))

    with Publisher(live_config) as publisher:
        post = publisher.publish("see https://github.com/jgframoz/claude-x")

    assert post.cost_usd == 0.20


def test_dry_run_publishes_nothing_and_costs_nothing(dry_config, httpx_mock):
    with Publisher(dry_config) as publisher:
        post = publisher.publish("this never leaves the machine")

    assert post.dry_run is True
    assert post.cost_usd == 0.0
    assert httpx_mock.get_requests() == []


def test_oversized_post_is_refused_before_any_request(live_config, httpx_mock):
    with Publisher(live_config) as publisher, pytest.raises(PolicyError, match="over the 280"):
        publisher.publish("a" * 281)

    assert httpx_mock.get_requests() == []


# --- Duplicates ---------------------------------------------------------


def test_exact_duplicate_is_refused(live_config, httpx_mock):
    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("1"))

    with Publisher(live_config) as publisher:
        publisher.publish("the same thing")

        with pytest.raises(PolicyError, match="published before"):
            publisher.publish("the same thing")


def test_duplicate_detection_ignores_whitespace_and_case(live_config, httpx_mock):
    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("1"))

    with Publisher(live_config) as publisher:
        publisher.publish("Hello World")

        with pytest.raises(PolicyError, match="published before"):
            publisher.publish("hello   world")


def test_dry_run_entries_do_not_block_a_real_post(dry_config, live_config, httpx_mock):
    """Rehearsing in dry run must not make the real post look like a duplicate."""
    with Publisher(dry_config) as publisher:
        publisher.publish("a draft I rehearsed")

    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("77"))
    with Publisher(live_config) as publisher:
        post = publisher.publish("a draft I rehearsed")

    assert post.id == "77"


def test_forgetting_a_post_allows_republishing(live_config, httpx_mock):
    """Deletion compliance: removing the record also clears the duplicate block."""
    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("1"))

    with Publisher(live_config) as publisher:
        publisher.publish("once")
        assert publisher.log.forget("1") == 1

        httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("2"))
        assert publisher.publish("once").id == "2"


# --- The ownership guard ------------------------------------------------


def test_replying_to_someone_elses_post_is_refused(live_config, httpx_mock):
    """The core compliance guard: we may only chain onto our own posts."""
    with Publisher(live_config) as publisher, pytest.raises(PolicyError, match="not one of ours"):
        publisher.publish("a reply", in_reply_to="9999999999")

    assert httpx_mock.get_requests() == []


def test_replying_to_our_own_post_is_allowed(live_config, httpx_mock):
    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("100"))

    with Publisher(live_config) as publisher:
        first = publisher.publish("part one")

        httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("101"))
        second = publisher.publish("part two", in_reply_to=first.id)

    assert second.in_reply_to == "100"


def test_a_dry_run_post_does_not_count_as_ours_for_replying(dry_config, live_config, httpx_mock):
    """A dry-run id was never real, so it must not unlock live replies."""
    with Publisher(dry_config) as publisher:
        rehearsed = publisher.publish("rehearsal")

    with Publisher(live_config) as publisher, pytest.raises(PolicyError, match="not one of ours"):
        publisher.publish("reply", in_reply_to=rehearsed.id)


# --- Threads ------------------------------------------------------------


def test_thread_chains_each_part_onto_the_previous(live_config, httpx_mock):
    for tweet_id in ("1", "2", "3"):
        httpx_mock.add_response(
            url=f"{API_BASE}/tweets", method="POST", json=tweet_response(tweet_id)
        )

    with Publisher(live_config) as publisher:
        posts = publisher.publish_thread(["one", "two", "three"])

    assert [post.id for post in posts] == ["1", "2", "3"]
    assert [post.in_reply_to for post in posts] == [None, "1", "2"]


def test_thread_validates_every_part_before_publishing_any(live_config, httpx_mock):
    """Catch an overlong part 3 before part 1 is already public."""
    with Publisher(live_config) as publisher, pytest.raises(PolicyError, match="over the 280"):
        publisher.publish_thread(["fine", "also fine", "b" * 281])

    assert httpx_mock.get_requests() == []
    assert PostLog(live_config).all() == []


def test_partial_thread_failure_reports_what_was_published(live_config, httpx_mock):
    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("1"))
    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", status_code=500, text="boom")

    with Publisher(live_config) as publisher, pytest.raises(PolicyError, match="already published"):
        publisher.publish_thread(["one", "two"])

    # The first part really is public; the log must reflect that.
    assert len(PostLog(live_config).all()) == 1


# --- Approval provenance ------------------------------------------------


def test_the_approval_route_is_recorded(live_config, httpx_mock):
    """History should be able to answer 'did I approve that, or did an agent?'"""
    from claude_x.publisher import APPROVAL_RELAYED

    httpx_mock.add_response(url=f"{API_BASE}/tweets", method="POST", json=tweet_response("1"))

    with Publisher(live_config) as publisher:
        publisher.publish("relayed by an agent", approval=APPROVAL_RELAYED)

    assert PostLog(live_config).all()[0]["approval"] == "agent-relayed"


def test_dry_runs_never_claim_an_approval(dry_config):
    """Nothing was published, so no approval was exercised."""
    from claude_x.publisher import APPROVAL_NONE, APPROVAL_RELAYED

    with Publisher(dry_config) as publisher:
        post = publisher.publish("rehearsal", approval=APPROVAL_RELAYED)

    assert post.approval == APPROVAL_NONE


def test_every_part_of_a_thread_records_the_approval(live_config, httpx_mock):
    from claude_x.publisher import APPROVAL_RELAYED

    for tweet_id in ("1", "2"):
        httpx_mock.add_response(
            url=f"{API_BASE}/tweets", method="POST", json=tweet_response(tweet_id)
        )

    with Publisher(live_config) as publisher:
        posts = publisher.publish_thread(["one", "two"], approval=APPROVAL_RELAYED)

    assert all(post.approval == "agent-relayed" for post in posts)
