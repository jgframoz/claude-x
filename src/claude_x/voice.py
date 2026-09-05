"""The user's voice guide.

Lives at ~/.claude-x/VOICE.md so it is reachable from any working directory —
the drafting agent is usually invoked from wherever the user happens to be, not
from this repo. Seeded on first use from the copy shipped with the package.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config, ensure_data_dir

VOICE_FILENAME = "VOICE.md"

_FALLBACK = """# Voice

Edit this file. Every draft is downstream of it.

## Tone
- Technical but human — explain the why, not just the what
- Honest about limits — "this doesn't handle X yet" is good
- Direct, slightly casual. No hype words, no engagement bait.

## The formula
1. Lead with the insight, not the product
2. Show what failed, not just what worked
3. Link to the work
4. End with a real question
"""


def _template() -> Path | None:
    """Find the shipped VOICE.md, in a wheel or an editable checkout."""
    candidates = (
        Path(__file__).parent / "data" / VOICE_FILENAME,
        Path(__file__).resolve().parent.parent.parent / VOICE_FILENAME,
    )
    return next((path for path in candidates if path.is_file()), None)


def voice_path(config: Config) -> Path:
    return config.data_dir / VOICE_FILENAME


def ensure_voice(config: Config) -> Path:
    """Return the user's voice guide, creating it from the template if new."""
    path = voice_path(config)
    if path.is_file():
        return path

    ensure_data_dir(config)
    template = _template()
    path.write_text(
        template.read_text(encoding="utf-8") if template else _FALLBACK,
        encoding="utf-8",
    )
    return path


def read_voice(config: Config) -> str:
    return ensure_voice(config).read_text(encoding="utf-8")
