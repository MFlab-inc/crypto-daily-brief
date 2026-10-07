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
import indicator_events  # noqa: E402
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
    # v1.110: 【市場のフロー】の【暗号通貨価格】にシステムが差し込む「 #BTC -0.51%、 #ETH -0.76%（24時間比）」は、daily_dataの値そのもの
    # （転記ではなく機械的な差し込み）なので、走査から除く。モデルが書いた数値（差し込みと同じ文字列でない部分）は従来どおり検知する。
    fragment = generate_post.build_flow_price_fragment(daily_data)

    def _scan_text(k: str) -> str:
        v = sections.get(k, "")
        return v.replace(fragment, "") if fragment and k == "part2_flow" and isinstance(v, str) else v

    llm_text = "\n".join(_scan_text(k) for k in llm_section_keys) + "\n" + headline_for_image
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


# v1.107（オーナー承認）: 表示値の再掲の判定を、文字列の部分一致から「数字・小数点に隣接しない一致」に改める。
# 背景: Fear & Greedの値（例: 26）は、ヘッドライン末尾の出典の括弧の日付（「2026年10月6日」の「2026」の中の「26」）や、
# 「10月」「6日」の数字と部分一致してC28がFAIL（致命的。下書きが縮退する）になる。過去57日のFear & Greedは36〜82で衝突は0日だったが、
# 20台以前の局面（値が20・26・10・6など）では起きる。日付の式（年・月・日・ISO形式）は、判定の前に取り除く
# （出典の括弧の日付は市場データの再掲ではない）。判定の趣旨（価格・24時間比・Fear & Greedの値の再掲を検知する）は変えない。
# C16bの_find_transcriptionsと同じ規則（前後の文字が数字・小数点でないとき一致とみなす）。
_C28_DATE_EXPR_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{4}年|\d{1,2}月|\d{1,2}日")


def _contains_standalone_value(text: str, value: str) -> bool:
    start = 0
    while True:
        idx = text.find(value, start)
        if idx == -1:
            return False
        before = text[idx - 1] if idx > 0 else ""
        after = text[idx + len(value)] if idx + len(value) < len(text) else ""
        if not _is_digit_or_dot(before) and not _is_digit_or_dot(after):
            return True
        start = idx + 1


def _find_display_value_hits(text: str, display_values: "set[str]") -> "list[str]":
    masked = _C28_DATE_EXPR_RE.sub(" ", text)
    return sorted(v for v in display_values if _contains_standalone_value(masked, v))


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
        value_hits = _find_display_value_hits(text, display_values)
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


# --- 警告（WARN）の種類の登録簿と件数表示（v1.91・オーナー承認）---
#
# オーナー指示: 新しく追加するWARNは、GENERATION_STATUS.mdの「向きの食い違いチェック」と同じ欄に
# まとめ、種類ごとの件数つきで表示する（毎朝の確認をそこだけで済ませるため）。警告の種類は
# ここに登録し、STATUSの欄（repair_post.render_final_audit_note／render_warning_block）は
# この登録簿から「種類別の件数」を作る。件数が0の種類も毎回表示する（「見ていない」と
# 「0件だった」を区別するため）。警告はいずれもFAILにしない（checks・failed・overall・終了コードに影響しない）。
WARNING_KINDS: "tuple[tuple[str, str], ...]" = (
    ("W_direction_mismatch", "向きの食い違い"),
    ("W_headline_hashtag", "見出しのタグ"),
    ("W_indicator_headline", "指標日の見出し"),
    ("W_flow_format", "フロー書式"),
    ("W_media_mismatch", "媒体名照合"),
    ("W_geo_rejected_fixed", "地政学の不採用"),
    ("W_bullet_normalized", "行頭の記号"),
    ("W_headline_reason", "見出し理由の不採用"),
    ("W_headline_repeat", "見出しの繰り返し"),
    ("W_dup_weak", "重複の根拠が弱い"),
)


# 本文の確認が要らない（機械的に整形した記録だけの）警告の種類。STATUS先頭の警告ブロックの見出しに使う。
INFORMATIONAL_WARNING_IDS = frozenset({"W_bullet_normalized"})


def warning_kind_label(wid: str) -> str:
    return dict(WARNING_KINDS).get(wid, "その他")


def format_warning_counts(warnings: "list[dict]") -> str:
    """種類別の警告件数（例: 「向きの食い違い0・見出しのタグ1」）。登録済みの種類は0件でも表示し、
    未登録のIDの警告は「その他」にまとめる（その他が0件のときは表示しない）。"""
    ws = warnings or []
    counts = {wid: 0 for wid, _ in WARNING_KINDS}
    other = 0
    for w in ws:
        wid = w.get("id")
        if wid in counts:
            counts[wid] += 1
        else:
            other += 1
    parts = [f"{label}{counts[wid]}" for wid, label in WARNING_KINDS]
    if other:
        parts.append(f"その他{other}")
    return "・".join(parts)


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


# --- 見出しのタグの警告（WARN。FAILではない。v1.91・オーナー承認）---
#
# 背景: 2026-10-02分で、ヘッドラインの末尾に「 #BTC #ETH」が付いていた（本文に銘柄名が無いのに）。
# 発端はv1.70（9/8）の「主要銘柄に言及する場合はハッシュタグを付す」で、v1.82で見出しに価格・値動きを
# 書かなくなった後も条件が見直されず残っていた。オーナー判断（10/4）: 見出しにタグは不要。
# プロンプト（generate_post.py）からタグの指示を外したうえで、タグが付いた日を見逃さないよう、
# ヘッドライン（part1_headline）にハッシュタグがあれば警告する（本文は変えない・FAILにしない）。
# 対象はヘッドラインのみ。市場のフローの連鎖末尾のタグは従来どおり許容する（別の指示）。
_HEADLINE_HASHTAG_RE = re.compile(r"(?<![A-Za-z0-9_])#[A-Za-z0-9_]+")


def find_headline_hashtags(headline) -> "list[str]":
    return _HEADLINE_HASHTAG_RE.findall(str(headline or ""))


def check_hashtag_warn(au: Audit, sections: dict) -> None:
    """ヘッドラインのハッシュタグをau.warningsへ追加する（FAILにしない。上のコメント参照）。"""
    headline = sections.get("part1_headline") or ""
    tags = find_headline_hashtags(headline)
    if tags:
        au.warn("W_headline_hashtag",
                f"ヘッドラインにハッシュタグ（{' '.join(tags)}）が付いています（オーナー指示: 見出しにタグは付けない）。"
                f" ヘッドライン: 「{_clip_sentence(headline, 100)}」",
                tags=tags, section="ヘッドライン", sentence=str(headline))


# --- 指標日の見出しの警告（WARN。FAILではない。v1.93・オーナー承認・案3）---
#
# 背景: 2026-10-02分（米雇用統計の日）で、雇用統計（Reuters・tier2）が台帳で採用されていたのに、ヘッドラインは
# FRBの個別の申請承認（Fleur Capital）で、雇用統計は主要なポイントの4番目だった。C22は「その日の台帳にtier1/2の採用が
# 1件でもあるか」しか見ず、見出しの内容との対応は見ない。オーナー判断（10/4）: 指標日（scheduled_eventsで重要度Highの米指標）に
# 対応する材料が採用済みなら、原則としてそれを見出しの主にする。ただし暗号通貨に直接関わる大型の制度材料が公式発表で確認できる日は
# それを見出しにし、指標は主要なポイントの1番目に置く（この例外の日に出る警告は、オーナーが目視で判断する）。
# この警告は、その規則から外れた日（指標に対応する採用済みの材料があるのに、見出しがその指標に触れていない日）を示す。
# 照合はキーワード（indicator_events.py）で、意味の判定ではない。警告の中に「主要なポイントの1番目が指標に触れているか」を
# 添えて、例外（2）に従った日かどうかを目視で判断しやすくする。
def check_indicator_headline_warn(au: Audit, sections: dict, audit_ledger, scheduled_events) -> None:
    """指標日の見出しの警告をau.warningsへ追加する（FAILにしない。上のコメント参照）。"""
    families = indicator_events.high_us_event_families(scheduled_events)
    headline = str(sections.get("part1_headline") or "")
    if not families or not headline.strip() or headline.strip() == generate_post.FIXED_HEADLINE:
        return
    adopted = [e for e in (audit_ledger if isinstance(audit_ledger, list) else [])
               if isinstance(e, dict) and str(e.get("decision", "")).startswith("採用")]
    first_point = next((ln for ln in str(sections.get("part1_points") or "").split("\n") if ln.strip()), "")
    for f in families:
        fam = f["family"]
        matched = [e for e in adopted if indicator_events.candidate_family_keys(e.get("title"), [f])]
        if not matched or indicator_events.headline_mentions(headline, fam):
            continue
        first = "触れています" if indicator_events.headline_mentions(first_point, fam) else "触れていません"
        ex = matched[0]
        au.warn("W_indicator_headline",
                f"指標日（{fam['label']}: {' / '.join(f['events'])}）に対応しうる材料が採用されていますが、ヘッドラインは"
                f"{fam['label']}に触れていません（主要なポイントの1番目は{first}）。"
                f" 採用された対応候補: 「{_clip_sentence(str(ex.get('title', '')), 80)}」［{ex.get('source', '')}］"
                f"（計{len(matched)}件）／ヘッドライン: 「{_clip_sentence(headline, 80)}」。"
                "暗号通貨に直接関わる大型の制度材料が公式発表で確認できる日（見出しはその材料、指標は主要なポイントの1番目）は"
                "規則どおりです。目視で確認してください。",
                family=fam["key"], events=f["events"], matched_titles=[str(e.get("title", "")) for e in matched],
                points_first_mentions=first == "触れています")


# --- 市場のフローの書式の警告（WARN。FAILではない。v1.94・オーナー承認）---
#
# 背景: 2026-10-02分の【市場のフロー】が、統合運用基準§3.3の書式（【出来事・ニュース】→【地政学・マクロの変化】→
# 【中間市場指標・市場心理】→【暗号通貨価格】、①②③区切り、1連鎖1文）ではなく、ラベルも矢印も無い3文の散文だった。
# 既存の機械監査（C12〜C28）は書式（ラベル・矢印・文数）を一切見ないため、17項目PASSのまま素通りした。
# 原因（モデルのばらつきか構造的か）はv1.82以降の本番のL0日が少なく断定できないため、まずWARNとして検出する
# （オーナー判断: WARNとして追加。誤検知の調整を実データで進めてからFAILに昇格するかを判断する）。
# 判定は連鎖（1行）ごと。材料が無い日の定型文（FIXED_FLOW）1件のみの日は対象外。
#   ①必須ラベル【出来事・ニュース】【暗号通貨価格】がある ②ラベルは定められた順序で、各1回以内
#   ③【出来事・ニュース】で始まる ④「→」の直後は必ずラベル／矢印は（段階数−1）本以上 ⑤1文（句点は
#   全角括弧（）内を除いて末尾の1つだけ） ⑥ハッシュタグは連鎖の末尾（句点の後）だけ
#   ⑦①②③（2本以上なら①から連番、1本なら付けない、最大3本） ⑧末尾（句点の直前45字以内）に限定表現
# ⑧は語彙に依存し最も壊れやすい（試作で、本番9/30の①「…とみられます」を誤検知した→語幹で判定）。
# 限界: 書式（構造）だけを見る。ラベルが付いていても中身が不適切な場合（確認済み事実でない内容を
# 【地政学・マクロの変化】に書く等）は検出できない。
_FLOW_LABELS = ("【出来事・ニュース】", "【地政学・マクロの変化】", "【中間市場指標・市場心理】", "【暗号通貨価格】")
_FLOW_NUMBERS = "①②③"
_FLOW_LIMITING_STEMS = ("可能性", "未確認", "意識され", "とみられ", "考えられ", "確認できません", "確認できない", "断定")
FLOW_FORMAT_REASON_LABELS = {
    "no_event_label": "【出来事・ニュース】が無い",
    "no_price_label": "【暗号通貨価格】が無い",
    "label_order": "段階の順序が違う",
    "label_dup": "同じ段階が複数回ある",
    "not_start_event": "【出来事・ニュース】で始まっていない",
    "arrow_label_mismatch": "「→」の直後がラベルでない",
    "arrows": "「→」が足りない",
    "no_arrows": "「→」が無い",
    "sentences": "1文でない（句点が末尾の1つだけでない。全角括弧内は除く）",
    "tag_in_body": "ハッシュタグが連鎖の途中にある（システムが差し込む【暗号通貨価格】の数値部分を除く）",
    "tag_not_after_period": "ハッシュタグが句点の後に無い",
    "numbering": "①②③の付け方が違う（複数なら①から連番、1本なら付けない）",
    "too_many_chains": "連鎖が4本以上ある（最大3本）",
    "no_limit_at_end": "末尾に限定表現（可能性・未確認等）が無い",
    "no_price_number": "【暗号通貨価格】に「 #BTC ±x.xx%、 #ETH ±x.xx%（24時間比）」の数値が無い（システムの差し込み漏れ）",
}


def _flow_chain_violations(raw: str, idx: int, n: int, require_price_fragment: bool = False) -> "list[str]":
    s = raw.strip()
    m = re.match(r"^([①②③])\s*", s)
    num = m.group(1) if m else None
    body = s[m.end():] if m else s
    tm = re.search(r"((?:\s#[A-Za-z]+)+)\s*$", body)
    core = body[:tm.start()] if tm else body
    r: "list[str]" = []
    # v1.110: システムが【暗号通貨価格】に差し込む「 #BTC -0.51%、 #ETH -0.76%（24時間比）で、」のハッシュタグは、途中のタグとみなさない
    if "#" in generate_post.FLOW_PRICE_FRAGMENT_RE.sub("", core):
        r.append("tag_in_body")
    if tm and not core.rstrip().endswith("。"):
        r.append("tag_not_after_period")
    if (n >= 2 and num != _FLOW_NUMBERS[idx:idx + 1]) or (n == 1 and num):
        r.append("numbering")
    if idx >= 3:
        r.append("too_many_chains")
    present = [lb for lb in _FLOW_LABELS if lb in core]
    pos = [core.index(lb) for lb in present]
    if _FLOW_LABELS[0] not in core:
        r.append("no_event_label")
    if _FLOW_LABELS[3] not in core:
        r.append("no_price_label")
    if pos != sorted(pos):
        r.append("label_order")
    if any(core.count(lb) > 1 for lb in _FLOW_LABELS):
        r.append("label_dup")
    if not core.lstrip().startswith(_FLOW_LABELS[0]):
        r.append("not_start_event")
    segs = re.split(r"\s*→\s*", core)
    if len(segs) > 1 and any(not any(sg.lstrip().startswith(lb) for lb in _FLOW_LABELS) for sg in segs):
        r.append("arrow_label_mismatch")
    if len(present) >= 2 and core.count("→") < len(present) - 1:
        r.append("arrows")
    if len(present) < 2 and "→" not in core:
        r.append("no_arrows")
    if re.sub(r"（[^（）]*）", "", core).count("。") != 1 or not core.rstrip().endswith("。"):
        r.append("sentences")
    last = core.rstrip().rstrip("。")
    if not any(w in last[-45:] for w in _FLOW_LIMITING_STEMS):
        r.append("no_limit_at_end")
    if require_price_fragment and _FLOW_LABELS[3] in core and not generate_post.FLOW_PRICE_FRAGMENT_RE.search(core):
        r.append("no_price_number")
    return r


def find_flow_format_violations(part2_flow, require_price_fragment: bool = False) -> "list[dict]":
    """市場のフロー（レンダリング済みの文字列）の書式違反を連鎖ごとに返す。各要素:
    {"chain_no"（1始まり）, "text"（連鎖）, "reasons"（FLOW_FORMAT_REASON_LABELSのコード）}。
    定型文（FIXED_FLOW）1件のみ・空の場合は対象外（空リスト）。"""
    text = str(part2_flow or "")
    items = [re.sub(r"^・", "", ln.strip()) for ln in text.split("\n") if ln.strip()]
    if not items or (len(items) == 1 and items[0].startswith(generate_post.FIXED_FLOW.rstrip("。"))):
        return []
    out = []
    for i, it in enumerate(items):
        reasons = _flow_chain_violations(it, i, len(items), require_price_fragment)
        if reasons:
            out.append({"chain_no": i + 1, "text": it, "reasons": reasons})
    return out


def check_flow_format_warn(au: Audit, sections: dict, require_price_fragment: bool = False) -> None:
    """市場のフローの書式違反をau.warningsへ追加する（連鎖ごとに1件。FAILにしない。上のコメント参照）。
    require_price_fragment（v1.110）: bundleに差し込み部分があるべき日（compose_postが差し込んだ日）は、各連鎖の【暗号通貨価格】に数値が入っているかも見る。"""
    for v in find_flow_format_violations(sections.get("part2_flow"), require_price_fragment):
        labels = "・".join(FLOW_FORMAT_REASON_LABELS.get(c, c) for c in v["reasons"])
        au.warn("W_flow_format",
                f"市場のフローの{v['chain_no']}本目が書式（統合運用基準§3.3）から外れています: {labels}。"
                f" 連鎖: 「{_clip_sentence(v['text'], 100)}」",
                chain_no=v["chain_no"], reasons=v["reasons"], sentence=v["text"])


# --- 本文の項目の媒体名と台帳の照合の警告（WARN。FAILではない。v1.95・オーナー承認・質問7の案A）---
#
# 背景: 強制不採用（generate_post.py・v1.79）は台帳のdecisionだけを「不採用」に変え、本文は変えない。そのため、
# 不採用にした候補を元にした記述が【ヘッドライン】【主要なポイント】に残っても、現行の機械監査（C12〜C28）は
# 検知できない（本文の項目と台帳の候補を結びつける検査が無い。調査では、過去のL0日の台帳で独立2ソースのペアを
# 両方不採用に書き換えても、21組中18組は全チェックPASSのままだった）。構造案S（本文の項目にcandidate_idsを持たせる）は保留とし、
# まず本文の項目末尾の「（媒体名、日付）」と台帳の採用候補の媒体を照合するWARNで観察する（オーナー判断・10/4）。
# 判定: 項目（【主要なポイント】の各行・日付つきの括弧があるヘッドライン）の「（媒体名、日付）」（複数文の項目は全部）の媒体名のうち、
# 台帳の候補の媒体（または設定済みの情報源名）として認識できるものが1つ以上あり、そのどれも台帳で採用された
# （採用／採用（独立2ソース））候補の媒体でない場合に警告する。tier1・tier2の事実をtier3が補強する書き方
# （「（FRB、CoinDesk、日付）」でFRBが採用）は、1つでも採用側の媒体があれば警告しない。
# 限界: ①同じ媒体の別記事が採用されている日は検知できない（過去データの試算では、強制不採用の再現18組中13組を検知）。
# ②媒体名が項目に付いていない・認識できない場合は判定しない。③ヘッドラインは日付つきの括弧が付くことが少なく、ほぼ対象外。
# ④検知するだけで直さない（人が確認する）。
_MEDIA_DATE_TOKEN_RE = re.compile(r"^\s*(?:\d{4}年)?\d{1,2}月\d{1,2}日|^\s*\d{1,2}日\s*$|^\s*\d{4}-\d{2}-\d{2}|^\s*\d{1,2}/\d{1,2}")
_MEDIA_PAREN_RE = re.compile(r"（([^（）]*)）")
_MEDIA_DATE_ANYWHERE_RE = re.compile(r"\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}")


def _normalize_media_name(name: str) -> str:
    """媒体名の照合用の正規化: 空白・末尾の括弧書き（「FRB（speeches）」「ホワイトハウス（大統領令等）」等）を除いて小文字化する。"""
    n = re.sub(r"[（(][^）)]*[）)]\s*$", "", str(name or "")).strip()
    return re.sub(r"\s+", "", n).lower()


def item_media_names(item: str) -> "list[str]":
    """項目内の「（媒体名、日付）」（日付つきの括弧すべて。複数文の項目は文ごとに付くため全部）から、媒体名の候補
    （日付らしい語を除いた語）を出現順・重複なしで返す。日付つきの括弧が無ければ空リスト。"""
    out: "list[str]" = []
    for m in _MEDIA_PAREN_RE.finditer(str(item or "")):
        if not _MEDIA_DATE_ANYWHERE_RE.search(m.group(1)):
            continue
        for t in re.split(r"[、・,，／/]", m.group(1)):
            t = t.strip()
            if t and not _MEDIA_DATE_TOKEN_RE.search(t) and t not in out:
                out.append(t)
    return out


def find_media_mismatches(sections: dict, audit_ledger, tier_map: "dict[str, int] | None" = None) -> "list[dict]":
    ledger = [e for e in (audit_ledger if isinstance(audit_ledger, list) else []) if isinstance(e, dict)]
    if not ledger:
        return []
    known = {_normalize_media_name(n) for n in (tier_map or {})} | {_normalize_media_name(e.get("source")) for e in ledger}
    known.discard("")
    adopted_sources = {_normalize_media_name(e.get("source")) for e in ledger
                       if str(e.get("decision", "")).startswith("採用")}
    adopted_sources.discard("")
    items: "list[tuple[str, str]]" = []
    headline = str(sections.get("part1_headline") or "")
    if headline.strip() and headline.strip() != generate_post.FIXED_HEADLINE:
        items.append(("ヘッドライン", headline))
    for ln in str(sections.get("part1_points") or "").split("\n"):
        if ln.strip() and ln.strip() != generate_post.FIXED_POINTS:
            items.append(("主要なポイント", re.sub(r"^・", "", ln.strip())))
    hits = []
    for section, text in items:
        media = [m for m in item_media_names(text) if _normalize_media_name(m) in known]
        if not media or any(_normalize_media_name(m) in adopted_sources for m in media):
            continue
        hits.append({"section": section, "media": media, "sentence": text,
                     "adopted_sources": sorted({str(e.get("source")) for e in ledger
                                                if str(e.get("decision", "")).startswith("採用")})})
    return hits


def check_media_warn(au: Audit, sections: dict, audit_ledger, tier_map: "dict[str, int] | None" = None) -> None:
    """本文の項目の媒体名と台帳の採用候補の媒体の不一致をau.warningsへ追加する（項目ごとに1件。FAILにしない）。"""
    for h in find_media_mismatches(sections, audit_ledger, tier_map):
        adopted = "・".join(h["adopted_sources"]) or "なし"
        au.warn("W_media_mismatch",
                f"{h['section']}の項目の媒体（{'・'.join(h['media'])}）が、台帳で採用された候補の媒体（{adopted}）のどれとも一致しません"
                "（不採用にした候補・強制不採用の候補を根拠にしている可能性。同じ媒体の別記事が採用されている場合は検知できません）。"
                f" 項目: 「{_clip_sentence(h['sentence'], 100)}」",
                section=h["section"], media=h["media"], sentence=h["sentence"], adopted_sources=h["adopted_sources"])


# --- 地政学・エネルギーの材料を不採用にして、見出しが定型文になった日の警告（WARN。FAILではない。v1.98・オーナー承認・案2）---
#
# 背景: 2026-10-04分で、見出し・主要なポイントが定型文（材料なし）になった。同じ日の台帳には、地政学・エネルギーの
# 材料（イエメン政府のフーシ派への攻勢・イラン石油相の辞任）が「B: …情報が薄く波及経路を具体的に説明できない」として
# 不採用で記録されていた。過去の本番出力（38日分）では、見出しが定型文だった16日のうち5日（8/29・9/5・9/6・9/20・10/4）で、
# 同種のB判定の不採用があった。これらは「波及経路はあるが、内容が薄いので不採用」という判断で、掲載の可否の基準が
# プロンプトに明確でなかった（v1.99で基準を明確化）。基準を変えたあとも、この種の不採用がどれだけ起きるかを毎朝の
# STATUSで確認できるようにする。
#
# 判定（すべて満たす日に1件の警告）:
#  ①【ヘッドライン】が定型文（generate_post.FIXED_HEADLINE。C22と同じ完全一致）。
#  ②台帳に、decision=不採用・情報源のtierが1〜3（tier4は候補発見専用で、もともと採用できないため除く。tier不明も除く）・
#    理由が「B:」で始まる（呼び出しAが「波及経路のある材料」と判定したもの）・題名が地政学またはエネルギーの語を含む、
#    の候補が1件以上ある。
# 警告は、不採用にした候補を一覧し（最大5件）、見直すべきかの判断材料にするためのもので、不採用が誤りだとは断定しない
# （題名の語による機械的な目印で、記事の内容は見ていない）。
# 限界: ①理由の先頭の「B:」はモデルの自由記述の慣習（プロンプトの指示）に依存し、付かなければ検知できない。②題名の語の
# 一覧に無い材料・題名に語が無い材料は検知できない（見逃し）。③「地政学・エネルギー」の語（原油・イラン・ロシア等）を含む
# 題名であれば、市況の話題（株価・ガソリン価格）も対象になる（誤検知。WARNなので許容）。④見出しが定型文でない日、
# 呼び出しAが失敗した日（台帳なし）は対象外。
_GEO_B_LABEL_RE = re.compile(r"^\s*B\s*[:：]")
_GEO_ENERGY_TERMS = (
    r"\b(?:oil|crude|brent|wti|opec\+?|petroleum|gasoline|gas prices?|fuel|diesel|refiner(?:y|ies)|pipelines?|lng|tankers?|"
    r"aramco|energy|strategic (?:petroleum )?(?:reserve|stockpile)s?|spr)\b"
    r"|原油|石油|燃料|ガソリン|軽油|製油|油田|パイプライン|タンカー|アラムコ|エネルギー|備蓄"
)
_GEO_POLITICS_TERMS = (
    r"\b(?:hormuz|red sea|suez|strait|houthis?|yemen\w*|iran\w*|iraq\w*|saudi|gulf|qatar\w*|uae|israel\w*|gaza|hezbollah|"
    r"lebanon|syria\w*|russia\w*|ukrain\w*|kyiv|middle east|ceasefire|cease-fire|truce|sanctions?|embargo|missiles?|drones?|"
    r"air ?strikes?|military|invasion|invad\w+)\b"
    r"|ホルムズ|紅海|スエズ|フーシ|イエメン|イラン|イラク|サウジ|湾岸|カタール|イスラエル|ガザ|中東|ロシア|ウクライナ|"
    r"制裁|停戦|休戦|ミサイル|ドローン|空爆|軍事|侵攻"
)
_GEO_TOPIC_GROUPS = (("エネルギー", re.compile(_GEO_ENERGY_TERMS, re.I)), ("地政学", re.compile(_GEO_POLITICS_TERMS, re.I)))
_GEO_WARN_MAX_LISTED = 5
_GEO_REASON_CHARS = 70


def find_geo_rejected_under_fixed_headline(sections: dict, audit_ledger,
                                            tier_map: "dict[str, int] | None" = None) -> "list[dict]":
    """見出しが定型文の日に、B判定（理由が「B:」始まり）の地政学・エネルギーの候補を不採用にした台帳の項目を返す
    （題名の語による目印。tier1〜3のみ）。見出しが定型文でない・台帳が無い日は空。"""
    headline = (sections.get("part1_headline") or "").strip() if isinstance(sections, dict) else ""
    if headline != generate_post.FIXED_HEADLINE or not isinstance(audit_ledger, list):
        return []
    tmap = tier_map if tier_map is not None else {}
    hits = []
    for e in audit_ledger:
        if not isinstance(e, dict) or e.get("decision") != "不採用":
            continue
        tier = tmap.get(e.get("source"))
        if tier not in (1, 2, 3):
            continue
        reason = str(e.get("reason", ""))
        if not _GEO_B_LABEL_RE.match(reason):
            continue
        title = str(e.get("title", ""))
        groups = [name for name, rx in _GEO_TOPIC_GROUPS if rx.search(title)]
        if groups:
            hits.append({"title": title, "source": e.get("source", ""), "tier": tier,
                         "topic": groups, "reason": reason})
    return hits


def check_geo_rejected_warn(au: Audit, sections: dict, audit_ledger,
                            tier_map: "dict[str, int] | None" = None) -> None:
    """見出しが定型文の日に、B判定の地政学・エネルギー材料の不採用があれば、その日に1件の警告をau.warningsへ追加する
    （FAILにしない）。"""
    hits = find_geo_rejected_under_fixed_headline(sections, audit_ledger, tier_map)
    if not hits:
        return
    listed = "".join(
        f" ・{h['source']}「{_clip_sentence(h['title'], 80)}」［{'・'.join(h['topic'])}］"
        f"（理由: {_clip_sentence(h['reason'], _GEO_REASON_CHARS)}）"
        for h in hits[:_GEO_WARN_MAX_LISTED])
    more = f" ほか{len(hits) - _GEO_WARN_MAX_LISTED}件" if len(hits) > _GEO_WARN_MAX_LISTED else ""
    au.warn("W_geo_rejected_fixed",
            f"【ヘッドライン】が定型文（材料なし）のまま、呼び出しAが波及経路のある材料（B）と判定した地政学・エネルギー関連の候補が"
            f"{len(hits)}件、不採用になっています（「内容が薄い」「単独報道」だけで不採用にしていないか要確認。"
            "解説・論評・人事など、優先の対象外として不採用にした妥当なものも含まれえます。"
            "題名の語による目印で、記事の内容は見ていません）。" + listed + more,
            count=len(hits), entries=[{k: h[k] for k in ("source", "tier", "title", "topic", "reason")} for h in hits])


# --- 行頭の記号の整形の警告（v1.102・オーナー承認。FAILではない）---
#
# 背景: 2026-10-05分の主要なポイントの行頭が「・・」と二重になった（呼び出しAの項目がすでに「・」で始まっていた）。
# 呼び出しA・Bの出力の項目の先頭の行頭記号・空白は、受け取った直後に機械的に整形する（generate_post.normalize_item_head）。
# 整形は確実に直るため本文の確認は要らない。この警告は、モデルが指示（行頭に記号を付けない）を守らなかった頻度を、
# 毎朝の警告欄で追跡するための表示（整形前の項目は診断用のattempt_diagnostics.jsonに保存）。
def check_bullet_normalized_warn(au: Audit, normalized: "dict | None") -> None:
    if not isinstance(normalized, dict):
        return
    n_points = int(normalized.get("part1_points", 0) or 0)
    n_flow = int(normalized.get("part2_flow", 0) or 0)
    if n_points + n_flow <= 0:
        return
    parts = ([f"主要なポイント{n_points}項目"] if n_points else []) + ([f"市場のフロー{n_flow}連鎖"] if n_flow else [])
    au.warn("W_bullet_normalized",
            "モデルの出力の行頭に余分な記号・空白（「・・」等）があったため、機械的に整形しました（" + "・".join(parts) + "）。"
            "本文は整形後で、確認は不要です（モデルが指示を守らなかった頻度の記録。整形前の項目は診断用ファイルに保存）。",
            part1_points=n_points, part2_flow=n_flow)


# --- 見出し・他の採用材料を理由にした不採用の警告（WARN。FAILではない。v1.106・オーナー承認・調査3の案D）---
#
# 背景: 2026-10-05分で、tier2（Reuters）の候補19・22が、reasonに「B: …他の採用材料がありヘッドラインには採らない」と書かれて不採用になった。
# 「ヘッドラインの主題にするか」と「主要なポイントに載せるか」は別の判断（Bの扱いの基準の6）のため、ヘッドラインに採らない・他に採用材料があることだけを
# 理由にした不採用は、載せるべき材料を落としている可能性がある。過去の本番出力（10/5までの35日分のledger）で該当したのは、9/2の3件（重複先を示さない「他の採用材料と内容が重複し独立項目としては不要」型。v1.106追補で除外条件を狭めた）と10/5の2件だけだった。
# 判定（その日に1件の警告）: 台帳に、decision=不採用・情報源のtierが1または2（tier3・tier4は、tier規律で「ヘッドラインの根拠にしない」と書くのが正当なため除く）・
# reasonが次のいずれかを含む候補がある: 「ヘッドライン」「他の採用材料」「他に採用」「見出し」（ただし「見出しだけ」「見出しのみ」「見出し程度」〔見出しだけでは誰が・何をを書けない等、内容が見出し程度という理由〕は除く）。
# 正当な理由は除く（「手続き的」「上限」を含む＝手続き的な発表・上限4項目のための見送り／「同一」「重複」を含み、かつ重複先の候補を「候補12」等と名指ししている＝同一事実の重複）。
# 限界: ①理由の言い回しに依存する（モデルが別の言い回し〔例:「見送り」のみ〕に変えると見逃す）。②「優先して掲載する対象に当たらない」型の不採用
# （従来のBに使うと誤り）は、この警告の対象外（語が違う）。③警告は「見直す材料」で、不採用が誤りだとは断定しない。
_HEADLINE_REASON_RE = re.compile(r"ヘッドライン|他の採用材料|他に採用|見出し(?!だけ|のみ|程度)")
# 除外する正当な理由: 「手続き的」（手続き的な発表）・「上限」（上限4項目のための見送り）は常に除く。「同一」「重複」（同一事実の重複）は、
# 重複先の候補を「候補12」「ID12」のように名指ししている場合だけ除く（v1.106追補: 重複先を示さない「他の採用材料と内容が重複し独立項目としては不要」
# 型の理由は、ヘッドラインに採らない・他に採用材料があることを理由にした不採用と区別できないため、除外しない）。
_HEADLINE_REASON_EXEMPT = ("手続き的", "上限")
_HEADLINE_REASON_EXEMPT_IF_CITED = ("同一", "重複")
_CANDIDATE_REF_RE = re.compile(r"候補\s*(?:ID\s*)?[0-9０-９]+|ID\s*[0-9０-９]+")
_HEADLINE_WARN_MAX_LISTED = 5


def find_headline_reason_rejections(audit_ledger, tier_map: "dict[str, int] | None" = None) -> "list[dict]":
    if not isinstance(audit_ledger, list):
        return []
    tmap = tier_map if tier_map is not None else {}
    hits = []
    for e in audit_ledger:
        if not isinstance(e, dict) or e.get("decision") != "不採用" or tmap.get(e.get("source")) not in (1, 2):
            continue
        reason = str(e.get("reason", ""))
        if (_HEADLINE_REASON_RE.search(reason) and not any(w in reason for w in _HEADLINE_REASON_EXEMPT)
                and not (any(w in reason for w in _HEADLINE_REASON_EXEMPT_IF_CITED) and _CANDIDATE_REF_RE.search(reason))):
            hits.append({"source": e.get("source", ""), "tier": tmap.get(e.get("source")), "title": str(e.get("title", "")), "reason": reason})
    return hits


def check_headline_reason_warn(au: Audit, audit_ledger, tier_map: "dict[str, int] | None" = None) -> None:
    hits = find_headline_reason_rejections(audit_ledger, tier_map)
    if not hits:
        return
    listed = "".join(f" ・{h['source']}「{_clip_sentence(h['title'], 80)}」（理由: {_clip_sentence(h['reason'], 70)}）" for h in hits[:_HEADLINE_WARN_MAX_LISTED])
    more = f" ほか{len(hits) - _HEADLINE_WARN_MAX_LISTED}件" if len(hits) > _HEADLINE_WARN_MAX_LISTED else ""
    au.warn("W_headline_reason",
            f"ヘッドラインにしないこと（または他に採用する材料があること）を理由に不採用にした候補が{len(hits)}件あります。"
            "見出しの主題にするかと、主要なポイントに載せるかは別の判断です（Bの扱いの基準の6）。主要なポイントに載せる判断を確認してください"
            "（理由の言い回しによる検知で、不採用が誤りだとは断定しません）。" + listed + more,
            count=len(hits), entries=hits)


# --- 見出しの繰り返しの警告（WARN。FAILではない。v1.108・オーナー承認・調査1）---
#
# 背景: 2026-10-06分で、ヘッドラインの主題（FRBボウマン理事の講演・候補3と19）が、主要なポイントの1番目で繰り返された。v1.105で
# 「ヘッドラインと同じ材料は主要なポイントで繰り返さない」と書いたが、台帳の理由文（「Reuters報道と同一事実のため両者をuseにして1項目にまとめた」）から、
# v1.104追補の「tier1とtier2が同一の事実のときは両方use:trueにして1項目にまとめる」（どこに載せるかを書いていなかった）を適用した可能性が高い。
# 繰り返しはv1.105より前（9/17・9/24・10/2・10/5など）からあり、機械的な検知は無かった。
# 判定（主要なポイントの項目ごとに1件）: ヘッドラインと主要なポイントの項目に、固有の語（英字3字以上・カタカナ3字以上・漢字3字以上の連なり。
# 括弧書き・媒体名・一般的な語を除く）が3語以上共通していれば警告する。定型文の項目・定型文のヘッドラインは対象外。
# 追跡用（オーナー指示: 毎日出てもよい）。限界: 語の重なりによる近似で、①同じ機関・人物の別の材料（同じ人物の別の発言）も共通語が多ければ拾う
# ②言い換えで共通語が少ない繰り返しは見逃す。過去分（〜10/6）では、v1.107より前の「1件だけの日は1項目」の運用による繰り返しも拾う。
_REPEAT_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&\-\.]{2,}|[ァ-ヴー]{3,}|[一-龥]{3,}")
_REPEAT_STOP = frozenset({
    "reuters", "coindesk", "cointelegraph", "block", "btc", "eth", "bnb", "usdc", "the", "and", "for", "with",
    "暗号通貨", "暗号資産", "暗号通貨市場", "暗号通貨専門", "専門メディア", "公式発表", "直接因果", "未確認", "可能性", "意識された",
    "市場", "影響", "材料", "報道", "報じられ", "発表", "確認", "媒体", "複数", "同一", "関わる", "関する", "ついて",
})
_REPEAT_MIN_SHARED = 3
_REPEAT_MAX_LISTED = 6


def _repeat_tokens(text: str) -> "set[str]":
    text = re.sub(r"（[^（）]*）", "", str(text or ""))  # （媒体名、日付）・断り書きの括弧は比べない
    return {m.group(0) for m in _REPEAT_TOKEN_RE.finditer(text) if m.group(0).lower() not in _REPEAT_STOP}


def find_headline_repeats(sections: dict) -> "list[dict]":
    """主要なポイントの項目のうち、ヘッドラインと固有の語が{_REPEAT_MIN_SHARED}語以上共通するものを返す。
    各要素: {"item_no"（1始まり）, "shared"（共通語。ソート済み）, "text"（項目）}。"""
    headline = str((sections or {}).get("part1_headline") or "").strip()
    if not headline or headline == generate_post.FIXED_HEADLINE:
        return []
    htoks = _repeat_tokens(headline)
    out = []
    items = [re.sub(r"^・", "", ln.strip()) for ln in str((sections or {}).get("part1_points") or "").split("\n") if ln.strip()]
    for i, it in enumerate(items, start=1):
        if it.strip() == generate_post.FIXED_POINTS:
            continue
        shared = sorted(htoks & _repeat_tokens(it))
        if len(shared) >= _REPEAT_MIN_SHARED:
            out.append({"item_no": i, "shared": shared, "text": it})
    return out


def check_headline_repeat_warn(au: Audit, sections: dict) -> None:
    for h in find_headline_repeats(sections):
        au.warn("W_headline_repeat",
                f"主要なポイントの{h['item_no']}番目が、ヘッドラインと同じ材料の繰り返しの可能性があります"
                f"（共通語: {'・'.join(h['shared'][:_REPEAT_MAX_LISTED])}）。ヘッドラインに載せた材料は主要なポイントでは繰り返さない規則です"
                "（v1.105・v1.107。語の重なりによる検知で、別の材料の可能性もあります）。"
                f" 項目: 「{_clip_sentence(h['text'], 100)}」",
                item_no=h["item_no"], shared=h["shared"], sentence=h["text"])


# --- 重複の根拠が弱い不採用の警告（WARN。FAILではない。v1.109・オーナー承認・調査2）---
#
# 背景: 2026-10-06分で、Reuters「Fed's Daly: need for more hikes hinges on what happens with shocks」（候補26。金融政策の発言）が、
# 「FRB高官発言だが候補3と重複する金融政策材料のため、上限4項目の関係で見送り」として不採用になった。候補3はボウマン理事の銀行監督の講演で、
# 別の事実。v1.104で`use:false`にしてよい理由を限定した結果、枠の都合で落とす理由として「重複」が使われた可能性がある。
# 判定（不採用の候補ごとに1件）: reasonに「重複」「同じ事実」「同一の事実」「同一事実」があり、
#   ①重複先の候補ID（「候補3」「ID3」）が書かれていない（no_ref）、または
#   ②書かれた重複先の候補の題名と、この候補の題名に、固有の語（英語の一般的な語・媒体名を除く）が1語も共通していない（no_shared）
# とき警告する。重複先がtier違い・別の事実でも、題名の語が共通していれば拾わない（同じ人物・出来事なら題名に同じ語が出る）。
# 台帳の候補IDは、v1.109以降の台帳の`candidate_id`を使う（それ以前の台帳には無いため、その日は判定しない）。
# 限界: ①題名の語の重なりによる近似で、言い換え（Wall Street shares notch records／S&P 500, Nasdaq reach record highs）の実際の重複を拾う
# （10/6の記録で、重複の主張9件のうち3件が該当し、うち2件が別の材料の疑い・1件が実際の重複）。②同じ語を共有する別の事実は拾えない。
# 精度は10/10までの記録で見直す（オーナー指示）。
_DUP_REASON_RE = re.compile(r"重複|同じ事実|同一の事実|同一事実")
_DUP_REF_RE = re.compile(r"(?:候補|ID)\s*(?:ID\s*)?([0-9０-９]+)")
_DUP_TITLE_STOP = frozenset({
    "reuters", "the", "a", "an", "and", "or", "for", "with", "in", "on", "at", "to", "of", "from", "by", "after", "over", "as", "is", "are",
    "its", "it", "says", "say", "new", "coindesk", "cointelegraph", "block", "-",
})
_DUP_WARN_MAX_LISTED = 5


def find_weak_duplicate_claims(audit_ledger) -> "list[dict]":
    ledger = [e for e in (audit_ledger if isinstance(audit_ledger, list) else []) if isinstance(e, dict)]
    by_id = {e["candidate_id"]: e for e in ledger if isinstance(e.get("candidate_id"), int) and not isinstance(e.get("candidate_id"), bool)}
    if not by_id:
        return []
    out = []
    for e in ledger:
        cid = e.get("candidate_id")
        reason = str(e.get("reason", ""))
        if e.get("decision") != "不採用" or not isinstance(cid, int) or not _DUP_REASON_RE.search(reason):
            continue
        refs = sorted({int(x.translate(str.maketrans("０１２３４５６７８９", "0123456789"))) for x in _DUP_REF_RE.findall(reason)} - {cid})
        if not refs:
            out.append({"candidate_id": cid, "code": "no_ref", "refs": [], "title": str(e.get("title", "")), "reason": reason})
            continue
        mine = generate_post._tokenize_title(e.get("title", "")) - _DUP_TITLE_STOP
        known = [r for r in refs if r in by_id]
        if known and all(not (mine & (generate_post._tokenize_title(by_id[r].get("title", "")) - _DUP_TITLE_STOP)) for r in known):
            out.append({"candidate_id": cid, "code": "no_shared", "refs": known, "title": str(e.get("title", "")), "reason": reason,
                        "ref_titles": [str(by_id[r].get("title", "")) for r in known]})
    return out


def check_dup_weak_warn(au: Audit, audit_ledger) -> None:
    hits = find_weak_duplicate_claims(audit_ledger)
    if not hits:
        return
    labels = {"no_ref": "重複先の候補IDが書かれていない", "no_shared": "重複先の候補と題名に共通する語が無い"}
    listed = "".join(f" ・候補{h['candidate_id']}「{_clip_sentence(h['title'], 60)}」（{labels[h['code']]}"
                     + (f"。重複先: 候補{'・'.join(str(r) for r in h['refs'])}「{_clip_sentence(h['ref_titles'][0], 50)}」" if h.get("ref_titles") else "")
                     + f"。理由: {_clip_sentence(h['reason'], 60)}）" for h in hits[:_DUP_WARN_MAX_LISTED])
    more = f" ほか{len(hits) - _DUP_WARN_MAX_LISTED}件" if len(hits) > _DUP_WARN_MAX_LISTED else ""
    au.warn("W_dup_weak",
            f"「重複」を理由に不採用にした候補のうち、根拠が弱いものが{len(hits)}件あります。同じ区分でも発言者や内容が違えば別の事実です"
            "（Bの扱いの基準の4(c)）。重複先と同じ事実かを確認してください（題名の語の重なりによる検知で、実際の重複でも言い換えで拾うことがあります）。"
            + listed + more,
            count=len(hits), entries=[{k: v for k, v in h.items() if k != "reason"} for h in hits])


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


def summarize_check_results(checks: "list[dict]") -> dict:
    """本文監査の結果の件数（v1.88・オーナー承認・表示のみの変更）。
    {"PASS": n, "SKIP": n, "FAIL": n, "total": n, "skip_ids": ["C19", ...]}。
    GENERATION_STATUS.mdの「overall=PASS（計17項目）」だけでは、L1の日のようにSKIPが
    多い（10/1は17項目中PASS13・SKIP4）ことが分からなかったため、件数を併記する。
    skip_idsはSKIPしたチェックの番号（C16b等の枝番は親番号に含め、重複は1つにまとめる）。"""
    counts = {"PASS": 0, "SKIP": 0, "FAIL": 0}
    skip_ids: list[str] = []
    for c in checks:
        r = c.get("result")
        if r in counts:
            counts[r] += 1
        if r == "SKIP":
            m = re.match(r"(C\d+[a-z]?)", str(c.get("id", "")))
            sid = m.group(1) if m else str(c.get("id", ""))
            if sid not in skip_ids:
                skip_ids.append(sid)
    return {**counts, "total": len(checks), "skip_ids": skip_ids}


def format_check_counts(summary: dict) -> str:
    """例: 「PASS13・SKIP4〔C19・C21・C22・C26〕・FAIL0」。"""
    skip = f"〔{'・'.join(summary['skip_ids'])}〕" if summary.get("skip_ids") else ""
    return f"PASS{summary['PASS']}・SKIP{summary['SKIP']}{skip}・FAIL{summary['FAIL']}"


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
    # v1.91: 警告の種類ごとに独立して実行する（1つの検知が失敗しても他の警告と監査全体は止めない）。
    for _label, _fn in (
        ("向きの食い違い", lambda: check_direction_warn(au, sections, headline_for_image)),
        ("見出しのタグ", lambda: check_hashtag_warn(au, sections)),
        ("指標日の見出し", lambda: check_indicator_headline_warn(
            au, sections, bundle.get("audit_ledger"), daily_data.get("scheduled_events"))),
        ("フロー書式", lambda: check_flow_format_warn(au, sections, bool(bundle.get("flow_price_fragment")))),
        ("媒体名照合", lambda: check_media_warn(au, sections, bundle.get("audit_ledger"), tier_map)),
        ("地政学の不採用", lambda: check_geo_rejected_warn(au, sections, bundle.get("audit_ledger"), tier_map)),
        ("行頭の記号", lambda: check_bullet_normalized_warn(au, bundle.get("format_normalized"))),
        ("見出し理由の不採用", lambda: check_headline_reason_warn(au, bundle.get("audit_ledger"), tier_map)),
        ("見出しの繰り返し", lambda: check_headline_repeat_warn(au, sections)),
        ("重複の根拠が弱い", lambda: check_dup_weak_warn(au, bundle.get("audit_ledger"))),
    ):
        try:
            _fn()
        except Exception as e:  # noqa: BLE001
            print(f"WARN: {_label}チェック自体が失敗しました（警告なしとして続行）: {type(e).__name__}: {e}", file=sys.stderr)
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
