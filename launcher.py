import asyncio
from datetime import datetime
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from tkinter import ttk
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from app import database
from app.config import APP_NAME, BASE_DIR, PROJECT_FILES_DIR, ensure_directories
from app.diagnostics import log_event
from app.resume_parser import get_soffice_status


HOST = "127.0.0.1"
START_PORT = 8000
MAX_PORT = 8010
LOG_DIR = PROJECT_FILES_DIR / "logs"
LAUNCHER_LOG_PATH = LOG_DIR / "launcher.log"
LOG_TAIL_LINES = 80


def _find_available_port() -> int:
    for port in range(START_PORT, MAX_PORT + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((HOST, port)) != 0:
                return port
    raise RuntimeError(f"Не найден свободный порт в диапазоне {START_PORT}-{MAX_PORT}")


class ServerThread(threading.Thread):
    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.error: Exception | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: uvicorn.Server | None = None

    def run(self) -> None:
        _write_launcher_log("Server thread starting")
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            from app.main import app as fastapi_app

            config = uvicorn.Config(
                fastapi_app,
                host=self.host,
                port=self.port,
                log_level="info",
                access_log=False,
                log_config=None,
            )
            self._server = uvicorn.Server(config)
            self._loop.run_until_complete(self._server.serve())
            if self._server and not self._server.should_exit:
                self.error = RuntimeError("Локальный сервер остановился во время запуска")
                _write_launcher_log("Server stopped without a shutdown request")
        except Exception as exc:
            self.error = exc
            _write_launcher_log(f"Server error: {exc}\n{traceback.format_exc()}")
            log_event("error", "app", "launcher_server_error", "Ошибка запуска локального сервера", {"detail": str(exc)})
        finally:
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                self._loop.run_until_complete(asyncio.sleep(0))
            finally:
                self._loop.close()
                _write_launcher_log("Server thread stopped")

    def stop(self) -> None:
        if self._server and self._loop:
            self._loop.call_soon_threadsafe(self._request_stop)

    def _request_stop(self) -> None:
        if self._server:
            self._server.should_exit = True


class LauncherWindow:
    def __init__(self, url: str, port: int):
        self.url = url
        self.port = port
        self.server_thread = ServerThread(HOST, port)
        self.browser_opened = False

        self.root = tk.Tk()
        self.root.title("HR Resume Registry Assistant")
        self.root.geometry("760x560")
        self.root.minsize(680, 500)
        self.root.configure(bg="#f3f6f8")
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.status_var = tk.StringVar(value="Подготовка запуска...")
        self.url_var = tk.StringVar(value=url)
        self.log_var = tk.StringVar(value=f"Логи запуска: {LAUNCHER_LOG_PATH}")
        self._build_ui()

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Launcher.TFrame", background="#f3f6f8")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Title.TLabel", background="#ffffff", foreground="#15202b", font=("Segoe UI", 16, "bold"))
        style.configure("Body.TLabel", background="#ffffff", foreground="#526174", font=("Segoe UI", 10))
        style.configure("Status.TLabel", background="#ffffff", foreground="#0c6f63", font=("Segoe UI", 11, "bold"))
        style.configure("Error.TLabel", background="#ffffff", foreground="#b42318", font=("Segoe UI", 11, "bold"))

        outer = ttk.Frame(self.root, style="Launcher.TFrame", padding=14)
        outer.pack(fill="both", expand=True)

        card = ttk.Frame(outer, style="Card.TFrame", padding=20)
        card.pack(fill="both", expand=True)

        ttk.Label(card, text="HR Resume Registry Assistant", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            text="Приложение работает локально. Браузер открывается автоматически, а это окно позволяет быстро открыть адрес, папку данных или остановить сервис.",
            style="Body.TLabel",
            wraplength=680,
            justify="left",
        ).pack(anchor="w", pady=(10, 12))

        self.status_label = ttk.Label(card, textvariable=self.status_var, style="Status.TLabel", wraplength=680)
        self.status_label.pack(anchor="w")
        ttk.Label(card, textvariable=self.url_var, style="Body.TLabel").pack(anchor="w", pady=(6, 16))

        button_row = tk.Frame(card, bg="#ffffff")
        button_row.pack(fill="x", pady=(0, 14))

        _make_button(button_row, "Открыть сайт", self.open_browser).pack(side="left")
        _make_button(button_row, "Папка данных", self.open_project_files).pack(side="left", padx=8)
        _make_button(button_row, "Открыть логи", self.open_logs).pack(side="left")
        _make_button(button_row, "Остановить", self.shutdown, variant="danger").pack(side="right")

        ttk.Label(card, textvariable=self.log_var, style="Body.TLabel", wraplength=680).pack(anchor="w", pady=(0, 8))
        self.log_text = tk.Text(
            card,
            height=14,
            wrap="word",
            bg="#0f1720",
            fg="#e5edf5",
            insertbackground="#e5edf5",
            relief="flat",
            padx=12,
            pady=10,
            font=("Consolas", 9),
        )
        self.log_text.pack(fill="both", expand=True)
        self._refresh_log_text()

    def start(self) -> None:
        self.status_var.set("Запускаем локальный сервис...")
        _write_launcher_log(f"Launcher started. URL: {self.url}")
        self.server_thread.start()
        self.root.after(500, self._poll_server_state)
        self.root.after(1000, self._refresh_log_text)
        log_event("info", "app", "launcher_started", "Запущено окно Windows-лаунчера", {"url": self.url, "port": self.port})
        self.root.mainloop()

    def open_browser(self) -> None:
        if not _server_accepts_http(self.url):
            self.status_var.set("Сервис еще запускается. Повторите открытие через пару секунд.")
            self.root.after(1000, self._poll_server_state)
            return
        webbrowser.open(self.url)
        if not self.browser_opened:
            self.browser_opened = True
            self.status_var.set("Сервис запущен. Браузер можно закрывать, окно программы оставьте открытым.")

    def open_project_files(self) -> None:
        ensure_directories()
        _open_path(PROJECT_FILES_DIR)

    def open_logs(self) -> None:
        _open_path(LAUNCHER_LOG_PATH)

    def shutdown(self) -> None:
        self.status_var.set("Останавливаем локальный сервис...")
        _write_launcher_log("Shutdown requested from launcher window")
        self.server_thread.stop()
        log_event("info", "app", "launcher_shutdown", "Окно launcher закрыто пользователем", {"url": self.url})
        self.root.after(600, self.root.destroy)

    def _poll_server_state(self) -> None:
        if self.server_thread.error:
            self.status_label.configure(style="Error.TLabel")
            self.status_var.set(f"Ошибка запуска: {self.server_thread.error}. Подробности видны ниже и в launcher.log.")
            self._refresh_log_text()
            return
        if not self.server_thread.is_alive():
            self.status_label.configure(style="Error.TLabel")
            self.status_var.set("Сервис остановлен. Закройте окно и запустите программу заново.")
            self._refresh_log_text()
            return
        if _server_accepts_http(self.url):
            self.status_label.configure(style="Status.TLabel")
            if not self.browser_opened:
                self.open_browser()
            else:
                self.status_var.set("Сервис работает. Можно открыть новый реестр, загрузить резюме или посмотреть диагностику.")
            self.root.after(1500, self._poll_server_state)
            return
        self.status_var.set("Сервис запускается. Если ожидание длится больше минуты, откройте папку данных и проверьте диагностику.")
        self.root.after(1000, self._poll_server_state)

    def _refresh_log_text(self) -> None:
        try:
            lines = LAUNCHER_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            content = "\n".join(lines[-LOG_TAIL_LINES:])
        except OSError:
            content = "Лог запуска пока пуст."
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", content)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        if self.root.winfo_exists():
            self.root.after(2000, self._refresh_log_text)


def _open_path(path: Path) -> None:
    if path == LAUNCHER_LOG_PATH and not path.exists():
        _write_launcher_log("Log file created by Open logs action")
    if os.name == "nt":
        os.startfile(str(path))
        return
    command = ["open", str(path)] if sys.platform == "darwin" else ["xdg-open", str(path)]
    subprocess.Popen(command)


def _server_accepts_http(url: str) -> bool:
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=0.6) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def _setup_launcher_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LAUNCHER_LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    _write_launcher_log("Launcher logging initialized")


def _log_startup_environment() -> None:
    write_ok, write_detail = _check_project_files_write_access()
    soffice = get_soffice_status()
    lines = [
        f"Python version: {sys.version}",
        f"Python executable: {sys.executable}",
        f"Frozen: {bool(getattr(sys, 'frozen', False))}",
        f"MEIPASS: {getattr(sys, '_MEIPASS', '')}",
        f"Base dir: {BASE_DIR}",
        f"Project files dir: {PROJECT_FILES_DIR}",
        f"Working dir: {Path.cwd()}",
        f"LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', '')}",
        f"Project files write access: {'ok' if write_ok else 'failed'} ({write_detail})",
        f"LibreOffice/soffice: {'found at ' + soffice['path'] if soffice['available'] else 'not found'}",
    ]
    for line in lines:
        _write_launcher_log(line)


def _check_project_files_write_access() -> tuple[bool, str]:
    try:
        PROJECT_FILES_DIR.mkdir(parents=True, exist_ok=True)
        test_path = PROJECT_FILES_DIR / ".launcher_write_test"
        test_path.write_text("ok", encoding="utf-8")
        if test_path.read_text(encoding="utf-8") != "ok":
            return False, "write test content mismatch"
        test_path.unlink(missing_ok=True)
        return True, "ok"
    except OSError as exc:
        return False, str(exc)


def _write_launcher_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}\n"
    try:
        with LAUNCHER_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(line)
    except OSError:
        pass
    logging.info(message)


def _make_button(parent, text: str, command, variant: str = "default") -> tk.Button:
    bg = "#0c6f63" if variant == "default" else "#b42318"
    active_bg = "#084c44" if variant == "default" else "#8f1f17"
    return tk.Button(
        parent,
        text=text,
        command=command,
        width=14,
        height=2,
        bg=bg,
        fg="#ffffff",
        activebackground=active_bg,
        activeforeground="#ffffff",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
        cursor="hand2",
    )


def main() -> None:
    ensure_directories()
    _setup_launcher_logging()
    _log_startup_environment()
    database.init_db()
    port = _find_available_port()
    url = f"http://{HOST}:{port}"
    window = LauncherWindow(url, port)
    window.start()


if __name__ == "__main__":
    main()
