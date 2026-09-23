"""Isolated FastVPN roots for the test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    (root / "tcp").mkdir(parents=True)
    (root / "udp").mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setenv("FASTVPN_ROOT", str(root))
    monkeypatch.setenv("FASTVPN_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("FASTVPN_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("FASTVPN_CACHE_HOME", str(tmp_path / "cache"))
    for name in ("FASTVPN_USERNAME", "FASTVPN_PASSWORD", "FASTVPN_CREDENTIALS"):
        monkeypatch.delenv(name, raising=False)
    return root
