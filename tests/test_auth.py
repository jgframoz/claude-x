from __future__ import annotations

import base64
import hashlib
import time
import urllib.parse

import pytest

from claude_x import auth
from claude_x.auth import Tokens, TokenStore
from claude_x.config import REDIRECT_URI, load_config
from claude_x.errors import AuthError


@pytest.fixture(autouse=True)
def no_keyring(monkeypatch):
    """Force the file fallback so tests never touch the real Keychain."""
    from keyring.errors import KeyringError

    def unavailable(*args, **kwargs):
        raise KeyringError("no backend in tests")

    monkeypatch.setattr(auth.keyring, "set_password", unavailable)
    monkeypatch.setattr(auth.keyring, "get_password", unavailable)
    monkeypatch.setattr(auth.keyring, "delete_password", unavailable)


def make_config(monkeypatch, **overrides):
    monkeypatch.setenv("X_CLIENT_ID", overrides.pop("client_id", "test-client-id"))
    return load_config(dry_run=overrides.pop("dry_run", True))


# --- PKCE ---------------------------------------------------------------


def test_pkce_challenge_is_the_sha256_of_the_verifier():
    verifier, challenge = auth.generate_pkce_pair()

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    assert challenge == expected


def test_pkce_pairs_are_unique_per_call():
    assert auth.generate_pkce_pair()[0] != auth.generate_pkce_pair()[0]


def test_pkce_verifier_length_is_within_the_spec():
    verifier, _ = auth.generate_pkce_pair()
    assert 43 <= len(verifier) <= 128


def test_authorize_url_carries_the_right_parameters():
    url = auth.build_authorize_url("client-123", "challenge-abc", "state-xyz")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)

    assert query["client_id"] == ["client-123"]
    assert query["code_challenge"] == ["challenge-abc"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"] == ["state-xyz"]
    assert query["redirect_uri"] == [REDIRECT_URI]
    assert query["response_type"] == ["code"]
    assert "offline.access" in query["scope"][0]


# --- Tokens -------------------------------------------------------------


def test_tokens_from_response_applies_an_expiry_margin():
    before = time.time()
    tokens = Tokens.from_response(
        {"access_token": "a", "refresh_token": "r", "expires_in": 7200, "scope": "tweet.read"}
    )

    assert tokens.expires_at < before + 7200
    assert tokens.is_expired is False


def test_tokens_without_access_token_is_an_error():
    with pytest.raises(AuthError, match="access_token"):
        Tokens.from_response({"refresh_token": "r"})


def test_expired_token_is_reported_as_expired():
    assert Tokens("a", "r", expires_at=time.time() - 1).is_expired is True


# --- Storage ------------------------------------------------------------


def test_token_store_round_trip_via_file_fallback(monkeypatch):
    config = make_config(monkeypatch)
    store = TokenStore(config)
    store.save(Tokens("access", "refresh", expires_at=time.time() + 3600, scope="tweet.read"))

    loaded = store.load()

    assert loaded is not None
    assert loaded.access_token == "access"
    assert loaded.refresh_token == "refresh"


def test_fallback_token_file_is_owner_only(monkeypatch):
    config = make_config(monkeypatch)
    store = TokenStore(config)
    store.save(Tokens("a", "r", expires_at=time.time() + 60))

    assert store.fallback_path.stat().st_mode & 0o777 == 0o600


def test_loading_with_nothing_stored_returns_none(monkeypatch):
    assert TokenStore(make_config(monkeypatch)).load() is None


def test_corrupt_token_file_reads_as_not_logged_in(monkeypatch):
    config = make_config(monkeypatch)
    store = TokenStore(config)
    store.save(Tokens("a", "r", expires_at=time.time() + 60))
    store.fallback_path.write_text("{not json")

    assert store.load() is None


def test_clear_removes_the_stored_tokens(monkeypatch):
    config = make_config(monkeypatch)
    store = TokenStore(config)
    store.save(Tokens("a", "r", expires_at=time.time() + 60))

    store.clear()

    assert store.load() is None


# --- Token endpoint -----------------------------------------------------


def test_exchange_code_posts_the_verifier(monkeypatch, httpx_mock):
    config = make_config(monkeypatch)
    httpx_mock.add_response(
        url=auth.TOKEN_URL,
        json={"access_token": "at", "refresh_token": "rt", "expires_in": 7200},
    )

    tokens = auth.exchange_code(config, "the-code", "the-verifier")

    request = httpx_mock.get_request()
    body = urllib.parse.parse_qs(request.content.decode())
    assert body["code_verifier"] == ["the-verifier"]
    assert body["grant_type"] == ["authorization_code"]
    assert body["redirect_uri"] == [REDIRECT_URI]
    assert tokens.access_token == "at"


def test_public_client_sends_no_basic_auth(monkeypatch, httpx_mock):
    config = make_config(monkeypatch)
    httpx_mock.add_response(url=auth.TOKEN_URL, json={"access_token": "at", "expires_in": 100})

    auth.exchange_code(config, "c", "v")

    assert "Authorization" not in httpx_mock.get_request().headers


def test_confidential_client_uses_basic_auth(monkeypatch, httpx_mock):
    monkeypatch.setenv("X_CLIENT_SECRET", "shhh")
    config = make_config(monkeypatch)
    httpx_mock.add_response(url=auth.TOKEN_URL, json={"access_token": "at", "expires_in": 100})

    auth.exchange_code(config, "c", "v")

    assert httpx_mock.get_request().headers["Authorization"].startswith("Basic ")


def test_token_endpoint_failure_is_reported_clearly(monkeypatch, httpx_mock):
    config = make_config(monkeypatch)
    httpx_mock.add_response(url=auth.TOKEN_URL, status_code=400, text="invalid_grant")

    with pytest.raises(AuthError, match="invalid_grant"):
        auth.exchange_code(config, "c", "v")


def test_refresh_keeps_the_old_refresh_token_when_none_is_returned(monkeypatch, httpx_mock):
    config = make_config(monkeypatch)
    httpx_mock.add_response(url=auth.TOKEN_URL, json={"access_token": "new", "expires_in": 7200})

    tokens = auth.refresh_tokens(config, "original-refresh")

    assert tokens.access_token == "new"
    assert tokens.refresh_token == "original-refresh"


def test_refresh_prefers_a_rotated_refresh_token(monkeypatch, httpx_mock):
    config = make_config(monkeypatch)
    httpx_mock.add_response(
        url=auth.TOKEN_URL,
        json={"access_token": "new", "refresh_token": "rotated", "expires_in": 7200},
    )

    assert auth.refresh_tokens(config, "original").refresh_token == "rotated"


# --- get_valid_tokens ---------------------------------------------------


def test_get_valid_tokens_without_login_explains_what_to_do(monkeypatch):
    with pytest.raises(AuthError, match="auth login"):
        auth.get_valid_tokens(make_config(monkeypatch))


def test_get_valid_tokens_returns_a_live_token_untouched(monkeypatch):
    config = make_config(monkeypatch)
    TokenStore(config).save(Tokens("still-good", "r", expires_at=time.time() + 3600))

    assert auth.get_valid_tokens(config).access_token == "still-good"


def test_get_valid_tokens_refreshes_and_persists_when_expired(monkeypatch, httpx_mock):
    config = make_config(monkeypatch)
    TokenStore(config).save(Tokens("stale", "refresh-me", expires_at=time.time() - 10))
    httpx_mock.add_response(
        url=auth.TOKEN_URL,
        json={"access_token": "fresh", "refresh_token": "rotated", "expires_in": 7200},
    )

    tokens = auth.get_valid_tokens(config)

    assert tokens.access_token == "fresh"
    # The refreshed pair must be written back, or every command would refresh.
    assert TokenStore(config).load().access_token == "fresh"


def test_expired_without_refresh_token_asks_for_a_new_login(monkeypatch):
    config = make_config(monkeypatch)
    TokenStore(config).save(Tokens("stale", None, expires_at=time.time() - 10))

    with pytest.raises(AuthError, match="[Ll]og in again"):
        auth.get_valid_tokens(config)


# --- Callback handling --------------------------------------------------


def test_login_rejects_a_mismatched_state(monkeypatch):
    config = make_config(monkeypatch)
    monkeypatch.setattr(auth, "webbrowser", type("W", (), {"open": staticmethod(lambda url: None)}))
    monkeypatch.setattr(
        auth, "wait_for_callback", lambda *a, **k: {"code": "c", "state": "not-the-one"}
    )

    with pytest.raises(AuthError, match="State mismatch"):
        auth.login(config)


def test_login_surfaces_a_denied_authorisation(monkeypatch):
    config = make_config(monkeypatch)
    monkeypatch.setattr(auth, "webbrowser", type("W", (), {"open": staticmethod(lambda url: None)}))
    monkeypatch.setattr(
        auth,
        "wait_for_callback",
        lambda *a, **k: {"error": "access_denied", "error_description": "user said no"},
    )

    with pytest.raises(AuthError, match="user said no"):
        auth.login(config)
