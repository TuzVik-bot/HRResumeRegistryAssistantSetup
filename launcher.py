import asyncio
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from app import database
from app.config import APP_NAME, PROJECT_FILES_DIR, ensure_directories
from app.diagnostics import log_event
from app.main import app as _app


HOST = "127.0.0.1"
START_PORT = 8000
MAX_PORT = 8010


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
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        config = uvicorn.Config(_app, host=self.host, port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)
        try:
            self._loop.run_until_complete(self._server.serve())
        except Exception as exc:
            self.error = exc
            log_event("error", "app", "launcher_server_error", "Ошибка запуска локального сервера", {"detail": str(exc)})
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            self._loop.run_until_complete(asyncio.sleep(0))
            self._loop.close()

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
        self.root.geometry("520x260")
        self.root.minsize(460, 240)
        self.root.configure(bg="#f3f6f8")
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.status_var = tk.StringVar(value="Подготовка запуска...")
        self.url_var = tk.StringVar(value=url)
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

        outer = ttk.Frame(self.root, style="Launcher.TFrame", padding=18)
        outer.pack(fill="both", expand=True)

        card = ttk.Frame(outer, style="Card.TFrame", padding=18)
        card.pack(fill="both", expand=True)

        ttk.Label(card, text="HR Resume Registry Assistant", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            text="Приложение работает локально. Браузер открывается автоматически, а это окно позволяет быстро открыть адрес, папку данных или остановить сервис.",
            style="Body.TLabel",
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(10, 12))

        ttk.Label(card, textvariable=self.status_var, style="Status.TLabel").pack(anchor="w")
        ttk.Label(card, textvariable=self.url_var, style="Body.TLabel").pack(anchor="w", pady=(6, 16))

        button_row = ttk.Frame(card, style="Card.TFrame")
        button_row.pack(fill="x")

        ttk.Button(button_row, text="Открыть", command=self.open_browser).pack(side="left")
        ttk.Button(button_row, text="Папка данных", command=self.open_project_files).pack(side="left", padx=8)
        ttk.Button(button_row, text="Остановить", command=self.shutdown).pack(side="right")

    def start(self) -> None:
        self.status_var.set("Запускаем локальный сервис...")
        self.server_thread.start()
        self.root.after(500, self._poll_server_state)
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

    def shutdown(self) -> None:
        self.status_var.set("Останавливаем локальный сервис...")
        self.server_thread.stop()
        log_event("info", "app", "launcher_shutdown", "Окно launcher закрыто пользователем", {"url": self.url})
        self.root.after(250, self.root.destroy)

    def _poll_server_state(self) -> None:
        if self.server_thread.error:
            self.status_var.set(f"Ошибка запуска: {self.server_thread.error}")
            return
        if not self.server_thread.is_alive():
            self.status_var.set("Сервис остановлен. Закройте окно и запустите программу заново.")
            return
        if _server_accepts_http(self.url):
            if not self.browser_opened:
                self.open_browser()
            else:
                self.status_var.set("Сервис работает. Можно открыть новый реестр, загрузить резюме или посмотреть диагностику.")
            self.root.after(1500, self._poll_server_state)
            return
        self.status_var.set("Сервис запускается. Если ожидание длится больше минуты, откройте папку данных и проверьте диагностику.")
        self.root.after(1000, self._poll_server_state)


def _open_path(path: Path) -> None:
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


def main() -> None:
    ensure_directories()
    database.init_db()
    port = _find_available_port()
    url = f"http://{HOST}:{port}"
    window = LauncherWindow(url, port)
    window.start()


if __name__ == "__main__":
    main()
