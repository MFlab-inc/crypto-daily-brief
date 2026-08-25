#!/usr/bin/env python3
"""_diag_followup_body_and_pairing.py — 一時的な調査用スクリプト（1回目診断の追試）。

1回目の診断（_diag_tier1_body_and_tier3_limit.py・削除済み）で判明した
2点を掘り下げる。

【1】FRBの本文抽出が失敗していた（<article>/<main>が見つからず
    full_bodyへフォールバックし、ナビゲーション文言しか取れなかった）。
    regexによる<main>検出が入れ子構造で失敗している可能性を疑い、
    標準ライブラリhtml.parser.HTMLParserでDOMを正しく辿る方式を試す
    （新規の重い依存を増やさない）。

【2】1回目のtier3ペア検出（difflib.SequenceMatcher・閾値0.6）は、
    既知の正例（8/24のCoinbase独立2ソース成立ペア）でも0.53しか
    出ず閾値未達だったことが判明し、測定方法に誤りがあった
    （閾値が厳しすぎて偽陰性を生んでいた）。単語集合のoverlap係数
    （交差 / 小さい方の集合サイズ）で再計測する（同ペアで0.45相当）。
    8/25の実データ全44件のtier3候補について、异なるソース間で
    overlap係数0.4以上のペアをすべて検出し、それぞれのペアが
    現在の順位で何位・何位にあり、上限をいくつまで上げれば両方とも
    候補集合に入るかを機械的に確認する。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import os
import re
import sys
from html.parser import HTMLParser

import requests

sys.path.insert(0, os.path.dirname(__file__))
import collect_news  # noqa: E402

BODY_CHAR_LIMIT = 2000
TARGET = "2026-08-25"

TIER1_TEST_URLS = [
    ("FRB", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260825a.htm"),
    ("日本銀行（コアCPI）", "http://www.boj.or.jp/research/research_data/cpi/index.htm"),
    ("ホワイトハウス（カナダ関税）",
     "https://www.whitehouse.gov/releases/2026/08/president-trump-is-finally-ending-canadas-free-ride/"),
]

_SKIP_TAGS = {"script", "style", "nav", "header", "footer"}
_MAIN_TAGS = {"main", "article"}


class _MainExtractor(HTMLParser):
    """<main>/<article>要素の直下テキストのみを抽出する（入れ子は正しく処理）。
    見つからない場合はbody全体のテキスト（nav/header/footer/script/style除く）に
    フォールバックする。
    """

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._main_depth = 0
        self.main_chunks: list[str] = []
        self.body_chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag in _MAIN_TAGS:
            self._main_depth += 1

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in _MAIN_TAGS and self._main_depth > 0:
            self._main_depth -= 1

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        if self._main_depth > 0:
            self.main_chunks.append(text)
        self.body_chunks.append(text)


def _extract_body_v2(html: str) -> tuple[str, str]:
    parser = _MainExtractor()
    try:
        parser.feed(html)
    except Exception as e:  # noqa: BLE001 — 調査用、失敗も記録すればよい
        return "parse_error", f"{type(e).__name__}: {e}"
    if parser.main_chunks and sum(len(c) for c in parser.main_chunks) > 200:
        method = "main_or_article(HTMLParser)"
        text = " ".join(parser.main_chunks)
    else:
        method = "full_body(HTMLParser)"
        text = " ".join(parser.body_chunks)
    text = re.sub(r"\s+", " ", text).strip()
    return method, text[:BODY_CHAR_LIMIT]


def problem1_retry() -> None:
    print("========== 問題1追試: html.parser.HTMLParserによる本文抽出 ==========")
    for name, url in TIER1_TEST_URLS:
        print(f"----- {name}: {url} -----")
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": collect_news.USER_AGENT})
            if resp.status_code != 200:
                print(f"  HTTP {resp.status_code}")
                print()
                continue
            method, extracted = _extract_body_v2(resp.text)
            print(f"  抽出方法: {method}  抽出後文字数: {len(extracted)}")
            print(f"  抽出結果（先頭600字）:")
            print(f"  {extracted[:600]!r}")
        except requests.RequestException as e:
            print(f"  取得失敗: {type(e).__name__}: {e}")
        print()


def _tokset(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def problem2_pairing() -> None:
    print("========== 問題2追試: overlap係数によるtier3ペア検出（全44件） ==========")
    news = collect_news.collect_news(TARGET)
    tier3 = [c for c in news.get("candidates", []) if c.get("tier") == 3]

    def pub_dt(c):
        return collect_news.parse_pubdate_jst(c.get("published_at", ""))

    from datetime import datetime
    tier3_sorted = sorted(
        tier3, key=lambda c: pub_dt(c) or datetime.min.replace(tzinfo=collect_news.JST), reverse=True)
    print(f"tier3候補総数: {len(tier3_sorted)}件（新しい順に0始まりの順位を付与）")

    toksets = [_tokset(c.get("title", "")) for c in tier3_sorted]
    THRESHOLD = 0.4
    pairs_found = []
    for i in range(len(tier3_sorted)):
        for j in range(i + 1, len(tier3_sorted)):
            if tier3_sorted[i].get("source") == tier3_sorted[j].get("source"):
                continue
            ov = _overlap(toksets[i], toksets[j])
            if ov >= THRESHOLD:
                pairs_found.append((i, j, ov))

    print(f"overlap係数{THRESHOLD}以上・異なるソース間のペア: {len(pairs_found)}組")
    for i, j, ov in pairs_found:
        a, b = tier3_sorted[i], tier3_sorted[j]
        rescue_limit = max(i, j) + 1
        print(f"  順位{i}・順位{j}（overlap={ov:.2f}） — 両方を候補集合に入れるにはLIMIT>={rescue_limit}が必要")
        print(f"    [{a.get('source')}] {a.get('title')!r}")
        print(f"    [{b.get('source')}] {b.get('title')!r}")
    if not pairs_found:
        print("  ペアなし")


def main() -> None:
    problem1_retry()
    problem2_pairing()


if __name__ == "__main__":
    main()
