"""Configuration loading and the constants the OAuth flow depends on.

Credentials are read from `.env.local` (gitignored) or the process environment.
They are never written to disk by this module and never included in `__repr__`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigError

# The loopback port registered as the app's callback URI in the X developer
# console. Changing this means updating the app settings there too.
CALLBACK_PORT = 8723
REDIRECT_URI = f"http://127.0.0.1:{CALLBACK_PORT}/callback"

# offline.access is what gets us a refresh token; without it the user would have
# to re-authorize every couple of hours.
SCOPES = ("tweet.read", "tweet.write", "users.read", "offline.access")

DEFAULT_DATA_DIR = Path.home() / ".claude-x"
ENV_FILENAME = ".env.local"

# Pay-per-use pricing as of Feb 2026. Used to warn before spending money —
# a post containing a link costs 13x a plain one.
COST_PER_POST_USD = 0.015
COST_PER_POST_WITH_LINK_USD = 0.20


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration.

    `client_secret` is None for a public (Native App) client, which is what the
    PKCE flow expects and what this project is set up to use.
    """

    client_id: str | None
    client_secret: str | None
    data_dir: Path
    dry_run: bool

    def require_client_id(self) -> str:
        """Return the client id, or explain how to set it."""
        if not self.client_id:
            raise ConfigError(
                f"X_CLIENT_ID is not set. Add it to {ENV_FILENAME} in the project root:\n"
                f"    X_CLIENT_ID=your_client_id\n"
                "You can find it in the X developer console under your app's "
                "'Keys & Tokens' tab."
            )
        return self.client_id

    def __repr__(self) -> str:  # pragma: no cover - trivial
        # Deliberately omits credential values so they can't leak into logs.
        return (
            f"Config(client_id={'set' if self.client_id else 'unset'}, "
            f"client_secret={'set' if self.client_secret else 'unset'}, "
            f"data_dir={self.data_dir}, dry_run={self.dry_run})"
        )


def find_env_file(start: Path | None = None) -> Path | None:
    """Walk up from `start` looking for a .env.local file.

    Lets the CLI work from anywhere inside the project rather than only its root.
    """
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / ENV_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_config(*, dry_run: bool = True, env_file: Path | None = None) -> Config:
    """Build a Config from .env.local plus the process environment.

    Real environment variables win over the file, so CI and one-off overrides
    don't need a file to exist at all.
    """
    path = env_file if env_file is not None else find_env_file()
    if path is not None:
        load_dotenv(path, override=False)

    data_dir_raw = os.getenv("CLAUDE_X_DATA_DIR")
    data_dir = Path(data_dir_raw).expanduser() if data_dir_raw else DEFAULT_DATA_DIR

    return Config(
        client_id=os.getenv("X_CLIENT_ID") or None,
        client_secret=os.getenv("X_CLIENT_SECRET") or None,
        data_dir=data_dir,
        dry_run=dry_run,
    )


def ensure_data_dir(config: Config) -> Path:
    """Create the data directory, owner-only, and return it.

    Tokens and post history live here, so the permissions matter even though
    the Keychain holds the sensitive half.
    """
    config.data_dir.mkdir(parents=True, exist_ok=True)
    config.data_dir.chmod(0o700)
    return config.data_dir
