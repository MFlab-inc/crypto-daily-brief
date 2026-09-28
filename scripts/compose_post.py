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
import verify_post  # noqa: E402  v1.79・force_drop後の再監査（C12〜C24）に使う
from compose_lp_comment import compose_lp_comment  # noqa: E402
from compose_numeric import (  # noqa: E402
    compose_part0_target_date,
    compose_part1_numeric,
    compose_part2_numeric,
)
from verify_data import CHG_RE  # noqa: E402  24時間比の書式（+2.43%等）を再利用

# --- §7.1 定型文（統合運用基準 §3.1 の逐語引用。言い換えない） ---
# ヘッドライン・主要なポイント・市場のフロー・総括いずれの定型文も
# generate_post.FIXED_HEADLINE/FIXED_POINTS/FIXED_FLOW/SUMMARY_BLANK_NOTEを
# 参照する（v1.15・v1.79で市場のフロー・総括も集約。呼び出しA自身が候補
# ゼロ時にプロンプトで同じ文言を出力するため、定義をこちらに二重に持たない
# — 常に同一の文言であることを保証する。v1.79: verify_post.pyのC27が
# この定型文を識別する必要が生じ、generate_post.py側へ集約した——詳細は
# generate_post.FIXED_FLOW/SUMMARY_BLANK_NOTEのコメント参照）。
# 【総括】の定型文は§7.1に逐語指定は無い（「指定文言なし。確認可能な事実だけで
# 簡潔に統合する」＝人が仕上げる前提）。呼び出しBが失敗した状態でLLMを介さず
# 要約を合成することはできないため、§7の表にあるL2の記述「散文欄は見出しを
# 残して空欄」のとおり本文を空欄にする。
FIXED_FLOW = generate_post.FIXED_FLOW
SUMMARY_BLANK_NOTE = generate_post.SUMMARY_BLANK_NOTE

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


def render_markdown(sections: dict[str, Any], level: str) -> tuple[str, str]:
    """sectionsからpart1_md・part2_mdを組み立てる（compose()から抽出。v1.76）。

    repair_post.pyがC18/C13の局所修正後にsectionsを書き換えたうえで
    part1_md・part2_mdを再構成するために使う。手作業でのMarkdown直接置換は
    post_bundle.jsonのsectionsとの不整合を招くため、再レンダリングは
    常に本関数を経由する（compose()と同一のロジックを共有し、挙動の
    乖離を防ぐ）。
    """
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
    if level == "L2":
        part1_parts.insert(0, L2_TOP_NOTE.rstrip("\n"))

    part1_md = "\n\n".join(part1_parts) + "\n"
    part2_md = "\n\n".join(part2_parts) + "\n"
    return part1_md, part2_md


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
        part1_headline = generate_post.FIXED_HEADLINE
        part1_points_text = generate_post.FIXED_POINTS

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

    part1_md, part2_md = render_markdown(sections, gen["level"])

    llm_section_keys = ["part1_headline", "part1_points", "part2_flow", "part2_summary"]

    return {
        "target_date_jst": daily_data.get("target_date_jst", ""),
        "level": gen["level"],
        "sections": sections,
        "llm_section_keys": llm_section_keys,
        "headline_for_image": headline_for_image,
        "audit_ledger": call_a["data"].get("audit_ledger") if a_ok else None,
        # v1.44: C23（総括の固有名詞バックリファレンス検査）がpart1_points・
        # reusable_for_summaryを参照する必要があるため追加（従来はbundleに
        # 含まれておらずverify_post.py側から参照できなかった）。
        "reusable_for_summary": call_a["data"].get("reusable_for_summary", []) if a_ok else [],
        "news_source_status": gen.get("news_source_status", {}),
        # C19（v1.17改定）: 空配列の許容判定にverify_post.py側で使う
        # （当日の候補自体が0件なら許容、候補はあったのに空配列はFAIL —
        # 「採否を判断した全候補の記録」という台本・統合運用基準の要求どおり）。
        # v1.20: 既定値を0（フェイルオープン）から-1（フェイルクローズ）へ
        # 変更。verify_post.py側のbundle.get("news_candidate_count", -1)と
        # 同じセンチネルに揃え、genが不完全な状態でcompose()が単体呼び出し
        # された場合でも「0件」と誤認しないようにする（独立レビュー指摘）。
        "news_candidate_count": gen.get("news_candidate_count", -1),
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


def _render_news_source_lines(news_status: dict[str, Any]) -> list[str]:
    if not news_status:
        return ["  （情報源未実行）"]
    lines = []
    for name, st in news_status.items():
        if st.get("status") == "ok":
            lines.append(f"  - {name}: ok（対象日{st.get('kept_count', 0)}件／取得{st.get('raw_count', 0)}件）")
        else:
            lines.append(f"  - {name}: failed（{st.get('detail', '')}）")
    return lines


def _inconsistent_symbols(daily_data: dict) -> list[str]:
    return [sym for sym, d in daily_data.get("intraday_range", {}).items()
            if isinstance(d, dict) and d.get("inconsistent")]


def _render_attempt_errors(label: str, call_result: dict[str, Any]) -> list[str]:
    """v1.48（オーナー指示）: リトライが発生した場合（最終的に成功した場合を
    含む）、各試行の失敗理由をGENERATION_STATUS.mdへ記録する。従来は成功時に
    それ以前の試行の失敗理由が失われており、リトライの常態化＝劣化の兆候に
    気づけなかった。1試行目で成功した場合（attempt_errorsが空）は何も出さない。
    """
    errors = call_result.get("attempt_errors") or []
    if not errors:
        return []
    lines = [f"  {label}試行履歴（リトライ発生・劣化の兆候として記録）:"]
    for i, err in enumerate(errors, start=1):
        lines.append(f"    {i}試行目: {err}")
    if call_result.get("ok"):
        lines.append(f"    {call_result['attempts']}試行目: 成功")
    return lines


def _final_audit_failing_ids(bundle: dict[str, Any], daily_data: dict) -> list[str]:
    au = verify_post.run_all(bundle, daily_data)
    return [c["id"] for c in au.checks if c["result"] == "FAIL"]


def _fallback_to_true_l1(daily_data: dict, gen: dict[str, Any], failing_checks: list[str],
                          client: "anthropic.Anthropic | None" = None) -> dict[str, Any]:
    """v1.79（オーナー承認）: 呼び出しAが最終試行の強制不採用
    （force_dropped_candidates。generate_post._derive_decisionsのforce_drop_unresolved
    参照）で続行した結果を含む本文が、除外後の再監査（C12〜C24）でもFAILする
    場合、呼び出しAを失敗扱いへ差し戻し、呼び出しBもnews_from_call_a=Noneで
    生成し直す（＝従来のL1と同じ状態に戻す）。オーナー承認の条件そのもの:
    「除外後にC12〜C24をすべて再検証し、通らなければ従来どおりL1にして
    ください」。

    call_Bは元々「Aが失敗している場合はニュースが空で渡される」前提で
    プロンプト設計されている（CALL_B_INSTRUCTIONS）ため再生成が必要——
    強制不採用前のcall_Bは除外された候補由来の材料を前提に書かれている
    可能性があり、そのまま流用すると呼び出しAをL1(未使用)にしたにも
    かかわらずpart2_flow等に未採用の材料が残るC24等の矛盾を招く。
    verify_post.py自体は変更しない（本フォールバックはcompose_post.py側の
    呼び出し順序の話であり、機械監査の判定ロジックには一切触れない）。
    """
    old_a = gen["call_a"]
    b2 = generate_post.regenerate_call_b_as_l1(daily_data, client=client)
    new_b = b2.to_dict()
    new_a = {**old_a, "ok": False, "data": None,
             "error": ("force_drop_unresolvedで続行したが除外後の再監査(C12〜C24)がFAILしたため"
                       f"L1へフォールバック（FAILしたチェック: {failing_checks}）")}
    failed_count = 1 + (0 if new_b["ok"] else 1)
    return {
        **gen,
        "call_a": new_a,
        "call_b": new_b,
        "level": {1: "L1", 2: "L2"}[failed_count],
        "total_usage": generate_post._add_usage(gen["total_usage"], b2.usage),
    }


def render_generation_status(gen: dict[str, Any], daily_data: dict | None = None,
                              force_dropped: list[dict] | None = None,
                              l1_fallback_failing_checks: list[str] | None = None) -> str:
    a, b = gen["call_a"], gen["call_b"]
    news_status = gen.get("news_source_status", {})
    attention, auto = _attention_and_auto_lists(gen)

    lines = [
        f"level: {gen['level']}",
        f"call_A: {'OK' if a['ok'] else 'FAILED'}"
        + (f" ({a['error']} / {a['attempts']}回試行)" if not a["ok"] else f"（{a['attempts']}回試行）"),
    ]
    lines += _render_attempt_errors("call_A", a)
    lines.append(
        f"call_B: {'OK' if b['ok'] else 'FAILED'}"
        + (f" ({b['error']} / {b['attempts']}回試行)" if not b["ok"] else f"（{b['attempts']}回試行）")
    )
    lines += _render_attempt_errors("call_B", b)
    lines += [
        "token_usage（実消費量）: "
        f"input={gen['total_usage']['input_tokens']}, output={gen['total_usage']['output_tokens']} "
        f"(call_A: in={a['usage']['input_tokens']} out={a['usage']['output_tokens']} / "
        f"call_B: in={b['usage']['input_tokens']} out={b['usage']['output_tokens']})",
        "news_sources:",
    ]
    lines += _render_news_source_lines(news_status)
    audit_ledger = (a.get("data") or {}).get("audit_ledger") if a["ok"] else None
    ledger_len = len(audit_ledger) if isinstance(audit_ledger, list) else "N/A"
    lines += [
        f"news_candidates_today: {gen.get('news_candidate_count', 0)}件 / audit_ledger: {ledger_len}件"
        "（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）",
    ]
    ts = a.get("truncation_stats", {})
    if ts.get("tier3_dropped", 0) > 0:
        lines.append(
            f"tier3候補 {ts['tier3_total']}件中 {ts['tier3_selected']}件を選定"
            f"（{ts['tier3_dropped']}件を件数上限により除外）"
        )
    if ts.get("tier3_pairs_rescued", 0) > 0:
        # v1.39フォローアップ: 独立2媒体ペアの救済（上限外での追加）が
        # 発生した日を可視化する（オーナー指示・トークン影響の観測用）。
        lines.append(
            f"独立2媒体ペア救済: {ts['tier3_pairs_rescued']}組"
            f"（{ts['tier3_pair_rescued_articles']}件を上限外で追加）"
        )
    if ts.get("tier4_dropped", 0) > 0:
        # v1.51（オーナー指示）: Google News RSS復旧（site:演算子への修正）に
        # 伴いtier4が上限に達する日が生じうるため、tier3と同様に可視化する。
        lines.append(
            f"tier4候補 {ts['tier4_total']}件中 {ts['tier4_selected']}件を選定"
            f"（{ts['tier4_dropped']}件を件数上限により除外）"
        )
    auto_filled = a.get("audit_ledger_auto_filled_count", 0)
    if auto_filled > 0:
        # v1.54フォローアップ（オーナー指示）: audit_ledgerのdecision/reasonが
        # 空文字で返る事象（非決定的・複数回観測）を、生成物全体を止めずに
        # 定型文で補完して通した件数を記録する。頻度の追跡が目的であり、
        # 補完自体は_reconstruct_audit_ledger()側で完結している。
        lines.append(
            f"audit_ledger自動補完: {auto_filled}件"
            "（decision/reasonが空だったため定型文で補完。C19は空欄検知のため"
            "PASSする——理由の質は監査対象外）"
        )
    if daily_data is not None:
        inconsistent = _inconsistent_symbols(daily_data)
        if inconsistent:
            # v1.44（オーナー指示）: 終値（CMC）が24時間レンジ（Coinbase/Bitstamp）の
            # 範囲外だった銘柄を記録する（本文への反映はcompose_numeric.py側で
            # 抑制済み。原因の切り分けは数日の実データを見てから判断するため
            # ここでは検出事実のみを記す。表記は v1.49・オーナー指示で
            # 「日中レンジ」から変更）。
            lines.append(
                f"24時間レンジ不整合検出: {'・'.join(inconsistent)}"
                "（終値が取得したレンジの範囲外のため、本文の24時間レンジ行を省略）"
            )
    if force_dropped:
        # v1.79（オーナー承認）: 「最終試行でも解決しない候補を『不採用』にして
        # 続行する分岐は承認します...除外した候補IDと理由はGENERATION_STATUS.md
        # に記録してください」への対応。
        lines.append(
            f"call_A 強制不採用（v1.79）: 最終試行でも独立2ソースの相方が成立しなかった"
            f"{len(force_dropped)}件を強制的に不採用にして続行しました。"
        )
        for d in force_dropped:
            lines.append(
                f"  - candidate_id={d.get('candidate_id')} title={d.get('title')!r} "
                f"source={d.get('source')!r}: {d.get('reason')}"
            )
    if l1_fallback_failing_checks is not None:
        lines.append(
            "call_A 強制不採用後の再監査(C12〜C24)がFAILしたため、call_Aを失敗扱いへ差し戻し"
            f"L1へフォールバックしました（FAILしたチェック: {l1_fallback_failing_checks}）。"
        )
    lines += [
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


def _write_l3_status(target_date: str, reason: str) -> Path:
    """v1.79（オーナー承認）: 「call_Aの失敗やフェイルクローズで本文をコミット
    しない日でも、GENERATION_STATUS.md（L0〜L3の判定、どのチェックがFAILしたか、
    その詳細）だけはコミットされるようにしてください」への対応。L3は
    daily_data.json欠損・C1〜C11未PASSでcompose()自体を呼べないため、他の
    レベルと同じrender_generation_status()の経路には乗せず、専用の最小限の
    内容を書く。本文（part1.md/part2.md）は従来どおり書かない。
    """
    out_dir = Path(f"outputs/{target_date}")
    out_dir.mkdir(parents=True, exist_ok=True)
    status_path = out_dir / "GENERATION_STATUS.md"
    status_path.write_text(
        "level: L3\n"
        f"判定理由: {reason}\n"
        "本文（part1.md / part2.md）は生成していません"
        "（daily_data.json欠損、またはC1〜C11監査が未PASSのためフェイルクローズ）。\n",
        encoding="utf-8")
    return status_path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: compose_post.py <対象日 YYYY-MM-DD>", file=sys.stderr)
        return 1
    target_date = sys.argv[1]

    is_l3, reason = _check_l3_precondition(target_date)
    if is_l3:
        print(f"L3: 生成しません（{reason}）。", file=sys.stderr)
        _write_l3_status(target_date, reason)
        return 1

    daily_data = json.loads(Path(f"outputs/{target_date}/daily_data.json").read_text(encoding="utf-8"))
    gen = generate_post.run(target_date)
    bundle = compose(daily_data, gen)

    # v1.79（オーナー承認）: 呼び出しAが最終試行の強制不採用で続行した場合、
    # 除外後の本文でC12〜C24を再監査し、なおFAILするなら従来どおりのL1へ
    # フォールバックする（「除外後にC12〜C24をすべて再検証し、通らなければ
    # 従来どおりL1にしてください」）。
    force_dropped = gen["call_a"].get("force_dropped_candidates", []) if gen["call_a"]["ok"] else []
    rejected_pairs = gen["call_a"].get("rejected_pairs", [])
    l1_fallback_failing_checks: list[str] | None = None
    if force_dropped:
        failing = _final_audit_failing_ids(bundle, daily_data)
        if failing:
            l1_fallback_failing_checks = failing
            gen = _fallback_to_true_l1(daily_data, gen, failing)
            bundle = compose(daily_data, gen)

    draft_dir = Path(f"outputs/{target_date}/draft")
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "part1.md").write_text(bundle["part1_md"], encoding="utf-8")
    (draft_dir / "part2.md").write_text(bundle["part2_md"], encoding="utf-8")
    (draft_dir / "post_bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    # v1.79（オーナー承認）: news_candidates.json（collect_news.py既存出力）と
    # 並べて、ペア判定で却下された候補の診断（両側のtitle/source・重なり係数）を
    # GitHub Actionsアーティファクトとして保存する（daily.yml側で対象に追加。
    # リポジトリへはコミットしない）。
    out_dir = Path(f"outputs/{target_date}")
    (out_dir / "rejected_pairs.json").write_text(
        json.dumps(rejected_pairs, ensure_ascii=False, indent=2), encoding="utf-8")

    status_path = out_dir / "GENERATION_STATUS.md"
    status_text = render_generation_status(
        gen, daily_data, force_dropped=force_dropped, l1_fallback_failing_checks=l1_fallback_failing_checks)
    status_path.write_text(status_text, encoding="utf-8")

    print(f"OK: level={gen['level']} → {draft_dir}/part1.md, part2.md, post_bundle.json, {status_path}")
    print("--- GENERATION_STATUS.md ---")
    print(status_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
