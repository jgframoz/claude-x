"""Publishing: the one path in this tool that spends money and goes public.

Everything here exists to make that path deliberate — duplicate detection, the
ownership guard on threading, and a record of what was actually sent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from . import policy
from .client import XClient
from .config import Config
from .errors import PolicyError
from .store import JsonlStore

POSTS_FILENAME = "posts.jsonl"


# How the human's approval reached this publish. Recorded so the history can
# answer "did I actually approve that?" months later. No flag can *prove* the
# user approved — the caller supplies this — but an audit trail of the claimed
# route is still worth having, and it makes an agent state its claim explicitly.
APPROVAL_INTERACTIVE = "interactive"  # a human typed 'post' at the prompt
APPROVAL_HUMAN_FLAG = "human-flag"  # a human passed --yes themselves
APPROVAL_RELAYED = "agent-relayed"  # an agent relaying approval given in chat
APPROVAL_NONE = "none"  # dry run: nothing was published


@dataclass(frozen=True)
class PublishedPost:
    id: str
    text: str
    url: str
    cost_usd: float
    posted_at: str
    dry_run: bool
    in_reply_to: str | None = None
    approval: str = APPROVAL_NONE


class PostLog:
    """History of what this tool has published.

    Doubles as the source of truth for two checks: whether a draft duplicates
    something already sent, and whether a post is ours to reply to.
    """

    def __init__(self, config: Config) -> None:
        self.store = JsonlStore(config.data_dir / POSTS_FILENAME)

    def record(self, post: PublishedPost) -> None:
        self.store.append(
            {
                "id": post.id,
                "text": post.text,
                "url": post.url,
                "cost_usd": post.cost_usd,
                "posted_at": post.posted_at,
                "dry_run": post.dry_run,
                "in_reply_to": post.in_reply_to,
                "approval": post.approval,
            }
        )

    def contains_text(self, text: str) -> bool:
        target = policy.normalise(text)
        return any(
            policy.normalise(record.get("text", "")) == target
            for record in self.store
            if not record.get("dry_run")
        )

    def owns(self, tweet_id: str) -> bool:
        """True if we published this post — dry-run entries don't count."""
        return any(
            record.get("id") == tweet_id and not record.get("dry_run") for record in self.store
        )

    def forget(self, tweet_id: str) -> int:
        """Drop a post from the local record, for deletion compliance."""
        return self.store.delete_where("id", tweet_id)

    def all(self) -> list[dict[str, Any]]:
        return self.store.read_all()


class Publisher:
    """Turns approved drafts into published posts."""

    def __init__(self, config: Config, client: XClient | None = None) -> None:
        self.config = config
        self.client = client or XClient(config)
        self.log = PostLog(config)

    def _guard_reply_target(self, tweet_id: str) -> None:
        """Refuse to reply to anything we did not publish ourselves.

        Threading is replying to your own post, which is just publishing your
        own content. Replying to *other people* automatically is what X's
        automation rules restrict, so the id has to be in our own log.
        """
        if not self.log.owns(tweet_id):
            raise PolicyError(
                f"Refusing to reply to post {tweet_id}: it is not one of ours. "
                "This tool only chains replies onto your own posts (threads). "
                "Automated replies to other people require prior written approval "
                "from X — see the README."
            )

    def publish(
        self,
        text: str,
        *,
        in_reply_to: str | None = None,
        approval: str = APPROVAL_NONE,
    ) -> PublishedPost:
        """Publish a single post. Approval is the caller's to establish."""
        policy.check_length(text)
        policy.check_style(text)

        if in_reply_to is not None:
            self._guard_reply_target(in_reply_to)

        if self.log.contains_text(text):
            raise PolicyError(
                "This exact text has been published before. Change it, or remove "
                "the old entry from the post log if it was deleted on X."
            )

        response = self.client.create_tweet(text, in_reply_to_tweet_id=in_reply_to)
        data = response["data"]
        tweet_id = data["id"]

        post = PublishedPost(
            id=tweet_id,
            text=text,
            url=f"https://x.com/i/web/status/{tweet_id}",
            cost_usd=0.0 if self.config.dry_run else policy.estimate_cost(text),
            posted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            dry_run=self.config.dry_run,
            in_reply_to=in_reply_to,
            approval=APPROVAL_NONE if self.config.dry_run else approval,
        )
        self.log.record(post)
        return post

    def publish_thread(
        self, parts: list[str], *, approval: str = APPROVAL_NONE
    ) -> list[PublishedPost]:
        """Publish parts as a chain, each replying to the one before it.

        Every reply target is a post this call just created, so the ownership
        guard is satisfied by construction — it stays as defence in depth.

        If a later part fails, the earlier ones are already public. The caller
        is told which ones landed rather than the failure being swallowed.
        """
        for part in parts:
            policy.check_length(part)
            policy.check_style(part)

        published: list[PublishedPost] = []
        previous_id: str | None = None

        for index, part in enumerate(parts):
            try:
                post = self.publish(part, in_reply_to=previous_id, approval=approval)
            except Exception as exc:
                if published:
                    raise PolicyError(
                        f"Thread part {index + 1} failed ({exc}). Parts 1-{len(published)} "
                        f"are already published: {published[-1].url}"
                    ) from exc
                raise
            published.append(post)
            previous_id = post.id

        return published

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Publisher:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
