from __future__ import annotations

import time

import pytest

from claude_x import auth, mentions
from claude_x.auth import Tokens, TokenStore
from claude_x.client import API_BASE, XClient
from claude_x.config import load_config
from claude_x.mentions import Mention, MentionLog


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


def make_mention(mention_id: str, *, handled: bool = False) -> Mention:
    return Mention(
        id=mention_id,
        username="someone",
        author_id="42",
        text="hello",
        created_at="2026-09-05T10:00:00.000Z",
        fetched_at="2026-09-05T11:00:00Z",
        handled=handled,
    )


def mentions_payload(*ids: str) -> dict:
    return {
        "data": [
            {
                "id": mention_id,
                "author_id": "42",
                "text": f"mention {mention_id}",
                "created_at": "2026-09-05T10:00:00.000Z",
            }
            for mention_id in ids
        ],
        "includes": {"users": [{"id": "42", "username": "someone", "name": "Some One"}]},
    }


# --- Storage ------------------------------------------------------------


def test_mention_url_points_at_the_original_post():
    assert make_mention("123").url == "https://x.com/someone/status/123"


def test_unhandled_excludes_handled_mentions(dry_config):
    log = MentionLog(dry_config)
    log.record(make_mention("1"))
    log.record(make_mention("2", handled=True))

    assert [mention.id for mention in log.unhandled()] == ["1"]


def test_marking_handled_persists(dry_config):
    log = MentionLog(dry_config)
    log.record(make_mention("1"))

    assert log.mark_handled("1") is True
    assert log.unhandled() == []
    assert len(log.all()) == 1


def test_marking_an_unknown_mention_reports_it(dry_config):
    assert MentionLog(dry_config).mark_handled("nope") is False


def test_newest_id_is_numeric_not_lexicographic(dry_config):
    """Snowflake ids: '9' must not beat '10' as it would when compared as text."""
    log = MentionLog(dry_config)
    log.record(make_mention("9"))
    log.record(make_mention("10"))

    assert log.newest_id() == "10"


def test_newest_id_is_none_when_nothing_is_stored(dry_config):
    assert MentionLog(dry_config).newest_id() is None


def test_forgetting_a_mention_removes_it(dry_config):
    """Deletion compliance for other people's content held locally."""
    log = MentionLog(dry_config)
    log.record(make_mention("1"))

    assert log.forget("1") == 1
    assert log.all() == []


# --- Fetching -----------------------------------------------------------


def test_fetch_records_new_mentions_with_usernames(live_config, httpx_mock):
    httpx_mock.add_response(
        url=f"{API_BASE}/users/me", json={"data": {"id": "1", "username": "me"}}
    )
    httpx_mock.add_response(json=mentions_payload("100"))

    with XClient(live_config) as client:
        new = mentions.fetch_new(live_config, client)

    assert len(new) == 1
    assert new[0].username == "someone"
    assert MentionLog(live_config).all()[0].id == "100"


def test_fetch_asks_only_for_what_it_has_not_seen(live_config, httpx_mock):
    """Reads are billed, so since_id must be sent once anything is stored."""
    MentionLog(live_config).record(make_mention("100"))

    httpx_mock.add_response(url=f"{API_BASE}/users/me", json={"data": {"id": "1"}})
    httpx_mock.add_response(json=mentions_payload("101"))

    with XClient(live_config) as client:
        mentions.fetch_new(live_config, client)

    mention_request = httpx_mock.get_requests()[-1]
    assert mention_request.url.params["since_id"] == "100"


def test_a_mention_already_stored_is_not_duplicated(live_config, httpx_mock):
    MentionLog(live_config).record(make_mention("100"))

    httpx_mock.add_response(url=f"{API_BASE}/users/me", json={"data": {"id": "1"}})
    httpx_mock.add_response(json=mentions_payload("100"))

    with XClient(live_config) as client:
        new = mentions.fetch_new(live_config, client)

    assert new == []
    assert len(MentionLog(live_config).all()) == 1


def test_an_unknown_author_does_not_break_the_fetch(live_config, httpx_mock):
    """Missing expansions shouldn't lose the mention entirely."""
    payload = mentions_payload("100")
    payload["includes"] = {"users": []}

    httpx_mock.add_response(url=f"{API_BASE}/users/me", json={"data": {"id": "1"}})
    httpx_mock.add_response(json=payload)

    with XClient(live_config) as client:
        new = mentions.fetch_new(live_config, client)

    assert new[0].username == "unknown"


def test_fetching_in_dry_run_touches_no_network(dry_config, httpx_mock):
    with XClient(dry_config) as client:
        new = mentions.fetch_new(dry_config, client)

    assert httpx_mock.get_requests() == []
    assert len(new) == 1


# --- Compliance ---------------------------------------------------------


def test_module_offers_no_way_to_send_a_reply():
    """The absence of reply-sending is the compliance argument. Guard it.

    If this fails because a send function was added, stop and re-read X's
    automation rules: posting AI-drafted replies needs prior written approval
    from X, and the account is what's at risk.
    """
    exported = {name for name in dir(mentions) if not name.startswith("_")}
    suspicious = {
        name
        for name in exported
        if any(word in name.lower() for word in ("reply", "send", "post", "respond"))
    }

    assert suspicious == set()


def test_dry_run_stores_nothing(dry_config):
    """A rehearsal must not put invented people or ids into the real log.

    A fabricated id would also become the since_id for the next real fetch.
    """
    with XClient(dry_config) as client:
        new = mentions.fetch_new(dry_config, client)

    assert len(new) == 1
    assert MentionLog(dry_config).all() == []
    assert MentionLog(dry_config).newest_id() is None
