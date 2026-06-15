from __future__ import annotations

from pathlib import Path
import shutil

from hr_matcher.models import Candidate, MatchResult, ResumeAudit, ResumeFile
from hr_matcher.name_tools import (
    filename_tokens,
    FIRST_NAME_TOKENS,
    filename_windows,
    load_aliases,
    name_tokens,
    name_variants,
    normalize_text,
    safe_filename,
    token_variants,
)
from hr_matcher.similarity import ratio, token_set_ratio, token_sort_ratio


SUPPORTED_RESUME_EXTENSIONS = {".pdf", ".doc", ".docx", ".rtf", ".odt", ".txt"}


def scan_resumes(resumes_dir: Path) -> list[ResumeFile]:
    files: list[ResumeFile] = []
    for path in sorted(resumes_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_RESUME_EXTENSIONS:
            files.append(ResumeFile(path=path, original_filename=path.name))
    return files


def match_candidates(
    candidates: list[Candidate],
    resumes: list[ResumeFile],
    aliases_path: Path | None = None,
    auto_threshold: int = 92,
    review_threshold: int = 78,
    gap_threshold: int = 8,
) -> list[MatchResult]:
    results, _resume_audits = match_candidates_with_audit(
        candidates,
        resumes,
        aliases_path=aliases_path,
        auto_threshold=auto_threshold,
        review_threshold=review_threshold,
        gap_threshold=gap_threshold,
    )
    return results


def match_candidates_with_audit(
    candidates: list[Candidate],
    resumes: list[ResumeFile],
    aliases_path: Path | None = None,
    auto_threshold: int = 92,
    review_threshold: int = 78,
    gap_threshold: int = 8,
) -> tuple[list[MatchResult], list[ResumeAudit]]:
    aliases = load_aliases(aliases_path)
    candidate_variants = {candidate: name_variants(candidate.full_name, aliases=aliases) for candidate in candidates}
    candidate_index = _build_candidate_index(candidate_variants)
    resume_windows = {resume: filename_windows(resume.original_filename) for resume in resumes}

    resume_audits: list[ResumeAudit] = []
    for resume in resumes:
        shortlist = _candidate_shortlist(resume_windows[resume], candidate_index, candidates)
        scored = sorted(
            [
                (
                    *_apply_evidence_rules(
                        *_score(candidate_variants[candidate], resume_windows[resume], resume.original_filename),
                        candidate=candidate,
                        resume=resume,
                        aliases=aliases,
                        auto_threshold=auto_threshold,
                        review_threshold=review_threshold,
                    ),
                    candidate,
                )
                for candidate in shortlist
            ],
            key=lambda item: item[0],
            reverse=True,
        )
        best_score, best_reason, best_candidate = scored[0] if scored else (0.0, "в Excel нет кандидатов для сравнения", None)
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        status = _classify(best_score, second_score, auto_threshold, review_threshold, gap_threshold)
        resume_audits.append(
            ResumeAudit(
                resume=resume,
                best_candidate=best_candidate,
                score=round(best_score, 2),
                second_score=round(second_score, 2),
                status=status,
                reason=f"{best_reason}; второй результат {second_score:.0f}/100",
            )
        )

    best_resume_by_candidate: dict[Candidate, ResumeAudit] = {}
    for audit in resume_audits:
        if audit.best_candidate is None or audit.status not in {"matched", "review"}:
            continue
        previous = best_resume_by_candidate.get(audit.best_candidate)
        if previous is None or audit.score > previous.score:
            best_resume_by_candidate[audit.best_candidate] = audit

    assigned_resumes = {audit.resume for audit in best_resume_by_candidate.values()}
    resume_audits = [
        ResumeAudit(
            resume=audit.resume,
            best_candidate=audit.best_candidate,
            score=audit.score,
            second_score=audit.second_score,
            status=audit.status,
            reason=audit.reason,
            assigned=audit.resume in assigned_resumes,
        )
        for audit in resume_audits
    ]

    result_by_candidate: dict[Candidate, MatchResult] = {}
    for candidate, audit in best_resume_by_candidate.items():
        result_by_candidate[candidate] = MatchResult(
            candidate=candidate,
            resume=audit.resume,
            score=audit.score,
            second_score=audit.second_score,
            status=audit.status,
            reason=audit.reason,
        )

    results = []
    for candidate in candidates:
        results.append(
            result_by_candidate.get(
                candidate,
                MatchResult(
                    candidate=candidate,
                    resume=None,
                    score=0.0,
                    second_score=0.0,
                    status="unmatched",
                    reason="для кандидата не найдено закрепленное резюме",
                ),
            )
        )
    return results, resume_audits


def copy_results(results: list[MatchResult], output_dir: Path) -> list[MatchResult]:
    matched_dir = output_dir / "matched_resumes"
    review_dir = output_dir / "review_resumes"
    matched_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    copied: list[MatchResult] = []
    for result in results:
        if not result.resume or result.status not in {"matched", "review"}:
            copied.append(result)
            continue
        marker = "MATCHED" if result.status == "matched" else "REVIEW"
        target_dir = matched_dir if result.status == "matched" else review_dir
        filename = "__".join(
            [
                safe_filename(result.candidate.candidate_code, max_length=40),
                marker,
                safe_filename(result.candidate.full_name, max_length=80),
                safe_filename(result.candidate.vacancy or "Vacancy", max_length=60),
            ]
        )
        target = _unique_path(target_dir / f"{filename}{result.resume.path.suffix.lower()}")
        shutil.copy2(result.resume.path, target)
        copied.append(
            MatchResult(
                candidate=result.candidate,
                resume=result.resume,
                score=result.score,
                second_score=result.second_score,
                status=result.status,
                reason=result.reason,
                output_path=target,
            )
        )
    return copied


def _score(candidate_variants: set[str], resume_windows: set[str], filename: str) -> tuple[float, str]:
    if not candidate_variants or not resume_windows:
        return 0.0, "не хватает ФИО для сравнения"
    best = 0.0
    best_pair = ("", "")
    full_filename = normalize_text(Path(filename).stem)
    full_filename_compact = full_filename.replace(" ", "")
    for candidate_name in candidate_variants:
        candidate_compact = candidate_name.replace(" ", "")
        best_full = max(token_set_ratio(candidate_name, full_filename), ratio(candidate_compact, full_filename_compact))
        if best_full > best:
            best = best_full
            best_pair = (candidate_name, full_filename)
        for window in resume_windows:
            score = max(
                token_sort_ratio(candidate_name, window),
                token_set_ratio(candidate_name, window),
                ratio(candidate_compact, window.replace(" ", "")),
            )
            if score > best:
                best = score
                best_pair = (candidate_name, window)
    return best, f"ФИО из Excel '{best_pair[0]}' похоже на имя файла '{best_pair[1]}' ({best:.0f}/100)"


def _apply_evidence_rules(
    score: float,
    reason: str,
    candidate: Candidate,
    resume: ResumeFile,
    aliases: dict[str, list[str]],
    auto_threshold: int,
    review_threshold: int,
) -> tuple[float, str]:
    if not _surname_is_visible(candidate, resume, aliases):
        capped = min(score, review_threshold - 1)
        return capped, f"{reason}; фамилия кандидата не найдена в имени файла, score ограничен до {capped:.0f}/100"
    if not _filename_has_two_name_signals(candidate, resume, aliases):
        capped = min(score, auto_threshold - 1)
        return capped, f"{reason}; в имени файла меньше двух признаков ФИО, score ограничен до {capped:.0f}/100"
    return score, reason


def _surname_is_visible(candidate: Candidate, resume: ResumeFile, aliases: dict[str, list[str]]) -> bool:
    tokens = name_tokens(candidate.full_name)
    if not tokens:
        return False
    surname_token = _likely_surname_token(tokens)
    surname_variants = token_variants(surname_token, aliases=aliases)
    resume_text = normalize_text(Path(resume.original_filename).stem)
    resume_text_compact = resume_text.replace(" ", "")
    resume_token_set = set(filename_tokens(resume.original_filename))
    for surname in surname_variants:
        if surname in resume_token_set or surname in resume_text_compact:
            return True
    return False


def _filename_has_two_name_signals(candidate: Candidate, resume: ResumeFile, aliases: dict[str, list[str]]) -> bool:
    if len(filename_tokens(resume.original_filename)) >= 2:
        return True
    compact_filename = normalize_text(Path(resume.original_filename).stem).replace(" ", "")
    visible = 0
    for token in name_tokens(candidate.full_name)[:3]:
        variants = token_variants(token, aliases=aliases)
        if any(variant and variant in compact_filename for variant in variants):
            visible += 1
    return visible >= 2


def _likely_surname_token(tokens: list[str]) -> str:
    if len(tokens) >= 2 and tokens[0] in FIRST_NAME_TOKENS:
        return tokens[1]
    return tokens[0]


def _classify(score: float, second_score: float, auto_threshold: int, review_threshold: int, gap_threshold: int) -> str:
    if score >= auto_threshold and (score - second_score >= gap_threshold or score >= 98):
        return "matched"
    if score >= review_threshold:
        return "review"
    return "unmatched"


def _build_candidate_index(candidate_variants: dict[Candidate, set[str]]) -> dict[str, set[Candidate]]:
    index: dict[str, set[Candidate]] = {}
    for candidate, variants in candidate_variants.items():
        for variant in variants:
            for token in variant.split():
                if len(token) >= 2:
                    index.setdefault(token, set()).add(candidate)
    return index


def _candidate_shortlist(
    resume_windows: set[str],
    candidate_index: dict[str, set[Candidate]],
    all_candidates: list[Candidate],
) -> set[Candidate]:
    candidates: set[Candidate] = set()
    for window in resume_windows:
        for token in window.split():
            if len(token) >= 2:
                candidates.update(candidate_index.get(token, set()))
    return candidates or set(all_candidates)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Не удалось подобрать свободное имя файла для {path.name}")
