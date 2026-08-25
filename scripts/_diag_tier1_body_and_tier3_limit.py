#!/usr/bin/env python3
"""_diag_tier1_body_and_tier3_limit.py — 一時的な調査用スクリプト。

8/25実データで判明した2つの構造的問題を検証する（オーナー指示）。

【問題1】tier1候補のRSS summaryが空/薄く、波及経路は説明できても
本文に書ける実質的な内容が無いまま不採用になる。対応案（tier1候補の
リンク先本文を取得して要約に加える）の実現可能性を、実際に8/25で
不採用になった3件のURL（FRB・日銀・ホワイトハウス）で検証する。
generic抽出（<script>/<style>/<nav>/<header>/<footer>除去→
<article>/<main>があれば優先的に使用→全文タグ除去→2000字切り詰め）を
試し、抽出結果が本文として使える品質かを目視確認する。

【問題2】TIER3_CANDIDATE_LIMIT=10が独立2ソース規定を満たすペアを
分断している。8/25の実データ（tier3候補44件）でLIMITを20へ引き上げた
場合の実際のcall_A出力トークン数を測定する。あわせて、上限を10→20へ
引き上げることで新たに候補集合へ入るtier3候補と、それが既存の候補と
タイトル類似度で同一事実を報じるペアになり得るかを機械的に確認する。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import generate_post  # noqa: E402

TARGET = "2026-08-25"
BODY_CHAR_LIMIT = 2000

TIER1_TEST_URLS = [
    ("FRB", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260825a.htm"),
    ("日本銀行（コアCPI）", "http://www.boj.or.jp/research/research_data/cpi/index.htm"),
    ("ホワイトハウス（カナダ関税）",
     "https://www.whitehouse.gov/releases/2026/08/president-trump-is-finally-ending-canadas-free-ride/"),
]

_STRIP_BLOCK_RE = re.compile(
    r"<(script|style|nav|header|footer)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_ARTICLE_RE = re.compile(r"<(article|main)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _extract_body(html: str) -> tuple[str, str]:
    """(抽出方法, 抽出結果) を返す。抽出方法は 'article_or_main' か 'full_body'。"""
    cleaned = _STRIP_BLOCK_RE.sub(" ", html)
    m = _ARTICLE_RE.search(cleaned)
    if m and len(_TAG_RE.sub(" ", m.group(2))) > 200:
        method = "article_or_main"
        raw = m.group(2)
    else:
        method = "full_body"
        raw = cleaned
    text = _TAG_RE.sub(" ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return method, text[:BODY_CHAR_LIMIT]


def problem1() -> None:
    print("========== 問題1: tier1本文取得の実現可能性 ==========")
    for name, url in TIER1_TEST_URLS:
        print(f"----- {name}: {url} -----")
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": collect_news.USER_AGENT})
            print(f"  HTTP {resp.status_code}  取得サイズ={len(resp.text)}文字")
            if resp.status_code != 200:
                print()
                continue
            method, extracted = _extract_body(resp.text)
            print(f"  抽出方法: {method}  抽出後文字数: {len(extracted)}")
            print(f"  抽出結果（先頭800字）:")
            print(f"  {extracted[:800]!r}")
        except requests.RequestException as e:
            print(f"  取得失敗: {type(e).__name__}: {e}")
        print()


def problem2() -> None:
    print("========== 問題2: TIER3_CANDIDATE_LIMIT引き上げの影響測定 ==========")
    news = collect_news.collect_news(TARGET)
    all_cands = news.get("candidates", [])
    tier3 = [c for c in all_cands if c.get("tier") == 3]
    print(f"当日tier3候補総数: {len(tier3)}件")

    def pub_dt(c):
        return collect_news.parse_pubdate_jst(c.get("published_at", ""))

    tier3_sorted = sorted(tier3, key=lambda c: pub_dt(c) or __import__("datetime").datetime.min.replace(
        tzinfo=collect_news.JST), reverse=True)
    top10 = tier3_sorted[:10]
    top20 = tier3_sorted[:20]
    newly_included = [c for c in top20 if c not in top10]
    print(f"上限10で選定される候補: {len(top10)}件 / 上限20で選定される候補: {len(top20)}件")
    print(f"上限20への引き上げで新たに含まれる候補: {len(newly_included)}件")

    # 新たに含まれる候補が、既存の上位10件（または他の新規候補）とタイトル類似度で
    # 同一事実を報じるペアになり得るかを機械的に確認する（difflib.SequenceMatcher）。
    print("新規候補とtop20内の他候補とのタイトル類似度（0.6以上を類似ペア候補として表示）:")
    found_pair = False
    for nc in newly_included:
        for other in top20:
            if other is nc or other.get("source") == nc.get("source"):
                continue
            ratio = difflib.SequenceMatcher(None, nc.get("title", "").lower(), other.get("title", "").lower()).ratio()
            if ratio >= 0.6:
                found_pair = True
                print(f"  類似度{ratio:.2f}: [{nc.get('source')}] {nc.get('title')!r}")
                print(f"              <-> [{other.get('source')}] {other.get('title')!r}")
    if not found_pair:
        print("  類似度0.6以上のペアは見つからなかった（本日のデータでは独立2ソース分断の直接的救済例なし）")
    print()

    daily_data = json.loads(open(f"outputs/{TARGET}/daily_data.json", encoding="utf-8").read())
    client = anthropic.Anthropic()

    orig_limit = generate_post.TIER3_CANDIDATE_LIMIT
    for limit in (10, 20):
        generate_post.TIER3_CANDIDATE_LIMIT = limit
        outcome = generate_post.call_a(client, daily_data, news, None)
        print(f"--- TIER3_CANDIDATE_LIMIT={limit} ---")
        print(f"call_A: {'OK' if outcome.ok else 'FAILED'}（{outcome.attempts}回試行）")
        if outcome.ok:
            print(f"  usage: input={outcome.usage.get('input_tokens')} output={outcome.usage.get('output_tokens')}")
            print(f"  audit_ledger件数: {len(outcome.data.get('audit_ledger', []))}")
        else:
            print(f"  エラー: {outcome.error}")
        print()
    generate_post.TIER3_CANDIDATE_LIMIT = orig_limit


def main() -> None:
    problem1()
    problem2()


if __name__ == "__main__":
    main()
