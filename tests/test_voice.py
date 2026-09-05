from __future__ import annotations

from claude_x import voice
from claude_x.config import load_config


def test_voice_is_seeded_on_first_use(monkeypatch):
    config = load_config()
    path = voice.ensure_voice(config)

    assert path.is_file()
    assert "Tone" in path.read_text()


def test_seeding_uses_the_repo_voice_guide(monkeypatch):
    """An editable install should pick up the real VOICE.md, not the fallback."""
    text = voice.read_voice(load_config())

    assert "highest-leverage file" in text or "Edit this file" in text


def test_existing_voice_guide_is_never_overwritten(monkeypatch):
    config = load_config()
    path = voice.ensure_voice(config)
    path.write_text("# My own voice\nWrite like me.\n")

    assert "Write like me." in voice.read_voice(config)


def test_voice_path_lives_in_the_data_dir(monkeypatch):
    config = load_config()
    assert voice.voice_path(config).parent == config.data_dir
