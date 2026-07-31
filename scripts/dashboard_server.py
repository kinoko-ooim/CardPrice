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
import urllib.parse
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
MAX_AI_PROXY_BODY_BYTES = 24 * 1024 * 1024
AI_PROXY_TIMEOUT_SECONDS = 180
ALLOWED_AI_PROXY_ORIGINS = {
    "null",
    f"http://{HOST}:{PORT}",
    f"http://localhost:{PORT}",
}


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


def proxy_ai_request(payload: dict[str, Any]) -> tuple[int, bytes, str]:
    api_url = str(payload.get("apiUrl") or "").strip()
    parsed_url = urllib.parse.urlparse(api_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("AI API URL 必须是有效的 http/https 地址")

    request_headers = payload.get("headers")
    if not isinstance(request_headers, dict):
        request_headers = {}
    blocked_headers = {"connection", "content-length", "host", "origin", "referer"}
    headers = {
        str(key): str(value)
        for key, value in request_headers.items()
        if str(key).lower() not in blocked_headers
    }
    headers["Content-Type"] = "application/json"

    request_body = payload.get("body")
    if not isinstance(request_body, dict):
        raise ValueError("AI 请求内容格式不正确")
    encoded_body = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    upstream_request = urllib.request.Request(
        api_url,
        data=encoded_body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(upstream_request, timeout=AI_PROXY_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "application/json; charset=utf-8")
            return response.status, response.read(), content_type
    except urllib.error.HTTPError as error:
        content_type = error.headers.get("Content-Type", "application/json; charset=utf-8")
        return error.code, error.read(), content_type


def ai_proxy_origin_allowed(origin: str | None) -> bool:
    return not origin or origin in ALLOWED_AI_PROXY_ORIGINS


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
        if self.path.startswith("/api/ai-proxy") and not ai_proxy_origin_allowed(self.headers.get("Origin")):
            self.send_response(403)
            self.end_headers()
            return
        self.json_response(200, {"ok": True})

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self.json_response(200, {"ok": True, "service": "card-dashboard-server"})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/ai-proxy"):
            if not ai_proxy_origin_allowed(self.headers.get("Origin")):
                self.send_response(403)
                self.end_headers()
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length <= 0 or content_length > MAX_AI_PROXY_BODY_BYTES:
                    raise ValueError("AI 请求大小不合法")
                payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("AI 请求格式不正确")
                status, body, content_type = proxy_ai_request(payload)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
            except (ValueError, json.JSONDecodeError) as error:
                self.json_response(400, {"ok": False, "error": str(error)})
            except Exception as error:
                self.json_response(502, {"ok": False, "error": f"AI API 代理请求失败：{error}"})
            return
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
