from pathlib import Path

from src.data_hub.db import DataHubDB


def test_database_path_uses_environment_when_not_explicit(monkeypatch, tmp_path):
    target = tmp_path / "persistent" / "tactical_lab.db"
    monkeypatch.setenv("DATABASE_PATH", str(target))
    monkeypatch.setattr(DataHubDB, "migrate", lambda self: None)

    db = DataHubDB()

    assert db.db_path == target
    assert target.parent.is_dir()


def test_explicit_database_path_overrides_environment(monkeypatch, tmp_path):
    env_target = tmp_path / "env.db"
    explicit_target = tmp_path / "explicit.db"
    monkeypatch.setenv("DATABASE_PATH", str(env_target))
    monkeypatch.setattr(DataHubDB, "migrate", lambda self: None)

    db = DataHubDB(db_path=explicit_target)

    assert db.db_path == explicit_target
