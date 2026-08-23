#!/usr/bin/env python3
"""_diag_fix12_verify.py — 一時的な調査用スクリプト（v2）。

v1（直接call_a()を呼んだ版）は2026-08-21・2026-08-22の両方で
call_Aが3回とも"JSONDecodeError: Expecting value: line 1 column 1
(char 0)"で失敗し、修正1・2の効果を検証できなかった。この失敗パターンは
v1.28検証時（8/20データ）にも一度観測されているが、生テキストを
一度も確認できていない（_call_json()の広い例外処理がstr(exception)
しか保持しないため）。

v2では client.messages.create() を直接呼び、_call_json()を経由せず
生レスポンスを毎回全文出力する。修正1・2で候補ごとのeligibility
フィールドを追加した分プロンプトが長くなっており、それが失敗の再現性に
関係するか（未確認の仮説）も含めて切り分ける。

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

TARGETS = ["2026-08-21", "2026-08-22"]
ATTEMPTS_PER_TARGET = 3


def _try_once(client, user_content: str, attempt_no: int) -> None:
    print(f"--- 試行 {attempt_no} ---")
    response = client.messages.create(
        model=generate_post.MODEL,
        max_tokens=generate_post.CALL_A_MAX_TOKENS,
        system=generate_post.SYSTEM_A,
        messages=[{"role": "user", "content": user_content}],
        thinking={"type": "disabled"},
    )
    usage = response.usage
    print(f"stop_reason: {response.stop_reason}, output_tokens: {usage.output_tokens}")
    print(f"content blocks: {[(getattr(b, 'type', None)) for b in response.content]}")
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


def _run_for(target: str, client) -> None:
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

    user_content, stats = generate_post._build_call_a_user_content(daily_data, news_today, None)
    print(f"候補統計: {stats}")
    print(f"user_contentの長さ（文字数）: {len(user_content)}")
    print()

    for i in range(1, ATTEMPTS_PER_TARGET + 1):
        try:
            _try_once(client, user_content, i)
        except Exception as e:  # noqa: BLE001
            print(f"試行{i}で例外: {type(e).__name__}: {e}")
            print()


def main() -> None:
    client = anthropic.Anthropic()
    for target in TARGETS:
        _run_for(target, client)


if __name__ == "__main__":
    main()
