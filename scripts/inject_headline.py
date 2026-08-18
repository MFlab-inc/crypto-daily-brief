#!/usr/bin/env python3
"""inject_headline.py — daily_data.json の summary へヘッドラインを差し込む（v0.3 §10 第1弾-1）。

set_headline.yml にインラインPythonとして存在していた処理を、再利用可能な
共通関数へ切り出したもの（v0.3 §6.3・§10 で指示された切り出し工程）。
set_headline.yml（人手のヘッドライン差し込み）と、将来の compose_post.py
（フェーズ2 第2弾・LLM生成のheadline_for_imageを自動注入）の双方から呼ぶ。

ロジックは切り出し前と完全に同一（エラー文言・判定順序とも変更なし）。
切り出し前後で daily_data.json・infographic.png がバイト一致することを
実測確認済み（DESIGN_CHANGES.md v1.6 参照）。

CLI（set_headline.yml から呼ばれる形）:
  TARGET_DIR=outputs/2026-08-16 HEADLINE="..." python scripts/inject_headline.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


class InjectHeadlineError(Exception):
    """headline が空文字、または対象の daily_data.json が存在しない場合。"""


def inject_headline(target_dir: Path, headline: str) -> Path:
    """target_dir/daily_data.json の summary を headline で上書きする。

    戻り値: 更新した daily_data.json のパス。
    headline が空文字/空白のみ、または daily_data.json が存在しない場合は
    InjectHeadlineError を送出し、ファイルには一切書き込まない
    （プレースホルダーのままコミットさせない、という制約を担保する）。
    """
    if not headline.strip():
        raise InjectHeadlineError(
            "headline が空文字です。プレースホルダーのままコミットしません。")

    jp = Path(target_dir) / "daily_data.json"
    if not jp.exists():
        raise InjectHeadlineError(
            f"{jp} が存在しません。先に daily-crypto-brief で対象日の"
            "成果物を生成してください。")

    d = json.loads(jp.read_text(encoding="utf-8"))
    d["summary"] = headline
    jp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return jp


def main() -> int:
    target_dir = os.environ.get("TARGET_DIR", "")
    if not target_dir:
        print("ERROR: 環境変数 TARGET_DIR が未設定です。", file=sys.stderr)
        return 1
    headline = os.environ.get("HEADLINE", "")
    try:
        jp = inject_headline(Path(target_dir), headline)
    except InjectHeadlineError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"OK: {jp} の summary を更新しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
