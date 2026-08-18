#!/usr/bin/env python3
"""compose_draft.py — 第1弾（数値テンプレート＋LP一言）の下書き出力（v0.3 §10 第1弾-3・§9 S1）。

LLM生成部分（ヘッドライン・主要なポイント・市場のフロー・総括）は第2弾未実装のため、
見出しのみ残して空欄にする（L2相当の下書き）。既存の outputs/{対象日}/ 直下の
成果物・監査・コミット判定には一切影響しない — 出力は outputs/{対象日}/draft/ のみ。

使い方: python scripts/compose_draft.py <対象日 YYYY-MM-DD>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compose_lp_comment import compose_lp_comment  # noqa: E402
from compose_numeric import (  # noqa: E402
    compose_part0_target_date,
    compose_part1_numeric,
    compose_part2_numeric,
)

PENDING = "（フェーズ2 第2弾［LLM呼び出し］未実装のため、この下書きでは空欄）"


def compose_draft(daily_data: dict) -> tuple[str, str]:
    part1 = "\n\n".join([
        "【対象日】" + compose_part0_target_date(daily_data),
        "【ヘッドライン】\n" + PENDING,
        "【主要なポイント】\n" + PENDING,
        compose_part1_numeric(daily_data),
    ])
    part2 = "\n\n".join([
        compose_part2_numeric(daily_data),
        "【市場のフロー】\n" + PENDING,
        "【LP運用者向けに一言】\n" + compose_lp_comment(daily_data),
        "【総括】\n" + PENDING,
    ])
    return part1, part2


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: compose_draft.py <対象日 YYYY-MM-DD>", file=sys.stderr)
        return 1
    target_date = sys.argv[1]
    src = Path(f"outputs/{target_date}/daily_data.json")
    if not src.exists():
        print(f"ERROR: {src} が存在しません。", file=sys.stderr)
        return 1

    daily_data = json.loads(src.read_text(encoding="utf-8"))
    part1, part2 = compose_draft(daily_data)

    out_dir = Path(f"outputs/{target_date}/draft")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "part1.md").write_text(part1 + "\n", encoding="utf-8")
    (out_dir / "part2.md").write_text(part2 + "\n", encoding="utf-8")
    print(f"OK: {out_dir}/part1.md, {out_dir}/part2.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
