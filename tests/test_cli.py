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
