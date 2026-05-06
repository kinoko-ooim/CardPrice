#!/usr/bin/env python3
"""Update Jihuanshe reference prices for unsold card inventory.

The updater stays inside the Jihuanshe safety boundary:
- It reads only the app's local CFURL cache, if present.
- It uses only plain JSON/text that the app has cached.
- It does not decrypt raw_data, copy auth headers, or call private signed APIs.

If a card's latest cached price payload is encrypted or absent, the existing
price values are preserved and a short note is stored on that item.
"""

from __future__ import annotations

import argparse
import ctypes
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_DATA_PATH = PROJECT_ROOT / "data" / "card_data.json"
DEFAULT_TABLE = "card_app_state"
DEFAULT_ROW_ID = "main"
DEFAULT_SUPABASE_URL = "https://hnnzyrslsmpankpkhjho.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = "sb_publishable_-rtge5LdKWSnkwKUFWc-aQ_gu3Q8vj0"
BUNDLED_NODE_BIN = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
BUNDLED_NODE_MODULES = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules"
JHS_APP_NAME = "集换社"


class AXCGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


APP_SERVICES = ctypes.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
CORE_FOUNDATION = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
APP_SERVICES.AXUIElementCreateApplication.restype = ctypes.c_void_p
APP_SERVICES.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
APP_SERVICES.AXUIElementCopyAttributeValue.restype = ctypes.c_int
APP_SERVICES.AXUIElementCopyAttributeValue.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
]
APP_SERVICES.AXUIElementSetAttributeValue.restype = ctypes.c_int
APP_SERVICES.AXUIElementSetAttributeValue.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
APP_SERVICES.AXUIElementPerformAction.restype = ctypes.c_int
APP_SERVICES.AXUIElementPerformAction.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
APP_SERVICES.AXValueGetValue.restype = ctypes.c_bool
APP_SERVICES.AXValueGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
APP_SERVICES.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
APP_SERVICES.CGEventCreateKeyboardEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint16, ctypes.c_bool]
APP_SERVICES.CGEventKeyboardSetUnicodeString.argtypes = [
    ctypes.c_void_p,
    ctypes.c_long,
    ctypes.POINTER(ctypes.c_uint16),
]
APP_SERVICES.CGEventPostToPid.argtypes = [ctypes.c_int, ctypes.c_void_p]
CORE_FOUNDATION.CFStringCreateWithCString.restype = ctypes.c_void_p
CORE_FOUNDATION.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
CORE_FOUNDATION.CFStringGetCString.restype = ctypes.c_bool
CORE_FOUNDATION.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_int]
CORE_FOUNDATION.CFStringGetTypeID.restype = ctypes.c_long
CORE_FOUNDATION.CFArrayGetTypeID.restype = ctypes.c_long
CORE_FOUNDATION.CFGetTypeID.restype = ctypes.c_long
CORE_FOUNDATION.CFGetTypeID.argtypes = [ctypes.c_void_p]
CORE_FOUNDATION.CFArrayGetCount.restype = ctypes.c_long
CORE_FOUNDATION.CFArrayGetCount.argtypes = [ctypes.c_void_p]
CORE_FOUNDATION.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
CORE_FOUNDATION.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
CORE_FOUNDATION.CFRetain.restype = ctypes.c_void_p
CORE_FOUNDATION.CFRetain.argtypes = [ctypes.c_void_p]
CORE_FOUNDATION.CFRelease.argtypes = [ctypes.c_void_p]
K_CF_STRING_ENCODING_UTF8 = 0x08000100
K_AX_VALUE_CG_SIZE_TYPE = 2
K_VK_ESCAPE = 53
K_VK_RETURN = 36
K_VK_NUMPAD_ENTER = 76
K_VK_DELETE = 51

RAW_LABELS = ("流通品相", "流通品", "集换价", "裸卡")
PSA10_LABELS = ("PSA10", "PSA 10", "PSA-10")
PRICE_FIELD_HINTS = (
    "price",
    "market_price",
    "marketPrice",
    "avg_price",
    "avgPrice",
    "jihuanshe_price",
    "jihuanshePrice",
    "reference_price",
    "referencePrice",
)


@dataclass
class PriceResult:
    raw_price: float | None = None
    psa10_price: float | None = None
    source: str = ""
    note: str = ""


def round2(value: float) -> float:
    return round(value + 1e-9, 2)


def number_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return round2(float(value))
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    return round2(float(match.group(0)))


def find_cache_dbs() -> list[Path]:
    home = str(Path.home())
    patterns = [
        f"{home}/Library/Containers/*/Data/Library/Caches/com.jihuanshe.app/Cache.db",
        f"{home}/Library/Containers/*/Data/Library/Caches/*jihuanshe*/Cache.db",
        f"{home}/Library/Group Containers/*/Library/Caches/com.jihuanshe.app/Cache.db",
        f"{home}/Library/Group Containers/*/Library/Caches/*jihuanshe*/Cache.db",
        f"{home}/Library/Caches/com.jihuanshe.app/Cache.db",
        f"{home}/Library/Caches/*jihuanshe*/Cache.db",
    ]
    dbs = [Path(path) for pattern in patterns for path in glob.glob(pattern)]
    return sorted(set(dbs))


def safe_text(value: bytes | str | None, limit: int = 250_000) -> str:
    if value is None:
        return ""
    text = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value)
    text = text.replace("\x00", "")
    return text[:limit]


def read_cached_body(db_path: Path, is_on_fs: Any, receiver_data: Any) -> str:
    text = safe_text(receiver_data)
    if not is_on_fs:
        return text
    fs_path = db_path.parent / "fsCachedData" / text.strip()
    try:
        return fs_path.read_bytes().decode("utf-8", errors="ignore")
    except OSError:
        return ""


def cache_rows(db_path: Path, query: str, limit: int) -> list[tuple[str, str]]:
    like = f"%{query}%"
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.text_factory = bytes
        rows = conn.execute(
            """
            select r.request_key, d.isDataOnFS, d.receiver_data
            from cfurl_cache_response r
            left join cfurl_cache_receiver_data d on r.entry_ID = d.entry_ID
            where cast(r.request_key as text) like ?
               or cast(d.receiver_data as text) like ?
            order by r.time_stamp desc
            limit ?
            """,
            (like, like, limit),
        ).fetchall()
    finally:
        conn.close()

    out: list[tuple[str, str]] = []
    for request_key, is_on_fs, receiver_data in rows:
        out.append((safe_text(request_key, 4000), read_cached_body(db_path, is_on_fs, receiver_data)))
    return out


def iter_values(value: Any) -> list[Any]:
    values = [value]
    if isinstance(value, dict):
        for child in value.values():
            values.extend(iter_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(iter_values(child))
    return values


def text_has_any(text: str, labels: tuple[str, ...]) -> bool:
    upper = text.upper()
    return any(label.upper() in upper for label in labels)


def price_from_object(obj: dict[str, Any]) -> float | None:
    for key in PRICE_FIELD_HINTS:
        if key in obj:
            price = number_or_none(obj.get(key))
            if price is not None:
                return price
    for value in obj.values():
        price = number_or_none(value)
        if price is not None:
            return price
    return None


def extract_prices_from_json(parsed: Any) -> PriceResult:
    result = PriceResult()
    for value in iter_values(parsed):
        if not isinstance(value, dict):
            continue
        text = json.dumps(value, ensure_ascii=False)
        price = price_from_object(value)
        if price is None:
            continue
        if result.psa10_price is None and text_has_any(text, PSA10_LABELS):
            result.psa10_price = price
        if result.raw_price is None and text_has_any(text, RAW_LABELS):
            result.raw_price = price
    return result


def extract_prices_from_text(text: str) -> PriceResult:
    result = PriceResult()
    compact = " ".join(text.split())
    raw_match = re.search(r"(?:流通品相|流通品|集换价|裸卡)[^\d¥￥]{0,20}[¥￥]?\s*(\d+(?:\.\d+)?)", compact, re.I)
    psa10_match = re.search(r"PSA[\s-]*10[^\d¥￥]{0,20}[¥￥]?\s*(\d+(?:\.\d+)?)", compact, re.I)
    if raw_match:
        result.raw_price = round2(float(raw_match.group(1)))
    if psa10_match:
        result.psa10_price = round2(float(psa10_match.group(1)))
    return result


def merge_price_result(base: PriceResult, incoming: PriceResult, source: str) -> PriceResult:
    if base.raw_price is None and incoming.raw_price is not None:
        base.raw_price = incoming.raw_price
        base.source = source
    if base.psa10_price is None and incoming.psa10_price is not None:
        base.psa10_price = incoming.psa10_price
        base.source = source
    return base


def lookup_card_prices(card_code: str, limit: int = 80) -> PriceResult:
    result = PriceResult()
    dbs = find_cache_dbs()
    if not dbs:
        result.note = "未找到集换社缓存"
        return result

    encrypted_hits = 0
    plain_hits = 0
    for db_path in dbs:
        try:
            rows = cache_rows(db_path, card_code, limit)
        except sqlite3.Error:
            continue
        for url, body in rows:
            searchable = f"{url}\n{body}"
            if card_code.lower() not in searchable.lower():
                continue
            if re.search(r'"raw_data"\s*:', body):
                encrypted_hits += 1
                continue
            if not body.strip():
                continue
            plain_hits += 1
            parsed_result = PriceResult()
            try:
                parsed_result = extract_prices_from_json(json.loads(body))
            except json.JSONDecodeError:
                parsed_result = extract_prices_from_text(body)
            result = merge_price_result(result, parsed_result, str(db_path))
            if result.raw_price is not None and result.psa10_price is not None:
                return result

    if result.raw_price is None and result.psa10_price is None:
        if encrypted_hits:
            result.note = "价格缓存为加密数据，保留原价"
        elif plain_hits:
            result.note = "缓存中未识别到价格"
        else:
            result.note = "未找到该编号缓存"
    elif result.psa10_price is None:
        result.note = "未识别到 PSA10"
    return result


def run_command(args: list[str], timeout: float = 15, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, env=env, check=False)


def run_osascript(script: str, timeout: float = 10) -> str:
    proc = run_command(["osascript", "-e", script], timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "osascript failed")
    return proc.stdout.strip()


def cf_release(ref: int | None) -> None:
    if ref:
        CORE_FOUNDATION.CFRelease(ctypes.c_void_p(ref))


def cf_string(value: str) -> int:
    return int(
        CORE_FOUNDATION.CFStringCreateWithCString(
            None,
            value.encode("utf-8"),
            K_CF_STRING_ENCODING_UTF8,
        )
    )


def cf_string_to_text(ref: int | None) -> str:
    if not ref or CORE_FOUNDATION.CFGetTypeID(ctypes.c_void_p(ref)) != CORE_FOUNDATION.CFStringGetTypeID():
        return ""
    buffer = ctypes.create_string_buffer(16384)
    ok = CORE_FOUNDATION.CFStringGetCString(
        ctypes.c_void_p(ref),
        buffer,
        len(buffer),
        K_CF_STRING_ENCODING_UTF8,
    )
    return buffer.value.decode("utf-8", errors="replace") if ok else ""


def ax_copy_attribute(element: int, name: str) -> int | None:
    key = cf_string(name)
    out = ctypes.c_void_p()
    try:
        err = APP_SERVICES.AXUIElementCopyAttributeValue(
            ctypes.c_void_p(element),
            ctypes.c_void_p(key),
            ctypes.byref(out),
        )
    finally:
        cf_release(key)
    return int(out.value) if err == 0 and out.value else None


def ax_set_string_attribute(element: int, name: str, value: str) -> bool:
    key = cf_string(name)
    string_value = cf_string(value)
    try:
        return (
            APP_SERVICES.AXUIElementSetAttributeValue(
                ctypes.c_void_p(element),
                ctypes.c_void_p(key),
                ctypes.c_void_p(string_value),
            )
            == 0
        )
    finally:
        cf_release(key)
        cf_release(string_value)


def cf_boolean(value: bool) -> int:
    return ctypes.c_void_p.in_dll(CORE_FOUNDATION, "kCFBooleanTrue" if value else "kCFBooleanFalse").value


def ax_set_bool_attribute(element: int, name: str, value: bool) -> bool:
    key = cf_string(name)
    try:
        return (
            APP_SERVICES.AXUIElementSetAttributeValue(
                ctypes.c_void_p(element),
                ctypes.c_void_p(key),
                ctypes.c_void_p(cf_boolean(value)),
            )
            == 0
        )
    finally:
        cf_release(key)


def ax_text_attribute(element: int, name: str) -> str:
    ref = ax_copy_attribute(element, name)
    try:
        return cf_string_to_text(ref)
    finally:
        cf_release(ref)


def ax_size_attribute(element: int) -> tuple[float, float] | None:
    ref = ax_copy_attribute(element, "AXSize")
    if not ref:
        return None
    try:
        size = AXCGSize()
        ok = APP_SERVICES.AXValueGetValue(
            ctypes.c_void_p(ref),
            K_AX_VALUE_CG_SIZE_TYPE,
            ctypes.byref(size),
        )
        return (size.width, size.height) if ok else None
    finally:
        cf_release(ref)


def ax_children(element: int) -> list[int]:
    arr = ax_copy_attribute(element, "AXChildren")
    if not arr:
        return []
    try:
        if CORE_FOUNDATION.CFGetTypeID(ctypes.c_void_p(arr)) != CORE_FOUNDATION.CFArrayGetTypeID():
            return []
        children: list[int] = []
        for index in range(CORE_FOUNDATION.CFArrayGetCount(ctypes.c_void_p(arr))):
            child = CORE_FOUNDATION.CFArrayGetValueAtIndex(ctypes.c_void_p(arr), index)
            if child:
                children.append(int(CORE_FOUNDATION.CFRetain(ctypes.c_void_p(child))))
        return children
    finally:
        cf_release(arr)


def jhs_process_id() -> int:
    proc = run_command(["pgrep", "-x", "jihuanshe_cn"], timeout=5)
    if proc.returncode != 0 or not proc.stdout.strip():
        proc = run_command(["pgrep", "-f", "jihuanshe_cn"], timeout=5)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError("未找到集换社进程")
    return int(proc.stdout.splitlines()[0].strip())


def post_key_to_jhs(key_code: int, repeats: int = 1) -> None:
    pid = jhs_process_id()
    for _ in range(repeats):
        down = APP_SERVICES.CGEventCreateKeyboardEvent(None, key_code, True)
        up = APP_SERVICES.CGEventCreateKeyboardEvent(None, key_code, False)
        if not down or not up:
            cf_release(down)
            cf_release(up)
            raise RuntimeError("无法创建集换社定向键盘事件")
        try:
            APP_SERVICES.CGEventPostToPid(pid, down)
            time.sleep(0.03)
            APP_SERVICES.CGEventPostToPid(pid, up)
        finally:
            cf_release(down)
            cf_release(up)
        time.sleep(0.08)


def post_text_to_jhs(text: str) -> None:
    pid = jhs_process_id()
    for char in text:
        code_units = char.encode("utf-16-le")
        units = (ctypes.c_uint16 * (len(code_units) // 2)).from_buffer_copy(code_units)
        down = APP_SERVICES.CGEventCreateKeyboardEvent(None, 0, True)
        up = APP_SERVICES.CGEventCreateKeyboardEvent(None, 0, False)
        if not down or not up:
            cf_release(down)
            cf_release(up)
            raise RuntimeError("无法创建集换社定向文本事件")
        try:
            APP_SERVICES.CGEventKeyboardSetUnicodeString(down, len(units), units)
            APP_SERVICES.CGEventKeyboardSetUnicodeString(up, len(units), units)
            APP_SERVICES.CGEventPostToPid(pid, down)
            time.sleep(0.01)
            APP_SERVICES.CGEventPostToPid(pid, up)
        finally:
            cf_release(down)
            cf_release(up)
        time.sleep(0.015)


def jhs_ax_window() -> int:
    app = APP_SERVICES.AXUIElementCreateApplication(jhs_process_id())
    if not app:
        raise RuntimeError("无法连接集换社无障碍窗口")
    windows = ax_copy_attribute(int(app), "AXWindows")
    if not windows:
        raise RuntimeError("未找到集换社窗口")
    try:
        if CORE_FOUNDATION.CFArrayGetCount(ctypes.c_void_p(windows)) <= 0:
            raise RuntimeError("未找到集换社窗口")
        window = CORE_FOUNDATION.CFArrayGetValueAtIndex(ctypes.c_void_p(windows), 0)
        if not window:
            raise RuntimeError("未找到集换社窗口")
        return int(CORE_FOUNDATION.CFRetain(ctypes.c_void_p(window)))
    finally:
        cf_release(windows)


def iter_jhs_ax_elements(max_depth: int = 20, max_nodes: int = 1600):
    root = jhs_ax_window()
    queue: list[tuple[int, int]] = [(root, 0)]
    seen = 0
    while queue and seen < max_nodes:
        element, depth = queue.pop(0)
        seen += 1
        role = ax_text_attribute(element, "AXRole")
        description = ax_text_attribute(element, "AXDescription")
        value = ax_text_attribute(element, "AXValue")
        identifier = ax_text_attribute(element, "AXIdentifier")
        yield {
            "element": element,
            "depth": depth,
            "role": role,
            "description": description,
            "value": value,
            "identifier": identifier,
            "text": "\n".join(part for part in (description, value, identifier) if part),
        }
        if depth < max_depth:
            queue.extend((child, depth + 1) for child in ax_children(element))


def ax_press_element(element: int) -> bool:
    action = cf_string("AXPress")
    try:
        return (
            APP_SERVICES.AXUIElementPerformAction(
                ctypes.c_void_p(element),
                ctypes.c_void_p(action),
            )
            == 0
        )
    finally:
        cf_release(action)


def ax_press_first(match, attempts: int = 1, pause: float = 0.35) -> bool:
    for _ in range(attempts):
        for node in iter_jhs_ax_elements():
            if match(node) and ax_press_element(node["element"]):
                time.sleep(pause)
                return True
        time.sleep(pause)
    return False


def find_jhs_ax_element(match, attempts: int = 1, pause: float = 0.35) -> dict[str, Any] | None:
    for _ in range(attempts):
        for node in iter_jhs_ax_elements():
            if match(node):
                return node
        time.sleep(pause)
    return None


def find_jhs_search_field(attempts: int = 2) -> dict[str, Any] | None:
    return find_jhs_ax_element(
        lambda node: node["identifier"] == "navSearchTextield" or node["role"] == "AXTextField",
        attempts=attempts,
        pause=0.6,
    )


def focus_jhs_search_field() -> bool:
    field = find_jhs_search_field()
    if not field:
        return False
    ax_press_element(field["element"])
    time.sleep(0.4)
    return True


def is_home_search_entry(node: dict[str, Any]) -> bool:
    if node["role"] != "AXButton" or node["description"]:
        return False
    size = ax_size_attribute(node["element"])
    return bool(size and size[0] >= 300 and 20 <= size[1] <= 60)


def ensure_jhs_app_open() -> None:
    run_command(["open", "-a", JHS_APP_NAME], timeout=10)
    time.sleep(1.2)
    try:
        run_osascript(f'tell application "{JHS_APP_NAME}" to activate')
    except RuntimeError:
        run_command(["open", "-b", "com.jihuanshe.app"], timeout=10)
        time.sleep(1.2)
        run_osascript(f'tell application "{JHS_APP_NAME}" to activate')
    time.sleep(0.8)


def restart_jhs_app() -> None:
    # The visible app is an iOS-on-Mac wrapper; leave this as a fallback for
    # half-closed renderer processes after UI automation gets stuck. Avoid
    # AppleScript quit here: the wrapper can hang while closing from a search
    # result page, which would stall the whole automation run.
    run_command(["pkill", "-TERM", "-f", "jihuanshe_cn"], timeout=5)
    time.sleep(1.0)
    run_command(["pkill", "-KILL", "-f", "jihuanshe_cn"], timeout=5)
    time.sleep(1.0)
    ensure_jhs_app_open()


def fetch_match_count_hint(card_code: str) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "is_all": "1",
            "is_match_card": "0",
            "keyword": card_code,
            "product_game_key": "pkm",
        }
    )
    url = f"https://api.jihuanshe.com/api/market/search/match-count?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "jhs-local-ui-price-updater/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return {}


def jhs_window_rect() -> tuple[int, int, int, int]:
    raw = run_osascript(
        '''
tell application "System Events"
  tell process "集换社"
    tell window 1
      set p to position as list
      set s to size as list
      return ((item 1 of p) as text) & "," & ((item 2 of p) as text) & "," & ((item 1 of s) as text) & "," & ((item 2 of s) as text)
    end tell
  end tell
end tell
'''
    )
    parts = [int(float(part.strip())) for part in raw.split(",")]
    if len(parts) != 4:
        raise RuntimeError(f"无法读取集换社窗口位置: {raw}")
    return parts[0], parts[1], parts[2], parts[3]


def press_escape(times: int = 1) -> None:
    for _ in range(times):
        try:
            post_key_to_jhs(K_VK_ESCAPE)
        except RuntimeError:
            pass
        time.sleep(0.35)


def dismiss_delete_history_alert() -> bool:
    has_alert = find_jhs_ax_element(
        lambda node: "是否删除搜索历史记录" in node["text"] or node["description"] == "警告",
        attempts=1,
        pause=0.2,
    )
    if not has_alert:
        return False
    dismissed = ax_press_first(
        lambda node: node["identifier"] == "action-button--999" or (node["role"] == "AXButton" and node["description"] == "取消"),
        attempts=2,
        pause=0.4,
    )
    time.sleep(0.5)
    return dismissed


def press_return() -> None:
    post_key_to_jhs(K_VK_RETURN)
    time.sleep(0.15)
    post_key_to_jhs(K_VK_NUMPAD_ENTER)


def is_search_history_visible() -> bool:
    return bool(find_jhs_ax_element(lambda node: node["description"] == "搜索历史" or node["description"] == "清空记录", attempts=1, pause=0.2))


def set_search_text_and_return(text: str) -> None:
    field = find_jhs_search_field(attempts=3)
    if not field:
        raise RuntimeError("未找到集换社搜索框")
    ax_press_element(field["element"])
    time.sleep(0.2)
    ax_set_bool_attribute(field["element"], "AXFocused", True)
    ax_set_string_attribute(field["element"], "AXValue", "")
    post_key_to_jhs(K_VK_DELETE, repeats=1)
    time.sleep(0.15)
    post_text_to_jhs(text)
    time.sleep(0.2)
    ax_set_string_attribute(field["element"], "AXValue", text)
    time.sleep(0.5)
    for _ in range(3):
        press_return()
        time.sleep(1.0)
        if not is_search_history_visible():
            break
    time.sleep(1.2)


def target_game_filter_label(hint: dict[str, Any], forced_label: str = "") -> str:
    forced_label = forced_label.strip()
    if forced_label:
        return forced_label
    if hint.get("switch_game_key") != "pkm":
        return ""
    sub_key = str(hint.get("switch_game_sub_key") or "").lower()
    if sub_key in {"jp", "ja", "jpn"}:
        return "宝可梦日文"
    if sub_key in {"en", "eng"}:
        return "宝可梦英文"
    if sub_key in {"cn", "sc", "zh", "zh_cn", "chs"}:
        return "宝可梦简中"
    return ""


def current_game_filter_label() -> str:
    node = find_jhs_ax_element(lambda item: item["identifier"] == "filterViewGameButton", attempts=1)
    return node["description"] if node else ""


def ensure_game_filter(hint: dict[str, Any], forced_label: str = "") -> None:
    target = target_game_filter_label(hint, forced_label)
    if not target or current_game_filter_label() == target:
        return
    if not ax_press_first(lambda node: node["identifier"] == "filterViewGameButton", attempts=2, pause=0.6):
        raise RuntimeError("未找到游戏筛选按钮")
    if not ax_press_first(lambda node: node["description"] == target, attempts=2, pause=0.6):
        raise RuntimeError(f"未找到游戏筛选项: {target}")
    if not ax_press_first(lambda node: node["description"] == "确认", attempts=2, pause=1.2):
        raise RuntimeError("游戏筛选确认失败")
    time.sleep(2.0)


def press_first_product_result(card_code: str) -> None:
    ignored = ("取消", "清除", "宝可梦", "罕贵度", "显示", "商品", "竞价", "动态", "用户", "卡牌", "系列")
    code_compact = normalized_ocr_text(card_code)
    candidate: dict[str, Any] | None = None
    seen_code = False
    for node in iter_jhs_ax_elements():
        text = node["text"]
        if "流通品相" in text and "PSA10" in text:
            return
        compact_text = normalized_ocr_text(text)
        if card_code in text or code_compact in compact_text or code_compact.replace("/", "") in compact_text:
            seen_code = True
        description = node["description"]
        if (
            node["role"] == "AXButton"
            and description
            and not any(part in description for part in ignored)
        ):
            compact_description = normalized_ocr_text(description)
            if code_compact in compact_description or code_compact.replace("/", "") in compact_description:
                candidate = node
                break
            if seen_code and candidate is None:
                candidate = node
    if not candidate:
        raise RuntimeError("未找到商品结果按钮")
    action = cf_string("AXPress")
    try:
        err = APP_SERVICES.AXUIElementPerformAction(
            ctypes.c_void_p(candidate["element"]),
            ctypes.c_void_p(action),
        )
    finally:
        cf_release(action)
    if err != 0:
        raise RuntimeError(f"商品结果按钮点击失败: AXError {err}")
    time.sleep(2.2)


def product_result_signal(card_code: str) -> str:
    code_compact = normalized_ocr_text(card_code)
    has_button = False
    has_code = False
    has_price = False
    for node in iter_jhs_ax_elements():
        text = node["text"]
        compact_text = normalized_ocr_text(text)
        if code_compact in compact_text or code_compact.replace("/", "") in compact_text:
            has_code = True
        if "¥" in text or "￥" in text or "起" in text:
            has_price = True
        description = node["description"]
        if (
            node["role"] == "AXButton"
            and description
            and not any(part in description for part in ("取消", "清除", "宝可梦", "罕贵度", "显示", "商品", "竞价", "动态", "用户", "卡牌", "系列"))
        ):
            has_button = True
    if has_code and has_button:
        return "code_button"
    if has_button and has_price:
        return "price_button"
    if has_button:
        return "button"
    return ""


def read_jhs_accessibility_text(timeout: float = 15) -> str:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            if dismiss_delete_history_alert():
                time.sleep(0.4)
                continue
            lines = []
            for node in iter_jhs_ax_elements():
                if node["description"]:
                    lines.append(node["description"])
                if node["value"]:
                    lines.append(node["value"])
            return "\n".join(lines)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.4)
    raise RuntimeError(last_error or "读取集换社无障碍文本超时")


def read_jhs_price_detail_text(timeout: float = 15) -> str:
    deadline = time.time() + timeout
    last_text = ""
    while time.time() < deadline:
        text = read_jhs_accessibility_text(timeout=2)
        last_text = text
        if "流通品相" in text and ("¥" in text or "￥" in text):
            return text
        time.sleep(0.6)
    return last_text


def screenshot_and_ocr_window() -> str:
    image_path = screenshot_jhs_window()
    return ocr_image_with_tesseract_js(image_path)


def normalized_ocr_text(text: str) -> str:
    return re.sub(r"\s+", "", text).upper().replace("—", "-").replace("–", "-")


def open_search_page() -> None:
    dismiss_delete_history_alert()
    if focus_jhs_search_field():
        return
    # First get out of transient image viewers/detail pages.
    press_escape(2)
    dismiss_delete_history_alert()
    if focus_jhs_search_field():
        return
    # If a detail page is open, use the accessibility back button. The iOS-on-Mac
    # wrapper can ignore synthetic coordinate clicks, but AXPress is reliable and
    # does not move the user's real mouse cursor.
    for _ in range(4):
        if focus_jhs_search_field():
            return
        if not ax_press_first(lambda node: node["identifier"] == "nav_back", attempts=1, pause=0.8):
            break
    if focus_jhs_search_field():
        return
    if ax_press_first(is_home_search_entry, attempts=2, pause=0.8):
        if focus_jhs_search_field():
            return
    raise RuntimeError("未找到集换社搜索框或首页搜索入口")


def open_card_detail_from_ui(card_code: str, game_label: str = "") -> bool:
    ensure_jhs_app_open()
    hint = fetch_match_count_hint(card_code)
    open_search_page()
    set_search_text_and_return(card_code)
    ensure_game_filter(hint, game_label)
    # Keep the result tab on 商品 before opening the first card result.
    # The 商品 tab is near the top, while the first商品 result row starts much
    # lower; keep these coordinates separated so we do not fall into 动态.
    if not ax_press_first(lambda node: node["description"] == "商品", attempts=2, pause=0.5):
        raise RuntimeError("未找到商品 tab，已停止避免误点动态")
    time.sleep(0.5)
    if int(hint.get("product_match_count") or 0) <= 0:
        raise RuntimeError("集换社商品搜索无结果")
    signal = product_result_signal(card_code)
    if not signal:
        result_text = screenshot_and_ocr_window()
        compact = normalized_ocr_text(result_text)
        expected_code = normalized_ocr_text(card_code)
        if expected_code not in compact and expected_code.replace("/", "") not in compact:
            raise RuntimeError("商品结果页未找到可点击商品结果，已停止避免误点动态")
    # First card result. Use accessibility instead of coordinates to avoid
    # opening the dynamic tab when the result list layout shifts. We no longer
    # require OCR to see the price on the list page; detail-page parsing is the
    # authoritative price read.
    press_first_product_result(card_code)
    return True


def screenshot_jhs_window() -> Path:
    rect = jhs_window_rect()
    path = Path(tempfile.gettempdir()) / f"jhs-price-{int(time.time() * 1000)}.png"
    region = f"{rect[0]},{rect[1]},{rect[2]},{rect[3]}"
    proc = run_command(["screencapture", "-x", f"-R{region}", str(path)], timeout=10)
    if proc.returncode != 0 or not path.exists():
        raise RuntimeError(proc.stderr.strip() or "截图失败")
    return path


def ocr_image_with_tesseract_js(image_path: Path) -> str:
    node_bin = Path(os.environ.get("NODE_BIN", str(BUNDLED_NODE_BIN)))
    if not node_bin.exists():
        node_bin = Path("node")
    env = os.environ.copy()
    if BUNDLED_NODE_MODULES.exists():
        existing = env.get("NODE_PATH", "")
        env["NODE_PATH"] = str(BUNDLED_NODE_MODULES) + (os.pathsep + existing if existing else "")
    js = r'''
const tesseract = require("tesseract.js");
const image = process.argv[1];
(async () => {
  const { data } = await tesseract.recognize(image, "eng");
  process.stdout.write(data.text || "");
})().catch((error) => {
  console.error(error && error.message ? error.message : String(error));
  process.exit(1);
});
'''
    proc = run_command([str(node_bin), "-e", js, str(image_path)], timeout=45, env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "OCR 失败")
    return proc.stdout


def extract_prices_from_ocr_text(text: str) -> PriceResult:
    result = PriceResult()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        normalized = line.replace("PSAT0", "PSA10").replace("PSA1O", "PSA10").replace("PSAIO", "PSA10")
        normalized = normalized.replace("￥", "¥")
        psa_match = re.search(r"PSA\s*10[^\d]{0,10}(\d{2,}(?:\.\d+)?)", normalized, re.I)
        raw_match = re.search(r"(\d{2,}(?:\.\d+)?)\s+PSA\s*10", normalized, re.I)
        if psa_match and result.psa10_price is None:
            result.psa10_price = round2(float(psa_match.group(1)))
        if raw_match and result.raw_price is None:
            result.raw_price = round2(float(raw_match.group(1)))
        if result.raw_price is not None and result.psa10_price is not None:
            result.source = "jihuanshe_ui_ocr"
            return result
    result.note = "UI截图未识别到流通品/PSA10价格"
    return result


def extract_prices_from_accessibility_text(text: str) -> PriceResult:
    result = PriceResult()
    compact = " ".join(text.replace("￥", "¥").split())
    raw_match = re.search(r"流通品相[^\d¥]{0,20}¥[^\d]{0,10}(\d+(?:\.\d+)?)", compact)
    psa_match = re.search(r"PSA\s*10[^\d¥]{0,20}¥[^\d]{0,10}(\d+(?:\.\d+)?)", compact, re.I)
    if raw_match:
        result.raw_price = round2(float(raw_match.group(1)))
    if psa_match:
        result.psa10_price = round2(float(psa_match.group(1)))
    if result.raw_price is not None or result.psa10_price is not None:
        result.source = "jihuanshe_ui_accessibility"
        return result
    result.note = "UI无障碍文本未识别到流通品/PSA10价格"
    return result


def card_code_search_variants(card_code: str) -> list[str]:
    code = card_code.strip()
    variants = [code]
    match = re.match(r"^(SV)P-(\d+)$", code, re.I)
    if match:
        variants.append(f"{match.group(1).upper()}-P-{match.group(2)}")
    match = re.match(r"^(SV)-P-(\d+)$", code, re.I)
    if match:
        variants.append(f"{match.group(1).upper()}P-{match.group(2)}")
    match = re.match(r"^(\d+TH)P-(\d+)$", code, re.I)
    if match:
        variants.append(f"{match.group(1)}-P-{match.group(2)}")
    match = re.match(r"^(\d+TH)-P-(\d+)$", code, re.I)
    if match:
        variants.append(f"{match.group(1)}P-{match.group(2)}")
    match = re.match(r"^(CBB\d+C)-(\d{2})(\d{2})$", code, re.I)
    if match:
        variants.append(f"{match.group(1)}-{match.group(2)} {match.group(3)}")
    match = re.match(r"^(CBB\d+C)-(\d{2})\s+(\d{2})$", code, re.I)
    if match:
        variants.append(f"{match.group(1)}-{match.group(2)}{match.group(3)}")
    return list(dict.fromkeys(variants))


def ui_price_note(kind: str, attempt: int, original_code: str, query_code: str, game_label: str = "") -> str:
    note = f"集换社App UI{kind}" if attempt == 0 else f"集换社App UI{kind}（重启后）"
    if query_code != original_code:
        note += f"（按 {query_code} 搜索）"
    if game_label:
        note += f"（{game_label}）"
    return note


def lookup_card_prices_via_ui(card_code: str, search_code: str = "", game_label: str = "") -> PriceResult:
    last_note = ""
    query_base = search_code.strip() or card_code
    variants = card_code_search_variants(query_base)
    for attempt in range(2):
        if attempt > 0:
            restart_jhs_app()
        for query_code in variants:
            try:
                open_card_detail_from_ui(query_code, game_label)
                accessible_text = read_jhs_price_detail_text()
                result = extract_prices_from_accessibility_text(accessible_text)
                if result.raw_price is not None or result.psa10_price is not None:
                    result.note = ui_price_note("读取", attempt, card_code, query_code, game_label)
                    return result
                image_path = screenshot_jhs_window()
                text = ocr_image_with_tesseract_js(image_path)
                result = extract_prices_from_ocr_text(text)
                if result.raw_price is not None or result.psa10_price is not None:
                    result.note = ui_price_note("识别", attempt, card_code, query_code, game_label)
                    return result
                last_note = result.note or "UI截图未识别到价格"
            except Exception as exc:
                last_note = f"UI模式失败({query_code}): {exc}"
    return PriceResult(note=f"{last_note}；已重启集换社重试1次")


def normalize_item(raw: Any, index: int) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {}
    card_code = str(item.get("cardCode") or "").strip() or infer_card_code_from_image_url(item.get("imageUrl"))
    return {
        **item,
        "id": item.get("id", index + 1),
        "cardCode": card_code,
        "status": item.get("status") or ("已售出" if item.get("sells") else "未售出"),
    }


def price_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def normalize_price_history(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    history: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        checked_at = str(entry.get("checkedAt") or entry.get("updatedAt") or entry.get("date") or "").strip()
        raw_price = price_number(entry.get("rawPrice", entry.get("jhsRawPrice")))
        psa10_price = price_number(entry.get("psa10Price", entry.get("jhsPsa10Price")))
        if not checked_at and raw_price is None and psa10_price is None:
            continue
        history.append(
            {
                "checkedAt": checked_at,
                "rawPrice": raw_price,
                "psa10Price": psa10_price,
                "note": str(entry.get("note") or "").strip(),
            }
        )
    return history[-120:]


def append_price_history(item: dict[str, Any], checked_at: str, previous_note: str = "") -> None:
    history = normalize_price_history(item.get("jhsPriceHistory"))
    raw_price = price_number(item.get("jhsRawPrice"))
    psa10_price = price_number(item.get("jhsPsa10Price"))
    previous_checked_at = str(item.get("jhsPriceUpdatedAt") or "").strip()

    if previous_checked_at and not any(entry.get("checkedAt") == previous_checked_at for entry in history):
        previous_raw = price_number(item.get("_previousJhsRawPrice"))
        previous_psa10 = price_number(item.get("_previousJhsPsa10Price"))
        if previous_raw is not None or previous_psa10 is not None:
            history.append(
                {
                    "checkedAt": previous_checked_at,
                    "rawPrice": previous_raw,
                    "psa10Price": previous_psa10,
                    "note": previous_note,
                }
            )

    if history and history[-1].get("checkedAt") == checked_at:
        history[-1] = {
            "checkedAt": checked_at,
            "rawPrice": raw_price,
            "psa10Price": psa10_price,
            "note": str(item.get("jhsPriceNote") or "").strip(),
        }
    else:
        history.append(
            {
                "checkedAt": checked_at,
                "rawPrice": raw_price,
                "psa10Price": psa10_price,
                "note": str(item.get("jhsPriceNote") or "").strip(),
            }
        )

    item["jhsPriceHistory"] = history[-120:]
    item.pop("_previousJhsRawPrice", None)
    item.pop("_previousJhsPsa10Price", None)


def decode_card_code_from_file_stem(stem: str) -> str:
    match = re.match(r"^(.*)-(\d{3})-([A-Za-z0-9.-]+)$", stem)
    if match:
        return f"{match.group(1)}-{match.group(2)}/{match.group(3)}"
    return stem


def infer_card_code_from_image_url(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"cardimg/([^/?#]+)\.(?:png|webp|jpg|jpeg)", text, re.I)
    if not match:
        return ""
    return decode_card_code_from_file_stem(match.group(1))


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [normalize_item(item, index) for index, item in enumerate(payload)]
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [normalize_item(item, index) for index, item in enumerate(payload["items"])]
    raise ValueError("数据格式不是卡牌列表")


def read_local_items(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        return extract_items(json.load(fh))


def write_local_items(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def supabase_headers(anon_key: str) -> dict[str, str]:
    return {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def read_supabase_items(url: str, anon_key: str, table: str, row_id: str) -> list[dict[str, Any]]:
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}?id=eq.{row_id}&select=payload"
    req = urllib.request.Request(endpoint, headers=supabase_headers(anon_key))
    with urllib.request.urlopen(req, timeout=30) as resp:
        rows = json.loads(resp.read().decode("utf-8"))
    if not rows:
        return []
    return extract_items(rows[0].get("payload"))


def write_supabase_items(url: str, anon_key: str, table: str, row_id: str, items: list[dict[str, Any]]) -> None:
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}?id=eq.{row_id}"
    body = json.dumps(
        {"id": row_id, "payload": items, "updated_at": datetime.now().astimezone().isoformat()},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers=supabase_headers(anon_key), method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        upsert_endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
        req = urllib.request.Request(upsert_endpoint, data=body, headers=supabase_headers(anon_key), method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()


def should_update(item: dict[str, Any]) -> bool:
    if item.get("status") != "未售出":
        return False
    return bool(str(item.get("cardCode") or "").strip())


def has_price_value(value: Any) -> bool:
    return value is not None and value != ""


def update_items(
    items: list[dict[str, Any]],
    limit: int,
    dry_run: bool,
    mode: str = "cache",
    max_items: int | None = None,
    only_card_code: str = "",
    only_missing_raw: bool = False,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, Any]:
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    updated = 0
    skipped = 0
    failed = 0
    details: list[dict[str, Any]] = []

    attempted = 0
    for item in items:
        if not should_update(item):
            skipped += 1
            continue
        if only_card_code and str(item.get("cardCode") or "").strip() != only_card_code:
            skipped += 1
            continue
        if only_missing_raw and has_price_value(item.get("jhsRawPrice")):
            skipped += 1
            continue
        if max_items is not None and attempted >= max_items:
            skipped += 1
            continue
        attempted += 1
        card_code = str(item.get("cardCode") or "").strip()
        jhs_search_code = str(item.get("jhsSearchCode") or item.get("jhsQueryCode") or "").strip()
        jhs_game_label = str(item.get("jhsGameLabel") or item.get("jhsGame") or item.get("cardLanguage") or "").strip()
        print(
            f"[{attempted}] id={item.get('id')} cardCode={card_code}"
            f"{f' search={jhs_search_code}' if jhs_search_code else ''}"
            f"{f' game={jhs_game_label}' if jhs_game_label else ''}",
            file=sys.stderr,
            flush=True,
        )
        result = (
            lookup_card_prices_via_ui(card_code, search_code=jhs_search_code, game_label=jhs_game_label)
            if mode == "ui"
            else lookup_card_prices(jhs_search_code or card_code, limit=limit)
        )
        if result.raw_price is None and result.psa10_price is None:
            failed += 1
            item["jhsPriceNote"] = result.note or "未更新"
            details.append({"id": item.get("id"), "cardCode": card_code, "status": "failed", "note": item["jhsPriceNote"]})
            print(f"  -> failed: {item['jhsPriceNote']}", file=sys.stderr, flush=True)
            if checkpoint:
                checkpoint()
            continue

        previous_note = str(item.get("jhsPriceNote") or "").strip()
        item["_previousJhsRawPrice"] = item.get("jhsRawPrice")
        item["_previousJhsPsa10Price"] = item.get("jhsPsa10Price")
        if result.raw_price is not None:
            item["jhsRawPrice"] = result.raw_price
        if result.psa10_price is not None:
            item["jhsPsa10Price"] = result.psa10_price
        item["jhsPriceNote"] = result.note
        append_price_history(item, checked_at, previous_note=previous_note)
        item["jhsPriceUpdatedAt"] = checked_at
        updated += 1
        print(
            f"  -> updated: raw={item.get('jhsRawPrice')} psa10={item.get('jhsPsa10Price')} note={item.get('jhsPriceNote') or ''}",
            file=sys.stderr,
            flush=True,
        )
        details.append(
            {
                "id": item.get("id"),
                "cardCode": card_code,
                "status": "updated",
                "jhsRawPrice": item.get("jhsRawPrice"),
                "jhsPsa10Price": item.get("jhsPsa10Price"),
                "note": item.get("jhsPriceNote") or "",
            }
        )
        if checkpoint:
            checkpoint()

    return {
        "checkedAt": checked_at,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "dryRun": dry_run,
        "mode": mode,
        "onlyMissingRaw": only_missing_raw,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Update unsold card Jihuanshe raw/PSA10 prices.")
    parser.add_argument("--mode", choices=["cache", "ui"], default=os.environ.get("JHS_PRICE_MODE", "cache"))
    parser.add_argument("--source", choices=["supabase", "local"], default=os.environ.get("JHS_PRICE_SOURCE", "supabase"))
    parser.add_argument("--local-data", default=str(LOCAL_DATA_PATH))
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL", DEFAULT_SUPABASE_URL))
    parser.add_argument("--supabase-anon-key", default=os.environ.get("SUPABASE_ANON_KEY", DEFAULT_SUPABASE_ANON_KEY))
    parser.add_argument("--table", default=os.environ.get("SUPABASE_TABLE", DEFAULT_TABLE))
    parser.add_argument("--row-id", default=os.environ.get("SUPABASE_ROW_ID", DEFAULT_ROW_ID))
    parser.add_argument("--cache-limit", type=int, default=80)
    parser.add_argument("--limit", type=int, default=0, help="UI/cache update maximum matching unsold items; 0 means all")
    parser.add_argument("--card-code", default="", help="Only update one card code, useful for UI-mode testing")
    parser.add_argument("--missing-raw", action="store_true", help="Only update matching unsold items without jhsRawPrice")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.source == "supabase":
        items = read_supabase_items(args.supabase_url, args.supabase_anon_key, args.table, args.row_id)
    else:
        items = read_local_items(Path(args.local_data))

    def checkpoint_items() -> None:
        if args.source == "supabase":
            write_supabase_items(args.supabase_url, args.supabase_anon_key, args.table, args.row_id, items)
        else:
            write_local_items(Path(args.local_data), items)

    summary = update_items(
        items,
        limit=args.cache_limit,
        dry_run=args.dry_run,
        mode=args.mode,
        max_items=args.limit if args.limit > 0 else None,
        only_card_code=args.card_code.strip(),
        only_missing_raw=args.missing_raw,
        checkpoint=None if args.dry_run else checkpoint_items,
    )
    if not args.dry_run:
        if args.source == "supabase":
            write_supabase_items(args.supabase_url, args.supabase_anon_key, args.table, args.row_id, items)
        else:
            write_local_items(Path(args.local_data), items)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
