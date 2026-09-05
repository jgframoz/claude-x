"""Checks on the skill definition itself.

The skill is prose, so these are shallow by nature — but the compliance rules
inside it are load-bearing, and a well-meaning edit could quietly remove them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SKILL_PATH = REPO_ROOT / "skills" / "claude-x" / "SKILL.md"


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def test_skill_exists_where_the_readme_says_it_does():
    assert SKILL_PATH.is_file()


def test_skill_has_frontmatter_with_name_and_description(skill_text):
    assert skill_text.startswith("---\n")
    frontmatter = skill_text.split("---", 2)[1]
    assert "name: claude-x" in frontmatter
    assert "description:" in frontmatter


def test_description_covers_the_phrases_that_should_trigger_it(skill_text):
    """A skill that never triggers is worse than no skill."""
    description = skill_text.split("---", 2)[1]
    for phrase in ("tweet", "post to X", "thread", "mentions"):
        assert phrase in description


def test_skill_forbids_publishing_without_approval(skill_text):
    assert "Never publish without the user's explicit go-ahead" in skill_text


def test_skill_forbids_the_yes_flag(skill_text):
    """--yes bypasses the confirmation prompt; the agent must never pass it."""
    assert "Never pass `--yes`" in skill_text


def test_skill_states_that_replies_are_drafted_not_posted(skill_text):
    assert "may **not** post replies" in skill_text


def test_skill_tells_the_agent_to_read_the_voice_guide(skill_text):
    assert "VOICE.md" in skill_text
    assert (REPO_ROOT / "VOICE.md").is_file()


def test_skill_warns_about_the_link_price(skill_text):
    assert "$0.20" in skill_text
