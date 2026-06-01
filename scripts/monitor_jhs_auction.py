#!/usr/bin/env python3
"""Monitor Jihuanshe auction availability for a card keyword.

This script stays inside the safe boundary:
- It calls only the plain `search/match-count` endpoint.
- It reads local CFURL cache files created by the user's Jihuanshe app.
- It does not decrypt raw_data, extract tokens, place bids, or modify app data.

For price/current bid fields, it can only report values if they appear as plain
JSON in local cache. Many Jihuanshe auction endpoints cache encrypted
`{"raw_data": "..."}` responses, in which case the monitor reports availability
counts but not current prices.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


MATCH_COUNT_URL = "https://api.jihuanshe.com/api/market/search/match-count"

PRICE_KEYS = {
    "auction_price",
    "bid_price",
    "bidPrice",
    "current_price",
    "currentPrice",
    "highest_price",
    "highestPrice",
    "max_bidding_price",
    "maxBiddingPrice",
    "price",
    "start_bidding_price",
    "startBiddingPrice",
    "starting_price",
    "startingPrice",
}

TIME_KEYS = {
    "auction_product_end_timestamp",
    "bidding_end_time",
    "biddingEndTime",
    "end_at",
    "endAt",
    "end_time",
    "endTime",
}


def find_cache_db() -> Path | None:
    base = Path.home() / "Library/Containers"
    if not base.exists():
        return None
    matches = list(base.glob("*/Data/Library/Caches/com.jihuanshe.app/Cache.db"))
    return matches[0] if matches else None


def fetch_match_count(keyword: str, timeout: float = 10) -> dict[str, Any]:
    params = {
        # This mirrors the search request shape the Jihuanshe app uses when it
        # auto-detects a Pokemon card code across languages.
        "is_all": "1",
        "is_match_card": "0",
        "keyword": keyword,
        "product_game_key": "pkm",
    }
    url = f"{MATCH_COUNT_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "jhs-local-auction-monitor/0.1",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    data["_url"] = url
    return data


def read_json_like_bytes(path: Path) -> Any | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    text = raw.decode("utf-8", errors="ignore").strip()
    if not text or not text.startswith(("{", "[")):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def text_contains_keyword(value: Any, keyword: str) -> bool:
    needle = keyword.lower()
    try:
        haystack = json.dumps(value, ensure_ascii=False).lower()
    except TypeError:
        haystack = str(value).lower()
    return needle in haystack


def flatten_items(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if any(k in value for k in PRICE_KEYS | TIME_KEYS) or "auction_product_id" in value:
            found.append(value)
        for child in value.values():
            found.extend(flatten_items(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(flatten_items(child))
    return found


def summarize_item(item: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in [
        "auction_product_id",
        "id",
        "name",
        "card_name",
        "cardName",
        "title",
        "status",
        "auction_status",
        "auctionStatus",
        "quantity",
        "count",
    ]:
        if key in item:
            summary[key] = item[key]
    for key in sorted(PRICE_KEYS):
        if key in item:
            summary[key] = item[key]
    for key in sorted(TIME_KEYS):
        if key in item:
            summary[key] = item[key]
    return summary or item


def cache_records(db_path: Path) -> list[tuple[str, str | None]]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """
            select r.request_key, d.isDataOnFS, d.receiver_data
            from cfurl_cache_response r
            join cfurl_cache_receiver_data d on r.entry_ID = d.entry_ID
            where r.request_key like '%auction%'
               or r.request_key like '%match-count%'
               or r.request_key like '%match-product%'
            order by r.time_stamp desc
            limit 300
            """
        ).fetchall()
    finally:
        conn.close()

    base = db_path.parent / "fsCachedData"
    out: list[tuple[str, str | None]] = []
    for request_key, is_on_fs, receiver_data in rows:
        body: str | None = None
        if receiver_data is not None:
            if isinstance(receiver_data, bytes):
                receiver_text = receiver_data.decode("utf-8", errors="ignore")
            else:
                receiver_text = str(receiver_data)
            if is_on_fs:
                fs_path = base / receiver_text
                parsed = read_json_like_bytes(fs_path)
                if parsed is not None:
                    body = json.dumps(parsed, ensure_ascii=False)
            else:
                body = receiver_text
        out.append((request_key, body))
    return out


def scan_cache(keyword: str, db_path: Path | None) -> dict[str, Any]:
    if db_path is None:
        return {"cache_db": None, "plain_items": [], "encrypted_hits": 0, "matching_urls": []}

    plain_items: list[dict[str, Any]] = []
    encrypted_hits = 0
    matching_urls: list[str] = []

    for url, body in cache_records(db_path):
        searchable = f"{url}\n{body or ''}"
        if keyword.lower() not in searchable.lower():
            continue
        matching_urls.append(url)
        if body and re.search(r'"raw_data"\s*:', body):
            encrypted_hits += 1
            continue
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            continue
        for item in flatten_items(parsed):
            if text_contains_keyword(item, keyword):
                plain_items.append(summarize_item(item))

    return {
        "cache_db": str(db_path),
        "plain_items": plain_items,
        "encrypted_hits": encrypted_hits,
        "matching_urls": matching_urls[:20],
    }


def build_snapshot(keyword: str) -> dict[str, Any]:
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    snapshot: dict[str, Any] = {"keyword": keyword, "checked_at": checked_at}

    try:
        match_count = fetch_match_count(keyword)
        auction_count = int(match_count.get("auction_product_match_count") or 0)
        snapshot["match_count"] = match_count
        snapshot["has_auction"] = auction_count > 0
        snapshot["auction_count"] = auction_count
        snapshot["switch_game_key"] = match_count.get("switch_game_key")
        snapshot["switch_game_sub_key"] = match_count.get("switch_game_sub_key")
    except Exception as exc:
        snapshot["match_count_error"] = str(exc)
        snapshot["has_auction"] = None
        snapshot["auction_count"] = None

    cache = scan_cache(keyword, find_cache_db())
    snapshot["cache"] = cache
    if cache["plain_items"]:
        snapshot["price_source"] = "plain_local_cache"
        snapshot["items"] = cache["plain_items"]
    else:
        snapshot["price_source"] = "unavailable_encrypted_or_not_cached"
        snapshot["items"] = []
    return snapshot


def print_snapshot(snapshot: dict[str, Any]) -> None:
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor Jihuanshe auction count/cache for a card keyword.")
    parser.add_argument("keyword", help="Card code/name, e.g. SVP-098")
    parser.add_argument("--interval", type=int, default=60, help="Polling interval seconds; use 0 for one shot")
    parser.add_argument("--jsonl", default="", help="Optional path to append JSONL snapshots")
    args = parser.parse_args()

    previous_key = None
    while True:
        snapshot = build_snapshot(args.keyword)
        current_key = json.dumps(
            {
                "has_auction": snapshot.get("has_auction"),
                "auction_count": snapshot.get("auction_count"),
                "items": snapshot.get("items"),
                "price_source": snapshot.get("price_source"),
            },
            sort_keys=True,
            ensure_ascii=False,
        )

        if current_key != previous_key:
            print_snapshot(snapshot)
            sys.stdout.flush()
            previous_key = current_key

        if args.jsonl:
            with open(args.jsonl, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

        if args.interval <= 0:
            break
        time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
