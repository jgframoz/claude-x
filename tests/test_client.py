from __future__ import annotations

import time

import pytest

from claude_x import auth
from claude_x.auth import Tokens, TokenStore
from claude_x.client import API_BASE, XClient
from claude_x.config import load_config
from claude_x.errors import APIError


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
    """A configured, authenticated, non-dry-run setup."""
    monkeypatch.setenv("X_CLIENT_ID", "test-client-id")
    config = load_config(dry_run=False)
    TokenStore(config).save(Tokens("test-access-token", "r", expires_at=time.time() + 3600))
    return config


@pytest.fixture
def dry_config(monkeypatch):
    monkeypatch.setenv("X_CLIENT_ID", "test-client-id")
    return load_config(dry_run=True)


# --- Dry run ------------------------------------------------------------


def test_dry_run_makes_no_network_calls(dry_config, httpx_mock):
    with XClient(dry_config) as client:
        assert client.get_me()["data"]["username"] == "dryrun"
        assert client.create_tweet("hello")["data"]["text"] == "hello"
        assert client.get_mentions("123")["meta"]["result_count"] == 1
        assert client.get_tweet_metrics(["1"])["data"][0]["public_metrics"]["like_count"] == 12

    # httpx_mock asserts no unmatched requests; zero registered responses plus
    # zero requests is the whole point of this test.
    assert httpx_mock.get_requests() == []


def test_dry_run_needs_no_stored_tokens(dry_config):
    """A dry run must work before the user has ever logged in."""
    with XClient(dry_config) as client:
        assert client.get_me()["data"]["id"]


# --- Live calls ---------------------------------------------------------


def test_get_me_hits_the_right_endpoint(live_config, httpx_mock):
    httpx_mock.add_response(
        url=f"{API_BASE}/users/me", json={"data": {"id": "1", "username": "joao"}}
    )

    with XClient(live_config) as client:
        assert client.get_me()["data"]["username"] == "joao"

    assert httpx_mock.get_request().headers["Authorization"] == "Bearer test-access-token"


def test_create_tweet_posts_the_text(live_config, httpx_mock):
    httpx_mock.add_response(
        url=f"{API_BASE}/tweets", method="POST", json={"data": {"id": "9", "text": "shipped"}}
    )

    with XClient(live_config) as client:
        assert client.create_tweet("shipped")["data"]["id"] == "9"

    import json as json_module

    assert json_module.loads(httpx_mock.get_request().content) == {"text": "shipped"}


def test_mentions_requests_the_fields_we_need(live_config, httpx_mock):
    httpx_mock.add_response(json={"data": [], "meta": {"result_count": 0}})

    with XClient(live_config) as client:
        client.get_mentions("42", since_id="100")

    url = httpx_mock.get_request().url
    assert "/users/42/mentions" in str(url)
    assert url.params["since_id"] == "100"
    assert "author_id" in url.params["tweet.fields"]


def test_metrics_batches_ids_into_one_request(live_config, httpx_mock):
    httpx_mock.add_response(json={"data": []})

    with XClient(live_config) as client:
        client.get_tweet_metrics(["1", "2", "3"])

    assert httpx_mock.get_request().url.params["ids"] == "1,2,3"


def test_metrics_with_no_ids_short_circuits(live_config, httpx_mock):
    with XClient(live_config) as client:
        assert client.get_tweet_metrics([]) == {"data": []}

    assert httpx_mock.get_requests() == []


def test_metrics_refuses_more_than_the_api_limit(live_config):
    with XClient(live_config) as client, pytest.raises(APIError, match="100"):
        client.get_tweet_metrics([str(n) for n in range(101)])


# --- Error handling -----------------------------------------------------


def test_rate_limiting_says_not_to_loop(live_config, httpx_mock):
    httpx_mock.add_response(url=f"{API_BASE}/users/me", status_code=429, text="slow down")

    with XClient(live_config) as client, pytest.raises(APIError, match="do not loop") as caught:
        client.get_me()

    assert caught.value.status_code == 429


def test_api_errors_carry_the_status_code(live_config, httpx_mock):
    httpx_mock.add_response(url=f"{API_BASE}/users/me", status_code=403, text="forbidden")

    with XClient(live_config) as client, pytest.raises(APIError) as caught:
        client.get_me()

    assert caught.value.status_code == 403
    assert "forbidden" in str(caught.value)


# --- Compliance ---------------------------------------------------------


def test_client_exposes_no_way_to_reply_to_someone_else():
    """The absence of reply-posting is the compliance argument — guard it.

    If a future change adds reply capability, this test should fail and the
    author should re-read X's automation rules before deleting it.
    """
    public_methods = {name for name in dir(XClient) if not name.startswith("_")}

    assert public_methods == {
        "get_me",
        "create_tweet",
        "get_mentions",
        "get_tweet_metrics",
        "close",
    }

    import inspect

    signature = inspect.signature(XClient.create_tweet)
    assert set(signature.parameters) == {"self", "text"}
