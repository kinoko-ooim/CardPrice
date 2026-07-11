#!/usr/bin/env python3
"""Local Jihuanshe listing helper.

This server accepts listing payloads from the static card dashboard and drives
the visible Jihuanshe macOS/iOS app through Accessibility. It does not read
login tokens, decrypt app data, or call private signed APIs.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import update_jhs_prices as jhs


HOST = "127.0.0.1"
PORT = 8767
PROJECT_ROOT = Path(__file__).resolve().parents[1]

APP_SERVICES = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
CORE_GRAPHICS_EVENT_TAP = 0
LEFT_MOUSE_DOWN = 1
LEFT_MOUSE_UP = 2
LEFT_MOUSE_DRAGGED = 6
LEFT_BUTTON = 0
K_VK_DELETE = 51


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class AXCGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


APP_SERVICES.CGEventCreateMouseEvent.restype = ctypes.c_void_p
APP_SERVICES.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
APP_SERVICES.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def normalize_number(value: Any, fallback: float = 0) -> float:
    try:
      return float(value)
    except (TypeError, ValueError):
      return fallback


def jhs_window_point(rx: float, ry: float) -> tuple[int, int]:
    x, y, w, h = jhs.jhs_window_rect()
    return int(x + w * rx), int(y + h * ry)


def click_at(x: int, y: int) -> None:
    point = CGPoint(float(x), float(y))
    down = APP_SERVICES.CGEventCreateMouseEvent(None, LEFT_MOUSE_DOWN, point, LEFT_BUTTON)
    up = APP_SERVICES.CGEventCreateMouseEvent(None, LEFT_MOUSE_UP, point, LEFT_BUTTON)
    try:
        APP_SERVICES.CGEventPost(CORE_GRAPHICS_EVENT_TAP, down)
        time.sleep(0.05)
        APP_SERVICES.CGEventPost(CORE_GRAPHICS_EVENT_TAP, up)
    finally:
        jhs.cf_release(down)
        jhs.cf_release(up)
    time.sleep(0.35)


def click_ratio(rx: float, ry: float) -> None:
    click_at(*jhs_window_point(rx, ry))


def ax_position_attribute(element: int) -> tuple[float, float] | None:
    ref = jhs.ax_copy_attribute(element, "AXPosition")
    if not ref:
        return None
    try:
        point = AXCGPoint()
        ok = APP_SERVICES.AXValueGetValue(ctypes.c_void_p(ref), 1, ctypes.byref(point))
        return (point.x, point.y) if ok else None
    finally:
        jhs.cf_release(ref)


def add_product_form_snapshot(
    labels: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]], dict[str, list[tuple[float, float]]]]:
    fields: list[dict[str, Any]] = []
    label_positions = {label: [] for label in labels}
    for node in jhs.iter_jhs_ax_elements(max_nodes=2600, max_seconds=4):
        role = node.get("role")
        text = str(node.get("description") or node.get("value") or "").strip()
        matched_labels = [label for label in labels if label in text]
        if role != "AXTextField" and not matched_labels:
            continue
        size = jhs.ax_size_attribute(node["element"])
        position = ax_position_attribute(node["element"])
        if not size or not position:
            continue
        if role == "AXTextField":
            fields.append({**node, "size": size, "position": position})
        for label in matched_labels:
            x, y = position
            width, height = size
            label_positions[label].append((x + width / 2, y + height / 2))
    fields.sort(key=lambda item: (item["position"][1], item["position"][0]))
    return fields, label_positions


def field_center(field: dict[str, Any]) -> tuple[float, float]:
    x, y = field["position"]
    width, height = field["size"]
    return x + width / 2, y + height / 2


def read_text_field_value(field: dict[str, Any]) -> str:
    try:
        return jhs.ax_text_attribute(field["element"], "AXValue").strip()
    except Exception:
        return ""


def set_text_field_value(field: dict[str, Any], text: str) -> bool:
    element = field["element"]
    for click_field in (False, True):
        try:
            if click_field:
                center_x, center_y = field_center(field)
                click_at(round(center_x), round(center_y))
            else:
                jhs.ax_press_element(element)
                time.sleep(0.15)
            jhs.ax_set_bool_attribute(element, "AXFocused", True)
            jhs.ax_set_string_attribute(element, "AXValue", "")
            time.sleep(0.08)
            jhs.post_key_to_jhs(K_VK_DELETE)
            time.sleep(0.08)
            if text:
                jhs.post_text_to_jhs(text)
            time.sleep(0.2)
            jhs.ax_set_string_attribute(element, "AXValue", text)
            time.sleep(0.2)
            if read_text_field_value(field) == text:
                return True
        except Exception:
            continue
    return False


def find_price_field(attempts: int = 1, pause: float = 0.4) -> dict[str, Any] | None:
    for attempt in range(attempts):
        fields, labels = add_product_form_snapshot(("商品价格",))
        candidates: list[tuple[float, dict[str, Any]]] = []
        fallback: list[dict[str, Any]] = []
        for field in fields:
            width, height = field["size"]
            value = str(field.get("value") or "").strip()
            if value and not re.fullmatch(r"\d+(?:\.\d{0,2})?", value):
                continue
            if not (35 <= width <= 180 and 15 <= height <= 45):
                continue
            fallback.append(field)
            center_x, center_y = field_center(field)
            for label_x, label_y in labels["商品价格"]:
                delta_x = center_x - label_x
                delta_y = abs(center_y - label_y)
                if 5 <= delta_x <= 220 and delta_y <= 36:
                    candidates.append((delta_y * 10 + abs(delta_x - 60), field))
        if candidates:
            return min(candidates, key=lambda item: item[0])[1]
        if len(fallback) == 1:
            return fallback[0]
        if attempt + 1 < attempts:
            time.sleep(pause)
    return None


def find_note_field(attempts: int = 1, pause: float = 0.4) -> dict[str, Any] | None:
    for attempt in range(attempts):
        fields, labels = add_product_form_snapshot(("商品备注",))
        candidates: list[tuple[float, dict[str, Any]]] = []
        fallback: list[dict[str, Any]] = []
        for field in fields:
            width, height = field["size"]
            if not (width >= 260 and 15 <= height <= 60):
                continue
            fallback.append(field)
            center_x, center_y = field_center(field)
            for label_x, label_y in labels["商品备注"]:
                delta_y = center_y - label_y
                if abs(center_x - label_x) <= 300 and 8 <= delta_y <= 80:
                    candidates.append((abs(delta_y - 34) + abs(center_x - label_x) / 20, field))
        if candidates:
            return min(candidates, key=lambda item: item[0])[1]
        if len(fallback) == 1:
            return fallback[0]
        if attempt + 1 < attempts:
            time.sleep(pause)
    return None


def find_label_position(label: str) -> tuple[float, float] | None:
    _, labels = add_product_form_snapshot((label,))
    return labels[label][0] if labels[label] else None


def find_qty_field() -> dict[str, Any] | None:
    fields, labels = add_product_form_snapshot(("库存数量",))
    if labels["库存数量"]:
        candidates = []
        for field in fields:
            width, height = field["size"]
            center_x, center_y = field_center(field)
            value = str(field.get("value") or "").strip()
            if not value.isdigit():
                continue
            for label_x, label_y in labels["库存数量"]:
                delta_x = center_x - label_x
                delta_y = abs(center_y - label_y)
                if 5 <= delta_x <= 150 and 12 <= width <= 90 and 8 <= height <= 36 and delta_y <= 32:
                    candidates.append((delta_y * 10 + abs(delta_x - 60), field))
        if candidates:
            return min(candidates, key=lambda item: item[0])[1]

    compact_candidates = []
    for field in fields:
        width, height = field["size"]
        value = str(field.get("value") or "").strip()
        if value.isdigit() and 12 <= width <= 45 and 8 <= height <= 32:
            compact_candidates.append(field)
    return compact_candidates[0] if len(compact_candidates) == 1 else None


def read_qty_field_value() -> int | None:
    field = find_qty_field()
    if not field:
        return None
    value = str(field.get("value") or "").strip()
    return int(value) if value.isdigit() else None


def click_qty_plus(field: dict[str, Any]) -> None:
    x, y = field["position"]
    width, height = field["size"]
    click_at(int(x + width + 22), int(y + height / 2))


def fill_qty_field(qty: int) -> None:
    field = find_qty_field()
    if field and set_text_field_value(field, str(qty)):
        time.sleep(0.35)
        if read_qty_field_value() == qty:
            return

    field = find_qty_field()
    current_qty = read_qty_field_value()
    if field and current_qty is not None and current_qty < qty:
        for _ in range(qty - current_qty):
            click_qty_plus(field)
            time.sleep(0.2)
        if read_qty_field_value() == qty:
            return

    raise RuntimeError(f"库存数量没有调整到 {qty}，已停止，避免数量错误上架")


def numeric_text_matches(value: str, expected: str) -> bool:
    try:
        return abs(float(value.strip()) - float(expected)) < 0.000001
    except (TypeError, ValueError):
        return False


def fill_price_field(price: float) -> None:
    price_text = f"{price:.2f}".rstrip("0").rstrip(".")
    for attempt in range(3):
        field = find_price_field(attempts=2)
        if field and set_text_field_value(field, price_text):
            if numeric_text_matches(read_text_field_value(field), price_text):
                return
        refreshed_field = find_price_field()
        if refreshed_field and numeric_text_matches(read_text_field_value(refreshed_field), price_text):
            return
        if attempt < 2:
            time.sleep(0.4)
    raise RuntimeError("没有定位并写入商品价格输入框，已停止；不会点击已有上架商品或用空价格继续")


def fill_note_field(note: str) -> bool:
    field = find_note_field(attempts=2)
    if field and set_text_field_value(field, note):
        return True
    raise RuntimeError("没有定位并写入商品备注输入框，已停止；不会使用固定坐标继续点击")


def paste_text(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=False)
    jhs.run_osascript('tell application "System Events" to keystroke "v" using command down', timeout=5)
    time.sleep(0.25)


def visible_text(timeout: float = 3) -> str:
    try:
        return jhs.read_jhs_accessibility_text(timeout=timeout)
    except Exception:
        return ""


def wait_until_text(pattern: str, timeout: float = 10) -> str:
    deadline = time.time() + timeout
    last = ""
    regex = re.compile(pattern)
    while time.time() < deadline:
        last = visible_text(timeout=2)
        if regex.search(last):
            return last
        time.sleep(0.5)
    raise RuntimeError(f"等待界面超时：{pattern}")


def existing_same_product_count(text: str) -> int:
    compact = re.sub(r"\s+", "", text or "")
    match = re.search(r"已上架同类商品(\d+)", compact)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def describe_existing_same_product() -> str:
    text = visible_text(timeout=2)
    count = existing_same_product_count(text)
    if count > 0:
        return f"检测到已有同类上架商品 {count} 条，将继续新增一条上架记录"
    return "未发现已上架同类商品"


def press_button_text(*labels: str, attempts: int = 3, pause: float = 0.6) -> bool:
    label_set = {label for label in labels if label}

    def match(node: dict[str, Any]) -> bool:
        text = node.get("description") or node.get("value") or node.get("text") or ""
        return node.get("role") == "AXButton" and any(label in text for label in label_set)

    return jhs.ax_press_first(match, attempts=attempts, pause=pause)


def click_form_option(row_label: str, *option_labels: str, attempts: int = 3) -> None:
    wanted = {label for label in option_labels if label}
    if not wanted:
        raise RuntimeError(f"{row_label}没有可选目标")

    for attempt in range(attempts):
        row_positions: list[tuple[float, float]] = []
        options: list[tuple[dict[str, Any], tuple[float, float]]] = []
        for node in jhs.iter_jhs_ax_elements(max_nodes=2600, max_seconds=4):
            text = str(node.get("description") or node.get("value") or "").strip()
            if text != row_label and text not in wanted:
                continue
            position = ax_position_attribute(node["element"])
            size = jhs.ax_size_attribute(node["element"])
            if not position or not size:
                continue
            x, y = position
            width, height = size
            center = (x + width / 2, y + height / 2)
            if text == row_label:
                row_positions.append(center)
            elif node.get("role") in {"AXButton", "AXStaticText"}:
                options.append((node, center))

        candidates: list[tuple[float, dict[str, Any], tuple[float, float]]] = []
        for node, center in options:
            center_x, center_y = center
            for label_x, label_y in row_positions:
                delta_x = center_x - label_x
                delta_y = abs(center_y - label_y)
                if 5 <= delta_x <= 260 and delta_y <= 28:
                    candidates.append((delta_y * 10 + delta_x, node, center))
        if candidates:
            _, node, center = min(candidates, key=lambda item: item[0])
            if node.get("role") == "AXButton" and jhs.ax_press_element(node["element"]):
                time.sleep(0.5)
                return
            click_at(round(center[0]), round(center[1]))
            time.sleep(0.5)
            return
        if attempt + 1 < attempts:
            time.sleep(0.5)

    choices = " / ".join(option_labels)
    raise RuntimeError(f"没有在“{row_label}”一行找到“{choices}”，已停止，避免误点已有上架商品")


def front_window_summary() -> str:
    try:
        return jhs.run_osascript(
            '''
tell application "System Events"
  set frontProc to first process whose frontmost is true
  set output to name of frontProc
  repeat with frontWindow in windows of frontProc
    set output to output & linefeed & (name of frontWindow as text) & "|" & (role of frontWindow as text) & "|" & (subrole of frontWindow as text)
  end repeat
  return output
end tell
''',
            timeout=5,
        )
    except Exception:
        return ""


def is_file_picker_visible() -> bool:
    summary = front_window_summary().lower()
    return any(
        marker in summary
        for marker in (
            "axdialog",
            "open",
            "choose",
            "打开",
            "选择",
            "前往文件夹",
            "go to the folder",
        )
    )


def wait_for_file_picker(timeout: float = 2.5) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_file_picker_visible():
            return True
        time.sleep(0.2)
    return False


def resolve_image_path(image_url: str) -> Path | None:
    if not image_url:
        return None
    if image_url.startswith("data:"):
        try:
            header, encoded = image_url.split(",", 1)
            import base64

            suffix = ".png"
            if "jpeg" in header or "jpg" in header:
                suffix = ".jpg"
            elif "webp" in header:
                suffix = ".webp"
            path = Path(tempfile.gettempdir()) / f"kajia-listing-{int(time.time() * 1000)}{suffix}"
            path.write_bytes(base64.b64decode(encoded))
            return path
        except Exception:
            return None
    if image_url.startswith("cardimg/"):
        path = PROJECT_ROOT / image_url
        return path if path.exists() else None
    if image_url.startswith(("http://", "https://")):
        try:
            suffix = Path(urllib.parse.urlparse(image_url).path).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}:
                suffix = ".jpg"
            path = Path(tempfile.gettempdir()) / f"kajia-listing-{int(time.time() * 1000)}{suffix}"
            req = urllib.request.Request(image_url, headers={"User-Agent": "kajia-listing-helper/0.1"})
            with urllib.request.urlopen(req, timeout=20) as response:
                path.write_bytes(response.read())
            return path if path.exists() and path.stat().st_size > 0 else None
        except Exception:
            return None
    path = Path(image_url)
    return path if path.exists() else None


def upload_tile_points() -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    label_center = find_label_position("上传商品图")
    if label_center:
        x, y = label_center
        points.extend([(int(x + 52), int(y + 96)), (int(x + 52), int(y + 72))])
    points.extend(jhs_window_point(rx, ry) for rx, ry in ((0.085, 0.855), (0.12, 0.84), (0.09, 0.80)))
    deduped: list[tuple[int, int]] = []
    for point in points:
        if point not in deduped:
            deduped.append(point)
    return deduped


def choose_image_file(image_path: Path) -> bool:
    if not wait_for_file_picker(timeout=1.5):
        return False
    try:
        jhs.run_osascript('tell application "System Events" to keystroke "g" using {command down, shift down}', timeout=5)
        time.sleep(0.3)
        if not wait_for_file_picker(timeout=1.5):
            return False
        paste_text(str(image_path))
        time.sleep(0.2)
        jhs.post_key_to_jhs(jhs.K_VK_RETURN)
        time.sleep(0.8)
        jhs.post_key_to_jhs(jhs.K_VK_RETURN)
        time.sleep(2.0)
        return not is_file_picker_visible()
    except Exception:
        return False


def upload_image_if_possible(image_url: str, required: bool = False) -> str:
    image_path = resolve_image_path(image_url)
    if not image_path:
        if required:
            raise RuntimeError("定价超过 500 元需要上传商品图，但当前商品没有可用图片；请先在网页商品里添加图片")
        return "未找到可上传的图片，已跳过商品图"

    for point in upload_tile_points():
        click_at(*point)
        time.sleep(0.9)
        press_button_text("从文件选择", "选择文件", "从相册选择", "照片图库", "相册", attempts=1, pause=0.5)
        time.sleep(0.5)
        if choose_image_file(image_path):
            return f"已上传商品图：{image_path.name}"

    raise RuntimeError("商品图没有上传成功，已停止；请确认集换社停在“上传商品图”的加号区域，或先给商品添加本地图片")


def select_listing_category(is_psa10: bool) -> None:
    wait_until_text(r"添加商品|类别及品相|商品价格", timeout=10)
    if is_psa10:
        click_form_option("商品类别", "评级卡")
        wait_until_text(r"评级公司", timeout=5)
        click_form_option("评级公司", "PSA", "PSA10")
    else:
        click_form_option("商品类别", "非评级卡")
        wait_until_text(r"卡牌品相", timeout=5)
        click_form_option("卡牌品相", "流通品相")


def fill_listing_form(payload: dict[str, Any]) -> dict[str, Any]:
    card_code = str(payload.get("cardCode") or payload.get("searchCode") or "").strip()
    game_label = str(payload.get("gameLabel") or payload.get("language") or "").strip()
    is_psa10 = bool(payload.get("isPsa10"))
    price = normalize_number(payload.get("price"))
    qty = max(1, int(normalize_number(payload.get("qty"), 1)))
    note = str(payload.get("note") or "").strip()
    image_url = str(payload.get("imageUrl") or "").strip()
    confirm_add = bool(payload.get("confirmAdd"))

    if not card_code:
        raise RuntimeError("缺少卡片编号，无法搜索上架")
    if price <= 0:
        raise RuntimeError("上架价格必须大于 0")

    steps: list[str] = []
    jhs.JHS_LOW_INTERRUPTION = False
    jhs.ensure_jhs_app_open()
    steps.append("已打开集换社")
    jhs.open_card_detail_from_ui(card_code, game_label=game_label)
    steps.append("已按编号和语言搜索并进入卡片详情")

    if not press_button_text("出售", attempts=3):
        click_ratio(0.44, 0.94)
    steps.append("已点击出售")
    time.sleep(1.2)

    select_listing_category(is_psa10)
    steps.append("已选择评级/品相")

    steps.append(describe_existing_same_product())

    fill_price_field(price)
    steps.append(f"已填写价格 {price:.2f}")

    if qty > 1:
        fill_qty_field(qty)
        steps.append(f"已调整库存数量到 {qty}")

    if note:
        fill_note_field(note[:120])
        steps.append("已填写备注")

    if price > 500:
        image_note = upload_image_if_possible(image_url, required=True)
    else:
        image_note = "价格不超过 500 元，已跳过上传商品图"
    steps.append(image_note)

    if confirm_add:
        if not press_button_text("添加", attempts=2):
            click_ratio(0.50, 0.94)
        steps.append("已点击添加，完成上架")
        status = "listed"
    else:
        steps.append("已停在添加前，请检查后手动点击添加；如需全自动，请勾选自动点击添加")
        status = "ready_for_confirm"

    return {"ok": True, "status": status, "steps": steps}


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        json_response(self, 200, {"ok": True})

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            json_response(self, 200, {
                "ok": True,
                "service": "jhs-listing-helper",
                "pid": os.getpid(),
                "executable": sys.executable,
                "accessibilityTrusted": jhs.is_accessibility_trusted(),
            })
            return
        json_response(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if not self.path.startswith("/listings"):
            json_response(self, 404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            result = fill_listing_form(payload)
            json_response(self, 200, result)
        except Exception as exc:
            json_response(self, 500, {"ok": False, "error": str(exc), "visibleText": visible_text(timeout=1)[-2000:]})

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[jhs-listing-helper] " + (fmt % args) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Jihuanshe listing helper server.")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Jihuanshe listing helper listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
