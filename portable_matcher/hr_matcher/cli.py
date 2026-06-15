from __future__ import annotations

import argparse
from pathlib import Path

from hr_matcher.app import run_match


def main() -> int:
    parser = argparse.ArgumentParser(description="Portable matcher for Excel registry and resume filenames.")
    parser.add_argument("--registry", required=True, help="Путь к Excel-реестру .xlsx")
    parser.add_argument("--resumes", required=True, help="Папка с резюме")
    parser.add_argument("--output", required=True, help="Папка результата")
    parser.add_argument("--aliases", default="", help="Необязательный JSON-файл с вариантами имен")
    args = parser.parse_args()

    summary = run_match(
        registry_path=Path(args.registry),
        resumes_dir=Path(args.resumes),
        output_dir=Path(args.output),
        aliases_path=Path(args.aliases) if args.aliases else None,
    )
    print(f"Кандидатов: {summary.total_candidates}")
    print(f"Резюме: {summary.total_resumes}")
    print(f"Найдено: {summary.matched}")
    print(f"На проверку: {summary.review}")
    print(f"Не найдено: {summary.unmatched}")
    print(f"Отчет: {summary.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
