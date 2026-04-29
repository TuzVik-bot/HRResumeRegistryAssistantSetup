import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.config import DB_PATH, ensure_directories


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    ensure_directories()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS registries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registry_id INTEGER NOT NULL,
                excel_row_number INTEGER NOT NULL,
                candidate_id TEXT NOT NULL,
                full_name TEXT,
                vacancy TEXT,
                status TEXT,
                recruiter TEXT,
                row_data_json TEXT NOT NULL,
                quality_warnings_json TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY (registry_id) REFERENCES registries(id)
            );

            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_hash TEXT,
                extracted_text TEXT,
                profile_json TEXT NOT NULL,
                ai_profile_json TEXT,
                processing_error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ai_resume_cache (
                file_hash TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL,
                resume_id INTEGER,
                score REAL NOT NULL,
                second_score REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                reason TEXT NOT NULL,
                new_filename TEXT,
                output_path TEXT,
                needs_manual_review INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(candidate_id),
                FOREIGN KEY (candidate_id) REFERENCES candidates(id),
                FOREIGN KEY (resume_id) REFERENCES resumes(id)
            );
            """
        )
        _ensure_column(conn, "resumes", "file_hash", "TEXT")
        _ensure_column(conn, "resumes", "ai_profile_json", "TEXT")
        _ensure_column(conn, "resumes", "processing_error", "TEXT")


def reset_working_data() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            DELETE FROM matches;
            DELETE FROM candidates;
            DELETE FROM resumes;
            DELETE FROM registries;
            """
        )


def insert_registry(filename: str, file_path: Path) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO registries (filename, file_path) VALUES (?, ?)",
            (filename, str(file_path)),
        )
        return int(cur.lastrowid)


def insert_candidate(
    registry_id: int,
    excel_row_number: int,
    candidate_id: str,
    row_data: dict[str, Any],
    full_name: str | None,
    vacancy: str | None,
    status: str | None,
    recruiter: str | None,
    quality_warnings: list[str],
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO candidates (
                registry_id, excel_row_number, candidate_id, full_name, vacancy,
                status, recruiter, row_data_json, quality_warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                registry_id,
                excel_row_number,
                candidate_id,
                full_name,
                vacancy,
                status,
                recruiter,
                json.dumps(row_data, ensure_ascii=False, default=str),
                json.dumps(quality_warnings, ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid)


def insert_candidates_bulk(candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        return
    values = []
    for candidate in candidates:
        values.append(
            (
                candidate["registry_id"],
                candidate["excel_row_number"],
                candidate["candidate_id"],
                candidate.get("full_name"),
                candidate.get("vacancy"),
                candidate.get("status"),
                candidate.get("recruiter"),
                json.dumps(candidate["row_data"], ensure_ascii=False, default=str),
                json.dumps(candidate["quality_warnings"], ensure_ascii=False),
            )
        )
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO candidates (
                registry_id, excel_row_number, candidate_id, full_name, vacancy,
                status, recruiter, row_data_json, quality_warnings_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )


def insert_resume(
    original_filename: str,
    file_path: Path,
    file_hash: str,
    extracted_text: str,
    profile: dict[str, Any],
    processing_error: str | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO resumes (
                original_filename, file_path, file_hash, extracted_text,
                profile_json, processing_error
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                original_filename,
                str(file_path),
                file_hash,
                extracted_text,
                json.dumps(profile, ensure_ascii=False),
                processing_error,
            ),
        )
        return int(cur.lastrowid)


def update_resume_profile(
    resume_id: int,
    profile: dict[str, Any],
    ai_profile: dict[str, Any] | None = None,
    processing_error: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE resumes
            SET profile_json = ?,
                ai_profile_json = COALESCE(?, ai_profile_json),
                processing_error = ?
            WHERE id = ?
            """,
            (
                json.dumps(profile, ensure_ascii=False),
                json.dumps(ai_profile, ensure_ascii=False) if ai_profile else None,
                processing_error,
                resume_id,
            ),
        )


def get_cached_ai_response(file_hash: str, provider: str, model: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT response_json
            FROM ai_resume_cache
            WHERE file_hash = ? AND provider = ? AND model = ?
            """,
            (file_hash, provider, model),
        ).fetchone()
        return json.loads(row["response_json"]) if row else None


def upsert_ai_response(file_hash: str, provider: str, model: str, response: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ai_resume_cache (file_hash, provider, model, response_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(file_hash) DO UPDATE SET
                provider=excluded.provider,
                model=excluded.model,
                response_json=excluded.response_json,
                created_at=CURRENT_TIMESTAMP
            """,
            (file_hash, provider, model, json.dumps(response, ensure_ascii=False)),
        )


def upsert_match(match: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO matches (
                candidate_id, resume_id, score, second_score, status, reason,
                new_filename, output_path, needs_manual_review
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                resume_id=excluded.resume_id,
                score=excluded.score,
                second_score=excluded.second_score,
                status=excluded.status,
                reason=excluded.reason,
                new_filename=excluded.new_filename,
                output_path=excluded.output_path,
                needs_manual_review=excluded.needs_manual_review,
                created_at=CURRENT_TIMESTAMP
            """,
            (
                match["candidate_db_id"],
                match.get("resume_db_id"),
                match["score"],
                match.get("second_score", 0),
                match["status"],
                match["reason"],
                match.get("new_filename"),
                match.get("output_path"),
                1 if match.get("needs_manual_review") else 0,
            ),
        )


def set_manual_match(
    candidate_db_id: int,
    resume_db_id: int | None,
    status: str,
    reason: str,
    score: float,
    new_filename: str | None = None,
    output_path: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO matches (
                candidate_id, resume_id, score, second_score, status, reason,
                new_filename, output_path, needs_manual_review
            )
            VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                resume_id=excluded.resume_id,
                score=excluded.score,
                second_score=0,
                status=excluded.status,
                reason=excluded.reason,
                new_filename=excluded.new_filename,
                output_path=excluded.output_path,
                needs_manual_review=excluded.needs_manual_review,
                created_at=CURRENT_TIMESTAMP
            """,
            (
                candidate_db_id,
                resume_db_id,
                score,
                status,
                reason,
                new_filename,
                output_path,
                1 if status == "review" else 0,
            ),
        )


def fetch_all(table: str) -> list[sqlite3.Row]:
    if table not in {"registries", "candidates", "resumes", "matches"}:
        raise ValueError("Unsupported table")
    with get_connection() as conn:
        return list(conn.execute(f"SELECT * FROM {table} ORDER BY id"))


def fetch_candidate(candidate_db_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_db_id,)).fetchone()


def fetch_resume(resume_db_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_db_id,)).fetchone()


def fetch_registry(registry_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM registries WHERE id = ?", (registry_id,)).fetchone()


def fetch_candidates_with_matches() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return list(
            conn.execute(
                """
                SELECT
                    c.*,
                    m.resume_id,
                    m.score,
                    m.second_score,
                    m.status AS match_status,
                    m.reason AS match_reason,
                    m.new_filename,
                    m.output_path,
                    m.needs_manual_review,
                    rg.filename AS registry_filename,
                    rg.file_path AS registry_file_path,
                    r.original_filename AS resume_original_filename,
                    r.file_path AS resume_file_path,
                    r.profile_json AS resume_profile_json,
                    r.processing_error AS resume_processing_error
                FROM candidates c
                LEFT JOIN matches m ON m.candidate_id = c.id
                LEFT JOIN resumes r ON r.id = m.resume_id
                LEFT JOIN registries rg ON rg.id = c.registry_id
                ORDER BY c.excel_row_number
                """
            )
        )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
