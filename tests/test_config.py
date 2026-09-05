from __future__ import annotations

import pytest

from claude_x.config import ENV_FILENAME, Config, ensure_data_dir, find_env_file, load_config
from claude_x.errors import ConfigError


def test_defaults_to_dry_run_and_no_credentials():
    config = load_config()
    assert config.dry_run is True
    assert config.client_id is None
    assert config.client_secret is None


def test_reads_client_id_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ENV_FILENAME
    env_file.write_text("X_CLIENT_ID=abc123\n")

    config = load_config(env_file=env_file)

    assert config.client_id == "abc123"
    assert config.require_client_id() == "abc123"


def test_process_env_wins_over_file(tmp_path, monkeypatch):
    env_file = tmp_path / ENV_FILENAME
    env_file.write_text("X_CLIENT_ID=from_file\n")
    monkeypatch.setenv("X_CLIENT_ID", "from_env")

    assert load_config(env_file=env_file).client_id == "from_env"


def test_require_client_id_explains_how_to_fix_it():
    with pytest.raises(ConfigError, match="X_CLIENT_ID"):
        load_config().require_client_id()


def test_find_env_file_walks_up_from_a_subdirectory(tmp_path, monkeypatch):
    (tmp_path / ENV_FILENAME).write_text("X_CLIENT_ID=x\n")
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert find_env_file() == tmp_path / ENV_FILENAME


def test_find_env_file_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert find_env_file() is None


def test_repr_never_leaks_credential_values(tmp_path):
    config = Config(
        client_id="super-secret-id",
        client_secret="super-secret-value",
        data_dir=tmp_path,
        dry_run=True,
    )
    rendered = repr(config)
    assert "super-secret-id" not in rendered
    assert "super-secret-value" not in rendered


def test_ensure_data_dir_is_owner_only(tmp_path):
    config = load_config()
    created = ensure_data_dir(config)

    assert created.is_dir()
    assert created.stat().st_mode & 0o777 == 0o700
