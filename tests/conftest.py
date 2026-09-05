from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Keep tests away from the real environment and the real ~/.claude-x.

    Autouse so no test can accidentally read the developer's own credentials or
    write to their actual post history.
    """
    for name in ("X_CLIENT_ID", "X_CLIENT_SECRET", "CLAUDE_X_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_X_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)
    return tmp_path
