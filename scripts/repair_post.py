#!/usr/bin/env python3
"""repair_post.py — C18/C13違反の局所修正（v1.76・オーナー承認・2026-09-16）。

compose_post.py が書き出した post_bundle.json を対象に、verify_post.py と
同じ機械監査(C12〜C24)を実行し、C18（断定表現）・C13（ハッシュタグ境界の
うち「'#'の直前が行頭/半角スペースでない」パターンのみ）が検出された場合に
限り、違反箇所だけを局所的に修正してから再検証する。運用観察報告
（DESIGN_CHANGES.md v1.75）で、観察期間7日中の監査FAIL3日がすべてC18のみに
起因していたことを受けて導入する。

設計方針（オーナー承認）:
  - verify_post.py自体は「純粋な機械監査（LLM非依存）」のまま変更しない。
    本スクリプトはcompose_post.pyとverify_post.pyの間に独立ステップとして
    挿入し、修正ロジックを完全に分離する（検知する側が直す側でもある状態は
    検出力を落とすため避ける）。
  - C18: 違反文だけをgenerate_post.call_r()へ渡し、事実関係を変えずに文末を
    限定表現（verify_post.LIMITING_EXPRESSIONS）で終端する形へ書き直させる。
    判定に使うのと同じ文検出（verify_post._find_c18_violations）を再利用する
    ため、「何が違反か」の定義は常に検知側と1箇所に一致する。
  - C13: 「'#'の直前が行頭/半角スペースでない」パターンのみ、LLMを介さず
    機械的に半角スペースを1つ挿入して修正する（決定論的・コストゼロ）。
    他の2パターン（タグ名欠落・終端文字不正）は観察期間中に未観測のため
    対象外とし、従来どおりFAILのまま扱う（観測していない事象に先回りで
    対処しない）。
  - 1ラウンド = その時点で検出されている対象違反すべてを1件ずつ修正した
    うえで、機械監査(C12〜C24)全体を再実行する（書き直しが他の文・他の
    チェックへ影響する可能性があるため、個別に確認せずまとめて直してから
    再検査する）。最大2ラウンドまで。2ラウンド終えても対象違反が残る場合は
    従来どおりFAILとして扱う——本スクリプトは常に正常終了（exit 0）し、
    後続のverify_post.pyが唯一の最終ゲートとして機能する。
  - 修正前後の文・対象セクション・ラウンド数・トークン増分をGENERATION_
    STATUS.mdへ記録する。修正後の意味保持（事実が変わっていないか）の
    自動チェックは見送り、ログでの目視確認に委ねる（オーナー承認）。

使い方:
  ANTHROPIC_API_KEY=... python scripts/repair_post.py <対象日 YYYY-MM-DD>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
import anthropic  # noqa: E402

import compose_post  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

MAX_ROUNDS = 2
REPAIRABLE_CHECK_IDS = {"C18_causal_assertion", "C13_hashtag_boundary"}

# C13: 「'#'の直前が行頭/半角スペースでない」という1パターンのみを対象に、
# 半角スペースを1つ挿入する。文字列の先頭（直前に文字が無い）は
# verify_post._hashtag_violations()側でも「行頭扱い＝違反ではない」ため、
# 肯定形の後読み（直前に実在する非空白文字が必要）で表現し、先頭の'#'には
# 一致させない。
_C13_MISSING_SPACE_RE = re.compile(r"(?<=[^\n ])#")


def _fix_c13_missing_space(text: str) -> tuple[str, int]:
    """該当パターンの'#'の直前に半角スペースを1つ挿入する。他の2パターン
    （タグ名欠落・終端文字不正）はこの正規表現にマッチしないため、
    一切変更されない。
    """
    return _C13_MISSING_SPACE_RE.subn(" #", text)


def _split_bullet_prefix(token: str) -> tuple[str, str]:
    """箇条書きの先頭記号（"・"）と前後の空白をLLMへ渡す本文から分離する。
    修正後に同じ接頭辞を付け直してから元テキストへ置換する。
    """
    m = re.match(r"^([\s・]*)(.*)$", token, re.DOTALL)
    return m.group(1), m.group(2)


def _find_c18_targets(bundle: dict) -> list[dict]:
    allowlist = verify_post._load_allowlist(bundle.get("target_date_jst", ""), "c18_allowlist.json")
    violations = verify_post._find_c18_violations(bundle["sections"], bundle["llm_section_keys"], allowlist)
    targets = []
    for v in violations:
        prefix, core = _split_bullet_prefix(v["sentence"])
        targets.append({"section": v["section"], "token": v["sentence"], "prefix": prefix, "core": core})
    return targets


def _repair_c18(client: "anthropic.Anthropic", bundle: dict, round_log: list[dict]) -> dict[str, int]:
    usage_total = {"input_tokens": 0, "output_tokens": 0}
    for target in _find_c18_targets(bundle):
        outcome = generate_post.call_r(client, target["core"], verify_post.LIMITING_EXPRESSIONS)
        usage_total = generate_post._add_usage(usage_total, outcome.usage)
        entry = {"check": "C18_causal_assertion", "section": target["section"], "before": target["token"]}
        if not outcome.ok:
            entry.update(ok=False, after=None, error=outcome.error)
            round_log.append(entry)
            continue
        # 渡した"core"は元セクション中の"。"を含まないため、書き直し結果も
        # 同じ規約（句点なし）である前提で貼り戻す。プロンプトで指示済みだが、
        # モデルが句点を付けて返した場合に元テキスト側の"。"と二重になる
        # （「〜可能性がある。。」）事故を避けるため、念のため末尾の句点を
        # 防御的に除去する。
        rewritten_core = str((outcome.data or {}).get("rewritten_sentence", "")).strip().rstrip("。")
        if not rewritten_core:
            entry.update(ok=False, after=None, error="空応答")
            round_log.append(entry)
            continue
        new_token = target["prefix"] + rewritten_core
        section_text = bundle["sections"][target["section"]]
        bundle["sections"][target["section"]] = section_text.replace(target["token"], new_token, 1)
        entry.update(ok=True, after=new_token, error=None)
        round_log.append(entry)
    return usage_total


def _repair_c13(bundle: dict, round_log: list[dict]) -> None:
    for key, text in list(bundle["sections"].items()):
        if not isinstance(text, str):
            continue
        fixed, n = _fix_c13_missing_space(text)
        if n:
            bundle["sections"][key] = fixed
            round_log.append({"check": "C13_hashtag_boundary", "section": key,
                               "before": text, "after": fixed, "ok": True, "fixes": n, "error": None})
    hfi = bundle.get("headline_for_image")
    if isinstance(hfi, str):
        fixed, n = _fix_c13_missing_space(hfi)
        if n:
            bundle["headline_for_image"] = fixed
            round_log.append({"check": "C13_hashtag_boundary", "section": "headline_for_image",
                               "before": hfi, "after": fixed, "ok": True, "fixes": n, "error": None})


def repair(target_date: str, *, client: "anthropic.Anthropic | None" = None) -> dict[str, Any]:
    """draft/post_bundle.jsonを読み込み、必要ならC18/C13を局所修正して
    書き戻す。呼び出し元に無関係な失敗（他チェックのFAIL）はそのまま残す。
    """
    draft_dir = Path(f"outputs/{target_date}/draft")
    bundle_path = draft_dir / "post_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    daily_data = json.loads(Path(f"outputs/{target_date}/daily_data.json").read_text(encoding="utf-8"))

    if client is None:
        client = anthropic.Anthropic()

    rounds_log: list[dict] = []
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    rounds_used = 0

    for round_no in range(1, MAX_ROUNDS + 1):
        au = verify_post.run_all(bundle, daily_data)
        failing_ids = {c["id"] for c in au.checks if c["result"] == "FAIL"}
        target_failing = failing_ids & REPAIRABLE_CHECK_IDS
        if not target_failing:
            break
        rounds_used = round_no
        round_log: list[dict] = []
        if "C18_causal_assertion" in target_failing:
            usage = _repair_c18(client, bundle, round_log)
            total_usage = generate_post._add_usage(total_usage, usage)
        if "C13_hashtag_boundary" in target_failing:
            _repair_c13(bundle, round_log)
        bundle["part1_md"], bundle["part2_md"] = compose_post.render_markdown(bundle["sections"], bundle["level"])
        rounds_log.append({"round": round_no, "target_failing": sorted(target_failing), "repairs": round_log})

    final_audit = verify_post.run_all(bundle, daily_data)
    final_failing = sorted(c["id"] for c in final_audit.checks if c["result"] == "FAIL")
    rescued = rounds_used > 0 and not (REPAIRABLE_CHECK_IDS & set(final_failing))

    if rounds_used:
        (draft_dir / "part1.md").write_text(bundle["part1_md"], encoding="utf-8")
        (draft_dir / "part2.md").write_text(bundle["part2_md"], encoding="utf-8")
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "target_date_jst": target_date,
        "rounds_used": rounds_used,
        "rounds_log": rounds_log,
        "total_usage": total_usage,
        "final_failing_checks": final_failing,
        "rescued": rescued,
    }


def render_status_note(result: dict[str, Any]) -> str:
    """GENERATION_STATUS.mdへ追記する局所修正ログ。修正が1件も発生しなかった
    場合（対象違反が最初からFAILしていない）は空文字列を返す。
    """
    if result["rounds_used"] == 0:
        return ""
    lines = ["", "局所修正（repair_post.py・C18/C13）:"]
    for r in result["rounds_log"]:
        lines.append(f"  ラウンド{r['round']}（対象: {'・'.join(r['target_failing'])}）:")
        for rep in r["repairs"]:
            status = "OK" if rep["ok"] else f"失敗（{rep.get('error', '')}）"
            lines.append(f"    [{rep['check']} / {rep['section']}] {status}")
            lines.append(f"      修正前: {rep['before']}")
            if rep["ok"]:
                lines.append(f"      修正後: {rep['after']}")
    u = result["total_usage"]
    lines.append(f"  修正呼び出し合計トークン: input={u['input_tokens']}, output={u['output_tokens']}")
    if result["rescued"]:
        lines.append("  最終結果: 救済（C18・C13ともPASSへ改善）")
    else:
        lines.append(f"  最終結果: 未救済（残存FAIL: {result['final_failing_checks']}）。従来どおりFAILとして扱う。")
    return "\n".join(lines) + "\n"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: repair_post.py <対象日 YYYY-MM-DD>", file=sys.stderr)
        return 1
    target_date = sys.argv[1]
    bundle_path = Path(f"outputs/{target_date}/draft/post_bundle.json")
    if not bundle_path.exists():
        print(f"{bundle_path} が存在しないため何もしません。", file=sys.stderr)
        return 0

    result = repair(target_date)
    note = render_status_note(result)
    if note:
        status_path = Path(f"outputs/{target_date}/GENERATION_STATUS.md")
        if status_path.exists():
            with status_path.open("a", encoding="utf-8") as f:
                f.write(note)
        print(note)
    else:
        print("局所修正の対象なし（初回検証でC18・C13ともFAILしていない）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
