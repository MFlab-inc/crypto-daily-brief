#!/usr/bin/env python3
"""_diag_fix12_verify.py — 一時的な調査用スクリプト。

v1.29（オーナー診断・修正1・2）の効果を、2026-08-21・2026-08-22の
実データでcall_Aを直接呼び出して検証する。修正1（情報源規律を項目数より
優先する旨の明記）・修正2（候補ごとの掲載可否ラベル付与）が、
tier3単独ソースの誤ったplain"採用"を防げているかを、verify_post.py の
C21ロジックをそのまま再利用して判定する。

daily_data.jsonはリポジトリにコミット済みのものをそのまま使う。ただし
news候補はRSSのライブ取得のため、当時の候補集合と完全一致する保証は
ない（フィードの保持件数が限られるため）。

call_Bは今回の修正がcall_A側のみのため呼び出さない（コスト削減）。

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
    print(f"候補（本スクリプト実行時点でのライブ取得）: 合計{len(cands)}件 tier別内訳={tier_counts}")

    outcome = generate_post.call_a(client, daily_data, news_today, None)
    print(f"call_A: {'OK' if outcome.ok else 'FAILED'}（{outcome.attempts}回試行）")
    if not outcome.ok:
        print(f"  エラー: {outcome.error}")
        print()
        return

    data = outcome.data
    points = data.get("part1_points", [])
    print(f"part1_points: {len(points)}件")
    for p in points:
        print(f"  - {p}")
    ledger = data.get("audit_ledger", [])
    print(f"audit_ledger: {len(ledger)}件")
    for i, e in enumerate(ledger):
        print(f"  [{i}] decision={e.get('decision')!r} source={e.get('source')!r} title={e.get('title')!r}")

    au = Audit()
    verify_post.check_c21(au, "L0", ledger, len(ledger), tier_map)
    c21 = au.checks[0]
    print(f"C21判定: {c21['result']}")
    print(f"  detail: {c21['detail']}")
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
