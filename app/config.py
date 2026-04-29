import os
import sys
from pathlib import Path


APP_NAME = "HRResumeRegistryAssistant"


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def _default_project_files_dir() -> Path:
    env_path = os.environ.get("HR_RESUME_ASSISTANT_PROJECT_FILES_DIR")
    if env_path:
        return Path(env_path)

    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / APP_NAME / "project_files"
        return Path.home() / f".{APP_NAME}" / "project_files"

    return BASE_DIR / "project_files"


BASE_DIR = _resource_dir()
PROJECT_FILES_DIR = _default_project_files_dir()
SOURCE_DIR = PROJECT_FILES_DIR / "source"
READY_DIR = PROJECT_FILES_DIR / "ready"
DATA_DIR = PROJECT_FILES_DIR / "data"
REGISTRY_UPLOAD_DIR = SOURCE_DIR / "registry"
RESUME_UPLOAD_DIR = SOURCE_DIR / "resumes"
MATCHED_RESUME_DIR = READY_DIR / "matched_resumes"
EXPORT_DIR = READY_DIR / "registry"
DB_PATH = DATA_DIR / "hr_resume_registry.db"


def ensure_directories() -> None:
    for path in [
        PROJECT_FILES_DIR,
        SOURCE_DIR,
        READY_DIR,
        DATA_DIR,
        REGISTRY_UPLOAD_DIR,
        RESUME_UPLOAD_DIR,
        MATCHED_RESUME_DIR,
        EXPORT_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
