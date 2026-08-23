#!/usr/bin/env python3
"""_diag_tier3_source_discovery.py — 一時的な調査用スクリプト。

Bloomberg日本語版・日本経済新聞・時事通信の公式RSS URLを特定するための調査。
サンドボックスはjiji.com・nikkei.com・bloomberg.co.jpいずれもegress遮断のため
到達性・実在URLの確認ができず、GitHub Actionsランナー（ネットワーク制限なし）
から実行する。

(1) 各サイトの主要ページのHTMLを取得し、RSS自動検出タグ
    （<link type="application/rss+xml">等）と、本文中の.rdf/.xml/.rss類似の
    URLを抽出する。
(2) 時事通信のRSS利用案内ページ（実在確認済み・RSS1.0/2.0/Atom提供を明記）の
    本文をそのまま出力し、記載されている実際のフィードURLを読み取れるように
    する。
(3) 併せて、いくつかの推測URLをcollect_news.fetch_rss()で直接検証する。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
import collect_news  # noqa: E402

PAGES_TO_SCAN = [
    ("Nikkei トップ", "https://www.nikkei.com/"),
    ("Nikkei マーケット", "https://www.nikkei.com/markets/"),
    ("Nikkei 国際", "https://www.nikkei.com/world/"),
    ("Bloomberg Japan トップ", "https://www.bloomberg.co.jp/"),
    ("Jiji RSS案内", "https://www.jiji.com/policy/rss.html"),
    ("Jiji トップ", "https://www.jiji.com/"),
]

LINK_TAG_RE = re.compile(
    r'<link[^>]+type=["\'](?:application/rss\+xml|application/atom\+xml)["\'][^>]*>',
    re.IGNORECASE,
)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
URLISH_RE = re.compile(r'https?://[^\s"\'<>)]+\.(?:rdf|xml|rss)[^\s"\'<>)]*', re.IGNORECASE)
# ファイル拡張子を問わず、RSS一覧・案内ページへのリンク（例: /rss/）も
# 拾うための広めのフォールバック（URLISH_REは.rdf/.xml/.rss拡張子必須のため
# 一覧ページ自体のリンクを見落とす）。
RSS_HREF_RE = re.compile(r'href=["\']([^"\']*rss[^"\']*)["\']', re.IGNORECASE)


def _fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": collect_news.USER_AGENT})
        print(f"  HTTP {resp.status_code}")
        if resp.status_code != 200:
            return None
        return resp.text
    except requests.RequestException as e:
        print(f"  取得失敗: {type(e).__name__}: {e}")
        return None


def main() -> None:
    for label, url in PAGES_TO_SCAN:
        print(f"===== {label} ({url}) =====")
        html = _fetch(url)
        if html is None:
            print()
            continue
        print(f"  取得成功: {len(html)}文字")
        tags = LINK_TAG_RE.findall(html)
        if tags:
            print(f"  RSS自動検出タグ: {len(tags)}件")
            for t in tags:
                m = HREF_RE.search(t)
                print(f"    {m.group(1) if m else t}")
        else:
            print("  RSS自動検出タグ: 0件")
        urlish = sorted(set(URLISH_RE.findall(html)))
        if urlish:
            print(f"  本文中の.rdf/.xml/.rss類似URL: {len(urlish)}件")
            for u in urlish[:30]:
                print(f"    {u}")
        rss_hrefs = sorted(set(RSS_HREF_RE.findall(html)))
        if rss_hrefs:
            print(f"  'rss'を含むhref（拡張子問わず・一覧ページ探索用）: {len(rss_hrefs)}件")
            for u in rss_hrefs[:30]:
                print(f"    {u}")
        if url == "https://www.jiji.com/policy/rss.html":
            print("  --- ページ本文（案内ページのため全文） ---")
            text_only = re.sub(r"<[^>]+>", "\n", html)
            text_only = re.sub(r"\n{2,}", "\n", text_only).strip()
            print(text_only[:4000])
        print()

    print("===== 推測URLの直接検証（collect_news.fetch_rss） =====")
    guesses = [
        "https://www.nikkei.com/rss/index/economy.rdf",
        "https://www.nikkei.com/rss/index/tstock.rdf",
        "https://www.nikkei.com/rss/index/kaigai.rdf",
        "https://www.nikkei.com/rss/marketscat.rdf",
        "https://www.nikkei.com/rss/",
        "https://www.bloomberg.co.jp/feed",
        "https://www.bloomberg.co.jp/rss",
        "https://www.bloomberg.co.jp/feeds/site.xml",
        "https://www.jiji.com/rss/ranking.rdf",
        "https://www.jiji.com/rss/economy.rdf",
        "https://www.jiji.com/rss/sp.rdf",
    ]
    for url in guesses:
        status, items, detail = collect_news.fetch_rss(url)
        print(f"  {url}: status={status} detail={detail} 件数={len(items) if items else 0}")

    print()
    print("===== ranking.rdfが件数0だった件の切り分け（RSS1.0/RDF名前空間の疑い） =====")
    _probe_ranking_rdf()


def _probe_ranking_rdf() -> None:
    """jiji.com/rss/ranking.rdfはHTTP 200・整形式XMLだがfetch_rss()は0件を
    返した。RSS 1.0（RDF）はitem要素が名前空間付き
    （{http://purl.org/rss/1.0/}item等）になるため、fetch_rss()の
    root.iter("item")（名前空間なし）が一致しない可能性を切り分ける。
    """
    from xml.etree import ElementTree as ET

    url = "https://www.jiji.com/rss/ranking.rdf"
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": collect_news.USER_AGENT})
    except requests.RequestException as e:
        print(f"  取得失敗: {type(e).__name__}: {e}")
        return
    print(f"  HTTP {resp.status_code}")
    print("  先頭1500文字:")
    print(resp.text[:1500])
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        print(f"  XML解析失敗: {e}")
        return
    bare = list(root.iter("item"))
    ns_agnostic = [el for el in root.iter() if el.tag.split("}")[-1] == "item"]
    print(f"  root.iter('item')（名前空間なし・fetch_rss()と同じ）: {len(bare)}件")
    print(f"  ローカル名一致（名前空間非依存）: {len(ns_agnostic)}件")
    if ns_agnostic:
        el = ns_agnostic[0]
        print(f"  1件目のタグ名: {el.tag}")
        for child in list(el)[:6]:
            print(f"    {child.tag} = {(child.text or '')[:80]!r}")


if __name__ == "__main__":
    main()
