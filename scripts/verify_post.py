#!/usr/bin/env python3
"""verify_post.py — 本文の機械監査 C12〜C22（v0.3 §8・§10 第2弾-6）。

compose_post.py が書き出す post_bundle.json を入力とする。1件でもFAILなら
exit 1（既存 verify_data.py の C1〜C11 と同じ fail-close の考え方）が、
本監査は現段階（S1）では既存の成果物・監査・コミット判定に接続していない
— draft/post_audit_{compact}.json に結果を保存するのみ。

縮退時（該当箇所が空欄）はそれ自体を理由にFAILさせない（§8「空欄は仕様」）。
C16bの走査範囲は post_bundle.json の llm_section_keys（LLM生成の4セクション）
のみとし、数値テンプレート・LP一言（C16の対象）は含めない。

使い方:
  python scripts/verify_post.py outputs/2026-08-18/draft/post_bundle.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import collect_news  # noqa: E402
import generate_post  # noqa: E402
from compose_lp_comment import FIXED_2, FIXED_4, FIXED_5, compose_lp_comment  # noqa: E402
from compose_numeric import (  # noqa: E402
    compose_part0_target_date,
    compose_part1_numeric,
    compose_part2_numeric,
)
from verify_data import Audit  # noqa: E402

BANNED_TERMS = ["仮想通貨", "前日比"]
# C18（v1.22改定・オーナー指示）: v1.20の「マーカー＋同一文内の価格変動語」
# 判定は、独立レビューの2巡目で誤検知（本パイプライン自身が使うヘッジ語彙
# 「可能性がある」「因果は未確認」等を含む正当な文まで機械的にFAILさせていた）
# が実行確認された。判定の趣旨は「断定」を禁じることであり、限定表現で
# 締められた文は基準が求める正しい書き方であるため、これをFAILさせるのは
# 設計ミスと判断された。限定表現（LIMITING_EXPRESSIONS）が同一文にあれば
# PASSへ回す判定へ変更。あわせてマーカー・価格変動語の語彙を拡充し
# （によって/せいで/を機に、暴落/急騰/反落を追加）、マーカーと価格変動語の
# 語順を問わない判定へ変更した（価格語が先に来る文も検知）。
CAUSAL_MARKERS = ["により", "を受けて", "が原因で", "のため", "によって", "せいで", "を機に"]
PRICE_MOVEMENT_WORDS = ["上昇", "下落", "高騰", "急落", "暴落", "急騰", "反落"]
CAUSAL_STANDALONE_PHRASES = ["が牽引した"]
# 限定表現（この語が同一文にあれば「断定」ではなく基準が求める正しい書き方と
# みなしFAILさせない）。「断定」は「断定はできない」等、助詞が挟まる活用差
# （でき/できない/できません）を吸収するため活用語尾を含めない広い形で採用。
# 「確認できません」は活用差を許容すると「確認された」等の非ヘッジ文まで
# 誤って救済してしまうため、原型のまま採用する（既知の限界：「確認は
# できません」のように助詞が挟まる形は本語では拾えない）。
LIMITING_EXPRESSIONS = ["可能性", "未確認", "意識された", "とみられる", "考えられる", "確認できません", "断定"]
ALLOWED_TAGS = {"BTC", "ETH", "BNB", "USDC"}
REQUIRED_HEADINGS_PART1 = ["【対象日】", "【ヘッドライン】", "【主要なポイント】", "【主要指標】"]
REQUIRED_HEADINGS_PART2 = ["【主要指標（詳細）】", "【市場のフロー】", "【LP運用者向けに一言】", "【総括】"]
C16B_MIN_LEN = 3


def _load_allowlist(target_date: str, filename: str) -> set[str]:
    """c16b_allowlist.json・c18_allowlist.json共通の読み込み（同一形式）。"""
    path = Path(__file__).parent.parent / "config" / filename
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return set()
    return {
        e.get("string", "") for e in data.get("exceptions", [])
        if isinstance(e, dict) and e.get("date") == target_date
    }


# --- C12 禁止語 ---

def check_c12(au: Audit, full_text: str) -> None:
    hits = [t for t in BANNED_TERMS if t in full_text]
    au.add("C12_banned_terms", not hits, f"検出: {hits}" if hits else "禁止語なし")


# --- C13 ハッシュタグ境界 ---

def _hashtag_violations(text: str) -> list[str]:
    violations = []
    for i, ch in enumerate(text):
        if ch != "#":
            continue
        prev_ch = text[i - 1] if i > 0 else "\n"
        if prev_ch not in ("\n", " "):
            violations.append(f"位置{i}: '#' の直前が行頭/半角スペースでない（直前={prev_ch!r}）")
            continue
        j = i + 1
        while j < len(text) and text[j].isalpha() and text[j].isascii():
            j += 1
        tag_name = text[i + 1:j]
        if not tag_name:
            violations.append(f"位置{i}: '#' の直後にタグ名(英字)がない")
            continue
        next_ch = text[j] if j < len(text) else "\n"
        if not (next_ch in ("：", " ", "\n") or next_ch.isdigit()):
            violations.append(f"位置{i}: '#{tag_name}' の直後が許可された終端文字でない（直後={next_ch!r}）")
    return violations


def check_c13(au: Audit, full_text: str) -> None:
    violations = _hashtag_violations(full_text)
    au.add("C13_hashtag_boundary", not violations, "; ".join(violations) or "境界違反なし")


# --- C14 表形式の不使用 ---

def check_c14(au: Audit, full_text: str) -> None:
    reasons = []
    if "|" in full_text:
        reasons.append("半角パイプ(|)を含む")
    if "\t" in full_text:
        reasons.append("タブ文字を含む")
    if "<table" in full_text.lower():
        reasons.append("HTML表タグを含む")
    au.add("C14_no_table", not reasons, "; ".join(reasons) or "表形式なし")


# --- C15 見出しの存在と順序 ---

def _headings_in_order(text: str, headings: list[str]) -> str | None:
    pos = -1
    for h in headings:
        idx = text.find(h, pos + 1)
        if idx == -1:
            return f"見出し{h!r}が既定順で見つからない"
        pos = idx
    return None


def check_c15(au: Audit, part1_md: str, part2_md: str) -> None:
    err1 = _headings_in_order(part1_md, REQUIRED_HEADINGS_PART1)
    err2 = _headings_in_order(part2_md, REQUIRED_HEADINGS_PART2)
    errs = [e for e in (err1, err2) if e]
    au.add("C15_heading_order", not errs, "; ".join(errs) or "見出し順序OK")


# --- C16 数値整合（テンプレート差し込み分） ---

def check_c16(au: Audit, daily_data: dict, sections: dict) -> None:
    """compose_numeric.py / compose_lp_comment.py を同一入力で再実行し、
    post_bundle.jsonのテンプレート系セクションと完全一致することを確認する
    （独自の数値算出をしていないことの直接的な回帰チェック）。
    """
    mismatches = []
    expected = {
        "part0_target_date": compose_part0_target_date(daily_data),
        "part1_numeric": compose_part1_numeric(daily_data),
        "part2_numeric": compose_part2_numeric(daily_data),
        "lp_comment": compose_lp_comment(daily_data),
    }
    for key, exp in expected.items():
        if sections.get(key) != exp:
            mismatches.append(key)
    au.add("C16_numeric_match", not mismatches, f"不一致: {mismatches}" if mismatches else "テンプレート一致")


# --- C16b 散文中の数値転記検知 ---

_VALUE_UNIT_MARKERS = ("$", "¥", "%", "％", "万", "億", "兆")
_ETH_QTY_RE = re.compile(r"\d\s*ETH\b")
# v1.27（オーナー指示）: C16bが検知したいのは「市場データの数値の転記」であり、
# ラベル（プール名・Fear&Greedの区分名等）は数値ではない。daily_data.json中の
# "Base 0.3%プール"のようなラベルには数値表現が含まれるため、文字列の内容
# （数値を含むか）では判定できず、キー名で判定する必要がある（C18の教訓と
# 同型の欠陥——判定対象を誤ると症状ごとのallowlist対処が際限なく必要になる）。
_LABEL_KEYS = frozenset({"name", "label"})


def _looks_like_market_value(s: str) -> bool:
    """C16bの候補対象を「市場データの数値」に限定する（台本の例示は$64,247・12.72%等）。
    target_date_jst（2026-08-17）や retrieved_at のような日付・時刻の文字列は、
    ニュースの出典表記（媒体名、日付）と当然のように暦日が一致しうるため、
    候補から除外しないと構造的に誤爆する（実測で判明。テスト参照）。
    """
    if not any(ch.isdigit() for ch in s):
        return False
    if any(m in s for m in _VALUE_UNIT_MARKERS):
        return True
    return bool(_ETH_QTY_RE.search(s))


def _collect_numeric_strings(obj, out: set[str], min_len: int = C16B_MIN_LEN) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in _LABEL_KEYS:
                continue
            _collect_numeric_strings(v, out, min_len)
    elif isinstance(obj, list):
        for v in obj:
            _collect_numeric_strings(v, out, min_len)
    elif isinstance(obj, str):
        if len(obj) >= min_len and _looks_like_market_value(obj):
            out.add(obj)


def _is_digit_or_dot(ch: str) -> bool:
    return ch.isdigit() or ch in ".．"


def _find_transcriptions(daily_data: dict, llm_text: str, allowlist: set[str]) -> list[str]:
    candidates: set[str] = set()
    _collect_numeric_strings(daily_data, candidates)
    hits = []
    for s in sorted(candidates, key=len, reverse=True):
        if s in allowlist:
            continue
        start = 0
        while True:
            idx = llm_text.find(s, start)
            if idx == -1:
                break
            before = llm_text[idx - 1] if idx > 0 else ""
            after = llm_text[idx + len(s)] if idx + len(s) < len(llm_text) else ""
            if not _is_digit_or_dot(before) and not _is_digit_or_dot(after):
                hits.append(s)
                break
            start = idx + 1
    return hits


def check_c16b(au: Audit, daily_data: dict, sections: dict, llm_section_keys: list[str],
               allowlist: set[str], headline_for_image: str = "") -> None:
    # v1.20: headline_for_imageもLLM生成物であり、独立レビューで走査対象外
    # （図版下部帯に焼き込まれる文言が無検査）と指摘されたため対象に含める。
    llm_text = "\n".join(sections.get(k, "") for k in llm_section_keys) + "\n" + headline_for_image
    hits = _find_transcriptions(daily_data, llm_text, allowlist)
    detail = (f"検知網ヒット（限界あり・要人手確認。誤爆時は config/c16b_allowlist.json へ登録）: {hits}"
              if hits else "転記検知なし")
    au.add("C16b_transcription_scan", not hits, detail)


# --- C17 LP免責定型文 ---

def check_c17(au: Audit, lp_comment: str) -> None:
    missing = [s for s in (FIXED_2, FIXED_4, FIXED_5) if s not in lp_comment]
    au.add("C17_lp_disclaimers", not missing,
           "定型文完全一致" if not missing else f"欠落: {len(missing)}件")


# --- C18 断定表現 ---

def _causal_violations_in_sentence(sentence: str) -> list[str]:
    """1文内で「因果マーカー」と価格変動語が語順を問わず共存する組み合わせ、
    および単独で断定的な表現を検出する（v1.22改定）。ただし同一文に
    LIMITING_EXPRESSIONS（限定表現）が含まれる場合はPASSとする——判定が
    禁じたいのは「断定」であり、限定表現で締めた文は基準が求める正しい
    書き方であるため（v1.20時点の誤検知への対処。オーナー指示）。

    限界: 文単位の粗い判定であり、(1) 因果マーカーと価格変動語が実際には
    無関係な別の節にたまたま同一文中で共存するケース（例: 読点で繋がれた
    2つの独立した事象）は誤検知として残りうる、(2) LIMITING_EXPRESSIONSの
    「確認できません」は活用差（「確認はできません」等の助詞挿入）を
    吸収しない、(3) CAUSAL_MARKERS・PRICE_MOVEMENT_WORDSに無い語彙
    （例: 「きっかけに」等）は検知対象外。誤検知はconfig/c18_allowlist.json
    で個別に除外できるが、上記の設計変更により通常は不要な想定
    （DESIGN_CHANGES.md参照）。
    """
    hit_markers = [m for m in CAUSAL_MARKERS if m in sentence]
    hit_words = [w for w in PRICE_MOVEMENT_WORDS if w in sentence]
    hit_standalone = [p for p in CAUSAL_STANDALONE_PHRASES if p in sentence]
    if not (hit_markers and hit_words) and not hit_standalone:
        return []
    if any(le in sentence for le in LIMITING_EXPRESSIONS):
        return []
    hits = []
    if hit_markers and hit_words:
        hits.append(f"マーカー{hit_markers}と価格変動語{hit_words}が同一文に存在（限定表現なし）")
    if hit_standalone:
        hits.append(f"断定的表現{hit_standalone}（限定表現なし）")
    return hits


def check_c18(au: Audit, sections: dict, llm_section_keys: list[str], allowlist: set[str]) -> None:
    llm_text = "\n".join(sections.get(k, "") for k in llm_section_keys)
    hits = []
    for sentence in re.split(r"[。\n]", llm_text):
        if not sentence.strip() or any(s in sentence for s in allowlist):
            continue
        hits += _causal_violations_in_sentence(sentence)
    detail = (f"検出（限界あり・完全な保証ではない。誤検知時は config/c18_allowlist.json へ登録）: {hits}"
              if hits else "断定表現なし")
    au.add("C18_causal_assertion", not hits, detail)


# --- C19 監査台帳（L0のみ検査） ---

def _field_present(e: dict, field: str) -> bool:
    """フィールドが実質的に空でないかを判定する（v1.20）。
    `str(None)` == "None"（非空文字列）になるため、旧実装の
    `str(e.get(f, "")).strip()` はJSONのnullを「充足」と誤判定していた
    （独立レビューで実行確認）。値が存在しない・Noneの場合は不充足として扱う。
    """
    v = e.get(field)
    return v is not None and str(v).strip() != ""


def check_c19(au: Audit, level: str, audit_ledger, candidate_count: int) -> None:
    if level != "L0":
        au.add("C19_audit_ledger", None, f"level={level} のためSKIP（呼び出しA失敗時は台帳が原理的に存在しない）")
        return
    if not isinstance(audit_ledger, list):
        au.add("C19_audit_ledger", False, "audit_ledgerがリストでない")
        return
    if not audit_ledger:
        # v1.17改定: audit_ledgerは「採否を判断した全候補の記録」（台本・
        # 統合運用基準の要求）。空配列を許容できるのは、当日の候補自体が
        # 1件も無かった（news_candidates_todayが空）場合のみ。候補が
        # 1件でも渡されていたのに空配列は「採否記録を怠った」可能性と
        # 区別できないためFAIL（RSS取得の成否ではなく候補の有無で判定する
        # — 取得自体は成功しても対象日該当0件のソースがあるため、v1.15の
        # 「RSSが1ソース成功していれば許容」は緩すぎた）。
        ok = candidate_count == 0
        au.add("C19_audit_ledger", ok,
               "空配列（当日の候補自体が0件のため許容）" if ok
               else f"空配列だが当日の候補が{candidate_count}件存在（採否記録が必要でFAIL）")
        return
    required_fields = ("source", "url", "published_at", "decision", "reason")
    bad = [i for i, e in enumerate(audit_ledger)
           if not isinstance(e, dict) or any(not _field_present(e, f) for f in required_fields)]
    if bad:
        au.add("C19_audit_ledger", False, f"{len(audit_ledger)}件中フィールド欠落: {bad}")
        return
    # v1.21改定: 「渡した候補数」とaudit_ledgerの件数を照合する（オーナー指示）。
    # 渡した全候補を1件残らず記録する設計（v1.17）である以上、件数の不一致は
    # 「一部を静かに取りこぼした」ことを意味し、フィールド充足だけでは検知できない。
    if len(audit_ledger) != candidate_count:
        au.add("C19_audit_ledger", False,
               f"渡した候補{candidate_count}件に対しaudit_ledgerは{len(audit_ledger)}件（件数不一致）")
        return
    au.add("C19_audit_ledger", True, f"{len(audit_ledger)}件・全フィールド充足・渡した候補数と一致")


# --- C20 図版ヘッドライン ---

def _zenkaku_len(s: str) -> float:
    total = 0.0
    for ch in s:
        code = ord(ch)
        if code < 0x100 or 0xFF61 <= code <= 0xFF9F:
            total += 0.5  # 半角（ASCII可視文字・半角カナ相当）
        else:
            total += 1.0  # 全角
    return total


def check_c20(au: Audit, headline_for_image: str) -> None:
    reasons = []
    if "#" in headline_for_image:
        reasons.append("'#' を含む")
    zlen = _zenkaku_len(headline_for_image)
    if zlen > 40:
        reasons.append(f"全角換算{zlen:.1f}字（40字超）")
    au.add("C20_image_headline", not reasons, "; ".join(reasons) or f"全角換算{zlen:.1f}字・#なし")


# --- C21・C22共通: ニュースソース名→tier ---

def _load_source_tier_map() -> dict[str, int]:
    """config/news_sources.jsonのsource名→tierを読み込む。collect_news.pyの
    Google Newsはニュース設定ファイルに載らない別枠（tier4・候補発見専用）
    のため個別に加える。読み込み失敗時は空dictを返し、C21・C22はすべての
    sourceをtier不明として扱う（フェイルクローズ。未知sourceの"採用"を
    誤ってPASSさせない）。
    """
    path = Path(__file__).parent.parent / "config" / "news_sources.json"
    tier_map: dict[str, int] = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for s in data.get("sources", []):
            if isinstance(s, dict) and "name" in s and "tier" in s:
                tier_map[s["name"]] = s["tier"]
    except (ValueError, OSError):
        pass
    tier_map.setdefault(collect_news.GOOGLE_NEWS_NAME, 4)
    return tier_map


# --- C21 audit_ledgerのdecisionとtierの整合 ---

def check_c21(au: Audit, level: str, audit_ledger, candidate_count: int,
              tier_map: dict[str, int]) -> None:
    if level != "L0" or not isinstance(audit_ledger, list) or not audit_ledger:
        au.add("C21_decision_tier_consistency", None,
               f"level={level}・candidate_count={candidate_count}のためSKIP"
               "（台帳の有無・完全性はC19が判定するためここでは扱わない）")
        return
    # v1.29（オーナー承認・案1）: 「独立2ソース」の妥当性は対象日の
    # audit_ledger内で同一decisionを持つ distinct source の件数のみで
    # 機械判定する。「同一事実を報じているか」の意味的な照合はしない
    # （既知の限界。DESIGN_CHANGES.md参照）——C18と同型の判断で、
    # 機械的に確定できない基準は誤検知を必ず生み、フェイルクローズ下では
    # 誤検知がそのまま「本文が生成されない日」に直結するため、確実な
    # 偽陽性を招くより稀な偽陰性を許容する。
    dual_sources = {
        e.get("source") for e in audit_ledger
        if isinstance(e, dict) and e.get("decision") == "採用（独立2ソース）"
    }
    violations = []
    for i, e in enumerate(audit_ledger):
        if not isinstance(e, dict):
            violations.append(f"[{i}] エントリがオブジェクトでない")
            continue
        decision = e.get("decision")
        source = e.get("source")
        if decision == "不採用":
            continue
        if decision == "採用":
            tier = tier_map.get(source)
            if tier not in (1, 2):
                # v1.59（オーナー承認）: tier2（Reuters・Google News経由で
                # 実体確認済み）はtier1と同様に単独採用可能（統合運用基準§2の
                # 優先度2・独立報道）。DESIGN_CHANGES.md v1.58・v1.59参照。
                violations.append(f"[{i}] source={source!r}（tier={tier!r}）が採用だがtier1・tier2でない")
        elif decision == "採用（独立2ソース）":
            if len(dual_sources) < 2:
                violations.append(
                    f"[{i}] source={source!r} が独立2ソースだが対象日のdistinct sourceは"
                    f"{len(dual_sources)}件（{sorted(dual_sources)}）")
        else:
            violations.append(f"[{i}] 未知のdecision値: {decision!r}")
    detail = "; ".join(violations) if violations else f"{len(audit_ledger)}件・整合性OK"
    au.add("C21_decision_tier_consistency", not violations, detail)


# --- C22 図版でなく本文ヘッドラインのtier1・tier2裏付け ---

def check_c22(au: Audit, part1_headline, audit_ledger, tier_map: dict[str, int],
              intraday_range: dict | None = None) -> None:
    """part1_headlineが定型文かどうかと、根拠（tier1・tier2採用・独立2ソース
    採用・notable_move）の有無との整合を検査する（v1.44改定・v1.59でtier2を
    追加・オーナー承認）。

    呼び出しA失敗等でpart1_headlineが文字列でない場合は、この検査自体が
    無意味なためSKIP（縮退時の話であり、本検査が対象とする「モデルが
    定型文を選んだ/実文言を書いた」という判断の話ではない）。
    """
    if not isinstance(part1_headline, str):
        au.add("C22_headline_tier1_basis", None, "part1_headlineが文字列でない（呼び出しA失敗等）のためSKIP")
        return

    # v1.59（オーナー承認）: tier2（Reuters・実体確認済み）もtier1と同様に
    # part1_headlineの正当な根拠になる（DESIGN_CHANGES.md v1.58・v1.59参照）。
    has_tier1_adopted = isinstance(audit_ledger, list) and any(
        isinstance(e, dict) and e.get("decision") == "採用" and tier_map.get(e.get("source")) in (1, 2)
        for e in audit_ledger
    )
    # v1.44（オーナー指示）: 独立2ソース材料単独（tier1・tier2裏付けなし）も
    # part1_headlineの正当な根拠になりうる（NO_CANDIDATES_FALLBACKの②）。
    has_pair_adopted = isinstance(audit_ledger, list) and any(
        isinstance(e, dict) and e.get("decision") == "採用（独立2ソース）"
        for e in audit_ledger
    )
    # v1.42（オーナー指示）: notable_move（24時間の値動き）はニュースの
    # 情報源階層（tier1/tier3等）の対象外の市場データ。
    has_notable_move = isinstance(intraday_range, dict) and any(
        isinstance(v, dict) and v.get("notable_move") is True for v in intraday_range.values()
    )

    is_fixed = part1_headline == generate_post.FIXED_HEADLINE
    if is_fixed:
        # v1.44（オーナー指示）: 根拠（tier1採用・独立2ソース採用・
        # notable_move）が存在するにもかかわらず定型文のままになっている
        # 状態は、8/23（BitMart）・8/24（Bitmine）・8/26（BankChain
        # Alliance）で繰り返し実測された「ヘッドラインと本文の矛盾」の
        # パターンであり、本来FAILとして検出すべき（従来は定型文なら
        # 無条件SKIPだった）。
        basis = []
        if has_tier1_adopted:
            basis.append("tier1・tier2由来の採用")
        if has_pair_adopted:
            basis.append("独立2ソース採用")
        if has_notable_move:
            basis.append("notable_move")
        if basis:
            au.add("C22_headline_tier1_basis", False,
                   f"定型文ヘッドラインだが{'/'.join(basis)}が存在（本文に未反映の可能性）")
            return
        au.add("C22_headline_tier1_basis", None, "材料なし（定型文ヘッドライン）のためSKIP")
        return

    if has_tier1_adopted:
        au.add("C22_headline_tier1_basis", True, "tier1・tier2由来の採用が存在")
        return
    if has_pair_adopted:
        au.add("C22_headline_tier1_basis", True, "独立2ソース採用が存在（v1.44・ヘッドラインの根拠として有効）")
        return
    if has_notable_move:
        au.add("C22_headline_tier1_basis", None,
               "tier1・tier2由来の採用・独立2ソース採用は無いがnotable_move（24時間の値動き）が存在するためSKIP"
               "（値動きは情報源階層の対象外）")
        return
    au.add("C22_headline_tier1_basis", False,
           "ヘッドラインが定型文でないにもかかわらずtier1・tier2由来の採用・独立2ソース採用・notable_moveのいずれも存在しない")


# --- C23 総括の固有名詞バックリファレンス ---

# v1.44（オーナー指示）: 総括（part2_summary）が本文（part1_points）で
# 確認されていない固有名詞を持ち出す事象が8/23（BitMart）・8/24
# （Bitmine）・8/26（米PCEインフレ指標・SEC）と3回実データで再現し、
# プロンプトへの抑止指示（v1.35「総括で言及してよい固有名詞・材料は
# part1_pointsに掲載済みのもの、またはreusable_for_summaryに渡された
# 継続材料に限る」）では防げないことが確認されたため、機械ゲートで
# 対処する。
#
# 実装方針（固有名詞の完全な抽出＝日本語NERは行わない）: 英字大文字で
# 始まるASCII表記のトークン（組織名・企業名・指標略称。例: SEC・PCE・
# BitMart・Bitmine・BankChain）のみを機械的に抽出し、part1_points・
# reusable_for_summaryに同じ文字列が存在するかを照合する。判定対象を
# ASCII表記に絞るのは、(1) 実際に確認された3件の違反事例がいずれも
# ASCII表記だったため対象を絞っても既知の事例は捕捉できる、(2) 片仮名・
# 漢字表記の一般語彙（「インフレ」「規則」等）とASCII表記でない固有名詞
# （日本銀行・金融庁等）を区別する簡便な機械的手段がなく、無差別に
# 抽出すると確実な偽陽性を招くため（C16b・C18・C21と同じ判断——機械的に
# 確実な側で吸収する）。既知の限界: 片仮名・漢字表記の固有名詞は検知
# 対象外。BTC・ETH等の基軸銘柄名・単位・略称は「材料」ではなく常時
# 参照される一般語彙とみなしallowlistで除外する。
_PROPER_NOUN_RE = re.compile(r"[A-Z][A-Za-z0-9&.\-]{1,}")
_PROPER_NOUN_ALLOWLIST = {
    "BTC", "ETH", "BNB", "USDC", "USD", "JPY", "JST", "NY",
    "TVL", "APR", "DEX", "LP", "IL", "ETF", "API", "V3",
    # Fear & Greed指数の分類ラベル（daily_data.jsonのmarket.fear_greed.label由来の
    # 固定語彙・CoinMarketCap APIの定型区分名であり、本文材料ではない）。
    # 8/26実データの実チェックで「Fear&Greed」「Extreme」が誤検知したため追加
    # （「Fear&Greed指数がExtreme greedを示しており」のような記述）。
    "FEAR", "GREED", "EXTREME", "NEUTRAL", "FEAR&GREED",
}


def check_c23(au: Audit, part2_summary, part1_points, reusable_for_summary) -> None:
    if not isinstance(part2_summary, str) or not part2_summary.strip():
        au.add("C23_summary_no_new_entities", None, "part2_summaryが空のためSKIP")
        return
    candidates = {m for m in _PROPER_NOUN_RE.findall(part2_summary)
                  if m.upper() not in _PROPER_NOUN_ALLOWLIST}
    if not candidates:
        au.add("C23_summary_no_new_entities", True, "総括に固有名詞候補（ASCII表記）なし")
        return
    backing = str(part1_points or "")
    if isinstance(reusable_for_summary, list):
        backing += "\n" + "\n".join(str(x) for x in reusable_for_summary)
    missing = sorted(c for c in candidates if c not in backing)
    if missing:
        au.add("C23_summary_no_new_entities", False,
               "総括に本文未確認の固有名詞候補（限界あり・ASCII表記のみ検知。"
               f"誤検知時は要目視確認）: {missing}")
        return
    au.add("C23_summary_no_new_entities", True,
           f"固有名詞候補{len(candidates)}件・すべてpart1_points/reusable_for_summaryに存在")


# --- C24 市場のフローの固有名詞バックリファレンス（part1_points限定） ---

# v1.56（オーナー指示）: 2026-08-29（土曜）の実データで、part1_headlineが
# 定型文「主要なマクロ材料は確認できない」（tier1裏付け・独立2ソース・
# notable_moveいずれも無し）にもかかわらず、part2_flowにETF資金流出・
# Polygon脆弱性開示という具体的な材料が書かれ、読者から見て矛盾する
# 事象が発生した（8/24・8/26に続き3回目）。原因は、呼び出しAが不採用と
# 判断しreusable_for_summary（継続監視材料）へ回した材料を、呼び出しBが
# part2_flowで本格的な因果連鎖（「材料→意識された可能性→値動き」）の
# 材料として使ってしまうこと。CALL_B_INSTRUCTIONSでpart2_flowの材料を
# part1_points採用済みのものに限定したが、C18・C23と同じ理由（指示が
# あってもLLMが常に遵守するとは限らない）で機械ゲートを追加する。
#
# C23（part2_summary用）とは独立したゲートとする（オーナー指示）。
# 最も重要な違い: バックリファレンス先をpart1_pointsのみに限定し、
# reusable_for_summaryを含めない——part2_summaryは継続材料の1行言及を
# 許容する（v1.35）が、part2_flowは因果連鎖を組む分より踏み込んだ主張に
# なるため、根拠の基準を厳しくする（v1.56・オーナー指示）。C23の
# allowlist（_PROPER_NOUN_ALLOWLIST）とは別に_PROPER_NOUN_ALLOWLIST_C24を
# 持ち、part2_flow特有の誤検知をpart2_summary側の判定に影響させず
# 独立して育てられるようにする（オーナー指示）。共通の一般語彙
# （BTC・ETH・Fear&Greed等）は基底として継承する。
_PROPER_NOUN_ALLOWLIST_C24 = set(_PROPER_NOUN_ALLOWLIST) | {
    # 2026-08-26実データ（ニュース材料が無い日のpart2_flow第2文、
    # CALL_B_INSTRUCTIONSが明示的に許容する「国内取引所とDEXの出来高動向」
    # の定型的な言及）で誤検知したため追加。「bitFlyer」は正規表現が
    # 小文字始まりの"bit"を含めず"Flyer"のみを抽出するため、登録も
    # "FLYER"（マッチ単位）で行う——"BITFLYER"では一致しない。
    "FLYER", "COINCHECK", "BASE",
}


def check_c24(au: Audit, part2_flow, part1_points) -> None:
    if not isinstance(part2_flow, str) or not part2_flow.strip():
        au.add("C24_flow_no_unadopted_material", None, "part2_flowが空のためSKIP")
        return
    candidates = {m for m in _PROPER_NOUN_RE.findall(part2_flow)
                  if m.upper() not in _PROPER_NOUN_ALLOWLIST_C24}
    if not candidates:
        au.add("C24_flow_no_unadopted_material", True, "市場のフローに固有名詞候補（ASCII表記）なし")
        return
    backing = str(part1_points or "")
    missing = sorted(c for c in candidates if c not in backing)
    if missing:
        au.add("C24_flow_no_unadopted_material", False,
               "市場のフローにpart1_points未確認の固有名詞候補（限界あり・ASCII表記のみ検知。"
               f"誤検知時は要目視確認）: {missing}")
        return
    au.add("C24_flow_no_unadopted_material", True,
           f"固有名詞候補{len(candidates)}件・すべてpart1_pointsに存在")


def run_all(bundle: dict, daily_data: dict) -> Audit:
    au = Audit()
    sections = bundle["sections"]
    llm_keys = bundle["llm_section_keys"]
    headline_for_image = bundle.get("headline_for_image", "")
    # v1.20: headline_for_imageもLLM生成物であり、full_text（C12/C13/C14の
    # 走査対象）へ含める。C13/C14は元々headline_for_imageに違反があれば
    # 検知して問題ない（副次的な網羅性向上）。
    full_text = bundle["part1_md"] + "\n" + bundle["part2_md"] + "\n" + headline_for_image
    target_date = bundle.get("target_date_jst", "")
    c16b_allowlist = _load_allowlist(target_date, "c16b_allowlist.json")
    c18_allowlist = _load_allowlist(target_date, "c18_allowlist.json")

    check_c12(au, full_text)
    check_c13(au, full_text)
    check_c14(au, full_text)
    check_c15(au, bundle["part1_md"], bundle["part2_md"])
    check_c16(au, daily_data, sections)
    check_c16b(au, daily_data, sections, llm_keys, c16b_allowlist, headline_for_image)
    check_c17(au, sections.get("lp_comment", ""))
    check_c18(au, sections, llm_keys, c18_allowlist)
    # news_candidate_countが欠落している場合は「0件」と区別できないよう
    # 負値を渡す（フェイルクローズ。存在しないキーを0件と混同して
    # 空配列を誤って許容しないようにする）。
    check_c19(au, bundle["level"], bundle.get("audit_ledger"), bundle.get("news_candidate_count", -1))
    check_c20(au, headline_for_image)
    tier_map = _load_source_tier_map()
    check_c21(au, bundle["level"], bundle.get("audit_ledger"), bundle.get("news_candidate_count", -1), tier_map)
    check_c22(au, sections.get("part1_headline"), bundle.get("audit_ledger"), tier_map,
              daily_data.get("intraday_range"))
    check_c23(au, sections.get("part2_summary"), sections.get("part1_points"),
              bundle.get("reusable_for_summary"))
    check_c24(au, sections.get("part2_flow"), sections.get("part1_points"))
    return au


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: verify_post.py <post_bundle.jsonのパス>", file=sys.stderr)
        return 1
    bundle_path = Path(sys.argv[1])
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    target_date = bundle.get("target_date_jst", "")
    daily_data_path = Path(f"outputs/{target_date}/daily_data.json")
    daily_data = json.loads(daily_data_path.read_text(encoding="utf-8"))

    au = run_all(bundle, daily_data)
    compact = target_date.replace("-", "")
    audit = {
        "overall": "PASS" if au.failed == 0 else "FAIL",
        "failed": au.failed,
        "level": bundle["level"],
        "checks": au.checks,
    }
    out_path = bundle_path.parent / f"post_audit_{compact}.json"
    out_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if au.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
