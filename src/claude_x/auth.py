"""OAuth 2.0 Authorization Code flow with PKCE, against a public client.

X issues no client secret for a Native App, so PKCE is what proves the token
request came from whoever started the flow. The user's browser does the consent;
we listen on a loopback port for the redirect.

Access tokens last two hours. The refresh token (from the offline.access scope)
is what keeps the CLI usable without re-authorising constantly, so it is the
value most worth protecting — it lives in the Keychain when one is available.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import secrets
import time
import urllib.parse
import webbrowser
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx
import keyring
from keyring.errors import KeyringError

from .config import CALLBACK_PORT, REDIRECT_URI, SCOPES, Config, ensure_data_dir
from .errors import AuthError

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
REVOKE_URL = "https://api.x.com/2/oauth2/revoke"

KEYRING_SERVICE = "claude-x"
KEYRING_USERNAME = "oauth-tokens"
TOKEN_FILENAME = "tokens.json"

# Refresh a little before the real expiry so a long-running command doesn't have
# a token die mid-flight.
EXPIRY_MARGIN_SECONDS = 60

# How long to wait for the user to finish the consent screen.
CALLBACK_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_at: float
    scope: str = ""

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> Tokens:
        try:
            access_token = payload["access_token"]
        except KeyError as exc:
            raise AuthError("Token response contained no access_token.") from exc

        expires_in = float(payload.get("expires_in", 7200))
        return cls(
            access_token=access_token,
            refresh_token=payload.get("refresh_token"),
            expires_at=time.time() + expires_in - EXPIRY_MARGIN_SECONDS,
            scope=payload.get("scope", ""),
        )


class TokenStore:
    """Keychain-backed token storage, falling back to an owner-only file.

    The fallback exists for headless environments and CI; on the Mac this should
    always be the Keychain.
    """

    def __init__(self, config: Config) -> None:
        self.config = config

    @property
    def fallback_path(self):
        return self.config.data_dir / TOKEN_FILENAME

    def save(self, tokens: Tokens) -> None:
        payload = json.dumps(asdict(tokens))
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, payload)
            return
        except KeyringError:
            pass

        ensure_data_dir(self.config)
        path = self.fallback_path
        path.write_text(payload, encoding="utf-8")
        path.chmod(0o600)

    def load(self) -> Tokens | None:
        raw: str | None = None
        try:
            raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except KeyringError:
            raw = None

        if raw is None and self.fallback_path.is_file():
            raw = self.fallback_path.read_text(encoding="utf-8")

        if not raw:
            return None

        try:
            data = json.loads(raw)
            return Tokens(**data)
        except (json.JSONDecodeError, TypeError):
            # Corrupt or from an older layout — treat as "not logged in" rather
            # than crashing; `auth login` will overwrite it.
            return None

    def clear(self) -> None:
        # Either store may legitimately hold nothing; clear both regardless.
        with contextlib.suppress(KeyringError):
            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        self.fallback_path.unlink(missing_ok=True)


def generate_pkce_pair() -> tuple[str, str]:
    """Return (verifier, challenge) for the S256 method."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_authorize_url(client_id: str, challenge: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


_SUCCESS_PAGE = b"""<!doctype html>
<meta charset="utf-8">
<title>claude-x</title>
<body style="font-family: system-ui; padding: 3rem; max-width: 32rem">
<h2>Authorised</h2>
<p>claude-x can now post on your behalf &mdash; after you approve each post.</p>
<p>You can close this tab and return to the terminal.</p>
</body>
"""

_FAILURE_PAGE = b"""<!doctype html>
<meta charset="utf-8">
<title>claude-x</title>
<body style="font-family: system-ui; padding: 3rem; max-width: 32rem">
<h2>Authorisation failed</h2>
<p>Return to the terminal for details.</p>
</body>
"""


class _CallbackHandler(BaseHTTPRequestHandler):
    """Captures the single redirect X sends back to the loopback address."""

    result: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        query = {key: values[0] for key, values in urllib.parse.parse_qs(parsed.query).items()}
        type(self).result = query

        body = _SUCCESS_PAGE if "code" in query else _FAILURE_PAGE
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        """Silence the default stderr access log."""


def wait_for_callback(timeout: float = CALLBACK_TIMEOUT_SECONDS) -> dict[str, str]:
    """Serve on the loopback port until the redirect arrives.

    Bound to 127.0.0.1 so nothing outside this machine can reach it.
    """
    _CallbackHandler.result = {}
    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), _CallbackHandler)
    server.timeout = timeout
    try:
        deadline = time.time() + timeout
        while not _CallbackHandler.result and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if not _CallbackHandler.result:
        raise AuthError("Timed out waiting for the authorisation redirect.")
    return _CallbackHandler.result


def _token_request(config: Config, data: dict[str, str]) -> Tokens:
    """POST to the token endpoint and parse the result."""
    auth = None
    if config.client_secret:
        # Confidential clients authenticate with HTTP Basic instead of sending
        # the client_id in the body.
        auth = (config.require_client_id(), config.client_secret)

    try:
        response = httpx.post(TOKEN_URL, data=data, auth=auth, timeout=30.0)
    except httpx.HTTPError as exc:
        raise AuthError(f"Could not reach the X token endpoint: {exc}") from exc

    if response.status_code != 200:
        raise AuthError(f"Token request failed ({response.status_code}): {response.text.strip()}")

    return Tokens.from_response(response.json())


def exchange_code(config: Config, code: str, verifier: str) -> Tokens:
    return _token_request(
        config,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
            "client_id": config.require_client_id(),
        },
    )


def refresh_tokens(config: Config, refresh_token: str) -> Tokens:
    refreshed = _token_request(
        config,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config.require_client_id(),
        },
    )
    if refreshed.refresh_token is None:
        # X normally rotates the refresh token; keep the old one if it didn't.
        refreshed = Tokens(
            access_token=refreshed.access_token,
            refresh_token=refresh_token,
            expires_at=refreshed.expires_at,
            scope=refreshed.scope,
        )
    return refreshed


def login(
    config: Config,
    *,
    open_browser: bool = True,
    on_url: Callable[[str], None] | None = None,
) -> Tokens:
    """Run the full interactive flow and persist the resulting tokens.

    `on_url` receives the authorize URL so the caller can display it; the PKCE
    pair is generated exactly once here, which is why the URL isn't built twice.
    """
    client_id = config.require_client_id()
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    url = build_authorize_url(client_id, challenge, state)

    if on_url is not None:
        on_url(url)
    if open_browser:
        webbrowser.open(url)

    result = wait_for_callback()

    if "error" in result:
        description = result.get("error_description", result["error"])
        raise AuthError(f"X refused the authorisation: {description}")

    if result.get("state") != state:
        raise AuthError("State mismatch on the callback — aborting rather than trusting it.")

    code = result.get("code")
    if not code:
        raise AuthError("Callback carried no authorisation code.")

    tokens = exchange_code(config, code, verifier)
    TokenStore(config).save(tokens)
    return tokens


def get_valid_tokens(config: Config) -> Tokens:
    """Return usable tokens, refreshing them first if they have expired."""
    store = TokenStore(config)
    tokens = store.load()
    if tokens is None:
        raise AuthError("Not authenticated. Run `claude-x auth login` first.")

    if not tokens.is_expired:
        return tokens

    if not tokens.refresh_token:
        raise AuthError("Access token expired and no refresh token is stored. Log in again.")

    refreshed = refresh_tokens(config, tokens.refresh_token)
    store.save(refreshed)
    return refreshed


def logout(config: Config) -> None:
    TokenStore(config).clear()
