#!/usr/bin/env python3
"""compose_post.py — 縮退ラダー判定と本文合成（v0.3 §7・§10 第2弾-5）。

collect_news.py（要・先行実行）→ generate_post.run()（呼び出しA・B）の結果を受けて、
縮退レベル（L0〜L3）に応じてLLM生成4セクション（ヘッドライン・主要なポイント・
市場のフロー・総括）を実文言または統合運用基準§3.1の逐語定型文へ振り分け、
数値テンプレート（bundle 1・compose_numeric.py）とLP一言（bundle 1・
compose_lp_comment.py）はレベルに関係なく常に組み込む（§7「数値とLP一言は
LLMに依存しないため、L2でも必ず出力される」）。

【S1段階での意図的な非対応（要確認としてユーザーへ報告する）】
§6.3は headline_for_image を daily_data.json の summary へ実際に書き込み、
infographic_renderer.py を再実行するところまでを記述している。しかし§9の
段階導入表はこれを **S3**（「ヘッドライン注入まで自動化」）の到達条件として
明記しており、今回実装するS1は「(5)〜(8)を実装し、生成物をdraft/に出力。
投稿はchat下書きを継続」に留まる。したがって本モジュールは
headline_for_image をテキストとして生成・報告するのみで、実際の
daily_data.json（本番ファイル）・infographic.png への書き込み/再描画は
行わない。手動のset_headline.ymlが実行系として残る。

出力（すべて既存の4点成果物・監査・コミット判定には影響しない）:
  outputs/{対象日}/draft/part1.md
  outputs/{対象日}/draft/part2.md
  outputs/{対象日}/draft/post_bundle.json      … verify_post.py の入力
  outputs/{対象日}/GENERATION_STATUS.md        … §7.2 の指定パスに追随（draft/配下ではない）

CLI:
  ANTHROPIC_API_KEY=... python scripts/compose_post.py <対象日 YYYY-MM-DD>
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import generate_post  # noqa: E402
from compose_lp_comment import compose_lp_comment  # noqa: E402
from compose_numeric import (  # noqa: E402
    compose_part0_target_date,
    compose_part1_numeric,
    compose_part2_numeric,
)
from verify_data import CHG_RE  # noqa: E402  24時間比の書式（+2.43%等）を再利用

# --- §7.1 定型文（統合運用基準 §3.1 の逐語引用。言い換えない） ---
FIXED_HEADLINE = "直近24時間に暗号通貨市場との関係を確認できる主要なマクロ材料は確認できない。"
FIXED_POINTS = "補足できる検証済み材料は確認できない。"
FIXED_FLOW = "価格変動との関係を確認できる主要材料は確認できない。"
# 【総括】は§7.1に逐語定型文の指定がない
# （「（指定文言なし。確認可能な事実だけで簡潔に統合する）」＝人が仕上げる前提）。
# 呼び出しBが失敗した状態でLLMを介さず要約を合成することはできないため、
# §7の表にあるL2の記述「散文欄は見出しを残して空欄」のとおり本文を空欄にする。
SUMMARY_BLANK_NOTE = "（今回は自動生成できませんでした。確認可能な事実のみで人が補ってください。）"

L2_TOP_NOTE = (
    "※本稿は自動生成が一部完了していません。以下の空欄箇所は人による確認・追記が必要です。\n"
)


def _mechanical_headline_for_image(daily_data: dict) -> str:
    """§7.1: 呼び出しA失敗時（L1・L2）のheadline_for_image機械生成。
    前日の値を再利用せず、24時間比の符号から都度組む。
    """
    t = date.fromisoformat(daily_data["target_date_jst"])
    weekday = daily_data.get("weekday_jp", "")

    def direction_label(symbol: str) -> str:
        asset = next((a for a in daily_data.get("assets", []) if a.get("asset") == symbol), None)
        chg = str((asset or {}).get("change_24h", ""))
        if not CHG_RE.match(chg):
            return "未確認"
        v = float(chg.rstrip("%"))
        if abs(v) < 0.10:
            return "横ばい"
        return "上昇" if v > 0 else "下落"

    return f"{t.month}月{t.day}日（{weekday}）の市況｜BTC {direction_label('BTC')}・ETH {direction_label('ETH')}"


def _render_bullets(items: list[str]) -> str:
    return "\n".join(f"・{p}" for p in items)


def compose(daily_data: dict, gen: dict[str, Any]) -> dict[str, Any]:
    """generate_post.run()の結果からセクション本文を組み立てる（純粋関数・I/Oなし）。

    戻り値のsectionsキーはGENERATION_STATUS.mdの手当箇所リストとC15の見出し照合の
    両方に使う。llm_section_keysはverify_post.pyのC16b（散文中の数値転記検知）の
    走査範囲を限定するために使う — 数値テンプレート・LP一言はC16の対象であり
    C16bの対象ではない。
    """
    call_a = gen["call_a"]
    call_b = gen["call_b"]
    a_ok, b_ok = call_a["ok"], call_b["ok"]

    if a_ok:
        headline_for_image = call_a["data"]["headline_for_image"]
        part1_headline = call_a["data"]["part1_headline"]
        part1_points_text = _render_bullets(call_a["data"]["part1_points"])
    else:
        headline_for_image = _mechanical_headline_for_image(daily_data)
        part1_headline = FIXED_HEADLINE
        part1_points_text = FIXED_POINTS

    if b_ok:
        part2_flow_text = _render_bullets(call_b["data"]["part2_flow"])
        part2_summary = call_b["data"]["part2_summary"]
    else:
        part2_flow_text = FIXED_FLOW
        part2_summary = SUMMARY_BLANK_NOTE

    sections = {
        "part0_target_date": compose_part0_target_date(daily_data),
        "part1_headline": part1_headline,
        "part1_points": part1_points_text,
        "part1_numeric": compose_part1_numeric(daily_data),
        "part2_numeric": compose_part2_numeric(daily_data),
        "part2_flow": part2_flow_text,
        "lp_comment": compose_lp_comment(daily_data),
        "part2_summary": part2_summary,
    }

    part1_parts = [
        "【対象日】" + sections["part0_target_date"],
        "【ヘッドライン】\n" + sections["part1_headline"],
        "【主要なポイント】\n" + sections["part1_points"],
        sections["part1_numeric"],
    ]
    part2_parts = [
        sections["part2_numeric"],
        "【市場のフロー】\n" + sections["part2_flow"],
        "【LP運用者向けに一言】\n" + sections["lp_comment"],
        "【総括】\n" + sections["part2_summary"],
    ]
    if gen["level"] == "L2":
        part1_parts.insert(0, L2_TOP_NOTE.rstrip("\n"))

    part1_md = "\n\n".join(part1_parts) + "\n"
    part2_md = "\n\n".join(part2_parts) + "\n"

    llm_section_keys = ["part1_headline", "part1_points", "part2_flow", "part2_summary"]

    return {
        "target_date_jst": daily_data.get("target_date_jst", ""),
        "level": gen["level"],
        "sections": sections,
        "llm_section_keys": llm_section_keys,
        "headline_for_image": headline_for_image,
        "audit_ledger": call_a["data"].get("audit_ledger") if a_ok else None,
        "part1_md": part1_md,
        "part2_md": part2_md,
    }


def _attention_and_auto_lists(gen: dict[str, Any]) -> tuple[list[str], list[str]]:
    attention: list[str] = []
    auto: list[str] = ["数値全項目（前編・後編）", "後編【LP運用者向けに一言】"]
    if gen["call_a"]["ok"]:
        auto.insert(0, "前編【ヘッドライン】【主要なポイント】")
    else:
        attention += ["前編【ヘッドライン】", "前編【主要なポイント】"]
    if gen["call_b"]["ok"]:
        auto.append("後編【市場のフロー】【総括】")
    else:
        attention += ["後編【市場のフロー】", "後編【総括】"]
    return attention, auto


def render_generation_status(gen: dict[str, Any]) -> str:
    a, b = gen["call_a"], gen["call_b"]
    news_status = gen.get("news_source_status", {})
    attention, auto = _attention_and_auto_lists(gen)

    lines = [
        f"level: {gen['level']}",
        f"call_A: {'OK' if a['ok'] else 'FAILED'}"
        + (f" ({a['error']} / {a['attempts']}回試行)" if not a["ok"] else f"（{a['attempts']}回試行）"),
        f"call_B: {'OK' if b['ok'] else 'FAILED'}"
        + (f" ({b['error']} / {b['attempts']}回試行)" if not b["ok"] else f"（{b['attempts']}回試行）"),
        f"cryptopanic: {news_status.get('cryptopanic', '未実行')}"
        + (f" ({news_status.get('count', 0)}件)" if news_status.get("cryptopanic") == "ok" else ""),
        f"web_search: {a.get('web_search_count', 0)}回",
        "",
        "手当が必要な箇所:",
    ]
    lines += [f"  - {x}" for x in attention] if attention else ["  （なし）"]
    lines += ["", "自動生成できた箇所:"]
    lines += [f"  - {x}" for x in auto]
    return "\n".join(lines) + "\n"


def _check_l3_precondition(target_date: str) -> tuple[bool, str]:
    """L3判定: daily_data.json欠損、またはC1〜C11監査が未PASSならTrueを返す
    （§7「何も出さない（既存フェイルクローズ）」）。
    """
    out_dir = Path(f"outputs/{target_date}")
    jp = out_dir / "daily_data.json"
    if not jp.exists():
        return True, f"{jp} が存在しません"
    compact = target_date.replace("-", "")
    audit_path = out_dir / f"final_audit_{compact}.json"
    if not audit_path.exists():
        return True, f"{audit_path} が存在しません（verify_data.py未実行）"
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        return True, f"final_audit の読込に失敗: {e}"
    if audit.get("overall") != "PASS":
        return True, f"final_audit が overall={audit.get('overall')}（C1〜C11 未PASS）"
    return False, ""


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: compose_post.py <対象日 YYYY-MM-DD>", file=sys.stderr)
        return 1
    target_date = sys.argv[1]

    is_l3, reason = _check_l3_precondition(target_date)
    if is_l3:
        print(f"L3: 生成しません（{reason}）。", file=sys.stderr)
        return 1

    daily_data = json.loads(Path(f"outputs/{target_date}/daily_data.json").read_text(encoding="utf-8"))
    gen = generate_post.run(target_date)
    bundle = compose(daily_data, gen)

    draft_dir = Path(f"outputs/{target_date}/draft")
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "part1.md").write_text(bundle["part1_md"], encoding="utf-8")
    (draft_dir / "part2.md").write_text(bundle["part2_md"], encoding="utf-8")
    (draft_dir / "post_bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    status_path = Path(f"outputs/{target_date}/GENERATION_STATUS.md")
    status_path.write_text(render_generation_status(gen), encoding="utf-8")

    print(f"OK: level={gen['level']} → {draft_dir}/part1.md, part2.md, post_bundle.json, {status_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
