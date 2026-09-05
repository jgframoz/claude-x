from __future__ import annotations

from typer.testing import CliRunner

from claude_x import __version__
from claude_x.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_config_reports_dry_run_by_default():
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "dry run" in result.stdout


def test_live_flag_switches_mode():
    result = runner.invoke(app, ["--live", "config"])
    assert result.exit_code == 0
    assert "live" in result.stdout


def test_config_never_prints_the_client_id_value(monkeypatch):
    monkeypatch.setenv("X_CLIENT_ID", "totally-secret-value")

    result = runner.invoke(app, ["config"])

    assert result.exit_code == 0
    assert "totally-secret-value" not in result.stdout
    assert "set" in result.stdout


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert "claude-x" in result.stdout


def test_dry_run_rejects_an_em_dash_before_the_live_attempt():
    """A rehearsal must fail on style, or the agent thinks the draft is fine."""
    result = runner.invoke(app, ["post", "--text", "built a thing — it works"])

    assert result.exit_code != 0


def test_dry_run_rejects_an_overlong_draft():
    result = runner.invoke(app, ["post", "--text", "a" * 281])

    assert result.exit_code != 0


def test_entry_point_uses_the_error_handling_wrapper():
    """pyproject's console script must point at run(), not app().

    Pointing it at app() bypasses ClaudeXError handling and users get a
    traceback instead of a message. That regression is invisible in tests
    that call app() directly, so assert on the packaging metadata.
    """
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    scripts = tomllib.loads(pyproject.read_text())["project"]["scripts"]

    assert scripts["claude-x"] == "claude_x.cli:run"
