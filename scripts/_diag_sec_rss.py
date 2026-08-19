#!/usr/bin/env python3
"""_diag_sec_rss.py — 一時的な調査用スクリプト（③ SEC RSS 0件問題の診断）。

本番パイプラインの一部ではない。2026-08-18のSECプレスリリース
（2026-76、暗号資産規則案）がなぜ公式RSSの対象日0件だったのかを
調べるため、フィードの実レスポンスを取得して以下を報告する：
- HTTPステータス、生の<item>件数
- 全<item>のtitle・pubDateの一覧
- pubDateの範囲（最古・最新）からローリングウィンドウ仮説を検証
- title中の "crypto" "digital asset" "2026-76" の有無
- https://www.sec.gov/about/rss-feeds のHTMLから他のRSSフィード候補を抽出

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import re
import sys
from xml.etree import ElementTree as ET

import requests

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
TIMEOUT_SEC = 20
CURRENT_FEED_URL = "https://www.sec.gov/news/pressreleases.rss"
RSS_FEEDS_PAGE_URL = "https://www.sec.gov/about/rss-feeds"
KEYWORDS = ["crypto", "digital asset", "2026-76"]


def diag_feed(url: str) -> None:
    print(f"=== フィード取得: {url} ===")
    try:
        resp = requests.get(url, timeout=TIMEOUT_SEC, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as e:
        print(f"取得失敗（例外）: {type(e).__name__}: {e}")
        return
    print(f"HTTPステータス: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type', '(none)')}")
    print(f"レスポンス本文バイト数: {len(resp.content)}")
    if resp.status_code != 200:
        print(f"本文冒頭500文字:\n{resp.text[:500]}")
        return

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"XML解析失敗: {e}")
        print(f"本文冒頭500文字:\n{resp.text[:500]}")
        return

    items = list(root.iter("item"))
    print(f"<item>件数（RAW_ITEM_LIMIT等の上限なし・全件）: {len(items)}")
    print()
    print("--- 全item一覧（title | pubDate | link） ---")
    pub_dates_raw = []
    for i, item in enumerate(items):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        pub_dates_raw.append(pub_date)
        hit = [k for k in KEYWORDS if k.lower() in title.lower()]
        marker = f"  <<< キーワード一致: {hit}" if hit else ""
        print(f"[{i}] {pub_date} | {title} | {link}{marker}")

    print()
    print("--- pubDate範囲（ローリングウィンドウ仮説の検証） ---")
    from email.utils import parsedate_to_datetime
    parsed = []
    for raw in pub_dates_raw:
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt is not None:
                parsed.append(dt)
        except (TypeError, ValueError, IndexError):
            continue
    if parsed:
        parsed.sort()
        print(f"最古のpubDate: {parsed[0].isoformat()}")
        print(f"最新のpubDate: {parsed[-1].isoformat()}")
        span = parsed[-1] - parsed[0]
        print(f"範囲の幅: {span}")
    else:
        print("pubDateを1件も解釈できませんでした。")

    print()
    print("--- タイトル中のキーワード一致まとめ ---")
    for kw in KEYWORDS:
        matches = [
            (i, (item.findtext("title") or "").strip())
            for i, item in enumerate(items)
            if kw.lower() in (item.findtext("title") or "").lower()
        ]
        print(f"'{kw}': {len(matches)}件一致 {matches if matches else ''}")


def diag_rss_feeds_page(url: str) -> None:
    print()
    print(f"=== RSSフィード一覧ページ取得: {url} ===")
    try:
        resp = requests.get(url, timeout=TIMEOUT_SEC, headers={"User-Agent": USER_AGENT})
    except requests.RequestException as e:
        print(f"取得失敗（例外）: {type(e).__name__}: {e}")
        return
    print(f"HTTPステータス: {resp.status_code}")
    if resp.status_code != 200:
        print(f"本文冒頭500文字:\n{resp.text[:500]}")
        return
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', resp.text)
    feed_like = sorted(set(
        h for h in hrefs
        if ".rss" in h.lower() or "/rss" in h.lower() or "feed" in h.lower()
    ))
    print(f"feedらしきhref件数: {len(feed_like)}")
    for h in feed_like:
        print(f"  {h}")


def main() -> None:
    diag_feed(CURRENT_FEED_URL)
    diag_rss_feeds_page(RSS_FEEDS_PAGE_URL)


if __name__ == "__main__":
    main()
    sys.exit(0)
