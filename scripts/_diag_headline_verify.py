#!/usr/bin/env python3
"""_diag_headline_verify.py — 一時的な調査用スクリプト。

v1.30「ヘッドラインの判定手順」追加の効果を、2026-08-21・2026-08-22の
実データでcall_Aを直接呼び出して検証する。verify_post.pyのC21・C22
ロジックを再利用し、以下を確認する。
- 8/21: C22がPASS（tier1採用材料が無いためpart1_headlineが定型文）し、
  かつ独立2ソース材料（Laser Digital）はpart1_pointsに引き続き残ること
- 8/22: 引き続き定型文のままであること

daily_data.jsonはリポジトリにコミット済みのものをそのまま使う。news候補は
RSSのライブ取得のため、当時の候補集合と完全一致する保証はない。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402
from verify_data import Audit  # noqa: E402

TARGETS = ["2026-08-21", "2026-08-22"]
ATTEMPTS_PER_TARGET = 3


def _run_for(target: str, client, tier_map: dict[str, int]) -> None:
    print(f"===== 対象日: {target} =====")
    daily_data_path = f"outputs/{target}/daily_data.json"
    daily_data = json.loads(open(daily_data_path, encoding="utf-8").read())
    news_today = collect_news.collect_news(target)
    cands = news_today.get("candidates", [])
    tier_counts: dict[int, int] = {}
    for c in cands:
        t = c.get("tier")
        tier_counts[t] = tier_counts.get(t, 0) + 1
    print(f"候補（ライブ取得）: 合計{len(cands)}件 tier別内訳={tier_counts}")

    for i in range(1, ATTEMPTS_PER_TARGET + 1):
        print(f"--- 試行 {i} ---")
        outcome = generate_post.call_a(client, daily_data, news_today, None)
        print(f"call_A: {'OK' if outcome.ok else 'FAILED'}（{outcome.attempts}回試行）")
        if not outcome.ok:
            print(f"  エラー: {outcome.error}")
            print()
            continue
        data = outcome.data
        headline = data.get("part1_headline", "")
        is_fixed_headline = headline == generate_post.FIXED_HEADLINE
        print(f"part1_headline: {'定型文' if is_fixed_headline else '実文言'}")
        print(f"  内容: {headline!r}")
        points = data.get("part1_points", [])
        print(f"part1_points: {len(points)}件")
        for p in points:
            print(f"  - {p}")
        ledger = data.get("audit_ledger", [])
        dual = [e for e in ledger if e.get("decision") == "採用（独立2ソース）"]
        print(f"audit_ledger: {len(ledger)}件（うち独立2ソース採用: {len(dual)}件）")
        for e in dual:
            print(f"  独立2ソース採用: source={e.get('source')!r} title={e.get('title')!r}")

        au = Audit()
        verify_post.check_c21(au, "L0", ledger, len(ledger), tier_map)
        verify_post.check_c22(au, headline, ledger, tier_map)
        for check in au.checks:
            print(f"{check['id']}: {check['result']}  ({check['detail']})")
        print()


def main() -> None:
    client = anthropic.Anthropic()
    tier_map = verify_post._load_source_tier_map()
    for target in TARGETS:
        try:
            _run_for(target, client, tier_map)
        except Exception as e:  # noqa: BLE001
            print(f"{target}で例外: {type(e).__name__}: {e}")
            print()


if __name__ == "__main__":
    main()
