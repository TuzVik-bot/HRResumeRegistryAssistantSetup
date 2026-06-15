from __future__ import annotations

from pathlib import Path
import sys

from hr_matcher.excel_io import read_candidates
from hr_matcher.matcher import copy_results, match_candidates_with_audit, scan_resumes
from hr_matcher.models import MatchSummary
from hr_matcher.report import write_report


def run_match(registry_path: Path, resumes_dir: Path, output_dir: Path, aliases_path: Path | None = None) -> MatchSummary:
    candidates = read_candidates(Path(registry_path))
    resumes = scan_resumes(Path(resumes_dir))
    results, resume_audits = match_candidates_with_audit(candidates, resumes, aliases_path=aliases_path or _default_aliases_path())
    copied_results = copy_results(results, Path(output_dir))
    report_path = write_report(copied_results, resumes, Path(output_dir), resume_audits=resume_audits)
    return MatchSummary(
        total_candidates=len(candidates),
        total_resumes=len(resumes),
        matched=sum(1 for result in copied_results if result.status == "matched"),
        review=sum(1 for result in copied_results if result.status == "review"),
        unmatched=sum(1 for result in copied_results if result.status == "unmatched"),
        report_path=report_path,
        output_dir=Path(output_dir),
    )


def _default_aliases_path() -> Path | None:
    candidates = []
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        candidates.append(executable.parent / "config" / "name_aliases.json")
        if ".app/Contents/MacOS" in str(executable):
            candidates.append(executable.parents[3] / "config" / "name_aliases.json")
    candidates.append(Path(__file__).resolve().parents[1] / "config" / "name_aliases.json")
    candidates.append(Path.cwd() / "config" / "name_aliases.json")
    for path in candidates:
        if path.exists():
            return path
    return None
