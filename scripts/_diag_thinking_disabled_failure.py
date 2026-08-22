#!/usr/bin/env python3
"""_diag_thinking_disabled_failure.py — 一時的な調査用スクリプト（v2）。

v1（初回）の欠陥: 対象日を `date.today() - timedelta(days=1)` で動的に
算出していたため、本スクリプトをUTCで動くGitHub Actionsランナー上で
2026-08-22に実行した結果、実際には2026-08-21のデータで検証してしまい、
本来検証すべき2026-08-20の失敗事象を一度も再現テストしていなかった
（2026-08-21は本番のcall_Aが1回試行で成功済みのデータであり、
このデータでの成功は何も証明しない）。

v2では対象日を "2026-08-20" に固定する。daily_data.jsonはリポジトリに
コミット済みのoutputs/2026-08-20/daily_data.jsonをそのまま使う。ただし
news候補はRSSのライブ取得のため、2026-08-20時点でRSSに存在した候補と
本スクリプト実行時点（2026-08-22以降）で取得できる候補が同一である保証は
ない（フィードの保持件数が限られるため）。この差異は結果とあわせて明記する。

失敗の再現有無によらず、raw_textは全文を出力する（v1は先頭200字のみで、
実際に失敗した際の生テキスト全体を一度も確認できていなかった）。

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

TARGET = "2026-08-20"


def _try_once(client, user_content: str, attempt_no: int) -> None:
    print(f"--- 試行 {attempt_no} ---")
    response = client.messages.create(
        model=generate_post.MODEL,
        max_tokens=8000,
        system=generate_post.SYSTEM_A,
        messages=[{"role": "user", "content": user_content}],
        thinking={"type": "disabled"},
    )
    usage = response.usage
    print(f"stop_reason: {response.stop_reason}, output_tokens: {usage.output_tokens}")
    raw_text = generate_post._extract_text(response)
    stripped = generate_post._strip_code_fence(raw_text)
    print(f"raw_textの長さ: {len(raw_text)}, strippedの長さ: {len(stripped)}")
    print("=== raw_text 全文（フェンス除去前） ===")
    print(raw_text)
    print("=== raw_text 全文ここまで ===")
    try:
        data = json.loads(stripped)
        missing = [k for k in generate_post.REQUIRED_KEYS_A if k not in data]
        print(f"JSON解析: 成功。必須キー欠落: {missing}")
    except json.JSONDecodeError as e:
        print(f"JSON解析: 失敗。{type(e).__name__}: {e}")
    print()


def main() -> None:
    print(f"対象日（固定）: {TARGET}")
    news_today = collect_news.collect_news(TARGET)
    tier_counts: dict[int, int] = {}
    for c in news_today:
        t = c.get("tier")
        tier_counts[t] = tier_counts.get(t, 0) + 1
    print(f"候補件数（本スクリプト実行時点でのライブ取得・8/20時点と同一である保証なし）: "
          f"合計{len(news_today)}件 tier別内訳={tier_counts}")
    daily_data_path = f"outputs/{TARGET}/daily_data.json"
    if os.path.exists(daily_data_path):
        daily_data = json.loads(open(daily_data_path, encoding="utf-8").read())
        print(f"daily_data.json: {daily_data_path}（コミット済み・8/20当時のもの）を使用")
    else:
        daily_data = {"target_date_jst": TARGET}
        print(f"daily_data.json: {daily_data_path} が見つからないため簡易データで代替")
    user_content, stats = generate_post._build_call_a_user_content(daily_data, news_today, None)
    print(f"候補統計: {stats}")
    print(f"user_contentの長さ（文字数）: {len(user_content)}")
    print()

    client = anthropic.Anthropic()
    for i in range(1, 6):
        try:
            _try_once(client, user_content, i)
        except Exception as e:  # noqa: BLE001
            print(f"試行{i}で例外: {type(e).__name__}: {e}")
            print()


if __name__ == "__main__":
    main()
