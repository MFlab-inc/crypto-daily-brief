#!/usr/bin/env python3
"""_diag_call_a_truncation.py — 一時的な調査用スクリプト。

call_Aがmax_tokens上限で打ち切られてJSON解析に失敗する事象（2026-08-20
実測: 3回とも出力ちょうど8000トークンでJSONDecodeError）の原因切り分け。
本番と同一のcollect_news.py・generate_post.pyのプロンプト構築ロジックを
再利用し、実際のRSS候補データに対してmax_tokens=8000（本番と同一）と
max_tokens=3000（意図的に狭くした対照実験）の両方でcall_Aを直接呼び出し、
JSON解析に失敗した場合は生テキストの全体像（文字数・エラー位置・
エラー周辺・末尾）を出力する。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import generate_post  # noqa: E402

JST = timezone(timedelta(hours=9))


def _describe_raw_text(label: str, text: str, err: Exception | None) -> None:
    print(f"--- {label} ---")
    print(f"生テキスト文字数: {len(text)}")
    if err is not None:
        print(f"エラー: {type(err).__name__}: {err}")
        pos = getattr(err, "pos", None)
        if pos is not None:
            start = max(0, pos - 150)
            end = min(len(text), pos + 150)
            print(f"エラー位置(pos={pos})の前後300字:")
            print(repr(text[start:end]))
    print("末尾300字:")
    print(repr(text[-300:]))
    print(f'"decision"の出現回数（audit_ledgerエントリ数の目安）: {text.count(chr(34) + "decision" + chr(34))}')
    print(f'"source"の出現回数: {text.count(chr(34) + "source" + chr(34))}')
    print()


def _try_call(client, user_content: str, max_tokens: int, label: str) -> None:
    print(f"=== {label}（max_tokens={max_tokens}） ===")
    response = client.messages.create(
        model=generate_post.MODEL,
        max_tokens=max_tokens,
        system=generate_post.SYSTEM_A,
        messages=[{"role": "user", "content": user_content}],
    )
    usage = response.usage
    print(f"stop_reason: {response.stop_reason}")
    print(f"usage: input={usage.input_tokens}, output={usage.output_tokens}")
    print(f"content block数: {len(response.content)}")
    for i, b in enumerate(response.content):
        btype = getattr(b, "type", None)
        btext = getattr(b, "text", None)
        blen = len(btext) if isinstance(btext, str) else None
        print(f"  block[{i}]: type={btype!r} text_len={blen} repr_head={repr(b)[:200]}")
    text = generate_post._strip_code_fence(generate_post._extract_text(response))
    try:
        data = json.loads(text)
        missing = [k for k in generate_post.REQUIRED_KEYS_A if k not in data]
        if missing:
            print(f"JSON解析は成功したが必須キー欠落: {missing}")
        else:
            ledger = data.get("audit_ledger", [])
            print(f"JSON解析成功。audit_ledger件数={len(ledger)}")
        _describe_raw_text(label, text, None)
    except json.JSONDecodeError as e:
        print("JSON解析失敗。")
        _describe_raw_text(label, text, e)


def main() -> None:
    target = (date.today() - timedelta(days=1)).isoformat()
    print(f"対象日: {target}（実行時JSTの前日相当・本番と同じ計算）")
    news_today = collect_news.collect_news(target)
    cands = news_today.get("candidates", [])
    print(f"取得候補数（全tier合計・生値）: {len(cands)}")
    by_tier: dict[int, int] = {}
    for c in cands:
        by_tier[c.get("tier")] = by_tier.get(c.get("tier"), 0) + 1
    print(f"tier別内訳: {by_tier}")

    daily_data_path = f"outputs/{target}/daily_data.json"
    if os.path.exists(daily_data_path):
        daily_data = json.loads(open(daily_data_path, encoding="utf-8").read())
    else:
        print(f"警告: {daily_data_path} が無いためダミーのdaily_dataで代用します。")
        daily_data = {"target_date_jst": target}

    user_content, stats = generate_post._build_call_a_user_content(daily_data, news_today, None)
    print(f"呼び出しAへ渡す候補数（選定後）: {stats}")
    print(f"user_content文字数: {len(user_content)}")
    print()

    client = anthropic.Anthropic()
    _try_call(client, user_content, 8000, "本番同一条件")
    _try_call(client, user_content, 500, "対照実験（block種別の確認用・コスト最小化のため500に縮小）")


if __name__ == "__main__":
    main()
