"""pillar_loader caching (uses temp pillar files)."""

from pathlib import Path

import pytest
import yaml

import app.utils.pillar_loader as pl


@pytest.fixture(autouse=True)
def clear_pillar_cache():
    pl._config_cache = None
    pl._config_mtime = None
    yield
    pl._config_cache = None
    pl._config_mtime = None


def test_pillars_missing_file_returns_empty(tmp_path: Path, monkeypatch):
    missing = tmp_path / "none.yaml"
    monkeypatch.setenv("AGENT_PILLARS_PATH", str(missing))
    assert pl.get_pillar_config() == {}


def test_pillars_reads_and_cache_hit(tmp_path: Path, monkeypatch):
    fp = tmp_path / "pillars.yaml"
    fp.write_text(yaml.safe_dump({"orchestration": {"x": 1}}), encoding="utf-8")
    monkeypatch.setenv("AGENT_PILLARS_PATH", str(fp))

    first = pl.get_pillar_config()
    assert first.get("orchestration", {}).get("x") == 1
    second = pl.get_pillar_config()
    assert second is first


def test_pillars_force_reload(tmp_path: Path, monkeypatch):
    fp = tmp_path / "pillars.yaml"
    fp.write_text(yaml.safe_dump({"a": 1}), encoding="utf-8")
    monkeypatch.setenv("AGENT_PILLARS_PATH", str(fp))
    pl.get_pillar_config()
    fp.write_text(yaml.safe_dump({"a": 2}), encoding="utf-8")
    refreshed = pl.get_pillar_config(force_reload=True)
    assert refreshed.get("a") == 2


def test_pillars_invalid_yaml_returns_empty(monkeypatch, tmp_path: Path):
    fp = tmp_path / "pillars.yaml"
    fp.write_text(": not [ valid", encoding="utf-8")
    monkeypatch.setenv("AGENT_PILLARS_PATH", str(fp))

    assert pl.get_pillar_config(force_reload=True) == {}


def test_pillars_file_path_env(monkeypatch, tmp_path: Path):
    p = tmp_path / "cfg.yaml"
    monkeypatch.setenv("AGENT_PILLARS_PATH", str(p))
    assert pl.pillars_file_path() == p.resolve()


def test_pillars_file_path_repo_relative(monkeypatch):
    monkeypatch.delenv("AGENT_PILLARS_PATH", raising=False)
    path = pl.pillars_file_path()
    assert path.name == "agent_pillars.yaml"
