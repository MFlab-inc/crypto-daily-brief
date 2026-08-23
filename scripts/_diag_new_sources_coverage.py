#!/usr/bin/env python3
"""_diag_new_sources_coverage.py — 一時的な調査用スクリプト。

v1.31で追加した米財務省・USTR・ホワイトハウス（2本）が、2026-08-20
（米財務省の長期債買入れ拡大が材料になった日）・2026-08-22（対カナダ
関税措置の日）の実データで、対象材料をtier1候補として拾えるかを確認する。
拾えた場合は、その候補がcall_Aのヘッドライン・主要なポイントへ実際に
反映されるかも確認する（call_Bは今回の検証対象外のため呼ばない）。

daily_data.jsonはリポジトリにコミット済みのものをそのまま使う。news候補は
RSSのライブ取得のため、当時の候補集合と完全一致する保証はない（フィードの
保持件数が限られるため、8/20分は8/22分より欠落しやすい）。

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

TARGETS = ["2026-08-20", "2026-08-22"]
NEW_SOURCE_NAMES = {"米財務省", "USTR", "ホワイトハウス", "ホワイトハウス（大統領令等）"}


def _check_candidates(target: str) -> dict:
    print(f"===== 対象日: {target} =====")
    news_today = collect_news.collect_news(target)
    for name, status in news_today.get("source_status", {}).items():
        if name in NEW_SOURCE_NAMES:
            print(f"  {name}: {status}")
    cands = news_today.get("candidates", [])
    new_source_cands = [c for c in cands if c.get("source") in NEW_SOURCE_NAMES]
    print(f"新規4情報源からの対象日候補: {len(new_source_cands)}件")
    for c in new_source_cands:
        print(f"  - source={c.get('source')!r} title={c.get('title')!r}")
        print(f"    summary={c.get('summary', '')[:200]!r}")
    print()
    return news_today


def main() -> None:
    client = anthropic.Anthropic()
    for target in TARGETS:
        news_today = _check_candidates(target)
        new_source_cands = [c for c in news_today.get("candidates", []) if c.get("source") in NEW_SOURCE_NAMES]
        if not new_source_cands:
            print(f"{target}: 新規情報源からの候補が0件のため、call_Aでの反映確認はスキップします。")
            print()
            continue
        daily_data_path = f"outputs/{target}/daily_data.json"
        daily_data = json.loads(open(daily_data_path, encoding="utf-8").read())
        print(f"--- {target}: call_Aでの反映確認 ---")
        outcome = generate_post.call_a(client, daily_data, news_today, None)
        print(f"call_A: {'OK' if outcome.ok else 'FAILED'}（{outcome.attempts}回試行）")
        if not outcome.ok:
            print(f"  エラー: {outcome.error}")
            print()
            continue
        data = outcome.data
        print(f"part1_headline: {data.get('part1_headline')!r}")
        print("part1_points:")
        for p in data.get("part1_points", []):
            print(f"  - {p}")
        ledger = data.get("audit_ledger", [])
        for e in ledger:
            if e.get("source") in NEW_SOURCE_NAMES:
                print(f"  audit_ledger[新規情報源]: decision={e.get('decision')!r} "
                      f"source={e.get('source')!r} title={e.get('title')!r} reason={e.get('reason')!r}")
        print()


if __name__ == "__main__":
    main()
