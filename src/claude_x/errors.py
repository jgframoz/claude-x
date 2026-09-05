"""Exceptions raised by claude-x.

All of these are caught at the CLI boundary and rendered as a clean message
rather than a traceback.
"""


class ClaudeXError(Exception):
    """Base class for every error this tool raises deliberately."""


class ConfigError(ClaudeXError):
    """Something is missing or malformed in the local configuration."""


class AuthError(ClaudeXError):
    """The user is not authenticated, or the stored tokens can't be refreshed."""


class APIError(ClaudeXError):
    """The X API returned an error response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PolicyError(ClaudeXError):
    """A requested action is refused because it would breach X's automation rules.

    This exists to make refusals explicit and greppable — see README for the
    rules this tool is built around.
    """
