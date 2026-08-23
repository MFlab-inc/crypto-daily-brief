#!/usr/bin/env python3
"""_diag_abc_classification_verify.py — 一時的な調査用スクリプト。

v1.33（重要性判定と因果表現の分離）の効果を8/21・8/22の実データで検証する。
collect_news.collect_news()でその時点の生RSSを取得し、call_a・call_bを実行、
compose_post.compose()でバンドルを組み立て、verify_post.run_all()で機械監査する
（本番daily.yml等と同じ組み立て方だが、news_candidates.jsonの committed
スナップショットではなく、実行時点のライブRSS取得を使う）。

確認項目（オーナー指示）:
- 8/22: 対カナダ関税材料がB分類され主要なポイントに掲載されるか
  （そもそも候補として存在するかも含めて確認する — v1.31/v1.32の調査では
  現行フィードに8/22付の当該記事が見つかっていない。候補が無ければこの
  基準はそもそも検証不能であり、それをそのまま報告する）
- 掲載文に「暗号通貨価格への直接因果は未確認」等の限定表現が入っているか
- C18（断定表現）が引き続きPASSするか
- 8/21: 金融庁・日銀7件が引き続きC（不採用）のままか

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import compose_post  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

TARGETS = ["2026-08-21", "2026-08-22"]
TRIALS = 3
FSA_BOJ_NAMES = {"金融庁", "日本銀行"}


def _prev_date(target: str) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(target) - timedelta(days=1)).isoformat()


def _run_once(client, target: str, daily_data: dict, news_today: dict, news_yesterday: dict | None) -> dict:
    a = generate_post.call_a(client, daily_data, news_today, news_yesterday)
    b = generate_post.call_b(client, daily_data, a.data if a.ok else None)
    failed = (0 if a.ok else 1) + (0 if b.ok else 1)
    level = {0: "L0", 1: "L1", 2: "L2"}[failed]
    selected_today, _ = generate_post._select_candidates_for_call_a(news_today.get("candidates", []))
    return {
        "target_date_jst": target,
        "level": level,
        "call_a": a.to_dict(),
        "call_b": b.to_dict(),
        "news_source_status": news_today.get("source_status", {}),
        "news_candidate_count": len(selected_today),
        "total_usage": {"input_tokens": 0, "output_tokens": 0},
    }


def main() -> None:
    client = anthropic.Anthropic()
    news_by_date = {t: collect_news.collect_news(t) for t in TARGETS}

    for target in TARGETS:
        print(f"===== 対象日: {target} =====")
        cands = news_by_date[target].get("candidates", [])
        print(f"当日候補総数: {len(cands)}件")
        canada_like = [c for c in cands if "カナダ" in (c.get("title", "") + c.get("summary", ""))
                       or "Canada" in (c.get("title", "") + c.get("summary", ""))
                       or "tariff" in (c.get("title", "") + c.get("summary", "")).lower()
                       or "関税" in (c.get("title", "") + c.get("summary", ""))]
        print(f"カナダ/関税関連らしき候補: {len(canada_like)}件")
        for c in canada_like:
            print(f"  - source={c.get('source')!r} title={c.get('title')!r} published_at={c.get('published_at')!r}")
        print()

        daily_data = json.loads(open(f"outputs/{target}/daily_data.json", encoding="utf-8").read())
        news_today = news_by_date[target]
        news_yesterday = news_by_date.get(_prev_date(target))

        for trial in range(1, TRIALS + 1):
            print(f"--- 試行 {trial}/{TRIALS} ---")
            gen = _run_once(client, target, daily_data, news_today, news_yesterday)
            if gen["level"] != "L0":
                print(f"  call_a/call_b失敗: level={gen['level']}")
                print(f"  call_a: ok={gen['call_a']['ok']} error={gen['call_a'].get('error')}")
                print(f"  call_b: ok={gen['call_b']['ok']} error={gen['call_b'].get('error')}")
                continue

            a_data = gen["call_a"]["data"]
            print(f"  part1_headline: {a_data.get('part1_headline')!r}")
            print("  part1_points:")
            for p in a_data.get("part1_points", []):
                print(f"    - {p}")

            print("  audit_ledger:")
            for e in a_data.get("audit_ledger", []):
                marker = "★FSA/BOJ★" if e.get("source") in FSA_BOJ_NAMES else ""
                print(f"    {marker} decision={e.get('decision')!r} source={e.get('source')!r} title={e.get('title')!r}")
                print(f"        reason={e.get('reason')!r}")

            bundle = compose_post.compose(daily_data, gen)
            audit = verify_post.run_all(bundle, daily_data)
            print(f"  監査結果: FAIL={audit.failed}件")
            for c in audit.checks:
                if c["id"] in ("C18_causal_assertion", "C21_decision_tier_consistency", "C22_headline_tier1_basis"):
                    print(f"    {c['id']}: {c['result']} — {c['detail']}")
            print()
        print()


if __name__ == "__main__":
    main()
