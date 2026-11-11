import argparse
import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn


THIS_DIR = Path(__file__).resolve().parent
SRC_DIR = THIS_DIR.parent
import sys

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app.web import create_app


DEFAULT_PORT = 3000
MIN_PORT = 3000
MAX_PORT = 3010


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _select_port(host: str, preferred_port: int) -> int:
    if preferred_port < MIN_PORT or preferred_port > MAX_PORT:
        raise ValueError(
            f"Port must be within {MIN_PORT}-{MAX_PORT}. Received: {preferred_port}"
        )

    for port in range(preferred_port, MAX_PORT + 1):
        if _port_available(host, port):
            return port
    for port in range(MIN_PORT, preferred_port):
        if _port_available(host, port):
            return port
    raise RuntimeError(
        f"No free port found in allowed range {MIN_PORT}-{MAX_PORT}. "
        "Stop another process in that range and retry."
    )


def _open_browser(host: str, port: int, delay_s: float = 1.0) -> None:
    time.sleep(delay_s)
    webbrowser.open(f"http://{host}:{port}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LGR Sim Workbench local app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    app = create_app()
    selected_port = _select_port(args.host, args.port)

    if not args.no_browser:
        thread = threading.Thread(target=_open_browser, args=(args.host, selected_port), daemon=True)
        thread.start()

    if selected_port != args.port:
        print(
            f"Requested port {args.port} is busy. Using first available port in range: {selected_port}"
        )

    uvicorn.run(app, host=args.host, port=selected_port, log_level="info")


if __name__ == "__main__":
    main()
