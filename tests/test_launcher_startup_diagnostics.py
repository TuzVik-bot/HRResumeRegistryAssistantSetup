from pathlib import Path

import launcher


def test_launcher_write_access_check_uses_project_files(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "PROJECT_FILES_DIR", tmp_path / "project_files")

    ok, detail = launcher._check_project_files_write_access()

    assert ok is True
    assert detail == "ok"


def test_launcher_logs_startup_environment(tmp_path, monkeypatch):
    log_path = tmp_path / "launcher.log"
    monkeypatch.setattr(launcher, "PROJECT_FILES_DIR", tmp_path / "project_files")
    monkeypatch.setattr(launcher, "LOG_DIR", tmp_path)
    monkeypatch.setattr(launcher, "LAUNCHER_LOG_PATH", log_path)
    monkeypatch.setattr(launcher, "get_soffice_status", lambda: {"available": True, "path": str(Path("/fake/soffice"))})

    launcher._log_startup_environment()
    content = log_path.read_text(encoding="utf-8")

    assert "Python version:" in content
    assert "Project files dir:" in content
    assert "Base dir:" in content
    assert "LibreOffice/soffice: found at /fake/soffice" in content
