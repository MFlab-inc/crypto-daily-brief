#!/usr/bin/env python3
"""compose_lp_comment.py — 【LP運用者向けに一言】のコード生成（v0.3 §6.2・§10 第1弾-2）。

daily_data.json の lp.pools[].change_vs_prev と ETH の24時間比から機械的に組む。
LLM不使用。個別のポジション・レンジ・数量・金額には一切言及しない。

change_vs_prev はプール単位・指標単位で独立に縮退する（v1.5）。
「両プールとも全指標あり」と「丸ごと無し」の2値ではないため、
v0.3 で追加された 1-a〜1-f の判定順に従う。
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from fetch_data import load_prev_pools  # noqa: E402  前日プール読み込みを再利用（重複実装しない）

PCT_RE = re.compile(r"^([+-]\d+\.\d{2})%$")

FIXED_2 = "なお参考APRはプール全体の単純年率換算であり、個別ポジションの実現収益とは異なります。"
FIXED_4 = "V3では価格が設定レンジを外れると手数料が発生しません。"
FIXED_5 = "APR単独ではレンジ幅を判断できないため、出来高の持続性・レンジ外リスク・ILとあわせた確認が必要です。"

# §11 未確定事項4: 実データ蓄積後に見直す前提の仮置き値。
MAIN_FACTOR_THRESHOLD_PT = 5.0

NO_PREV_DAY = "前日データが利用できないため、参考APRの変化は比較できません。"


def _parse_pct(s: Any) -> float | None:
    m = PCT_RE.match(str(s))
    return float(m.group(1)) if m else None


def _direction_word(delta: float) -> str:
    # delta == 0.00 の扱いは台本で未規定。実データでの厳密な同値は
    # 独立した2値APIレスポンスの偶然一致を要し実質起こらないため、
    # 0以上を「上昇」側とする（verify_data.py の C4 とは別の軽微な仮置き）。
    return "上昇" if delta >= 0 else "低下"


def _pool_sentence(name: str, pool: dict, prev_pool: dict | None) -> str:
    """1-b・1-c・1-d: 1プール分の文を組む（1-aの一部＝プール単位の起点）。"""
    cv = pool.get("change_vs_prev") or {}
    apr_chg = _parse_pct(cv.get("apr_change", ""))
    if apr_chg is None:
        # 1-d: 当日値または前日値が未確認で apr_change 自体が算出できない。
        # 文言注意: 「前日」の直後に「比」を置かない（C12の禁止語「前日比」との
        # 部分一致衝突を避ける — v1.2/v1.4で確立した既存の注意点と同種）。
        # 「前日比較」ではなく「比較に必要な前日の値」の語順にする。
        return f"{name}は比較に必要な前日の値が取得できなかったため、参考APRの変化は提示できません。"

    curr_apr = pool.get("apr", "未確認")
    prev_apr = (prev_pool or {}).get("apr", "未確認")
    direction = _direction_word(apr_chg)

    vol_raw = cv.get("volume_24h_change", "")
    tvl_raw = cv.get("tvl_change", "")
    vol_chg = _parse_pct(vol_raw)
    tvl_chg = _parse_pct(tvl_raw)

    if vol_chg is None or tvl_chg is None:
        # 1-c: 出来高・TVLのいずれかが欠落。
        return (f"{name}の参考APRは{prev_apr}→{curr_apr}へ{direction}しました"
                f"（要因の内訳は一部が取得不能のため提示しません）。")

    # 1-b: 3指標すべて利用可能。
    sentence = (f"{name}の参考APRは{prev_apr}→{curr_apr}へ{direction}しました"
                f"（24時間出来高 {vol_raw}、TVL {tvl_raw}）。")
    # 主因の判定（台本 §6.2 の記述どおり）。テンプレート本文に主因の挿入位置が
    # 明示されていなかったため、算出結果を末尾に1文追加する形で実装した
    # （v0.3レビュー時に要確認としてユーザーへ報告する）。
    diff = abs(vol_chg) - abs(tvl_chg)
    if diff >= MAIN_FACTOR_THRESHOLD_PT:
        sentence += "24時間出来高の変化が主因です。"
    elif -diff >= MAIN_FACTOR_THRESHOLD_PT:
        sentence += "TVLの変化が主因です。"
    return sentence


def _apr_change_available(pool: dict) -> bool:
    cv = pool.get("change_vs_prev") or {}
    return _parse_pct(cv.get("apr_change", "")) is not None


def _fully_available(pool: dict) -> bool:
    cv = pool.get("change_vs_prev") or {}
    return (
        _parse_pct(cv.get("apr_change", "")) is not None
        and _parse_pct(cv.get("volume_24h_change", "")) is not None
        and _parse_pct(cv.get("tvl_change", "")) is not None
    )


def _section_1(pools: list[dict], prev_pools: dict[str, dict] | None) -> list[str]:
    has_change_vs_prev = any(isinstance(p.get("change_vs_prev"), dict) for p in pools)
    if not has_change_vs_prev:
        # change_vs_prev キー自体が存在しない（v1.5以前の形式）。
        return [NO_PREV_DAY]

    if all(not _apr_change_available(p) for p in pools):
        # 1-e: 両プールとも1-dに該当。
        return [NO_PREV_DAY]

    lines: list[str] = []
    if len(pools) == 2 and all(_fully_available(p) for p in pools):
        d0 = _direction_word(_parse_pct(pools[0]["change_vs_prev"]["apr_change"]))
        d1 = _direction_word(_parse_pct(pools[1]["change_vs_prev"]["apr_change"]))
        if d0 == d1:
            # 1-f: 両プールとも1-bに該当し方向が同一の場合のみ、圧縮見出しを冒頭へ。
            lines.append(f"参考APRは両プールとも前日から{d0}しました。")

    for pool in pools:
        name = pool.get("name", "")
        prev_pool = (prev_pools or {}).get(name)
        lines.append(_pool_sentence(name, pool, prev_pool))
    return lines


def _section_3(daily_data: dict) -> str:
    eth = next((a for a in daily_data.get("assets", []) if a.get("asset") == "ETH"), {})
    eth_chg = eth.get("change_24h", "未確認")
    eth_dir = eth.get("direction", "neutral")
    if eth_chg == "未確認" or eth_dir not in ("up", "down"):
        return "ETHの24時間比が未確認のため、方向に応じた確認事項は提示できません。"
    if eth_dir == "up":
        return f"ETHは24時間比{eth_chg}と上昇中のため、USDC偏り・上限側レンジ外・反落耐性を確認してください。"
    return f"ETHは24時間比{eth_chg}と下落中のため、ETH偏り・下限側レンジ外・下落耐性を確認してください。"


def compose_lp_comment(daily_data: dict[str, Any]) -> str:
    pools = daily_data.get("lp", {}).get("pools", [])

    prev_pools: dict[str, dict] | None = None
    try:
        target = date.fromisoformat(daily_data.get("target_date_jst", ""))
        prev_pools = load_prev_pools(target)
    except (ValueError, TypeError):
        prev_pools = None

    lines = list(_section_1(pools, prev_pools))
    lines.append(FIXED_2)
    lines.append(_section_3(daily_data))
    lines.append(FIXED_4)
    lines.append(FIXED_5)
    return "\n".join(lines)


def main() -> int:
    import json
    if len(sys.argv) != 2:
        print("Usage: compose_lp_comment.py <daily_data.json のパス>", file=sys.stderr)
        return 1
    d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(compose_lp_comment(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
