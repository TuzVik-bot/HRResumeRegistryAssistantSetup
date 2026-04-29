import socket
import threading
import time
import webbrowser

import uvicorn

from app.config import APP_NAME
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


def _open_browser(url: str) -> None:
    time.sleep(1.2)
    webbrowser.open(url)


def main() -> None:
    port = _find_available_port()
    url = f"http://{HOST}:{port}"
    print(f"{APP_NAME} запущен: {url}")
    print("Не закрывайте это окно, пока работает приложение.")
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    uvicorn.run(_app, host=HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
