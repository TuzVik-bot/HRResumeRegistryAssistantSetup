from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from hr_matcher.app import run_match


class MatcherWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("HR Resume Matcher")
        self.geometry("860x600")
        self.minsize(760, 520)
        self.registry_var = tk.StringVar()
        self.resumes_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Выберите Excel-реестр и папку с резюме.")
        self.result_path: Path | None = None
        self.report_path: Path | None = None
        self.matched_resumes_path: Path | None = None
        self.review_resumes_path: Path | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(22, 18, 22, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Сопоставление резюме с реестром", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Локальная portable-программа: Excel + имена файлов, без AI и сервисов.",
            foreground="#555555",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        body = ttk.Frame(self, padding=(22, 8, 22, 16))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        self._path_row(body, 0, "Excel-реестр", self.registry_var, "Загрузить Excel", self._choose_registry)
        self._path_row(body, 1, "Папка с резюме", self.resumes_var, "Загрузить резюме", self._choose_resumes)
        self._path_row(body, 2, "Папка результата", self.output_var, "Выбрать папку", self._choose_output)

        action_bar = ttk.Frame(body)
        action_bar.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(18, 8))
        action_bar.columnconfigure(0, weight=1)
        self.run_button = ttk.Button(action_bar, text="Сопоставить", command=self._run)
        self.run_button.grid(row=0, column=1, padx=(8, 0))

        self.progress = ttk.Progressbar(body, mode="indeterminate")
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 8))

        result_box = ttk.LabelFrame(body, text="Готовые файлы", padding=12)
        result_box.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        result_box.columnconfigure(4, weight=1)
        self.open_report_button = ttk.Button(result_box, text="Открыть Excel-отчет", command=self._open_report, state="disabled")
        self.open_report_button.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.open_matched_button = ttk.Button(result_box, text="Открыть готовые резюме", command=self._open_matched_resumes, state="disabled")
        self.open_matched_button.grid(row=0, column=1, sticky="w", padx=(0, 8))
        self.open_review_button = ttk.Button(result_box, text="Открыть резюме на проверку", command=self._open_review_resumes, state="disabled")
        self.open_review_button.grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.open_result_button = ttk.Button(result_box, text="Открыть папку результата", command=self._open_result, state="disabled")
        self.open_result_button.grid(row=0, column=3, sticky="w")

        status_box = ttk.LabelFrame(body, text="Статус", padding=12)
        status_box.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        status_box.columnconfigure(0, weight=1)
        status_box.rowconfigure(0, weight=1)
        ttk.Label(status_box, textvariable=self.status_var, wraplength=780, justify="left").grid(row=0, column=0, sticky="nw")

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, button_text: str, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=8)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=(12, 8), pady=8)
        ttk.Button(parent, text=button_text, command=command).grid(row=row, column=2, sticky="e", pady=8)

    def _choose_registry(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите Excel-реестр",
            filetypes=[("Excel files", "*.xlsx *.xlsm"), ("All files", "*.*")],
        )
        if path:
            self.registry_var.set(path)
            if not self.output_var.get():
                self.output_var.set(str(Path(path).parent / "hr_matcher_result"))

    def _choose_resumes(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку с резюме")
        if path:
            self.resumes_var.set(path)

    def _choose_output(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку результата")
        if path:
            self.output_var.set(path)

    def _run(self) -> None:
        registry = Path(self.registry_var.get())
        resumes = Path(self.resumes_var.get())
        output_value = self.output_var.get().strip()
        output = Path(output_value)
        if not registry.exists():
            messagebox.showerror("Не выбран реестр", "Выберите существующий Excel-файл реестра.")
            return
        if not resumes.exists():
            messagebox.showerror("Не выбрана папка", "Выберите существующую папку с резюме.")
            return
        if not output_value:
            messagebox.showerror("Не выбрана папка результата", "Выберите папку, куда сохранить результат.")
            return

        self.run_button.configure(state="disabled")
        self._set_result_buttons_state("disabled")
        self.progress.start(12)
        self.status_var.set("Идет сопоставление. Большая папка может обрабатываться несколько минут.")
        thread = threading.Thread(target=self._run_worker, args=(registry, resumes, output), daemon=True)
        thread.start()

    def _run_worker(self, registry: Path, resumes: Path, output: Path) -> None:
        try:
            summary = run_match(registry, resumes, output)
        except Exception as exc:
            self.after(0, lambda: self._finish_error(exc))
            return
        self.after(0, lambda: self._finish_success(summary))

    def _finish_success(self, summary) -> None:
        self.progress.stop()
        self.run_button.configure(state="normal")
        self.result_path = summary.output_dir
        self.report_path = summary.report_path
        self.matched_resumes_path = summary.output_dir / "matched_resumes"
        self.review_resumes_path = summary.output_dir / "review_resumes"
        self._set_result_buttons_state("normal")
        self.status_var.set(
            "Готово.\n"
            f"Кандидатов: {summary.total_candidates}\n"
            f"Резюме: {summary.total_resumes}\n"
            f"Найдено: {summary.matched}\n"
            f"На проверку: {summary.review}\n"
            f"Не найдено: {summary.unmatched}\n"
            f"Excel-отчет: {summary.report_path}\n"
            f"Готовые резюме: {self.matched_resumes_path}\n"
            f"Резюме на проверку: {self.review_resumes_path}"
        )

    def _finish_error(self, exc: Exception) -> None:
        self.progress.stop()
        self.run_button.configure(state="normal")
        self.status_var.set(f"Не удалось выполнить сопоставление: {exc}")
        messagebox.showerror("Ошибка", str(exc))

    def _open_result(self) -> None:
        if not self.result_path:
            return
        open_path(self.result_path)

    def _open_report(self) -> None:
        if not self.report_path:
            return
        open_path(self.report_path)

    def _open_matched_resumes(self) -> None:
        if not self.matched_resumes_path:
            return
        open_path(self.matched_resumes_path)

    def _open_review_resumes(self) -> None:
        if not self.review_resumes_path:
            return
        open_path(self.review_resumes_path)

    def _set_result_buttons_state(self, state: str) -> None:
        self.open_report_button.configure(state=state)
        self.open_matched_button.configure(state=state)
        self.open_review_button.configure(state=state)
        self.open_result_button.configure(state=state)


def open_path(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> int:
    window = MatcherWindow()
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
