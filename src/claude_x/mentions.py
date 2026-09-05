"""Mentions: fetching them, and remembering which ones have been dealt with.

There is deliberately no reply-sending anywhere in this module. Drafting a
suggestion is allowed; posting it automatically is what X's automation rules
restrict, so the user sends replies by hand. Adding a send function here is not
a small change, it is the change that puts the account at risk.

These records are other people's posts held on this machine, so `forget` exists
for the deletion-compliance obligation in X's developer agreement.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from .client import XClient
from .config import Config
from .store import JsonlStore

MENTIONS_FILENAME = "mentions.jsonl"


@dataclass(frozen=True)
class Mention:
    id: str
    username: str
    author_id: str
    text: str
    created_at: str
    fetched_at: str
    handled: bool = False

    @property
    def url(self) -> str:
        return f"https://x.com/{self.username}/status/{self.id}"


class MentionLog:
    """Local record of mentions already seen."""

    def __init__(self, config: Config) -> None:
        self.store = JsonlStore(config.data_dir / MENTIONS_FILENAME)

    def all(self) -> list[Mention]:
        return [Mention(**record) for record in self.store]

    def known_ids(self) -> set[str]:
        return {record.get("id", "") for record in self.store}

    def unhandled(self) -> list[Mention]:
        return [mention for mention in self.all() if not mention.handled]

    def newest_id(self) -> str | None:
        """Highest id seen, for since_id on the next fetch.

        X ids are snowflakes, so numerically larger means newer. Passing this
        keeps repeat fetches from re-reading (and re-billing) old mentions.
        """
        ids = [mention.id for mention in self.all() if mention.id.isdigit()]
        return max(ids, key=int) if ids else None

    def record(self, mention: Mention) -> None:
        self.store.append(asdict(mention))

    def mark_handled(self, mention_id: str) -> bool:
        """Mark one as dealt with. Append-only storage, so rewrite the record."""
        matches = [record for record in self.store if record.get("id") == mention_id]
        if not matches:
            return False

        self.store.delete_where("id", mention_id)
        updated = {**matches[-1], "handled": True}
        self.store.append(updated)
        return True

    def forget(self, mention_id: str) -> int:
        """Delete a locally stored mention, for deletion compliance."""
        return self.store.delete_where("id", mention_id)


def _usernames(payload: dict[str, Any]) -> dict[str, str]:
    users = payload.get("includes", {}).get("users", [])
    return {user["id"]: user.get("username", "unknown") for user in users}


def fetch_new(config: Config, client: XClient) -> list[Mention]:
    """Fetch mentions newer than anything already stored, and record them.

    Reads are billed, so this asks only for what it hasn't seen.

    A dry run returns the fixture without storing it. Persisting fake mentions
    would put a fabricated id into the log, which then becomes the since_id for
    the next real fetch and leaves invented people in the user's history.
    """
    log = MentionLog(config)
    me = client.get_me()["data"]

    payload = client.get_mentions(me["id"], since_id=log.newest_id())
    usernames = _usernames(payload)
    known = log.known_ids()
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    new: list[Mention] = []
    for item in payload.get("data", []):
        if item["id"] in known:
            continue
        mention = Mention(
            id=item["id"],
            username=usernames.get(item.get("author_id", ""), "unknown"),
            author_id=item.get("author_id", ""),
            text=item.get("text", ""),
            created_at=item.get("created_at", ""),
            fetched_at=fetched_at,
        )
        if not config.dry_run:
            log.record(mention)
        new.append(mention)

    return new
