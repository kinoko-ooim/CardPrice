#!/usr/bin/env python3
"""通过日版宝可梦卡牌编号查找对应图片。

支持两类来源：
1. 旧编号优先尝试 tcg.mik.moe 的直链图片。
2. 新编号或 tcg.mik.moe 不存在时，回退到 TCG Collector 的检索结果。

示例：
  python3 scripts/card_image_lookup.py M1L-089/063
  python3 scripts/card_image_lookup.py M1L-089/063 --download
  python3 scripts/card_image_lookup.py CSM2bC-034 --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent


R_JINA_PREFIX = "https://r.jina.ai/http://"
TCGCOLLECTOR_SETS_URL = (
    "https://www.tcgcollector.com/sets/jp"
    "?cardCountMode=anyCardVariant&releaseDateOrder=newToOld&displayAs=images"
)
TCGCOLLECTOR_SEARCH_URL = (
    "https://www.tcgcollector.com/cards/jp"
    "?cardSource=inCardVariant&releaseDateOrder=newToOld&displayAs=images&cardSearch={query}"
)
TCG_MIK_URL = "https://tcg.mik.moe/static/img/{set_code}/{card_num}.png"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


@dataclass
class CardCode:
    raw: str
    set_code: str
    card_num: str
    denominator: str = ""

    @property
    def card_number(self) -> str:
        return f"{self.card_num}/{self.denominator}" if self.denominator else self.card_num

    @property
    def canonical(self) -> str:
        return f"{self.set_code}-{self.card_number}"

    @property
    def filename_stem(self) -> str:
        if self.denominator:
            return f"{self.set_code}-{self.card_num}-{self.denominator}"
        return f"{self.set_code}-{self.card_num}"


@dataclass
class LookupResult:
    code: str
    source: str
    title: str
    image_url: str
    page_url: str
    set_name: str = ""
    downloaded_to: str = ""


def build_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT})


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(build_request(url), timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def url_exists(url: str) -> bool:
    try:
        with urllib.request.urlopen(build_request(url), timeout=20) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            return False
        raise


def download_file(url: str, target_path: Path) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(build_request(url), timeout=60) as response:
            data = response.read()
        target_path.write_bytes(data)
    except Exception:  # noqa: BLE001
        subprocess.run(
            [
                "curl",
                "-L",
                "-f",
                "-A",
                USER_AGENT,
                "-o",
                str(target_path),
                url,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return target_path


def r_jina_url(url: str) -> str:
    return f"{R_JINA_PREFIX}{url}"


def parse_card_code(raw: str) -> CardCode:
    cleaned = re.sub(r"\s+", "", raw.strip())
    cleaned = cleaned.replace("–", "-").replace("—", "-").replace("_", "-")

    match = re.match(r"^(?P<set>.+)-(?P<num>\d{1,3})(?:/(?P<den>[A-Za-z0-9.-]+))?$", cleaned)
    if not match:
        match = re.match(
            r"^(?P<set>[A-Za-z0-9.-]+?)(?P<num>\d{2,3})(?:/(?P<den>[A-Za-z0-9.-]+))?$",
            cleaned,
        )

    if not match:
        raise ValueError(
            "编号格式无法识别，请使用类似 CSM2bC-034 或 M1L-089/063 的格式。"
        )

    set_code = match.group("set")
    card_num = match.group("num").zfill(3)
    denominator = match.group("den") or ""
    return CardCode(raw=raw, set_code=set_code, card_num=card_num, denominator=denominator)


def load_set_code_map() -> Dict[str, str]:
    markdown = fetch_text(r_jina_url(TCGCOLLECTOR_SETS_URL))
    pattern = re.compile(
        r"\[(?P<name>[^\[\]\n]+?)\]"
        r"\(https://www\.tcgcollector\.com/sets/\d+/[^\)]+\)"
        r"(?P<code>[A-Za-z0-9.-]+)"
    )
    mapping: Dict[str, str] = {}
    for match in pattern.finditer(markdown):
        name = match.group("name").strip()
        code = match.group("code").strip()
        if code not in mapping:
            mapping[code] = name
    if not mapping:
        raise RuntimeError("未能从 TCG Collector 解析出日版卡包列表。")
    return mapping


def search_tcgcollector(code: CardCode, set_name: str) -> LookupResult:
    query = urllib.parse.quote(code.card_number, safe="")
    url = TCGCOLLECTOR_SEARCH_URL.format(query=query)
    markdown = fetch_text(r_jina_url(url))

    entry_pattern = re.compile(
        r"\[\!\[Image \d+: (?P<title>[^\]]+)\]\("
        r"(?P<image>https://static\.tcgcollector\.com/content/images/[^\)]+)\)\s+"
        r"!\[Image \d+: (?P<set_name>[^\]]+)\]\([^\)]*\)\s+"
        r"(?P<number>\d+/\d+).*?\]\("
        r"(?P<page>https://www\.tcgcollector\.com/cards/\d+/[^ \)]+)",
        re.S,
    )

    matches: List[LookupResult] = []
    for match in entry_pattern.finditer(markdown):
        if match.group("number").strip() != code.card_number:
            continue
        matches.append(
            LookupResult(
                code=code.canonical,
                source="tcgcollector",
                title=match.group("title").strip(),
                image_url=match.group("image").strip(),
                page_url=match.group("page").strip(),
                set_name=match.group("set_name").strip(),
            )
        )

    if not matches:
        raise RuntimeError(f"没有在 TCG Collector 中找到 {code.card_number} 的结果。")

    if set_name:
        for item in matches:
            if item.set_name == set_name:
                return item

    if len(matches) == 1:
        return matches[0]

    available = " / ".join(f"{item.set_name}: {item.title}" for item in matches[:5])
    raise RuntimeError(
        f"找到了多个同编号结果，但没法唯一匹配 {code.set_code}。候选：{available}"
    )


def lookup_card_image(code: CardCode, set_name_map: Optional[Dict[str, str]] = None) -> LookupResult:
    tcg_mik_url = TCG_MIK_URL.format(set_code=code.set_code, card_num=code.card_num)
    if url_exists(tcg_mik_url):
        return LookupResult(
            code=code.canonical,
            source="tcg.mik.moe",
            title=code.canonical,
            image_url=tcg_mik_url,
            page_url="",
            set_name="",
        )

    if not code.denominator:
        raise RuntimeError(
            f"{code.canonical} 在 tcg.mik.moe 上不存在，且编号里没有总卡数，无法继续到 TCG Collector 精确匹配。"
        )

    if set_name_map is None:
        set_name_map = load_set_code_map()
    set_name = set_name_map.get(code.set_code, "")
    return search_tcgcollector(code, set_name)


def infer_extension(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".png", ".webp", ".jpg", ".jpeg", ".gif"):
        if path.endswith(ext):
            return ext
    return ".png"


def print_human(result: LookupResult) -> None:
    print(result.code)
    print(f"  来源: {result.source}")
    if result.title:
        print(f"  标题: {result.title}")
    if result.set_name:
        print(f"  卡包: {result.set_name}")
    print(f"  图片: {result.image_url}")
    if result.page_url:
        print(f"  页面: {result.page_url}")
    if result.downloaded_to:
        print(f"  下载: {result.downloaded_to}")


def run() -> int:
    parser = argparse.ArgumentParser(description="通过卡牌编号查找对应图片")
    parser.add_argument("codes", nargs="+", help="卡牌编号，例如 M1L-089/063")
    parser.add_argument(
        "--download",
        action="store_true",
        help="把图片下载到项目根目录下的 cardimg/ 文件夹",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "cardimg"),
        help="下载目录，默认是 <项目根目录>/cardimg",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON",
    )
    args = parser.parse_args()

    set_name_map: Optional[Dict[str, str]] = None
    results: List[LookupResult] = []

    for raw_code in args.codes:
        try:
            card_code = parse_card_code(raw_code)
            if card_code.denominator:
                if set_name_map is None:
                    set_name_map = load_set_code_map()
                result = lookup_card_image(card_code, set_name_map)
            else:
                result = lookup_card_image(card_code)

            if args.download:
                ext = infer_extension(result.image_url)
                target = Path(args.output_dir) / f"{card_code.filename_stem}{ext}"
                saved_path = download_file(result.image_url, target)
                result.downloaded_to = str(saved_path.resolve())

            results.append(result)
        except Exception as exc:  # noqa: BLE001
            if args.json:
                results.append(
                    LookupResult(
                        code=raw_code,
                        source="error",
                        title=str(exc),
                        image_url="",
                        page_url="",
                    )
                )
            else:
                print(f"{raw_code}\n  错误: {exc}", file=sys.stderr)

    if args.json:
        print(
            json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2)
        )
    else:
        for index, result in enumerate(results):
            if index:
                print()
            print_human(result)

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(run())
