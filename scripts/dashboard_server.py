#!/usr/bin/env python3
"""Local dashboard server for the card-price HTML app.

It serves the static dashboard and exposes a localhost-only endpoint that can
start the Jihuanshe listing helper when the browser needs it.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


HOST = "127.0.0.1"
PORT = 8000
HELPER_URL = "http://127.0.0.1:8767/health"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
HELPER_SCRIPT = PROJECT_ROOT / "scripts" / "jhs_listing_helper.py"
HELPER_PROCESS: subprocess.Popen[str] | None = None


def helper_is_ready(timeout: float = 0.6) -> bool:
    try:
        with urllib.request.urlopen(HELPER_URL, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
            return response.status == 200 and data.get("ok") is True
    except Exception:
        return False


def start_helper() -> dict[str, Any]:
    global HELPER_PROCESS
    if helper_is_ready():
        return {"ok": True, "status": "already_running"}
    if HELPER_PROCESS and HELPER_PROCESS.poll() is None:
        status = "starting"
    else:
        log_path = PROJECT_ROOT / "data" / "jhs_listing_helper.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command_path = PROJECT_ROOT / "data" / "start_jhs_listing_helper.command"
        command_path.write_text(
            "#!/bin/zsh\n"
            f"cd {shlex.quote(str(PROJECT_ROOT))} || exit 1\n"
            f"exec {shlex.quote(sys.executable)} {shlex.quote(str(HELPER_SCRIPT))} "
            f">> {shlex.quote(str(log_path))} 2>&1\n",
            encoding="utf-8",
        )
        os.chmod(command_path, 0o755)
        subprocess.run(["open", "-a", "Terminal", str(command_path)], check=False)
        HELPER_PROCESS = None
        status = "started"

    deadline = time.time() + 5
    while time.time() < deadline:
        if helper_is_ready(timeout=0.8):
            return {"ok": True, "status": status}
        time.sleep(0.3)
    return {"ok": False, "status": status, "error": "本地上架服务启动超时，请查看 data/jhs_listing_helper.log"}


def open_accessibility_settings() -> dict[str, Any]:
    subprocess.run(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"],
        check=False,
    )
    return {"ok": True, "status": "opened"}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(PROJECT_ROOT), **kwargs)

    def end_headers(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in {"/", "/index.html"}:
          self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
          self.send_header("Pragma", "no-cache")
          self.send_header("Expires", "0")
        super().end_headers()

    def json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.json_response(200, {"ok": True})

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self.json_response(200, {"ok": True, "service": "card-dashboard-server"})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/start-jhs-listing-helper"):
            result = start_helper()
            self.json_response(200 if result.get("ok") else 500, result)
            return
        if self.path.startswith("/open-accessibility-settings"):
            result = open_accessibility_settings()
            self.json_response(200, result)
            return
        self.json_response(404, {"ok": False, "error": "not found"})


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Card dashboard server listening on http://{HOST}:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
