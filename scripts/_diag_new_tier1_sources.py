#!/usr/bin/env python3
"""_diag_new_tier1_sources.py — 一時的な調査用スクリプト。

米財務省（home.treasury.gov）・USTR（ustr.gov）・ホワイトハウス
（whitehouse.gov）のRSSフィードURLを実測で特定する。サンドボックスからは
これらのドメインへ到達できない（egress遮断）ため、GitHub Actions
ランナー（フル到達性）上で実行する。

手順:
1. 各サイトのプレスリリース一覧ページのHTMLを取得し、
   <link rel="alternate" type="application/rss+xml"> タグを探す。
2. 見つからない場合、想定されるURLパターンを複数試し、
   HTTPステータス・Content-Typeを報告する。
3. 到達できたURLについては、実際にRSSとしてパースできるか
   （itemの有無・件数）も確認する。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import re
import sys

import requests

UA = "Mozilla/5.0 (compatible; crypto-daily-brief-research/1.0)"
TIMEOUT = 15


def _get(url: str) -> tuple[int | None, str | None, bytes | None]:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True)
        return r.status_code, r.headers.get("Content-Type", ""), r.content
    except Exception as e:  # noqa: BLE001
        print(f"  例外: {type(e).__name__}: {e}")
        return None, None, None


def _find_rss_links_in_html(html: bytes) -> list[str]:
    text = html.decode("utf-8", errors="ignore")
    links = re.findall(
        r'<link[^>]+type=["\']application/rss\+xml["\'][^>]*href=["\']([^"\']+)["\']', text, re.IGNORECASE)
    links += re.findall(
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]*type=["\']application/rss\+xml["\']', text, re.IGNORECASE)
    # 素朴なフィード/RSSっぽいhrefも収集（重複除去は後段）
    links += re.findall(r'href=["\']([^"\']*(?:rss|feed)[^"\']*\.xml)["\']', text, re.IGNORECASE)
    return sorted(set(links))


def check_html_page(label: str, url: str) -> None:
    print(f"--- {label}: HTMLページからRSSリンクを探索 ---")
    print(f"URL: {url}")
    status, ctype, body = _get(url)
    print(f"status={status} content-type={ctype}")
    if status == 200 and body:
        links = _find_rss_links_in_html(body)
        print(f"検出したRSSらしきリンク: {links}")
    print()


def check_candidate_feed(label: str, url: str) -> None:
    print(f"--- {label}: 候補URLを直接検証 ---")
    print(f"URL: {url}")
    status, ctype, body = _get(url)
    print(f"status={status} content-type={ctype}")
    if status == 200 and body:
        text = body.decode("utf-8", errors="ignore")
        item_count = len(re.findall(r"<item[ >]", text, re.IGNORECASE))
        entry_count = len(re.findall(r"<entry[ >]", text, re.IGNORECASE))
        is_xml = text.strip().startswith("<?xml") or "<rss" in text[:2000].lower() or "<feed" in text[:2000].lower()
        print(f"XML形式らしい={is_xml} item数={item_count} entry数={entry_count}")
        print(f"冒頭300字: {text[:300]!r}")
    print()


def main() -> None:
    # 1) プレスリリース一覧ページ本体からRSSリンクタグを探す
    check_html_page("米財務省", "https://home.treasury.gov/news/press-releases")
    check_html_page("USTR", "https://ustr.gov/about-us/policy-offices/press-office/press-releases")
    check_html_page("ホワイトハウス（トップ）", "https://www.whitehouse.gov/")

    # 2) 想定されるURLパターンを直接検証
    treasury_candidates = [
        "https://home.treasury.gov/rss",
        "https://home.treasury.gov/rss/press-releases",
        "https://home.treasury.gov/system/files/rss/press-releases.xml",
        "https://home.treasury.gov/news/press-releases/feed",
        "https://home.treasury.gov/feed",
        "https://home.treasury.gov/rss.xml",
    ]
    for u in treasury_candidates:
        check_candidate_feed("米財務省候補", u)

    ustr_candidates = [
        "https://ustr.gov/rss.xml",
        "https://ustr.gov/feed",
        "https://ustr.gov/about-us/policy-offices/press-office/press-releases/feed",
        "https://ustr.gov/rss/press-releases",
        "https://ustr.gov/news-and-events/feed",
    ]
    for u in ustr_candidates:
        check_candidate_feed("USTR候補", u)

    whitehouse_candidates = [
        "https://www.whitehouse.gov/feed/",
        "https://www.whitehouse.gov/rss/",
        "https://www.whitehouse.gov/news/feed/",
        "https://www.whitehouse.gov/briefing-room/feed/",
        "https://www.whitehouse.gov/presidential-actions/feed/",
        "https://www.whitehouse.gov/rss.xml",
    ]
    for u in whitehouse_candidates:
        check_candidate_feed("ホワイトハウス候補", u)


if __name__ == "__main__":
    sys.exit(main() or 0)
