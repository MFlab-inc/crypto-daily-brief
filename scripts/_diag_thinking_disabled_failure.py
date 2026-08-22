#!/usr/bin/env python3
"""_diag_thinking_disabled_failure.py — 一時的な調査用スクリプト。

v1.28（thinking無効化）実装後の実運用ディスパッチ（2026-08-20）で、
call_Aが3回とも "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"
で失敗した事象の原因切り分け。thinking無効化自体は事前の診断で有効性を
確認済みだが、このエラーは「テキストの先頭が有効なJSON開始文字でない」
ことを意味し、_strip_code_fence()がコードフェンス直前の前置き文（プリアンブル）
を想定していないために取りこぼしている可能性を検証する。

本番と同一のcollect_news.py・generate_post.pyのプロンプト構築ロジックを
再利用し、実際のRSS候補データに対しthinking無効化・max_tokens=8000
（本番同一）でcall_Aを複数回呼び出し、失敗時は生テキストの冒頭200字と
エラー位置を出力する。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import generate_post  # noqa: E402


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
    print(f"raw_text冒頭200字（フェンス除去前）: {raw_text[:200]!r}")
    print(f"stripped冒頭100字（フェンス除去後）: {stripped[:100]!r}")
    try:
        data = json.loads(stripped)
        missing = [k for k in generate_post.REQUIRED_KEYS_A if k not in data]
        print(f"JSON解析: 成功。必須キー欠落: {missing}")
    except json.JSONDecodeError as e:
        print(f"JSON解析: 失敗。{type(e).__name__}: {e}")
        print(f"raw_textの長さ: {len(raw_text)}, strippedの長さ: {len(stripped)}")
    print()


def main() -> None:
    target = (date.today() - timedelta(days=1)).isoformat()
    print(f"対象日: {target}")
    news_today = collect_news.collect_news(target)
    daily_data_path = f"outputs/{target}/daily_data.json"
    if os.path.exists(daily_data_path):
        daily_data = json.loads(open(daily_data_path, encoding="utf-8").read())
    else:
        daily_data = {"target_date_jst": target}
    user_content, stats = generate_post._build_call_a_user_content(daily_data, news_today, None)
    print(f"候補統計: {stats}")
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
