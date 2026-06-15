from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, eq=False)
class Candidate:
    row_number: int
    candidate_code: str
    full_name: str
    vacancy: str = ""
    row_values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, eq=False)
class ResumeFile:
    path: Path
    original_filename: str


@dataclass(frozen=True)
class MatchResult:
    candidate: Candidate
    resume: ResumeFile | None
    score: float
    second_score: float
    status: str
    reason: str
    output_path: Path | None = None


@dataclass(frozen=True)
class ResumeAudit:
    resume: ResumeFile
    best_candidate: Candidate | None
    score: float
    second_score: float
    status: str
    reason: str
    assigned: bool = False


@dataclass(frozen=True)
class MatchSummary:
    total_candidates: int
    total_resumes: int
    matched: int
    review: int
    unmatched: int
    report_path: Path
    output_dir: Path
