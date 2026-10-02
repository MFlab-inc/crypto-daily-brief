#!/usr/bin/env python3
"""verify_post.py — 本文の機械監査 C12〜C28（v0.3 §8・§10 第2弾-6。C23〜C28は後続の版で追加。
v1.85で「警告（WARN）」＝FAILにしない向きの食い違いの検知も追加）。

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
# v1.81（オーナー承認・運用上の変更）: 【主要指標】【主要指標（詳細）】は
# 投稿本文（part1_md・part2_md）から外し、numeric_record.md（監査専用）で
# のみ保全することになった（compose_post.render_markdown()参照）。C15は
# 「実際に投稿される全文」の見出し順を検査する趣旨のため、この2見出しを
# 必須リストから除く。数値の内容自体の正しさはC16が引き続き検査する
# （C16はbundle["sections"]と比較しており、この変更の影響を受けない）。
REQUIRED_HEADINGS_PART1 = ["【対象日】", "【ヘッドライン】", "【主要なポイント】"]
REQUIRED_HEADINGS_PART2 = ["【市場のフロー】", "【LP運用者向けに一言】", "【総括】"]
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
    au.add("C12_banned_terms", not hits, f"検出: {hits}" if hits else "禁止語なし", terms=list(hits))


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
    au.add("C16b_transcription_scan", not hits, detail, hits=list(hits))


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


def _find_c18_violations(sections: dict, llm_section_keys: list[str], allowlist: set[str],
                          headline_for_image: str = "") -> list[dict]:
    """C18の検知をセクション単位で行い、違反文をセクションへ帰属させて返す
    （v1.76・repair_post.pyが局所修正の対象文を特定するために使う）。

    従来実装は4セクションを"\n"でjoinしてから一括で文分割していたが、
    どのセクション由来の違反かをコードが追跡できなかった。本関数は
    セクションごとに同じ分割・判定を適用する——joinに使う"\n"自体が
    分割文字でもあるため、文がセクション境界をまたいで結合されることは
    なく、検知結果（PASS/FAILおよびhitsの内容）は旧実装と完全に同値
    （test_bundle2.pyの既存C18回帰テストで確認）。
    返す"sentence"は`re.split`が返す生の部分文字列（区切り文字・前後の
    空白を除去していない）——post_bundle.json内の元テキストへの
    `str.replace(sentence, ..., 1)`による置換で使うため、意図的に
    stripしていない。

    headline_for_image（v1.79・オーナー承認）: 2026-09-24分の
    headline_for_image「米金利上昇でBTC・ETHは軟調推移」が原因を断定する
    表現でありながらC18の対象外（sections・llm_section_keysに含まれない）
    のためPASSしていた事象への対処。sections由来ではないため専用の
    section名"headline_for_image"で違反を帰属させる。repair_post.pyの
    局所修正（_find_c18_targets）は本引数を渡さないため、この経路の
    違反は自動修正の対象に含めない（本セッションで承認されたのは検知の
    拡張のみで、修正ロジックの拡張は別途）。
    """
    violations = []
    for key in llm_section_keys:
        text = sections.get(key, "")
        if not isinstance(text, str):
            continue
        for sentence in re.split(r"[。\n]", text):
            if not sentence.strip() or any(s in sentence for s in allowlist):
                continue
            reasons = _causal_violations_in_sentence(sentence)
            if reasons:
                violations.append({"section": key, "sentence": sentence, "reasons": reasons})
    if isinstance(headline_for_image, str) and headline_for_image:
        for sentence in re.split(r"[。\n]", headline_for_image):
            if not sentence.strip() or any(s in sentence for s in allowlist):
                continue
            reasons = _causal_violations_in_sentence(sentence)
            if reasons:
                violations.append({"section": "headline_for_image", "sentence": sentence, "reasons": reasons})
    return violations


def check_c18(au: Audit, sections: dict, llm_section_keys: list[str], allowlist: set[str],
              headline_for_image: str = "") -> None:
    violations = _find_c18_violations(sections, llm_section_keys, allowlist, headline_for_image)
    hits = [r for v in violations for r in v["reasons"]]
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

def check_c22(au: Audit, part1_headline, audit_ledger, tier_map: dict[str, int]) -> None:
    """part1_headlineが定型文かどうかと、根拠（tier1・tier2採用・独立2ソース
    採用）の有無との整合を検査する（v1.44改定・v1.59でtier2を追加・オーナー
    承認）。

    v1.82（オーナー承認）: notable_move（24時間の値動き）は、ヘッドラインの
    根拠として扱わない。統合運用基準§3.1により【ヘッドライン】に価格・24時間比・
    値動きを書かないため、材料（tier1・tier2採用・独立2ソース採用）が無い日は
    notable_moveの有無によらず定型文が正しい（大きな値動きはheadline_for_image
    と【市場のフロー】の最終段階で伝える）。従来はnotable_moveがあると定型文
    ヘッドラインをFAILとし、値動きを主題にした非定型文ヘッドラインをSKIPと
    していたが、この扱いは廃止した（引数intraday_rangeも廃止）。

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

    is_fixed = part1_headline == generate_post.FIXED_HEADLINE
    if is_fixed:
        # v1.44（オーナー指示）: 根拠（tier1採用・独立2ソース採用）が
        # 存在するにもかかわらず定型文のままになっている
        # 状態は、8/23（BitMart）・8/24（Bitmine）・8/26（BankChain
        # Alliance）で繰り返し実測された「ヘッドラインと本文の矛盾」の
        # パターンであり、本来FAILとして検出すべき（従来は定型文なら
        # 無条件SKIPだった）。
        basis = []
        if has_tier1_adopted:
            basis.append("tier1・tier2由来の採用")
        if has_pair_adopted:
            basis.append("独立2ソース採用")
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
    au.add("C22_headline_tier1_basis", False,
           "ヘッドラインが定型文でないにもかかわらずtier1・tier2由来の採用・独立2ソース採用のいずれも存在しない")


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

# v1.62（オーナー指示）: v1.53のscheduled_events（経済カレンダー）導入以降、
# 本文に通貨コード（CAD・NZD等）が出現する頻度が上がり、C23・C24の
# 「ASCII大文字始まりの一般語彙」誤検知パターンが3回再発した（v1.56の
# Base/Coincheck/Flyer、v1.57のBase/DeFi、9/2の['CAD','NZD']）。個別の
# allowlist追加を繰り返すのではなく、ISO 4217（通貨コード）が有限・確定の
# リストであることを利用し、全コードを基底allowlistへ一括登録することで
# 将来の再発を構造的に防ぐ。scheduled_eventsには主要通貨に限らず想定外の
# 国の指標も現れ得るため、主要通貨だけでなくISO 4217の現行アクティブ
# コード全体（ISO 4217 Table A.1、資金の代替単位・貴金属コード含む）を
# 対象とする。ISO標準の通貨コードは自明に「本文で新規に持ち出された材料」
# ではないため、これらをallowlistに含めても検知精度は損なわれない。
_ISO4217_CURRENCY_CODES = {
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BOV",
    "BRL", "BSD", "BTN", "BWP", "BYN", "BZD",
    "CAD", "CDF", "CHE", "CHF", "CHW", "CLF", "CLP", "CNY", "COP", "COU",
    "CRC", "CUC", "CUP", "CVE", "CZK",
    "DJF", "DKK", "DOP", "DZD",
    "EGP", "ERN", "ETB", "EUR",
    "FJD", "FKP",
    "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD",
    "HKD", "HNL", "HTG", "HUF",
    "IDR", "ILS", "INR", "IQD", "IRR", "ISK",
    "JMD", "JOD", "JPY",
    "KES", "KGS", "KHR", "KMF", "KPW", "KRW", "KWD", "KYD", "KZT",
    "LAK", "LBP", "LKR", "LRD", "LSL", "LYD",
    "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU", "MUR", "MVR",
    "MWK", "MXN", "MXV", "MYR", "MZN",
    "NAD", "NGN", "NIO", "NOK", "NPR", "NZD",
    "OMR",
    "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG",
    "QAR",
    "RON", "RSD", "RUB", "RWF",
    "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP", "SLE", "SOS", "SRD",
    "SSP", "STN", "SVC", "SYP", "SZL",
    "THB", "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS",
    "UAH", "UGX", "USD", "USN", "UYI", "UYU", "UYW", "UZS",
    "VED", "VES", "VND", "VUV",
    "WST",
    "XAF", "XAG", "XAU", "XBA", "XBB", "XBC", "XBD", "XCD", "XDR", "XOF",
    "XPD", "XPF", "XPT", "XSU", "XTS", "XUA", "XXX",
    "YER",
    "ZAR", "ZMW", "ZWG",
}

_PROPER_NOUN_ALLOWLIST = {
    "BTC", "ETH", "BNB", "USDC", "USD", "JPY", "JST", "NY",
    "TVL", "APR", "DEX", "LP", "IL", "ETF", "API", "V3",
    # Fear & Greed指数の分類ラベル（daily_data.jsonのmarket.fear_greed.label由来の
    # 固定語彙・CoinMarketCap APIの定型区分名であり、本文材料ではない）。
    # 8/26実データの実チェックで「Fear&Greed」「Extreme」が誤検知したため追加
    # （「Fear&Greed指数がExtreme greedを示しており」のような記述）。
    # 9/8実データで「Index」単独が誤検知したため追加（「Fear & Greed Index」
    # という英語表記の一部であり、本文材料の新規持ち出しではない）。
    "FEAR", "GREED", "EXTREME", "NEUTRAL", "FEAR&GREED", "INDEX",
} | _ISO4217_CURRENCY_CODES


# v1.83（オーナー承認・2026-09-30）: 機関名の表記ゆれ（同義語）の照合。
# 9/29分でC23が総括の「Fed」をFAILした（原文は未確認）。本文が「FRB」「米連邦
# 準備制度理事会」など別の表記で同じ機関を書いていても、総括が「Fed」と書くと
# 文字列一致で「本文未確認の固有名詞」と誤判定される——同じ機関を指す表記の
# ゆれは新規の持ち出しではない。機関ごとに同義語の集合を定め、総括の固有名詞候補が
# その集合のいずれかの表記で照合先に存在すれば「確認済み」とする。
#
# 許可リスト（案B: SEC・CFTCを無条件に候補から除外する）は採用しない（オーナー
# 判断）。同義語照合は「本文のどこかに同じ機関の記述がある」場合に限って確認済みと
# するため、根拠の無い「SECの…」「Fedの…」の持ち出し（8/26型の真の新規持ち出し）は
# 従来どおりFAILになる。別の機関の同義語では確認済みにならない（例: 本文がFRBだけ
# の日に総括がSECと書けばFAIL）。
#
# 英字の表記は「ASCII英数字に挟まれない」場合のみ一致とみなす（FRBがFedExの中の
# Fedに一致しない等。_ROLE_TERM_PATTERNSと同じ理由で\bは使わない）。日本語の表記は
# 部分一致（「連邦準備」は連邦準備制度・連邦準備理事会・連邦準備制度理事会・
# 米連邦準備理事会のすべてに含まれる）。既存の挙動（候補の文字列そのものが
# 照合先に部分一致すれば確認済み）は維持する——本機構は既存より厳しくならない
# （同義語による確認済みの追加のみ）。
#
# 限界: (1) 総括側で機関名を検知できるのはASCII表記の略称（Fed・FRB・FOMC・SEC・
# CFTC・BOJ・ECB・BOE）のみ（日銀・日本銀行など日本語表記はC23の検知対象外）。
# 英語の正式名称（Federal Reserve等）は照合先側の同義語としてのみ扱う。
# (2) C23（総括）とC24（市場のフロー）に同じ同義語照合を適用する（C24へはv1.84・オーナー承認）。
#     C24の照合先は従来どおり part1_headline・part1_points のみ（reusable_for_summaryを含めない。v1.56）。
# 大文字小文字の表記ゆれ（英語報道で一般的な「BoJ」「BoE」、全大文字の「FED」）は、
# 全面的な大文字小文字の無視（本文の「sec」＝秒や動詞の「fed」がSEC・Fedの根拠に
# なる偽PASSを生む）ではなく、明示的な同義語として登録する（独立レビューの指摘。v1.83）。
_INSTITUTION_ALIAS_GROUPS = (
    ("Fed", "FED", "FRB", "FOMC", "Federal Reserve", "連邦準備", "連邦公開市場委員会"),
    ("SEC", "Securities and Exchange Commission", "証券取引委員会"),
    ("CFTC", "Commodity Futures Trading Commission", "商品先物取引委員会"),
    ("BOJ", "BoJ", "Bank of Japan", "日銀", "日本銀行"),
    ("ECB", "European Central Bank", "欧州中央銀行"),
    ("BOE", "BoE", "Bank of England", "英中銀", "イングランド銀行"),
)
# 総括の固有名詞候補（ASCIIの略称。空白を含まない英字表記）から同義語の集合を引く
_INSTITUTION_ALIAS_INDEX: dict[str, tuple[str, ...]] = {
    alias.upper(): group
    for group in _INSTITUTION_ALIAS_GROUPS
    for alias in group
    if alias.isascii() and " " not in alias
}


def _alias_in_text(alias: str, text: str) -> bool:
    """aliasがtextに存在するか。ASCII表記はASCII英数字に挟まれない場合のみ一致、
    日本語表記は部分一致。"""
    if alias.isascii():
        return re.search(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", text) is not None
    return alias in text


def _is_backed(candidate: str, backing: str) -> bool:
    """総括の固有名詞候補が照合先textで確認済みか。候補の文字列そのものが部分一致する
    （従来の判定）、または同じ機関を指す同義語のいずれかが存在すれば確認済み。"""
    if candidate in backing:
        return True
    # 候補は[A-Za-z0-9&.\-]の連続として抽出されるため、末尾に句読点相当（. - &）が
    # 付くことがある（例: 英文の「SEC.」）。同義語の検索キーからは除く。
    group = _INSTITUTION_ALIAS_INDEX.get(candidate.rstrip(".-&").upper())
    return bool(group) and any(_alias_in_text(a, backing) for a in group)


def check_c23(au: Audit, part2_summary, part1_points, reusable_for_summary, scheduled_events=None,
              part1_headline=None) -> None:
    """v1.83（オーナー承認）: 機関名（Fed・FRB・FOMC・SEC・CFTC・BOJ・ECB・BOE）は
    同義語（日本語表記を含む）のいずれかが照合先にあれば確認済みとする
    （_INSTITUTION_ALIAS_GROUPS参照。無条件の許可リストではない）。
    part1_headline（v1.82・オーナー承認）: バックリファレンス先へ、part1_points
    に加えてpart1_headlineも含める。part1_headlineは当日の最重要材料を書く欄で
    あり、part1_pointsとは別の材料（例: 9/23の「FRBの利上げ観測」）を載せる
    ことがある。総括がその材料に触れることは「本文で確認済みの材料への言及」
    であり、新規の持ち出しではない。9/23の試験生成（9サンプル中2件）で、
    ヘッドラインにのみあるFRBを総括が言及してC23がFAILした事象への対処
    （C24へのpart1_headline追加と同じ理由・同じ扱い。v1.82参照）。
    scheduled_events（v1.79・オーナー承認）: 2026-09-25分でC23が'BOE'を
    誤検知した。原因はBOE総裁講演がその日のdaily_data.scheduled_events
    （経済カレンダー。generate_post.SCHEDULED_EVENTS_GUIDANCE参照）に
    載っていた予定であり、統合運用基準§3.1の【総括】欄は「翌日に確認す
    べき対象」を記載してよいと定めているため、scheduled_eventsに実在する
    固有名詞を総括で言及すること自体は正当な記述だったこと。part1_points・
    reusable_for_summaryに加え、scheduled_eventsの各titleもバック
    リファレンス対象へ含める。
    """
    if not isinstance(part2_summary, str) or not part2_summary.strip():
        au.add("C23_summary_no_new_entities", None, "part2_summaryが空のためSKIP")
        return
    candidates = {m for m in _PROPER_NOUN_RE.findall(part2_summary)
                  if m.upper() not in _PROPER_NOUN_ALLOWLIST}
    if not candidates:
        au.add("C23_summary_no_new_entities", True, "総括に固有名詞候補（ASCII表記）なし")
        return
    backing = str(part1_points or "") + "\n" + str(part1_headline or "")
    if isinstance(reusable_for_summary, list):
        backing += "\n" + "\n".join(str(x) for x in reusable_for_summary)
    if isinstance(scheduled_events, list):
        backing += "\n" + "\n".join(
            str(e.get("title", "")) for e in scheduled_events if isinstance(e, dict))
    missing = sorted(c for c in candidates if not _is_backed(c, backing))
    if missing:
        au.add("C23_summary_no_new_entities", False,
               "総括に本文未確認の固有名詞候補（限界あり・ASCII表記のみ検知。"
               f"誤検知時は要目視確認）: {missing}", names=list(missing))
        return
    au.add("C23_summary_no_new_entities", True,
           f"固有名詞候補{len(candidates)}件・すべてpart1_headline/part1_points/reusable_for_summaryに存在")


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


def check_c24(au: Audit, part2_flow, part1_points, part1_headline=None) -> None:
    """part1_headline（v1.82・オーナー承認）: バックリファレンス先へ、part1_points
    に加えてpart1_headlineも含める。材料が1件だけの日はpart1_pointsが定型文
    のみになり（ヘッドラインと重複しない補足が無いため）、その1件の材料は
    part1_headlineにしか載らない。市場のフローはpart1_headline・part1_pointsに
    掲載済みの材料を連鎖の起点とする（CALL_B_INSTRUCTIONS）ため、ヘッドライン
    のみに載る固有名詞をFAILにしない。reusable_for_summaryを含めない点は
    従来どおり（v1.56）。
    v1.84（オーナー承認）: C23と同じ機関名の同義語照合（_is_backed・
    _INSTITUTION_ALIAS_GROUPS）を適用する。フローが「Fed」、本文が「FRB」「米連邦
    準備制度理事会」の表記だと、同じ機関でも文字列一致だけでは未確認と誤判定される
    ため。無条件の許可リストではなく、本文（ヘッドライン・主要なポイント）に同じ機関の
    記述がある場合に限って確認済みとする（別機関では確認済みにならない）。
    """
    if not isinstance(part2_flow, str) or not part2_flow.strip():
        au.add("C24_flow_no_unadopted_material", None, "part2_flowが空のためSKIP")
        return
    candidates = {m for m in _PROPER_NOUN_RE.findall(part2_flow)
                  if m.upper() not in _PROPER_NOUN_ALLOWLIST_C24}
    if not candidates:
        au.add("C24_flow_no_unadopted_material", True, "市場のフローに固有名詞候補（ASCII表記）なし")
        return
    backing = str(part1_points or "") + "\n" + str(part1_headline or "")
    missing = sorted(c for c in candidates if not _is_backed(c, backing))
    if missing:
        au.add("C24_flow_no_unadopted_material", False,
               "市場のフローにpart1_headline・part1_points未確認の固有名詞候補（限界あり・ASCII表記のみ検知。"
               f"誤検知時は要目視確認）: {missing}", names=list(missing))
        return
    au.add("C24_flow_no_unadopted_material", True,
           f"固有名詞候補{len(candidates)}件・すべてpart1_headline・part1_pointsに存在")


# --- C26〜C28 共通: 統合運用基準§3.1「4つの編集見出しの役割」表の"記載しない
# 内容"列のうち、機械的に確実に検知できる語句 ---

# v1.79（オーナー承認）: 「相対強弱」「根拠のない段階」等、意味判定が必要な
# 項目は対象外とする（C16b/C18/C21/C23と同じ判断——機械的に確実な側だけを
# 扱い、誤検知の懸念がある項目は目視確認に委ねる）。英字は単語境界つきの
# 正規表現で判定し、部分一致による誤検知を避ける（オーナー指示。例:
# 「APR」が「APRIL」や「HELP」の一部として誤って一致しない）。
#
# 実装上の注意: Python の re モジュールは日本語の漢字・ひらがな・カタカナを
# \w（単語構成文字）として扱うため、素朴な \bTERM\b は「LP流動性」のように
# 英字の直後に空白なしで日本語が続く（本システムの生成文で実際に多用される）
# ケースで一致しない（英字と日本語の間に\bの境界が生じないため）。そのため
# \b ではなく、直前・直後がASCII英数字でないことを明示的に確認する肯定的な
# 先読み・後読みを使う——ASCII英数字との連結のみを「部分一致」とみなし、
# 日本語文字との連結は正常な区切りとして許容する。
# 日本語の言い換えも対象に加える。「利回り」単独は対象外とする——「米国債
# 利回り」のような正当な記述と機械的に区別できないため（オーナー指示）。
_ROLE_TERMS_EN = ["LP", "APR", "DEX", "Fear & Greed", "Greed"]
_ROLE_TERMS_JP = ["強欲", "恐怖", "分散型取引所", "年率換算", "流動性提供", "LPプール", "参考APR"]
_ROLE_TERM_PATTERNS = (
    [re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])") for t in _ROLE_TERMS_EN]
    + [re.compile(re.escape(t)) for t in _ROLE_TERMS_JP]
)


def _find_role_term_hits(text: str) -> list[str]:
    return [p.pattern for p in _ROLE_TERM_PATTERNS if p.search(text)]


# --- C26 市場のフローの役割分離 ---

def check_c26(au: Audit, part2_flow) -> None:
    if not isinstance(part2_flow, str) or not part2_flow.strip():
        au.add("C26_flow_role_separation", None, "part2_flowが空のためSKIP")
        return
    if part2_flow == generate_post.FIXED_FLOW:
        au.add("C26_flow_role_separation", None, "縮退時の固定文言のためSKIP")
        return
    hits = _find_role_term_hits(part2_flow)
    au.add("C26_flow_role_separation", not hits,
           f"統合運用基準§3.1により【市場のフロー】に記載しない語句を検出: {hits}" if hits
           else "役割分離の禁止語句なし", patterns=list(hits))


# --- C27 総括の役割分離（価格表記の混入・文数超過） ---

_PRICE_NOTATION_RE = re.compile(r"[$¥]\s?[0-9][0-9,.]*")


def check_c27(au: Audit, part2_summary) -> None:
    if not isinstance(part2_summary, str) or not part2_summary.strip():
        au.add("C27_summary_role_separation", None, "part2_summaryが空のためSKIP")
        return
    if part2_summary == generate_post.SUMMARY_BLANK_NOTE:
        au.add("C27_summary_role_separation", None, "縮退時の固定文言（人が補う前提）のためSKIP")
        return
    reasons = []
    term_hits = _find_role_term_hits(part2_summary)
    if term_hits:
        reasons.append(f"統合運用基準§3.1により【総括】に記載しない語句を検出: {term_hits}")
    price_hits = _PRICE_NOTATION_RE.findall(part2_summary)
    if price_hits:
        reasons.append(f"価格表記（$・¥＋数値）を検出: {price_hits}")
    sentence_count = len([s for s in part2_summary.split("。") if s.strip()])
    if sentence_count >= 3:
        reasons.append(f"文数が{sentence_count}文（「。」区切りで3文以上はFAIL・1〜2文で統合する規定）")
    au.add("C27_summary_role_separation", not reasons, "; ".join(reasons) if reasons else "役割分離OK",
           patterns=list(term_hits), prices=list(price_hits))


# --- C28 ヘッドライン・主要なポイントの役割分離（価格・24時間比・Fear&Greedの再掲） ---

def _daily_data_display_values(daily_data: dict) -> set[str]:
    """C28専用（v1.79・オーナー承認）: #BTC・#ETH・#BNBのusd/jpy/change_24hと
    Fear & Greedの値（daily_data.jsonの生の表示値そのもの）を集める。

    C16b（散文中の数値転記検知）はdaily_data全体を走査対象にする汎用チェック
    であり全4セクションに一律適用されるのに対し、C28は【ヘッドライン】
    【主要なポイント】の2見出しに限り「価格・24時間比・Fear & Greedを一切
    書かない」という統合運用基準§3.1の役割分離を機械的に強制するための
    専用チェックであるため、対象をこの2見出しの語彙に絞って照合する
    （「$・¥＋数値」の一律判定にすると、ニュース中の正当な金額表記——
    取引所被害額やETF資金流出額等——まで誤検知するため採用しない。
    オーナー指示）。
    """
    values: set[str] = set()
    for asset in daily_data.get("assets", []):
        if asset.get("asset") not in ("BTC", "ETH", "BNB"):
            continue
        for key in ("usd", "jpy", "change_24h"):
            v = asset.get(key)
            if isinstance(v, str) and v:
                values.add(v)
    fg_value = daily_data.get("market", {}).get("fear_greed", {}).get("value")
    if isinstance(fg_value, (int, float)) and not isinstance(fg_value, bool):
        values.add(str(fg_value))
    return values


# v1.82（オーナー承認）: ヘッドラインに限り、銘柄名と値動き語が同一文にある場合も
# FAILとする。統合運用基準§3.1は【ヘッドライン】に価格・24時間比を書かないと
# 定めており、「24時間比」の文字列・実際の表示値・語句一覧（上記）だけでは、
# 「BTC・ETHは軟調推移」のように数値も「24時間比」も使わない定性的な値動きの
# 記述を検知できない（C28提案時に開示した限界への対応）。ニュースの引用等で
# 誤検知した場合は、config/c28_allowlist.jsonへ日付と文字列（部分一致）を
# 登録する（C18のc18_allowlist.jsonと同じ日付限定の運用）。
# 英字（BTC・ETH・BNB）はASCII英数字との連結のみを部分一致とみなす
# （上記_ROLE_TERM_PATTERNSと同じ理由。日本語との連結は許容）。
_HEADLINE_SYMBOL_PATTERNS = (
    [(t, re.compile(r"(?<![A-Za-z0-9])" + re.escape(t) + r"(?![A-Za-z0-9])")) for t in ("BTC", "ETH", "BNB")]
    + [(t, re.compile(re.escape(t))) for t in ("ビットコイン", "イーサリアム")]
)
_HEADLINE_MOVE_TERMS = ("上昇", "下落", "反発", "反落", "横ばい")


def _find_headline_symbol_move_sentences(headline: str, allowlist: set[str]) -> list[str]:
    hits = []
    for sentence in re.split(r"[。\n]", headline):
        if not sentence.strip() or any(a in sentence for a in allowlist):
            continue
        symbols = [t for t, pat in _HEADLINE_SYMBOL_PATTERNS if pat.search(sentence)]
        moves = [w for w in _HEADLINE_MOVE_TERMS if w in sentence]
        if symbols and moves:
            hits.append(f"{symbols}×{moves}（{sentence.strip()}）")
    return hits


def check_c28(au: Audit, part1_headline, part1_points, daily_data: dict) -> None:
    headline = part1_headline if isinstance(part1_headline, str) else ""
    points = part1_points if isinstance(part1_points, str) else ""
    if not headline.strip() and not points.strip():
        au.add("C28_headline_points_role_separation", None,
               "part1_headline・part1_pointsともに空のためSKIP")
        return

    reasons = []
    display_values = _daily_data_display_values(daily_data)
    for label, text in (("ヘッドライン", headline), ("主要なポイント", points)):
        if not text.strip():
            continue
        if "24時間比" in text:
            reasons.append(f"{label}に「24時間比」の文字列を検出")
        value_hits = sorted(v for v in display_values if v in text)
        if value_hits:
            reasons.append(f"{label}にdaily_data.jsonの表示値の再掲を検出: {value_hits}")
    if headline.strip():
        term_hits = _find_role_term_hits(headline)
        if term_hits:
            reasons.append(f"ヘッドラインに統合運用基準§3.1で記載しない語句を検出: {term_hits}")
        c28_allowlist = _load_allowlist(daily_data.get("target_date_jst", ""), "c28_allowlist.json")
        move_hits = _find_headline_symbol_move_sentences(headline, c28_allowlist)
        if move_hits:
            reasons.append(
                "ヘッドラインの同一文に銘柄名と値動き語が存在（統合運用基準§3.1: ヘッドラインに"
                f"価格・値動きを書かない。誤検知時は config/c28_allowlist.json へ登録）: {move_hits}")
    au.add("C28_headline_points_role_separation", not reasons,
           "; ".join(reasons) if reasons else "役割分離OK")


# --- 向きの食い違いの警告（WARN。FAILではない。v1.85・オーナー承認）---
#
# 背景: 2026-09-30分で、本文（主要なポイント）が「FRBの利上げ観測が後退」と書いている
# のに、ヘッドラインは「Fedの利下げ観測」、市場のフローは「FRBの利下げ観測が後退し得る」と、
# 向きが逆の記述になっていた。意味の判定を伴うため、既存の機械監査（C12〜C28）では検出できない。
# オーナー判断で、まずFAILではなく「警告（WARN）」として始め、1〜2週間の結果を見てFAILに
# するか判断する。警告はAudit.warningsへ入れ、checks・failed・overall・終了コードには
# 一切影響しない（post_audit JSONの"warnings"・GENERATION_STATUS.mdの先頭に表示する）。
#
# 対象の語の対: 「利上げ／利下げ」「上昇／下落」「流入／流出」。比較の向き: 主要なポイント
# （part1_points）と、ヘッドライン・市場のフロー・headline_for_imageのそれぞれ。
# 判定: 同じ「主語」について、対象側の方向語の集合と主要なポイント側の方向語の集合が
# 重ならない（対象側が下落だけ・本文が上昇だけ、等）場合に警告する。どちらかが両方の
# 方向語を含む（「上昇した後に下落」等）場合、または主語が違う場合は警告しない。
# - 利上げ／利下げ: それ自体が主語（文全体で集合を取る）。
# - 上昇／下落・流入／流出: 方向語の直前（同じ節内・30文字以内）で最後に現れる主語キーワード
#   （原油・金利・株式・ドル・ゴールド・ビットコイン・イーサリアム・BNB・暗号通貨・資金〔ETF・
#   マネーを含む〕・ステーブルコイン・取引所）をその方向語の主語とみなす。
# 限界: 主語の取り出しは単純なキーワード照合で、日本語の係り受けは解析しない。主語が
# 一覧に無い・方向語が省略された主語にかかる場合は検知できない（見逃し）。逆に、同じ主語の
# 別の時点・別の対象を述べた文を食い違いと誤判定する可能性がある（だからWARNから始める）。
# 実データ（本番にコミット済みの34日分）では、警告が出たのは本物の食い違いだった9/30のみで、
# それ以外の日は0件だった（DESIGN_CHANGES.md v1.85参照）。
_DIRECTION_RATE_TERMS = ("利上げ", "利下げ")
_DIRECTION_SUBJECT_PAIRS = (("上昇", "下落"), ("流入", "流出"))
_DIRECTION_SUBJECTS = (
    ("原油", ("原油", "WTI", "ブレント")),
    ("金利", ("金利", "利回り")),
    ("株式", ("株式", "株価", "S&P", "ナスダック", "ダウ", "日経平均", "日経", "株")),
    ("ドル", ("ドル",)),
    ("ゴールド", ("ゴールド", "金価格")),
    ("ビットコイン", ("ビットコイン", "BTC")),
    ("イーサリアム", ("イーサリアム", "ETH", "イーサ")),
    ("BNB", ("BNB",)),
    ("暗号通貨全体", ("暗号通貨", "暗号資産", "仮想通貨")),
    ("資金", ("資金", "マネー", "ETF")),
    ("ステーブルコイン", ("ステーブルコイン", "USDC", "USDT")),
    ("取引所", ("取引所",)),
)
_DIRECTION_BOUNDARY = "、，,。；;→】）)\n"
_DIRECTION_WINDOW = 30


def _direction_subject_before(text: str, idx: int) -> "str | None":
    start = max(text.rfind(b, 0, idx) for b in _DIRECTION_BOUNDARY) + 1
    window = text[max(start, idx - _DIRECTION_WINDOW):idx]
    best = None  # (主語キーワードの終端位置, 長さ, 主語)
    for subject, keywords in _DIRECTION_SUBJECTS:
        for kw in keywords:
            pos = window.rfind(kw)
            if pos >= 0:
                cand = (pos + len(kw), len(kw), subject)
                if best is None or cand[:2] > best[:2]:
                    best = cand
    return best[2] if best else None


def _direction_map(text: str) -> "dict[tuple[str, str], set[str]]":
    """{(語の対, 主語): {方向語}}。利上げ／利下げは主語を持たない（主語は"-"）。"""
    out: dict[tuple[str, str], set[str]] = {}
    for term in _DIRECTION_RATE_TERMS:
        if term in text:
            out.setdefault(("利上げ/利下げ", "-"), set()).add(term)
    for a, b in _DIRECTION_SUBJECT_PAIRS:
        for term in (a, b):
            for m in re.finditer(re.escape(term), text):
                subject = _direction_subject_before(text, m.start())
                if subject:
                    out.setdefault((f"{a}/{b}", subject), set()).add(term)
    return out


def _sentence_with(text: str, term: str, subject_hint: "str | None" = None) -> str:
    """termを含む最初の文（なければ空）。ログ・警告の根拠表示用。"""
    for sent in re.split(r"[。\n]", text):
        if term in sent:
            return sent.strip()[:120]
    return ""


def find_direction_mismatches(points, targets: "dict[str, str]") -> "list[dict]":
    """主要なポイント（points）と、各対象（見出し名→本文）の向きの食い違いを返す。"""
    pts = points if isinstance(points, str) else ""
    pm = _direction_map(pts)
    hits = []
    for name, txt in targets.items():
        if not isinstance(txt, str) or not txt.strip():
            continue
        for key, dirs in _direction_map(txt).items():
            pdirs = pm.get(key)
            if pdirs and not (dirs & pdirs):
                t_term, p_term = sorted(dirs)[0], sorted(pdirs)[0]
                hits.append({
                    "section": name, "pair": key[0], "subject": None if key[1] == "-" else key[1],
                    "section_directions": sorted(dirs), "points_directions": sorted(pdirs),
                    "section_sentence": _sentence_with(txt, t_term),
                    "points_sentence": _sentence_with(pts, p_term),
                })
    return hits


def check_direction_warn(au: Audit, sections: dict, headline_for_image) -> None:
    """向きの食い違いをau.warningsへ追加する（FAILにしない。上のコメント参照）。"""
    targets = {"ヘッドライン": sections.get("part1_headline"),
               "市場のフロー": sections.get("part2_flow"),
               "headline_for_image": headline_for_image}
    for h in find_direction_mismatches(sections.get("part1_points"), targets):
        subj = f"（{h['subject']}）" if h["subject"] else ""
        au.warn("W_direction_mismatch",
                f"{h['section']}は「{'・'.join(h['section_directions'])}」、主要なポイントは"
                f"「{'・'.join(h['points_directions'])}」と、{h['pair']}{subj}の向きが食い違っています。"
                f" {h['section']}: 「{h['section_sentence']}」／主要なポイント: 「{h['points_sentence']}」",
                **h)


def summarize_check_ids(checks: "list[dict]") -> str:
    """実際に評価したチェックのID要約（例: 「C12〜C24・C26〜C28・計17項目」）。
    GENERATION_STATUS.mdの監査表記を、固定文言ではなく実際の評価対象から作る（v1.85）。
    C16b等の枝番つきIDは親番号に含め、項目数（計N項目）には数える。"""
    nums = sorted({int(m.group(1)) for c in checks for m in [re.match(r"C(\d+)", str(c.get("id", "")))] if m})
    if not nums:
        return f"計{len(checks)}項目"
    ranges, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        ranges.append((start, prev))
        start = prev = n
    ranges.append((start, prev))
    parts = [f"C{a}" if a == b else f"C{a}〜C{b}" for a, b in ranges]
    return "・".join(parts) + f"・計{len(checks)}項目"


# --- FAIL時の証拠（セクション・該当語・該当文）の抽出（v1.86・オーナー承認・案G）---
#
# 背景: 2026-10-01分で、強制不採用後の再監査がC18でFAILしL1へ落ちたが、GENERATION_STATUS.md
# にはチェックIDしか残らず、どの文のどの語が検出されたか（誤検知か否か）が分からなかった。
# オーナーはCI成果物を見られないため、STATUSだけで判断できるよう、FAILしたチェックごとに
# 「セクション・（由来となった呼び出し）・該当語・該当文（先頭100字）」を取り出す。
# 判定（run_allの結果）には一切影響しない純粋な事後説明で、位置を特定できないチェックは
# detail（従来どおり）のみを示す。

# 各セクションがどの呼び出し・テンプレートに由来するか（compose_post.compose()の構成どおり）。
SECTION_ORIGIN = {
    "part1_headline": "call_A", "part1_points": "call_A", "headline_for_image": "call_A",
    "part2_flow": "call_B", "part2_summary": "call_B",
    "lp_comment": "テンプレート", "part1_numeric": "テンプレート",
    "part2_numeric": "テンプレート", "part0_target_date": "テンプレート",
}
_EVIDENCE_SCAN_ORDER = ("part1_headline", "part1_points", "part2_flow", "part2_summary",
                        "headline_for_image", "lp_comment", "part1_numeric", "part2_numeric",
                        "part0_target_date")
EVIDENCE_SENTENCE_CHARS = 100


def _clip_sentence(s: str, n: int = EVIDENCE_SENTENCE_CHARS) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n] + "…"


def _evidence_texts(bundle: dict) -> list[tuple[str, str]]:
    sections = bundle.get("sections", {}) or {}
    out = []
    for key in _EVIDENCE_SCAN_ORDER:
        v = bundle.get("headline_for_image") if key == "headline_for_image" else sections.get(key)
        if isinstance(v, str) and v.strip():
            out.append((key, v))
    return out


def _display_term(word: str, regex: bool) -> str:
    """STATUS表示用。C26/C27の語句は単語境界つきの正規表現（_ROLE_TERM_PATTERNS）で
    持っているため、読めるよう先読み・後読みとエスケープを取り除く。"""
    if not regex:
        return word
    return re.sub(r"\(\?<!\[A-Za-z0-9\]\)|\(\?!\[A-Za-z0-9\]\)", "", word).replace("\\", "")


def _find_term_evidence(bundle: dict, check_id: str, words: list[str], *, regex: bool = False,
                         scope: "tuple[str, ...] | None" = None) -> list[dict]:
    """words（語・正規表現）を含む文を、セクション走査順に1語につき最初の1件だけ返す。"""
    found: list[dict] = []
    for word in words:
        pat = re.compile(word) if regex else None
        for name, text in _evidence_texts(bundle):
            if scope is not None and name not in scope:
                continue
            hit = next((s for s in re.split(r"[。\n]", text)
                        if s.strip() and ((pat.search(s) is not None) if pat else (word in s))), None)
            if hit is not None:
                clipped = _clip_sentence(hit)
                shown = _display_term(word, regex)
                same = next((f for f in found if f["section"] == name and f["sentence"] == clipped), None)
                if same is not None:  # 同じ文に複数の語がある場合は1件にまとめる
                    same["words"].append(shown)
                else:
                    found.append({"check": check_id, "section": name, "origin": SECTION_ORIGIN.get(name),
                                  "words": [shown], "sentence": clipped})
                break
    return found


def collect_fail_evidence(bundle: dict, checks: "list[dict]") -> "list[dict]":
    """FAILしたチェックごとの証拠を返す。各要素は
    {"check", "section", "origin", "words": [...], "sentence"}。位置を特定できない
    FAILは section=None の1件（detailのみ示す側で使う）。"""
    evidence: list[dict] = []
    sections = bundle.get("sections", {}) or {}
    hfi = bundle.get("headline_for_image", "")
    target_date = bundle.get("target_date_jst", "")
    for c in checks:
        if c.get("result") != "FAIL":
            continue
        cid = c["id"]
        found: list[dict] = []
        try:
            if cid == "C18_causal_assertion":
                allowlist = _load_allowlist(target_date, "c18_allowlist.json")
                for v in _find_c18_violations(sections, bundle.get("llm_section_keys", []), allowlist, hfi):
                    sent = v["sentence"]
                    words = ([m for m in CAUSAL_MARKERS if m in sent]
                             + [w for w in PRICE_MOVEMENT_WORDS if w in sent]
                             + [p for p in CAUSAL_STANDALONE_PHRASES if p in sent])
                    found.append({"check": cid, "section": v["section"],
                                  "origin": SECTION_ORIGIN.get(v["section"]), "words": words,
                                  "sentence": _clip_sentence(sent)})
            elif cid == "C12_banned_terms":
                found = _find_term_evidence(bundle, cid, c.get("terms", []))
            elif cid == "C13_hashtag_boundary":
                for name, text in _evidence_texts(bundle):
                    for msg in _hashtag_violations(text):
                        m = re.match(r"位置(\d+):", msg)
                        pos = int(m.group(1)) if m else 0
                        start = max(text.rfind("。", 0, pos), text.rfind("\n", 0, pos)) + 1
                        ends = [i for i in (text.find("。", pos), text.find("\n", pos)) if i != -1]
                        sentence = text[start:min(ends) if ends else len(text)]
                        found.append({"check": cid, "section": name, "origin": SECTION_ORIGIN.get(name),
                                      "words": [msg], "sentence": _clip_sentence(sentence)})
            elif cid == "C16b_transcription_scan":
                found = _find_term_evidence(bundle, cid, c.get("hits", []),
                                            scope=tuple(bundle.get("llm_section_keys", [])) + ("headline_for_image",))
            elif cid == "C23_summary_no_new_entities":
                found = _find_term_evidence(bundle, cid, c.get("names", []), scope=("part2_summary",))
            elif cid == "C24_flow_no_unadopted_material":
                found = _find_term_evidence(bundle, cid, c.get("names", []), scope=("part2_flow",))
            elif cid == "C26_flow_role_separation":
                found = _find_term_evidence(bundle, cid, c.get("patterns", []), regex=True, scope=("part2_flow",))
            elif cid == "C27_summary_role_separation":
                found = (_find_term_evidence(bundle, cid, c.get("patterns", []), regex=True, scope=("part2_summary",))
                         + _find_term_evidence(bundle, cid, c.get("prices", []), scope=("part2_summary",)))
        except Exception as e:  # noqa: BLE001 — 証拠抽出の失敗で監査・STATUS生成を止めない
            print(f"WARN: FAIL証拠の抽出に失敗しました（{cid}）: {type(e).__name__}: {e}", file=sys.stderr)
            found = []
        evidence.extend(found if found else [
            {"check": cid, "section": None, "origin": None, "words": [], "sentence": ""}])
    return evidence


def format_fail_evidence_lines(evidence: "list[dict]", check_id: "str | None" = None,
                               indent: str = "    ") -> "list[str]":
    """GENERATION_STATUS.md用。セクションを特定できた証拠だけを1件1行で返す。"""
    lines = []
    for e in evidence:
        if not e.get("section"):
            continue
        if check_id is not None and e.get("check") != check_id:
            continue
        origin = f"（由来: {e['origin']}）" if e.get("origin") else ""
        words = "・".join(e.get("words", [])) or "—"
        lines.append(f"{indent}└ セクション={e['section']}{origin}／該当語: {words}／該当文: 「{e['sentence']}」")
    return lines


def failing_check_details(bundle: dict, checks: "list[dict]") -> "list[dict]":
    """FAILしたチェックごとに {"id","detail","evidence":[...]} を返す（STATUS・失敗試行の保存用）。"""
    evidence = collect_fail_evidence(bundle, checks)
    out = []
    for c in checks:
        if c.get("result") != "FAIL":
            continue
        out.append({"id": c["id"], "detail": c["detail"],
                    "evidence": [e for e in evidence if e["check"] == c["id"] and e.get("section")]})
    return out


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
    check_c18(au, sections, llm_keys, c18_allowlist, headline_for_image)
    # news_candidate_countが欠落している場合は「0件」と区別できないよう
    # 負値を渡す（フェイルクローズ。存在しないキーを0件と混同して
    # 空配列を誤って許容しないようにする）。
    check_c19(au, bundle["level"], bundle.get("audit_ledger"), bundle.get("news_candidate_count", -1))
    check_c20(au, headline_for_image)
    tier_map = _load_source_tier_map()
    check_c21(au, bundle["level"], bundle.get("audit_ledger"), bundle.get("news_candidate_count", -1), tier_map)
    check_c22(au, sections.get("part1_headline"), bundle.get("audit_ledger"), tier_map)
    check_c23(au, sections.get("part2_summary"), sections.get("part1_points"),
              bundle.get("reusable_for_summary"), daily_data.get("scheduled_events"),
              sections.get("part1_headline"))
    check_c24(au, sections.get("part2_flow"), sections.get("part1_points"), sections.get("part1_headline"))
    check_c26(au, sections.get("part2_flow"))
    check_c27(au, sections.get("part2_summary"))
    check_c28(au, sections.get("part1_headline"), sections.get("part1_points"), daily_data)
    # 警告（WARN）: FAILにしない。checks・failed・overall・終了コードに影響しない（v1.85）。
    # 警告の検知の失敗で監査全体を止めない（例外はログに出して警告なしとして続行）。
    try:
        check_direction_warn(au, sections, headline_for_image)
    except Exception as e:  # noqa: BLE001
        print(f"WARN: 向きの食い違いチェック自体が失敗しました（警告なしとして続行）: {type(e).__name__}: {e}", file=sys.stderr)
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
        # v1.85: 警告（FAILではない）。overall・failed・終了コードには影響しない。
        "warnings": au.warnings,
    }
    out_path = bundle_path.parent / f"post_audit_{compact}.json"
    out_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    for w in au.warnings:
        print(f"⚠ WARN（FAILではない）: {w['id']} — {w['detail']}")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if au.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
