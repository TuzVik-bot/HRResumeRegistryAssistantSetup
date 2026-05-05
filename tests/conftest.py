from pathlib import Path

import pytest

from app import config, database, exporter, settings


@pytest.fixture
def isolated_project_files(tmp_path, monkeypatch):
    project_files_dir = tmp_path / "project_files"
    source_dir = project_files_dir / "source"
    ready_dir = project_files_dir / "ready"
    data_dir = project_files_dir / "data"
    registry_dir = source_dir / "registry"
    resume_dir = source_dir / "resumes"
    matched_dir = ready_dir / "matched_resumes"
    export_dir = ready_dir / "registry"
    db_path = data_dir / "test.db"
    env_path = project_files_dir / ".env"

    monkeypatch.setattr(config, "PROJECT_FILES_DIR", project_files_dir)
    monkeypatch.setattr(config, "SOURCE_DIR", source_dir)
    monkeypatch.setattr(config, "READY_DIR", ready_dir)
    monkeypatch.setattr(config, "DATA_DIR", data_dir)
    monkeypatch.setattr(config, "REGISTRY_UPLOAD_DIR", registry_dir)
    monkeypatch.setattr(config, "RESUME_UPLOAD_DIR", resume_dir)
    monkeypatch.setattr(config, "MATCHED_RESUME_DIR", matched_dir)
    monkeypatch.setattr(config, "EXPORT_DIR", export_dir)
    monkeypatch.setattr(config, "DB_PATH", db_path)

    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(exporter, "EXPORT_DIR", export_dir)
    monkeypatch.setattr(settings, "ENV_PATH", env_path)

    for path in [project_files_dir, source_dir, ready_dir, data_dir, registry_dir, resume_dir, matched_dir, export_dir]:
        path.mkdir(parents=True, exist_ok=True)

    return {
        "project_files_dir": project_files_dir,
        "registry_dir": registry_dir,
        "resume_dir": resume_dir,
        "export_dir": export_dir,
        "db_path": db_path,
    }
