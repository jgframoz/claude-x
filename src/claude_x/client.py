"""A deliberately small X API v2 client.

Four calls, nothing more. Every method returns plain dicts — parsing into richer
types would only add a layer to keep in sync with an API we barely touch.

Note what is *absent*: there is no way to post a reply to somebody else's post.
That is not an oversight and not a flag to flip; see README.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from .auth import get_valid_tokens
from .config import Config
from .errors import APIError

API_BASE = "https://api.x.com/2"
USER_AGENT = "claude-x (+https://github.com/jgframoz/claude-x)"

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    """Canned response used by dry runs so nothing hits the network."""
    with (FIXTURE_DIR / f"{name}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


class XClient:
    """Talks to X on behalf of the authenticated user.

    In dry-run mode every method returns a fixture and makes no request, so the
    whole tool can be exercised without spending money or touching the account.
    """

    def __init__(self, config: Config, *, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=API_BASE, timeout=30.0)
        return self._client

    def _headers(self) -> dict[str, str]:
        tokens = get_valid_tokens(self.config)
        return {
            "Authorization": f"Bearer {tokens.access_token}",
            "User-Agent": USER_AGENT,
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http().request(method, path, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise APIError(f"Request to {path} failed: {exc}") from exc

        if response.status_code == 429:
            raise APIError(
                "Rate limited by X. Wait before retrying — do not loop on this.",
                status_code=429,
            )

        if response.status_code >= 400:
            raise APIError(
                f"X returned {response.status_code} for {path}: {response.text.strip()}",
                status_code=response.status_code,
            )

        return response.json()

    def get_me(self) -> dict[str, Any]:
        """The authenticated user. Cheap, and doubles as an auth check."""
        if self.config.dry_run:
            return _load_fixture("me")
        return self._request("GET", "/users/me")

    def create_tweet(self, text: str) -> dict[str, Any]:
        """Publish a post. This is the only write this client can perform.

        Threading (replying to your own post) arrives in Phase 2 alongside the
        ownership guard that keeps it from becoming a general reply capability.
        """
        if self.config.dry_run:
            fixture = _load_fixture("created_tweet")
            fixture["data"]["text"] = text
            return fixture
        return self._request("POST", "/tweets", json={"text": text})

    def get_mentions(
        self, user_id: str, *, since_id: str | None = None, max_results: int = 25
    ) -> dict[str, Any]:
        """Posts mentioning the user. Read-only input for drafting suggestions."""
        if self.config.dry_run:
            return _load_fixture("mentions")

        params: dict[str, Any] = {
            "max_results": max_results,
            "tweet.fields": "created_at,author_id,conversation_id,text",
            "expansions": "author_id",
            "user.fields": "username,name",
        }
        if since_id:
            params["since_id"] = since_id
        return self._request("GET", f"/users/{user_id}/mentions", params=params)

    def get_tweet_metrics(self, tweet_ids: list[str]) -> dict[str, Any]:
        """Public metrics for the given posts, up to 100 per call."""
        if not tweet_ids:
            return {"data": []}
        if len(tweet_ids) > 100:
            raise APIError("X accepts at most 100 tweet ids per request.")

        if self.config.dry_run:
            return _load_fixture("metrics")

        return self._request(
            "GET",
            "/tweets",
            params={"ids": ",".join(tweet_ids), "tweet.fields": "public_metrics,created_at"},
        )

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> XClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
