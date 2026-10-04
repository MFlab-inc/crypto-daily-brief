#!/usr/bin/env python3
"""フェーズ2 第2弾のオフライン検証（本物のAnthropic/RSS APIは呼ばない）。
一時ディレクトリへ os.chdir して実行し、実リポジトリの outputs/ を汚染しない。

使い方:
  python test/test_bundle2.py
"""
import json
import os
import sys
import tempfile
from datetime import date as _date, datetime as _datetime, timedelta as _timedelta, timezone as _timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRATCH = Path(tempfile.mkdtemp(prefix="bundle2_test_"))
sys.path.insert(0, str(REPO / "scripts"))
os.chdir(SCRATCH)

import generate_post  # noqa: E402
import compose_post  # noqa: E402
import verify_post  # noqa: E402
import collect_news  # noqa: E402
import fetch_data  # noqa: E402
import compose_numeric  # noqa: E402
import repair_post  # noqa: E402
import indicator_events  # noqa: E402


# 警告の種類別件数の期待文字列を、登録簿（verify_post.WARNING_KINDS）から作る（警告の種類が増えてもテストが壊れないように）。
# 例: _wk(direction=1) → 「向きの食い違い1・見出しのタグ0・指標日の見出し0…」
_WK_SHORT = {"direction": "W_direction_mismatch", "hashtag": "W_headline_hashtag", "indicator": "W_indicator_headline",
             "flow": "W_flow_format", "media": "W_media_mismatch"}


def _wk(**counts):
    ids = {_WK_SHORT[k]: v for k, v in counts.items()}
    return "・".join(f"{label}{ids.get(wid, 0)}" for wid, label in verify_post.WARNING_KINDS)


PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
    else:
        FAIL.append(f"{name} :: {detail}")
        print(f"  [FAIL] {name} :: {detail}")


# ---------- フィクスチャ ----------

DAILY_DATA = {
    "target_date_jst": "2026-08-17",
    "weekday_jp": "月",
    "date_title": "2026年8月17日（月）暗号通貨・DEX市場概況",
    "summary": "（シャドー運用中）",
    "assets": [
        {"asset": "BTC", "usd": "$64,247", "jpy": "約1,022.8万円", "change_24h": "+2.43%", "direction": "up"},
        {"asset": "ETH", "usd": "$1,903", "jpy": "約30.3万円", "change_24h": "+1.65%", "direction": "up"},
        {"asset": "BNB", "usd": "$604", "jpy": "約9.62万円", "change_24h": "+0.48%", "direction": "up"},
    ],
    "market": {
        "fear_greed": {"value": 40, "label": "Neutral"},
        "market_cap": "$2.194兆", "market_cap_jpy": "¥349.2兆",
        "volume_24h": "$514.1億", "volume_24h_jpy": "¥8.18兆",
        "btc_dominance": "58.79%", "eth_dominance": "10.47%",
    },
    "base": {
        "tvl": "$47.36億", "tvl_jpy": "¥7,540億", "tvl_change": "+2.69%", "tvl_direction": "up",
        "dex_volume": "$4.318億", "dex_volume_jpy": "¥687億", "usdc_dominance": "86.0%",
        "dex_volume_eth_usdc": "$12.5M", "dex_volume_eth_usdc_jpy": "¥19.9億",
    },
    "lp": {
        "pools": [
            {"name": "Base 0.05%プール", "apr": "12.72%", "tvl": "$10.15M", "volume_24h": "$7.08M",
             "change_vs_prev": {"apr_change": "+1.20%", "volume_24h_change": "+8.40%", "tvl_change": "+0.50%"}},
            {"name": "Base 0.3%プール", "apr": "24.00%", "tvl": "$112.38M", "volume_24h": "$24.63M",
             "change_vs_prev": {"apr_change": "-0.80%", "volume_24h_change": "-2.00%", "tvl_change": "-1.00%"}},
        ],
        "check_message": "#ETHが上昇中",
    },
    "domestic": {
        "bitflyer_eth_24h": "4,248.58 ETH", "coincheck_eth_24h": "788.98 ETH",
        "combined_eth": "5,037.56 ETH", "combined_usd": "$9.59M",
        "retrieved_at": "2026-08-18 07:50 JST",
    },
    "footer": {
        "retrieved_at": "2026-08-18 07:50 JST", "usd_jpy": "¥159.20",
        "sources": "CoinMarketCap API / GeckoTerminal / DefiLlama / ExchangeRate-API / bitFlyer Lightning API / Coincheck Public API",
    },
}

CALL_A_DATA = {
    "headline_for_image": "規制動向を材料に暗号通貨市場は総じて上昇",
    "part1_headline": "米規制当局の発言が確認され、同時期に主要銘柄は軒並み上昇して推移しました（因果は未確認）。",
    "part1_points": ["規制当局高官が友好的な発言（Reuters、2026-08-17）", "機関投資家の資金流入が継続との報道（Bloomberg、2026-08-17）"],
    "reusable_for_summary": ["某国の法整備は継続審議中、新展開なし"],
    "audit_ledger": [
        # v1.29: sourceはC21がtier判定に使うため実在のtier1名（SEC）を使う
        # （以前は仮の"Reuters"だったが、config/news_sources.jsonに存在せず
        # C21がtier不明＝FAILと判定してしまうため変更）。
        {"source": "SEC", "url": "https://example.com/a", "title": "...", "published_at": "2026-08-17",
         "verified_by": "RSS summary", "decision": "採用", "reason": "一次情報で確認"},
    ],
}
CALL_B_DATA = {
    # v1.94: 統合運用基準§3.3の書式（【出来事・ニュース】→…→【暗号通貨価格】・1文・末尾に限定表現）に合わせた
    # 共通フィクスチャ（書式を見るWARNが他のテストの警告件数に混ざらないようにするため）。
    "part2_flow": ["【出来事・ニュース】規制当局が発言した → 【地政学・マクロの変化】好感された可能性 → "
                   "【暗号通貨価格】主要銘柄の上昇が同時期に確認されたが、因果は未確認です。"],
    "part2_summary": "地合いは総じて改善。継続的な確認が必要。",
}

NEWS_TODAY = {
    "collected_at": "2026-08-17T09:00:00+09:00",
    "target_date_jst": "2026-08-17",
    "source_status": {"SEC": {"status": "ok", "raw_count": 2, "kept_count": 1}},
    "candidates": [
        {"title": "Test filing", "url": "https://example.gov/x", "source": "SEC",
         "published_at": "Mon, 17 Aug 2026 10:00:00 GMT", "summary": "Test summary text.",
         "kind": "official", "tier": 1},
    ],
}


# ---------- フェイクAnthropicクライアント ----------

class FakeTextBlock:
    type = "text"
    def __init__(self, text):
        self.text = text


class FakeStopDetails:
    def __init__(self, category=None):
        self.category = category


class FakeResponse:
    def __init__(self, content, stop_reason="end_turn", stop_details=None):
        self.content = content
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class FakeMessages:
    def __init__(self, fn):
        self.fn = fn
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.fn(kwargs, len(self.calls))


class FakeClient:
    def __init__(self, fn):
        self.messages = FakeMessages(fn)


def json_response(obj):
    return FakeResponse([FakeTextBlock(json.dumps(obj, ensure_ascii=False))])


def _parse_leading_json(text: str) -> dict:
    """v1.66: user_contentの先頭に書かれたJSON部分だけを取り出す。
    build_retry_note（v1.66）導入後、リトライ時のuser_contentはJSONの
    後ろに修正指示の追記テキストが続く形になり得るため、json.loads()の
    単純な全文パースでは失敗する。json.loads()ではなくraw_decode()を
    使い、先頭のJSON値だけを読み取って後続のテキストは無視する。"""
    return json.JSONDecoder().raw_decode(text)[0]


def _mock_audit_ledger_from_request(kw: dict) -> list:
    """v1.48: FakeClientのfn(kw, n)へ渡された実際のリクエストから
    news_candidates_todayのcandidate_idを読み取り、audit_ledgerを動的に
    構成する。固定フィクスチャが候補数・IDに依存してしまう問題を避け、
    どんな候補セット（0件を含む）でも整合するモック応答を作れるように
    する。監査内容の妥当性（tier整合等）を検証する目的のテストではない
    ため、tier1はuse:true（decisionは"採用"に導出される）、tier3/4は
    use:false（"不採用"）で一律とする（v1.53フォローアップ）。tier3/4を
    一律use:trueにすると、pairs_with_candidate_idの申告なし・相方も
    存在しないため_reconstruct_audit_ledger()が例外を送出してしまう
    ——このヘルパーはそもそも決定内容を検証しないテスト群が使うため、
    構造的に必ず成功する組み合わせを選ぶ。
    """
    try:
        content = _parse_leading_json(kw["messages"][0]["content"])
        candidates = content.get("news_candidates_today", [])
    except (KeyError, ValueError, TypeError):
        return []
    return [{"candidate_id": c["candidate_id"], "use": c.get("tier") == 1,
             "verified_by": "RSS summary" if c.get("tier") == 1 else "",
             "reason": "一次情報で確認" if c.get("tier") == 1 else "C: 対象外"}
            for c in candidates if "candidate_id" in c]


def _call_a_response(kw: dict) -> dict:
    """v1.48: CALL_A_DATAのheadline_for_image等はそのまま使い、audit_ledger
    だけをリクエストの実際の候補セットへ整合する形へ差し替えたモック応答。"""
    return {**CALL_A_DATA, "audit_ledger": _mock_audit_ledger_from_request(kw)}


print("=== generate_post._call_json ===")

# 1) 成功（1回目でJSON妥当）・toolsパラメータを一切渡さないことも確認（v1.15）
c = FakeClient(lambda kw, n: json_response(_call_a_response(kw)))
out = generate_post.call_a(c, DAILY_DATA, NEWS_TODAY, None)
check("callA success 1発", out.ok and out.attempts == 1, str(out.error))
check("callA: toolsパラメータを渡さない（v1.15・ツール無し呼び出し）",
      "tools" not in c.messages.calls[0], str(list(c.messages.calls[0].keys())))
check("callA: thinkingを明示的に無効化する（v1.28）",
      c.messages.calls[0].get("thinking") == {"type": "disabled"}, str(c.messages.calls[0].get("thinking")))

# 2) JSON不正 → リトライで成功
def flaky_json(kw, n):
    if n == 1:
        return FakeResponse([FakeTextBlock("not json{{{")])
    return json_response(_call_a_response(kw))
c = FakeClient(flaky_json)
out = generate_post.call_a(c, DAILY_DATA, {"candidates": []}, None)
check("callA JSON不正→リトライ成功", out.ok and out.attempts == 2, str(out.error))
check("callA JSON不正→リトライ成功: attempt_errorsに1試行目の失敗が残る（v1.48・成功時も保持）",
      len(out.attempt_errors) == 1 and "not json" not in out.attempt_errors[0]
      and ("JSONDecodeError" in out.attempt_errors[0] or "ValueError" in out.attempt_errors[0]),
      str(out.attempt_errors))

# 2b) audit_ledgerが存在しない候補IDを参照 → post_process内で例外→リトライ→成功（v1.48）
def bad_candidate_id_then_ok(kw, n):
    if n == 1:
        bad = {**CALL_A_DATA, "audit_ledger": [{"candidate_id": 999, "use": True,
                                                  "verified_by": "x", "reason": "y"}]}
        return json_response(bad)
    return json_response(_call_a_response(kw))
c = FakeClient(bad_candidate_id_then_ok)
out = generate_post.call_a(c, DAILY_DATA, NEWS_TODAY, None)
check("callA: 存在しない候補IDを参照したaudit_ledgerはリトライされ、2回目で成功する（v1.48）",
      out.ok and out.attempts == 2, f"ok={out.ok} attempts={out.attempts} error={out.error}")
check("callA: 存在しない候補IDのリトライ理由がattempt_errorsに記録される（v1.48）",
      len(out.attempt_errors) == 1 and "AuditLedgerReconstructionError" in out.attempt_errors[0],
      str(out.attempt_errors))
check("callA: リトライ後に成功した最終audit_ledgerは候補データで正しく再構成されている（v1.48）",
      out.data["audit_ledger"][0]["url"] == NEWS_TODAY["candidates"][0]["url"], str(out.data["audit_ledger"]))

# 2c) call_a()のpair_overlap_threshold引数がend-to-endで効くことの確認（v1.53フォローアップ・オーナー指示）
NEWS_PAIR_CANDIDATES = {
    "collected_at": "2026-08-17T09:00:00+09:00", "target_date_jst": "2026-08-17", "source_status": {},
    "candidates": [
        {"title": "Company A files BTC ETF approval", "url": "https://example.com/pa", "source": "CoinDesk",
         "published_at": "Mon, 17 Aug 2026 10:00:00 GMT", "summary": "...", "kind": "supplementary", "tier": 3},
        {"title": "Company A discusses BTC outlook today", "url": "https://example.com/pb",
         "source": "Cointelegraph", "published_at": "Mon, 17 Aug 2026 09:30:00 GMT", "summary": "...",
         "kind": "supplementary", "tier": 3},
    ],
}  # overlap係数0.5（company/a/btcの3語が共通）


def _pair_claim_response(kw: dict) -> dict:
    content = _parse_leading_json(kw["messages"][0]["content"])
    ids = sorted(c["candidate_id"] for c in content.get("news_candidates_today", []))
    entries = [{"candidate_id": ids[0], "use": True, "pairs_with_candidate_id": ids[1], "reason": "同一事実"},
               {"candidate_id": ids[1], "use": True, "reason": "同一事実"}]
    return {**CALL_A_DATA, "audit_ledger": entries}


c_loose = FakeClient(lambda kw, n: json_response(_pair_claim_response(kw)))
out_loose = generate_post.call_a(c_loose, DAILY_DATA, NEWS_PAIR_CANDIDATES, None, 0.4)
check("callA: pair_overlap_threshold=0.4（overlap0.5のペア成立）を明示指定すると1回目に成功する"
      "（v1.53フォローアップ・パラメータの実効性確認）",
      out_loose.ok and out_loose.attempts == 1, f"ok={out_loose.ok} attempts={out_loose.attempts} error={out_loose.error}")

c_strict = FakeClient(lambda kw, n: json_response(_pair_claim_response(kw)))
out_strict = generate_post.call_a(c_strict, DAILY_DATA, NEWS_PAIR_CANDIDATES, None, 0.6)
check("callA: pair_overlap_threshold=0.6（overlap0.5のペア不成立）を明示指定すると、"
      "MAX_ATTEMPTS回のうち最初の2回は通常どおりリトライされる"
      "（config/pair_overlap.jsonで調整可能なことをend-to-endで確認）",
      out_strict.attempts == generate_post.MAX_ATTEMPTS,
      f"ok={out_strict.ok} attempts={out_strict.attempts}")
check("callA: v1.79（オーナー承認）・最終試行でも解消しない場合は例外化せず強制不採用にして続行する"
      "ため、最終的にはokになる（force_dropped_candidatesに両候補が記録される）",
      out_strict.ok
      and {c["candidate_id"] for c in out_strict.force_dropped_candidates} == {1, 2},
      f"ok={out_strict.ok} force_dropped={out_strict.force_dropped_candidates}")
check("callA: 強制不採用にした候補のaudit_ledger上のdecisionは「不採用」になる（v1.79）",
      out_strict.ok
      and all(e["decision"] == "不採用" for e in out_strict.data["audit_ledger"]),
      str(out_strict.data.get("audit_ledger") if out_strict.data else None))
check("callA: 閾値超過による失敗のattempt_errorsに「独立2ソースの相方が成立しない」が記録される"
      "（1・2試行目は例外化されるため。GENERATION_STATUS.mdへの記録経路の確認・オーナー指示の確認事項）",
      len(out_strict.attempt_errors) == generate_post.MAX_ATTEMPTS - 1
      and all("独立2ソースの相方が成立しない" in e for e in out_strict.attempt_errors),
      str(out_strict.attempt_errors))
check("callA: rejected_pairsに最終試行（強制不採用が発生した試行）の却下ペア診断が記録される"
      "（v1.79・GitHub Actionsアーティファクト用の診断情報）",
      len(out_strict.rejected_pairs) == 1
      and out_strict.rejected_pairs[0]["reason"] == "overlap_below_threshold"
      and out_strict.rejected_pairs[0]["claimant_title"] and out_strict.rejected_pairs[0]["target_title"],
      str(out_strict.rejected_pairs))

print("=== generate_post.regenerate_call_b_as_l1（v1.79・オーナー承認・"
      "force_drop後の再監査FAILからのL1フォールバック用） ===")

c_l1 = FakeClient(lambda kw, n: json_response(CALL_B_DATA))
out_l1 = generate_post.regenerate_call_b_as_l1(DAILY_DATA, client=c_l1)
check("regenerate_call_b_as_l1: call_b()をnews_from_call_a=Noneで呼び出した場合と同じ結果になる",
      out_l1.ok, str(out_l1.error))
_l1_sent = json.loads(c_l1.messages.calls[0]["messages"][0]["content"])
check("regenerate_call_b_as_l1: 送信されたuser_contentのnews_from_call_aがNoneになっている"
      "（呼び出しAを失敗扱いに差し戻した従来のL1と同じ入力）",
      _l1_sent.get("news_from_call_a") is None, json.dumps(_l1_sent))

print("=== generate_post._call_json: build_retry_noteによる失敗フィードバック（v1.66・オーナー承認） ===")

# 2d) _call_json汎用: build_retry_note指定時、直前の例外内容が次の試行のuser_content
# へ追記されること・build_retry_note未指定時は従来どおり無変更で再送されること
# （9/3実データで同一エラーが2回連続再現しトークンを4倍消費した事象への対処。
# DESIGN_CHANGES.md v1.64参照）
def _fail_once_then_ok(kw, n):
    if n == 1:
        raise ValueError("dummy failure: bad ids [7, 9]")
    return json_response({"a": 1})


c_note = FakeClient(_fail_once_then_ok)
out_note = generate_post._call_json(
    c_note, system="sys", user_content="BASE_CONTENT_MARKER", max_tokens=100,
    required_keys=["a"], build_retry_note=lambda exc: f"NOTE_ABOUT:{exc}")
check("_call_json: build_retry_note指定時、1回目はuser_content無変更で送られる（v1.66）",
      c_note.messages.calls[0]["messages"][0]["content"] == "BASE_CONTENT_MARKER",
      c_note.messages.calls[0]["messages"][0]["content"])
check("_call_json: build_retry_note指定時、2回目には元のuser_content＋直前の例外内容の"
      "注記が追記される（v1.66・オーナー承認・トークン浪費対策）",
      out_note.ok and out_note.attempts == 2
      and "BASE_CONTENT_MARKER" in c_note.messages.calls[1]["messages"][0]["content"]
      and "NOTE_ABOUT:dummy failure: bad ids [7, 9]" in c_note.messages.calls[1]["messages"][0]["content"],
      c_note.messages.calls[1]["messages"][0]["content"])

c_nonote = FakeClient(_fail_once_then_ok)
out_nonote = generate_post._call_json(
    c_nonote, system="sys", user_content="BASE_CONTENT_MARKER", max_tokens=100,
    required_keys=["a"])
check("_call_json: build_retry_note未指定（デフォルトNone）時は従来どおり2回目もuser_content"
      "無変更（後方互換・call_B等の既存呼び出しに影響しない）",
      out_nonote.ok and out_nonote.attempts == 2
      and c_nonote.messages.calls[1]["messages"][0]["content"] == "BASE_CONTENT_MARKER",
      c_nonote.messages.calls[1]["messages"][0]["content"])


def _fail_every_time(kw, n):
    raise ValueError(f"fail-{n}")


c_accum = FakeClient(_fail_every_time)
out_accum = generate_post._call_json(
    c_accum, system="sys", user_content="BASE", max_tokens=100,
    required_keys=["a"], build_retry_note=lambda exc: f"NOTE:{exc}")
check("_call_json: build_retry_noteは直前1回分の失敗のみを反映し、複数回分を蓄積しない（v1.66）",
      not out_accum.ok and len(c_accum.messages.calls) == generate_post.MAX_ATTEMPTS
      and "NOTE:fail-1" in c_accum.messages.calls[1]["messages"][0]["content"]
      and "NOTE:fail-1" not in c_accum.messages.calls[2]["messages"][0]["content"]
      and "NOTE:fail-2" in c_accum.messages.calls[2]["messages"][0]["content"],
      str([call["messages"][0]["content"] for call in c_accum.messages.calls]))

# 2e) call_a()固有: AuditLedgerReconstructionErrorに限り、失敗した候補IDを
# 名指しした修正指示が2回目のuser_contentへ追記されること。「名指しされた
# 候補IDについてのみ」「他の候補は変更しない」という限定的な文言により、
# オーナーが懸念した「疑わしければ全て落とす」という過剰反応を防ぐ設計に
# なっていることを確認する。
c_pairnote = FakeClient(lambda kw, n: json_response(_pair_claim_response(kw)))
out_pairnote = generate_post.call_a(c_pairnote, DAILY_DATA, NEWS_PAIR_CANDIDATES, None, 0.6)
_attempt2_content = c_pairnote.messages.calls[1]["messages"][0]["content"]
check("call_a: AuditLedgerReconstructionError発生時、2回目のuser_contentに元の候補データが"
      "維持されたまま修正指示が追記される（v1.66）。v1.79導入後は最終（3回目）試行で"
      "強制不採用により続行するためout_pairnote.ok自体はTrueになるが、1→2回目の"
      "リトライノート注入という本チェックの対象動作自体は変わらない",
      out_pairnote.ok
      and "news_candidates_today" in _attempt2_content
      and "直前の試行への修正指示" in _attempt2_content,
      _attempt2_content[-400:])
check("call_a: 修正指示に「名指しされた候補IDについてのみ」という限定的な文言が含まれる"
      "（オーナー指示・過剰反応防止の確認事項）",
      "候補IDについてのみ" in _attempt2_content, _attempt2_content[-400:])
check("call_a: 修正指示に「名指しされていない他の候補」は変更しない旨が明記される"
      "（オーナー指示・「疑わしければ全て落とす」の防止）",
      "名指しされていない他の候補" in _attempt2_content and "変更しないでください" in _attempt2_content,
      _attempt2_content[-400:])
check("call_a: 修正指示に直前の試行の実際のエラー内容（該当候補IDを含む）がそのまま含まれる",
      "独立2ソースの相方が成立しない候補ID" in _attempt2_content,
      _attempt2_content[-400:])

# call_b()は_call_json()のbuild_retry_note未指定呼び出しのままであり、
# 既存のリトライ挙動（無変更で再送）に影響しないことを確認する。
def _callb_fail_then_ok(kw, n):
    if n == 1:
        return FakeResponse([FakeTextBlock("not json{{{")])
    return json_response(CALL_B_DATA)


c_b = FakeClient(_callb_fail_then_ok)
out_b = generate_post.call_b(c_b, DAILY_DATA, CALL_A_DATA)
check("call_b: build_retry_note未指定のためリトライ時もuser_contentは無変更のまま"
      "（v1.66導入後もcall_bの既存挙動に影響がないことの回帰確認）",
      out_b.ok and out_b.attempts == 2
      and c_b.messages.calls[0]["messages"][0]["content"] == c_b.messages.calls[1]["messages"][0]["content"],
      None)

# 3) 必須キー欠落 → 最大試行後に失敗
def missing_key(kw, n):
    return json_response({"headline_for_image": "x"})  # 他キー欠落
c = FakeClient(missing_key)
out = generate_post.call_a(c, DAILY_DATA, {"candidates": []}, None)
check("callA 必須キー欠落→MAX_ATTEMPTS回試行後FAILED",
      not out.ok and out.attempts == generate_post.MAX_ATTEMPTS and len(c.messages.calls) == generate_post.MAX_ATTEMPTS,
      f"ok={out.ok} attempts={out.attempts} calls={len(c.messages.calls)}")

# 4) コードフェンス付き（禁止されているが寛容に剥がす）
def fenced(kw, n):
    return FakeResponse([FakeTextBlock("```json\n" + json.dumps(CALL_B_DATA, ensure_ascii=False) + "\n```")])
c = FakeClient(fenced)
out = generate_post.call_b(c, DAILY_DATA, CALL_A_DATA)
check("callB コードフェンス除去", out.ok and out.attempts == 1, str(out.error))

print("=== generate_post._strip_code_fence: フェンス前プリアンブルの吸収（v1.29） ===")
# 実データで確認された実際の失敗パターン: フェンスの前に説明文（プリアンブル）が
# 付き、旧実装（位置0のフェンスのみ剥がす）はこれを剥がせずJSONDecodeErrorに
# なっていた（DESIGN_CHANGES.md参照）。
_json_body = json.dumps({"a": 1, "b": "値"}, ensure_ascii=False)
check("フェンスが位置0（プリアンブルなし）は従来どおり剥がせる",
      generate_post._strip_code_fence(f"```json\n{_json_body}\n```") == _json_body)
check("フェンス前にプリアンブルがあっても中身を取り出せる",
      generate_post._strip_code_fence(f"候補を確認しました。理由の説明。\n\n```json\n{_json_body}\n```") == _json_body)
check("複数行にわたる長いプリアンブルにも対応する",
      generate_post._strip_code_fence(
          f"1行目の検討。\n2行目の検討。\n3行目、結論として以下を出力します。\n```json\n{_json_body}\n```"
      ) == _json_body)
check("フェンスもプリアンブルも無ければ従来どおりそのまま",
      generate_post._strip_code_fence(_json_body) == _json_body)
check("フェンス無し・プリアンブルありでも最初の{から最後の}までを抽出する",
      generate_post._strip_code_fence(f"説明文です。\n{_json_body}") == _json_body)

# プリアンブル付きフェンスがcall_A経由でも正しくJSON解析されることを確認
# （_strip_code_fence単体だけでなく実際の呼び出し経路で回帰しないことの確認）
def preambled(kw, n):
    body = json.dumps(_call_a_response(kw), ensure_ascii=False)
    return FakeResponse([FakeTextBlock(f"候補を確認しました。tier1は少ないため慎重に判断します。\n\n```json\n{body}\n```")])
c = FakeClient(preambled)
out = generate_post.call_a(c, DAILY_DATA, {"candidates": []}, None)
check("callA: プリアンブル付きフェンスでも1回試行で成功する", out.ok and out.attempts == 1, str(out.error))

# 5) refusal → 失敗
def refused(kw, n):
    return FakeResponse([], stop_reason="refusal", stop_details=FakeStopDetails(category="frontier_llm"))
c = FakeClient(refused)
out = generate_post.call_a(c, DAILY_DATA, {"candidates": []}, None)
check("callA refusal→FAILED", not out.ok and "refusal" in (out.error or ""), str(out.error))

# 6) news_candidates_today（summary付き）がユーザーメッセージへそのまま伝播する
captured = {}
def capture_fn(kw, n):
    captured["kw"] = kw
    return json_response(_call_a_response(kw))
c = FakeClient(capture_fn)
generate_post.call_a(c, DAILY_DATA, NEWS_TODAY, None)
sent = json.loads(captured["kw"]["messages"][0]["content"])
check("callA: news_candidates_todayにsummaryがそのまま伝播する",
      sent["news_candidates_today"][0]["summary"] == "Test summary text.",
      json.dumps(sent.get("news_candidates_today"), ensure_ascii=False))

print("=== generate_post: web_search撤去の確認（v1.15） ===")
check("SYSTEM_Aに旧v1.13の検索必須文言が残っていない",
      "必ず web_search" not in generate_post.SYSTEM_A
      and "候補が空であることを理由に検索を省略してはならない" not in generate_post.SYSTEM_A)
check("SYSTEM_Aにweb_searchを使わない旨の記述がある",
      "web_searchは" in generate_post.SYSTEM_A and "使わない" in generate_post.SYSTEM_A)
check("SYSTEM_Aに「候補一覧のみを根拠にする」の指示がある",
      "候補一覧のみを根拠にする" in generate_post.SYSTEM_A)
check("SYSTEM_Aの候補ゼロ時fallbackに統合運用基準§3.1の定型文(FIXED_HEADLINE/FIXED_POINTS)を含む",
      generate_post.FIXED_HEADLINE in generate_post.SYSTEM_A and generate_post.FIXED_POINTS in generate_post.SYSTEM_A)
check("SYSTEM_Aの候補ゼロ時fallbackがaudit_ledger空配列を許容する",
      "空配列" in generate_post.NO_CANDIDATES_FALLBACK)

print("=== generate_post: audit_ledger完全性の確認（v1.17） ===")
check("NO_CANDIDATES_FALLBACKに「採否を判断した全候補の記録」の要求（統合運用基準・台本準拠）",
      "採否を判断した全候補の記録" in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKで空配列許容が「候補0件」の場合のみに限定されている",
      "audit_ledgerを空配列 [] にしてよいのは、" in generate_post.NO_CANDIDATES_FALLBACK
      and "候補が1件でも渡されている場合、audit_ledgerを空配列で返して" in generate_post.NO_CANDIDATES_FALLBACK)

print("=== generate_post.py: tier 2プロンプトの確認（v1.59・オーナー承認・指定文言の逐語反映） ===")
check("NEWS_SELECTIONにtier2の説明がオーナー指定文言のとおり逐語で含まれる",
      "tier 2: 優先度2：Reuters等の独立報道。単独で採用可能だが、tier1の公式発表と\n"
      "        異なり報道であることを明示すること（『Reutersによると』等）。"
      in generate_post.NEWS_SELECTION)
check("_ELIGIBILITY_LABELSでtier2が「掲載可」になっている（tier1と同格）",
      generate_post._ELIGIBILITY_LABELS[2] == "掲載可")

print("=== generate_post.py: tier 3プロンプトの確認（v1.20） ===")
check("NEWS_SELECTIONにtier 3の「補完・裏取り」記述がある",
      "tier 3" in generate_post.NEWS_SELECTION and "補完・裏取り" in generate_post.NEWS_SELECTION)
check("NEWS_SELECTIONにtier 3単独を主根拠にしない旨の記述がある",
      "tier 3の候補のみを根拠に" in generate_post.NEWS_SELECTION)
check("WRITES_Aがtier 1・2・3・4すべてを記録対象としている（v1.59でtier2を追加）",
      "tier 1・2・3・4のすべて" in generate_post.WRITES_A)

print("=== generate_post.py: 独立2ソース規定の確認（v1.28・統合運用基準の既定を実装へ反映） ===")
check("NEWS_SELECTIONに独立2ソース規定の3条件が記述されている",
      all(s in generate_post.NEWS_SELECTION for s in (
          "独立2ソース規定", "2つ以上の独立したtier3媒体", "意見・予想・分析ではなく",
          "媒体名を複数列挙")))
check("独立2ソース規定(c): 「一次情報」という内部用語ではなく読者向けの表現（公式発表）を使うよう指示する（v1.64・オーナー指示）",
      "公式発表での確認が取れていない旨を" in generate_post.NEWS_SELECTION
      and "内部用語は使わず、読者向けの平易な表現を" in generate_post.NEWS_SELECTION
      and "一次情報での裏付けが未確認である旨を明記する" not in generate_post.NEWS_SELECTION)
check("独立2ソース規定はpart1_headlineでの扱いをpart1_headline・part1_pointsの決定へ委譲する"
      "（v1.44・旧来のtier1限定の絶対文言は撤去）",
      "part1_headlineでの扱いは下記「part1_headline・part1_pointsの決定」を" in generate_post.NEWS_SELECTION
      and "【ヘッドライン】への昇格は引き続きtier1の裏付けを必要とする" not in generate_post.NEWS_SELECTION)
check("独立2ソース規定の自己申告（pairs_with_candidate_id）がOUTPUT_FORMAT_Aの例に含まれる"
      "（v1.53フォローアップ・オーナー指示・decision値はコード側導出のためLLMは書かない）",
      "pairs_with_candidate_id" in generate_post.OUTPUT_FORMAT_A
      and "採用（独立2ソース）" not in generate_post.OUTPUT_FORMAT_A
      and "採用（独立2ソース）" in generate_post.NEWS_SELECTION)
check("NO_CANDIDATES_FALLBACKに独立2ソース材料単独でもpart1_headlineの根拠になる旨が明記されている"
      "（v1.44・②の詳細）",
      "②（(i)なし・(ii)あり）の詳細" in generate_post.NO_CANDIDATES_FALLBACK
      and "独立2ソース材料の内容に基づき、part1_headlineに実文言を書く" in generate_post.NO_CANDIDATES_FALLBACK)

print("=== generate_post.py: 情報源規律と項目数の優先順位（v1.29・オーナー指示・修正1） ===")
check("NEWS_SELECTIONに情報源規律が項目数より優先する旨が明記されている",
      "情報源の規律は項目数より優先する" in generate_post.NEWS_SELECTION)
check("NEWS_SELECTIONに0項目が正しい結果である旨が明記されている",
      "は失敗ではなく" in generate_post.NEWS_SELECTION
      and "が定める正しい結果である" in generate_post.NEWS_SELECTION)
check("WRITES_Aから固定の「3〜4項目」目標が除かれている（上限のみへ変更）",
      "3〜4項目" not in generate_post.WRITES_A and "上限4項目" in generate_post.WRITES_A)
check("WRITES_Aの項目数が情報源の規律に従う旨・tier3単独ソースを埋め草にしない旨を記述",
      "項目数は目標ではなく" in generate_post.WRITES_A
      and "項目数を埋めるためにtier3単独ソースを採用しない" in generate_post.WRITES_A)

print("=== generate_post.py: ヘッドラインの判定手順（v1.44改定・単一箇所への集約） ===")
check("NEWS_SELECTIONのヘッドラインの判定手順がpart1_headline・part1_pointsの決定へ委譲されている",
      "part1_headline・headline_for_imageの決定手順は下記" in generate_post.NEWS_SELECTION
      and "①〜③を参照" in generate_post.NEWS_SELECTION)
check("旧来のtier1限定の絶対文言（独立2ソース材料単独では昇格しない）がNEWS_SELECTIONから撤去されている",
      "独立2ソース材料は【主要なポイント】には掲載できるが、【ヘッドライン】の"
      not in generate_post.NEWS_SELECTION)
check("WRITES_Aのheadline_for_image・part1_headlineがpart1_headline・part1_pointsの決定へ従う旨を記述",
      generate_post.WRITES_A.count("part1_headline・part1_pointsの決定") >= 2)

print("=== generate_post.py: 重要性判定と因果表現の分離（v1.33・オーナー指示） ===")
check("NEWS_SELECTIONに重要性（関連性）と因果関係を分けて判定する旨が明記されている",
      "重要性（関連性）と、暗号通貨価格への因果関係を" in generate_post.NEWS_SELECTION
      and "分けて判定する" in generate_post.NEWS_SELECTION)
check("NEWS_SELECTIONにA（直接材料）・B（波及経路のあるマクロ）・C（一般ニュース）の3分類がある",
      all(s in generate_post.NEWS_SELECTION for s in (
          "A：暗号通貨への直接材料", "B：明確な波及経路があるマクロ・地政学材料",
          "C：波及経路を説明できない一般ニュース")))
check("NEWS_SELECTIONにBの波及経路の例（金利・為替・流動性・原油等）が列挙されている",
      all(s in generate_post.NEWS_SELECTION for s in ("金利", "為替", "流動性", "通商政策・関税", "原油")))
check("NEWS_SELECTIONに「直接因果が未確認」のみを不採用理由にしてはならない旨が明記されている",
      "「暗号通貨価格への直接因果が未確認である」ことを、" in generate_post.NEWS_SELECTION
      and "不採用の理由としてはならない" in generate_post.NEWS_SELECTION)
check("NEWS_SELECTIONに因果未確認でも掲載したうえで明記する旨が明記されている",
      "掲載したうえで" in generate_post.NEWS_SELECTION
      and "暗号通貨価格への直接因果は未確認" in generate_post.NEWS_SELECTION)
check("NEWS_SELECTIONにA/B/C分類がtierとは別軸である旨が明記されている（tier規律との混同防止）",
      "下記tier（情報源の信頼性）とは別の軸である" in generate_post.NEWS_SELECTION)
check("NO_CANDIDATES_FALLBACKにaudit_ledgerのreason冒頭でA/B/C段階を明記する指示がある",
      "reasonの冒頭に上記A/B/Cのどの段階と判定したか" in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKに直接因果未確認のみを理由にしたuse:falseを禁じる文言がある"
      "（v1.53フォローアップでdecision:\"不採用\"からuse:falseへ改定）",
      "「暗号通貨価格への直接因果が未確認」であること" in generate_post.NO_CANDIDATES_FALLBACK
      and "のみを理由にuse:falseとしてはならない" in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKにuse:falseのreason全角60字上限、use:trueは対象外という指示がある"
      "（v1.47・v1.53フォローアップでdecision文言からuse文言へ改定・オーナー指示）",
      "use:false のreasonは全角60字以内に収める" in generate_post.NO_CANDIDATES_FALLBACK
      and "use:trueのreasonにはこの字数制限を適用しない" in generate_post.NO_CANDIDATES_FALLBACK)
check("WRITES_Aのpart1_pointsがB分類材料に因果未確認の限定表現を含める旨を参照している",
      "重要性判定と因果表現の分離" in generate_post.WRITES_A
      and "暗号通貨価格への直接因果は未確認" in generate_post.WRITES_A)

print("=== generate_post.py: part1_headline・part1_pointsの2軸決定"
      "（v1.44・オーナー指示。v1.82でnotable_move〈旧(iii)・旧③〉を除外・オーナー承認） ===")
check("NO_CANDIDATES_FALLBACKに(i)tier1・tier2・(ii)独立2ソースの2軸が明記されている"
      "（v1.53フォローアップ・LLM自身のuse:true/pairs_with_candidate_id判断ベースへ改定・"
      "v1.59で(i)へtier2を追加）",
      "(i)   tier1またはtier2の候補でuse:trueと判断したものがあるか" in generate_post.NO_CANDIDATES_FALLBACK
      and "(ii)  tier3の候補で、独立2ソース規定に該当すると判断し" in generate_post.NO_CANDIDATES_FALLBACK)
check("v1.82: notable_move(iii)は判定軸から除外されている（(iii)の判定項目が残っていない）",
      "(iii) 入力の intraday_range に notable_move: true の銘柄があるか"
      not in generate_post.NO_CANDIDATES_FALLBACK
      and "(i)(ii)(iii)" not in generate_post.NO_CANDIDATES_FALLBACK
      and "次の2つを独立に確認して" in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKに①〜③の優先順位すべてが記述されている（旧③〈値動き〉は廃止・旧④が③へ）",
      all(s in generate_post.NO_CANDIDATES_FALLBACK for s in (
          "① (i)あり", "② (i)なし・(ii)あり", "③ (i)なし・(ii)なし → 統合運用基準§3.1の定型文を使う")),
      generate_post.NO_CANDIDATES_FALLBACK[:1500])
check("v1.82: 旧③（値動きをヘッドラインの主題にする）・旧④の記述が残っていない",
      "(iii)あり → 値動きを記述する" not in generate_post.NO_CANDIDATES_FALLBACK
      and "④ (i)なし" not in generate_post.NO_CANDIDATES_FALLBACK
      and "③と④を取り違えないこと" not in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKに定型文を使うのは(i)(ii)の両方が「なし」の場合のみという明示がある",
      "定型文を使うのは、(i)(ii)の両方が「なし」の場合に限る" in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKの①〜③が、audit_ledgerのA/B/C（重要性判定）とは別分類である旨を明記（混同防止）",
      "とは別の分類である。混同しないこと" in generate_post.NO_CANDIDATES_FALLBACK)
check("v1.82: ヘッドライン・主要なポイントは材料の有無・notable_moveの有無によらず価格・24時間比・値動きを書かない旨が"
      "明記され、値動きの伝達先はheadline_for_imageと市場のフローの最終段階と指示されている",
      "材料の有無にかかわらず、価格・" in generate_post.NO_CANDIDATES_FALLBACK
      and "24時間比・値動きを書かない（統合運用基準§3.1）" in generate_post.NO_CANDIDATES_FALLBACK
      and "定型文を使うかどうかも(i)(ii)のみで決める" in generate_post.NO_CANDIDATES_FALLBACK
      and "headline_for_image（呼び出しA）と【市場のフロー】の最終段階" in generate_post.NO_CANDIDATES_FALLBACK)
check("②は独立2ソース材料単独でpart1_headlineの根拠になる（v1.44新設）。公式発表未確認の"
      "旨はpart1_headlineではなくpart1_pointsに明記する（v1.70・オーナー指示・9/7手直しへの対処）",
      "②（(i)なし・(ii)あり）の詳細" in generate_post.NO_CANDIDATES_FALLBACK
      and "独立2ソース材料の内容に基づき、part1_headlineに実文言を書く" in generate_post.NO_CANDIDATES_FALLBACK
      and "「公式発表での確認が取れていない」旨の但し書きはpart1_headlineに" in generate_post.NO_CANDIDATES_FALLBACK
      and "書かず、part1_pointsの該当項目に明記する" in generate_post.NO_CANDIDATES_FALLBACK)
check("②: 「一次情報」を内部用語として使わせない指示は維持されている（v1.64・オーナー指示）",
      "一次情報での確認ができていない旨を明記する" not in generate_post.NO_CANDIDATES_FALLBACK
      and "「一次情報」等の内部用語は使わず、読者向けの平易な表現を用いること" in generate_post.NO_CANDIDATES_FALLBACK)
check("②: headline_for_imageにも但し書きを含めない旨が明記されている（v1.70・オーナー指示）",
      "headline_for_imageも同様にこの材料の内容を反映してよい（但し書きは" in generate_post.NO_CANDIDATES_FALLBACK)

print("=== generate_post.py: ヘッドラインの構成要件（v1.70・オーナー指示・9/7手直しへの対処） ===")
check("NO_CANDIDATES_FALLBACKにヘッドラインの構成要件の見出しがある",
      "### ヘッドラインの構成要件（v1.70・オーナー指示。v1.82・v1.91改定）" in generate_post.NO_CANDIDATES_FALLBACK)
check("v1.91（オーナー指示）: ヘッドラインの構成要件はハッシュタグを付けない旨を明記し、v1.70の「主要銘柄に言及する場合はタグを付す」を廃止している",
      "ハッシュタグ（`#`）は付けない（v1.91・オーナー指示: 見出しにタグは不要。" in generate_post.NO_CANDIDATES_FALLBACK
      and "主要銘柄（BTC・ETH・BNB等）に言及する場合は" not in generate_post.NO_CANDIDATES_FALLBACK
      and "主要銘柄（BTC・ETH・BNB等）に言及する場合は" not in generate_post.SYSTEM_A)
check("ヘッドラインの構成要件: 公式発表未確認の但し書きをヘッドラインに書かない旨を指示している",
      "「公式発表での確認が取れていない」旨の但し書きをpart1_headlineに"
      in generate_post.NO_CANDIDATES_FALLBACK)
check("ヘッドラインの構成要件: 対象日の日付をヘッドライン冒頭に書かない旨を指示している",
      "対象日の日付をヘッドライン冒頭に書かない" in generate_post.NO_CANDIDATES_FALLBACK)
check("ヘッドラインの構成要件: 日付書き出しの禁止例と代替の書き出し例を具体的に示している"
      "（v1.70フォローアップ・実データ検証で抽象的な指示では効かなかったため強化）",
      "「9月7日は、」「9月7日、」のように日付から" in generate_post.NO_CANDIDATES_FALLBACK
      and "材料の内容から書き始めること" in generate_post.NO_CANDIDATES_FALLBACK)
check("v1.82・修正2: 書き出し例文は「〇〇（発表主体）が△△を発表しました。」のプレースホルダー形式で、"
      "「24時間比」を含む旧例文は撤去され、事実として流用しない旨が明記されている",
      "（例:「〇〇（発表主体）が△△を発表しました。」" in generate_post.NO_CANDIDATES_FALLBACK
      and "プレースホルダーであり、この文言や内容を事実として流用しないこと" in generate_post.NO_CANDIDATES_FALLBACK
      and "24時間比で下落しました" not in generate_post.NO_CANDIDATES_FALLBACK
      and "値動きや材料の内容から書き始めること" not in generate_post.NO_CANDIDATES_FALLBACK)
check("v1.82: ヘッドラインの構成要件に1〜2文・価格/24時間比/値動き等の禁止が明記されている（統合運用基準§3.1）",
      "1〜2文にとどめる（統合運用基準§3.1）" in generate_post.NO_CANDIDATES_FALLBACK
      and "価格・24時間比・値動き・Fear & Greed・相対強弱・DEX・APR・LP助言を" in generate_post.NO_CANDIDATES_FALLBACK)
check("ヘッドラインの構成要件がSYSTEM_Aに含まれる（NO_CANDIDATES_FALLBACK経由）",
      "### ヘッドラインの構成要件（v1.70・オーナー指示。v1.82・v1.91改定）" in generate_post.SYSTEM_A)

print("=== generate_post.py: RULES_HASHTAG強化（v1.71・9/8実データのC13境界違反への対処） ===")
check("RULES_HASHTAGがタグ名の直後に助詞・読点が続く書き方を明示的に禁止している"
      "（実際にC13をFAILさせた「#BTCは下落し、#ETHは」というパターンを名指し）",
      "#BTCは下落し、#ETHは" in generate_post.RULES_HASHTAG)
check("RULES_HASHTAGが文中主語ではなく連鎖の末尾にまとめて置く代替パターンを具体例で示している（v1.91: 【市場のフロー】の例に整理）",
      "【市場のフロー】で銘柄を文中の主語にする場合は" in generate_post.RULES_HASHTAG
      and "前編には使わない" in generate_post.RULES_HASHTAG
      and "BTC・ETHは24時間比でそれぞれ下落・" not in generate_post.RULES_HASHTAG)
check("v1.91（オーナー指示）: RULES_HASHTAGは、タグを付けてよいのは【市場のフロー】の連鎖末尾だけで、ヘッドライン・主要なポイント・総括・headline_for_imageには付けない旨を先頭に明記し、SYSTEM_A・SYSTEM_Bの両方に入る",
      generate_post.RULES_HASHTAG.split("\n- `#` は行頭")[0].count("【市場のフロー】") >= 1
      and "付けない（v1.91・オーナー指示: 見出しにタグは不要）" in generate_post.RULES_HASHTAG
      and generate_post.RULES_HASHTAG in generate_post.SYSTEM_A and generate_post.RULES_HASHTAG in generate_post.SYSTEM_B)
check("RULES_HASHTAGが#の直前に日本語の句読点が来る位置を明示的に禁止している",
      "日本語の句読点になる位置には置かない" in generate_post.RULES_HASHTAG)

print("=== generate_post.py: 固有名詞の関与の描写（v1.70・オーナー指示・Coldcard事例への対処） ===")
check("ENTITY_INVOLVEMENT_GUIDANCEが事故・不正・盗難等での固有名詞の扱いを規定している",
      "事故・不正・盗難等の事案を報じる候補に特定の製品名・企業名が含まれて"
      in generate_post.ENTITY_INVOLVEMENT_GUIDANCE)
check("ENTITY_INVOLVEMENT_GUIDANCEが関わり方不明確時に誤読を避ける言い換えを指示している",
      "その製品・企業に問題があったかのように読める書き方を" in generate_post.ENTITY_INVOLVEMENT_GUIDANCE
      and "避ける一般的な表現に言い換えること" in generate_post.ENTITY_INVOLVEMENT_GUIDANCE)
check("ENTITY_INVOLVEMENT_GUIDANCEが書き方の制約であり採否基準ではない旨を明記している"
      "（v1.70フォローアップ・実データ検証で採否誤判定を誘発したため強化）",
      "これは書き方（表現）の制約であり、採否（use）の判断基準ではない" in generate_post.ENTITY_INVOLVEMENT_GUIDANCE
      and "材料をuse:falseにしてはならない" in generate_post.ENTITY_INVOLVEMENT_GUIDANCE)
check("ENTITY_INVOLVEMENT_GUIDANCEが言い換え例（名称を理由に事実ごと不採用にしない）を示している"
      "（v1.70フォローアップ・実データ検証で抽象的な指示だけでは事実ごと不採用になったため強化）",
      "製品名を関与の主語にせず" in generate_post.ENTITY_INVOLVEMENT_GUIDANCE
      and "名称を理由に事実ごと不採用にしない" in generate_post.ENTITY_INVOLVEMENT_GUIDANCE)
check("ENTITY_INVOLVEMENT_GUIDANCEがSYSTEM_Aに含まれる",
      "固有名詞の関与の描写（v1.70・オーナー指示）" in generate_post.SYSTEM_A)
check("v1.82: ③（(i)なし・(ii)なし）はheadline・pointsとも定型文をそのまま使う"
      "（値動きを主題にする旧③は廃止）",
      "### ③（(i)なし・(ii)なし）の詳細" in generate_post.NO_CANDIDATES_FALLBACK
      and generate_post.FIXED_HEADLINE in generate_post.NO_CANDIDATES_FALLBACK
      and generate_post.FIXED_POINTS in generate_post.NO_CANDIDATES_FALLBACK
      and "「ニュース材料は確認できなかった」" not in generate_post.NO_CANDIDATES_FALLBACK)
check("v1.82: headline_for_imageの指示が、値動きの形状を反映してよい先（notable_move）として"
      "明示されており、材料も値動きも無い場合はdirectionに基づく定性的な見出しにとどめる",
      "- headline_for_image: 図版下部帯用。【ヘッドライン】【主要なポイント】と" in generate_post.NO_CANDIDATES_FALLBACK
      and "値動きの形状を反映してよい" in generate_post.NO_CANDIDATES_FALLBACK
      and "材料も notable_move も無い場合は" in generate_post.NO_CANDIDATES_FALLBACK
      and "direction（up/down）に基づく短い定性的な見出し" in generate_post.NO_CANDIDATES_FALLBACK)

print("=== generate_post.py: 呼び出しAの文体統一（v1.64・オーナー指示。呼び出しAには"
      "です・ます調の指示が一度も無かったことが9/1・9/3の常体混入の主因と判明） ===")
check("WRITES_A（SYSTEM_Aに含まれる）に「です・ます調」で統一する旨が明記されている",
      "です・ます調" in generate_post.WRITES_A
      and "で統一する" in generate_post.WRITES_A
      and "です・ます調" in generate_post.SYSTEM_A)
check("WRITES_Aに「である調」を使わない旨が明記されている",
      "である調" in generate_post.WRITES_A
      and "は使わない" in generate_post.WRITES_A)

print("=== generate_post.py: 呼び出しBの文体統一・総括の言及範囲制限（v1.35・オーナー指示） ===")
check("CALL_B_INSTRUCTIONSに「です・ます調」で統一する旨が明記されている",
      "です・ます調" in generate_post.CALL_B_INSTRUCTIONS
      and "で統一する" in generate_post.CALL_B_INSTRUCTIONS)
check("CALL_B_INSTRUCTIONSに「である調」を使わない旨が明記されている",
      "である調" in generate_post.CALL_B_INSTRUCTIONS
      and "は使わない" in generate_post.CALL_B_INSTRUCTIONS)
check("CALL_B_INSTRUCTIONSに前編と文体を揃える旨が明記されている",
      "前編（part1_headline・" in generate_post.CALL_B_INSTRUCTIONS
      and "文体を揃える" in generate_post.CALL_B_INSTRUCTIONS)
check("CALL_B_INSTRUCTIONSに総括で言及してよい範囲がpart1_headline・part1_points掲載済み・"
      "reusable_for_summaryの継続材料に限る旨が明記されている（v1.82でヘッドラインを追加・オーナー承認）",
      "part1_headline・part1_points に" in generate_post.CALL_B_INSTRUCTIONS.replace("\n  ", "")
      and "掲載済みのもの" in generate_post.CALL_B_INSTRUCTIONS
      and "reusable_for_summary に渡された継続材料（前日以前の投稿で扱ったもの）に限る" in generate_post.CALL_B_INSTRUCTIONS.replace("\n  ", ""))
check("CALL_B_INSTRUCTIONSに本文で扱っていない新規の固有名詞を総括で持ち出さない旨が明記されている",
      "本文（part1_headline・part1_points）で扱っていない新規の固有名詞・" in generate_post.CALL_B_INSTRUCTIONS
      and "材料を総括で初めて持ち出さない" in generate_post.CALL_B_INSTRUCTIONS)
check("CALL_B_INSTRUCTIONS: 総括の言及範囲の旧表記（part1_pointsのみ）が残っていない（v1.82）",
      "本文（part1_points）で扱っていない" not in generate_post.CALL_B_INSTRUCTIONS
      and "part1_points に掲載済みのもの、" not in generate_post.CALL_B_INSTRUCTIONS)
check("SYSTEM_BがCALL_B_INSTRUCTIONSの更新内容を含む",
      "です・ます調" in generate_post.SYSTEM_B)

print("=== generate_post.py: part2_flowの材料をpart1_points採用済みに限定（v1.56・オーナー指示） ===")

check("CALL_B_INSTRUCTIONSにpart2_flowの材料を呼び出しAのpart1_headline・part1_points掲載済みに限る旨が"
      "明記されている（v1.82でヘッドラインを追加。材料が1件の日はpart1_pointsが定型文のみになるため）",
      "ここで扱う材料は、呼び出しAのpart1_headline・" in generate_post.CALL_B_INSTRUCTIONS
      and "part1_pointsに既に掲載されている材料に限る" in generate_post.CALL_B_INSTRUCTIONS)
check("CALL_B_INSTRUCTIONSにreusable_for_summaryをpart2_flowで使わない旨が明記されている"
      "（reusable_for_summaryはpart2_summaryの1行言及にのみ使う）",
      "part1_pointsに書かれていない新規の材料をpart2_flowで持ち出さない" in generate_post.CALL_B_INSTRUCTIONS
      and "（v1.56・オーナー指示）" in generate_post.CALL_B_INSTRUCTIONS
      and "reusable_for_summary\n  （前日以前の投稿で扱った継続材料。part2_summaryでの1行言及にのみ使う）"
      in generate_post.CALL_B_INSTRUCTIONS)

print("=== generate_post.py: ETF資金フローの土日表記（v1.56・オーナー指示） ===")

check("ETF_WEEKEND_GUIDANCEに土日は具体的な金額を記載してはならない旨が明記されている",
      "weekday_jp が「土」または「日」の場合" in generate_post.ETF_WEEKEND_GUIDANCE
      and "具体的な金額を本文に記載してはならない" in generate_post.ETF_WEEKEND_GUIDANCE)
check("ETF_WEEKEND_GUIDANCEに直近営業日の確定値表記が明記されている",
      "直近営業日までの確定値として確認された」旨を明記すること" in generate_post.ETF_WEEKEND_GUIDANCE)
check("SYSTEM_A・SYSTEM_BともにETF_WEEKEND_GUIDANCEを含む",
      "weekday_jp が「土」または「日」の場合" in generate_post.SYSTEM_A
      and "weekday_jp が「土」または「日」の場合" in generate_post.SYSTEM_B)

print("=== generate_post.py: 候補ごとの掲載可否ラベル（v1.29・オーナー指示・修正2） ===")
_elig_candidates = [
    {"tier": 1, "source": "SEC", "title": "t1", "url": "https://example.com/1",
     "published_at": "Mon, 17 Aug 2026 10:00:00 GMT"},
    {"tier": 3, "source": "CoinDesk", "title": "t3", "url": "https://example.com/3",
     "published_at": "Mon, 17 Aug 2026 09:00:00 GMT"},
    {"tier": 4, "source": "Google News (Reuters検索)", "title": "t4", "url": "https://example.com/4",
     "published_at": "Mon, 17 Aug 2026 08:00:00 GMT"},
]
_elig_labeled = generate_post._label_eligibility(_elig_candidates)
check("tier1候補のeligibilityは「掲載可」",
      next(c for c in _elig_labeled if c["tier"] == 1)["eligibility"] == "掲載可")
check("tier3候補のeligibilityは単独不可を明記",
      "単独では掲載不可" in next(c for c in _elig_labeled if c["tier"] == 3)["eligibility"])
check("tier4候補のeligibilityは掲載不可",
      "掲載不可" in next(c for c in _elig_labeled if c["tier"] == 4)["eligibility"])
check("eligibility付与後も元のフィールド（title等）が保持される",
      all(c.get("title") and c.get("url") for c in _elig_labeled))
_news_today_elig = {"candidates": [
    {"tier": 1, "source": "SEC", "title": "u1", "url": "https://example.com/u1",
     "published_at": "Mon, 17 Aug 2026 10:00:00 GMT"},
]}
_uc, _, _id_map = generate_post._build_call_a_user_content(DAILY_DATA, _news_today_elig, None)
_uc_parsed = json.loads(_uc)
check("_build_call_a_user_content: news_candidates_todayの各項目にeligibilityが付与される",
      all("eligibility" in c for c in _uc_parsed["news_candidates_today"]))
check("_build_call_a_user_content: news_candidates_todayの各項目にcandidate_idが付与される（v1.48）",
      all("candidate_id" in c for c in _uc_parsed["news_candidates_today"])
      and _uc_parsed["news_candidates_today"][0]["candidate_id"] == 1,
      json.dumps(_uc_parsed.get("news_candidates_today"), ensure_ascii=False))
check("_build_call_a_user_content: id_to_candidateはcandidate_id→候補データの対応を返す（v1.48）",
      _id_map[1]["url"] == "https://example.com/u1" and _id_map[1]["title"] == "u1", str(_id_map))
check("NEWS_SELECTIONがeligibilityフィールドの存在と、それに従う旨を候補に明記している",
      "eligibility" in generate_post.NEWS_SELECTION
      and "判定に従うこと" in generate_post.NEWS_SELECTION)

print("=== generate_post.py: audit_ledgerのcandidate_id方式による再構成（v1.48・オーナー指示） ===")

check("_assign_candidate_ids: 1始まりの連番を付与する",
      [c["candidate_id"] for c in generate_post._assign_candidate_ids(
          [{"title": "a"}, {"title": "b"}, {"title": "c"}])] == [1, 2, 3])

_id_candidates = {
    1: {"source": "SEC", "url": "https://example.gov/real-a", "title": "Real title A",
        "published_at": "Mon, 17 Aug 2026 10:00:00 GMT", "candidate_id": 1, "tier": 1},
    2: {"source": "CoinDesk", "url": "https://example.com/real-b", "title": "Real title B",
        "published_at": "Mon, 17 Aug 2026 09:00:00 GMT", "candidate_id": 2, "tier": 3},
}
_llm_out = [
    {"candidate_id": 1, "use": True, "verified_by": "RSS summary", "reason": "一次情報で確認"},
    {"candidate_id": 2, "use": False, "reason": "C: 波及経路を説明できない"},
]
_rebuilt = generate_post._reconstruct_audit_ledger(_llm_out, _id_candidates)
check("_reconstruct_audit_ledger: source/url/title/published_atは候補データからそのまま補完される"
      "（LLMは転記しない）",
      _rebuilt[0]["source"] == "SEC" and _rebuilt[0]["url"] == "https://example.gov/real-a"
      and _rebuilt[0]["title"] == "Real title A"
      and _rebuilt[0]["published_at"] == "Mon, 17 Aug 2026 10:00:00 GMT", str(_rebuilt[0]))
check("_reconstruct_audit_ledger: decisionはtier・useからコード側で導出される（v1.53フォローアップ・"
      "オーナー指示。tier1のuse:true→採用、use:false→不採用。reason/verified_byはLLM出力をそのまま使う）",
      _rebuilt[0]["decision"] == "採用" and _rebuilt[0]["reason"] == "一次情報で確認"
      and _rebuilt[0]["verified_by"] == "RSS summary"
      and _rebuilt[1]["decision"] == "不採用" and _rebuilt[1]["reason"] == "C: 波及経路を説明できない",
      str(_rebuilt))
check("_reconstruct_audit_ledger: verified_byを省略したuse:falseエントリは空文字になる",
      _rebuilt[1]["verified_by"] == "", str(_rebuilt[1]))
check("_reconstruct_audit_ledger: 出力件数は候補数と一致する", len(_rebuilt) == 2, str(_rebuilt))


def _raises_reconstruction_error(entries, candidates):
    try:
        generate_post._reconstruct_audit_ledger(entries, candidates)
        return False
    except generate_post.AuditLedgerReconstructionError:
        return True


check("_reconstruct_audit_ledger: 存在しない候補IDは例外（_call_json()のリトライへ委ねる）",
      _raises_reconstruction_error([{"candidate_id": 99, "use": True, "reason": "x"}], _id_candidates))
check("_reconstruct_audit_ledger: candidate_idの重複は例外",
      _raises_reconstruction_error(
          [{"candidate_id": 1, "use": True, "reason": "x"},
           {"candidate_id": 1, "use": False, "reason": "y"}], _id_candidates))
check("_reconstruct_audit_ledger: 候補の一部が記録されていない（欠落）場合は例外",
      _raises_reconstruction_error(
          [{"candidate_id": 1, "use": True, "reason": "x"}], _id_candidates))  # id=2が欠落
check("_reconstruct_audit_ledger: candidate_idが文字列（型不正）の場合も例外",
      _raises_reconstruction_error(
          [{"candidate_id": "1", "use": True, "reason": "x"},
           {"candidate_id": 2, "use": False, "reason": "y"}], _id_candidates))
check("_reconstruct_audit_ledger: audit_ledger自体がリストでない場合も例外",
      _raises_reconstruction_error({"not": "a list"}, _id_candidates))
check("_reconstruct_audit_ledger: 候補0件・LLM出力も空配列なら空配列を返す（従来の「候補が無い日」の扱いを維持）",
      generate_post._reconstruct_audit_ledger([], {}) == [])

check("OUTPUT_FORMAT_Aのaudit_ledger例がcandidate_id方式になっている（source/url/title/published_atを含まない）",
      '"candidate_id": 1' in generate_post.OUTPUT_FORMAT_A
      and '"source"' not in generate_post.OUTPUT_FORMAT_A)
check("WRITES_Aのaudit_ledger説明がcandidate_id方式を明記している（v1.53フォローアップでdecisionを除去）",
      "candidate_id・use・pairs_with_candidate_id" in generate_post.WRITES_A
      and "source・url・title・published_at・decisionは書かない" in generate_post.WRITES_A)
check("NO_CANDIDATES_FALLBACKのaudit_ledger節がcandidate_id方式・転記させない旨を明記している",
      "candidate_id（news_candidates_today内の該当候補のID）・" in generate_post.NO_CANDIDATES_FALLBACK
      and "あなたが転記する必要は無い" in generate_post.NO_CANDIDATES_FALLBACK
      and "candidate_idはちょうど1回のみ" in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKにverified_byはuse:trueの場合のみ書く旨が明記されている"
      "（v1.53フォローアップでdecision文言からuse文言へ改定）",
      "verified_byはuse:trueの場合のみ書く" in generate_post.NO_CANDIDATES_FALLBACK
      and "use:falseの場合は空文字でよい" in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKにpairs_with_candidate_idの妥当性確認条件が明記されている"
      "（v1.53フォローアップ・オーナー指示）",
      "相互に指し合う必要はなく" in generate_post.NO_CANDIDATES_FALLBACK
      and "妥当性が確認できない" in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKに「tier1裏取りで言及したtier3はuse:falseのまま」の"
      "区別が明記されている（v1.53フォローアップ・実データ検証で判明した"
      "「言及＝use:trueと誤解する」事故への対応）",
      "本文で言及・参照した」\n  ことと「useをtrueにする」ことは別であり" in generate_post.NO_CANDIDATES_FALLBACK)
check("NEWS_SELECTIONのtier3節に「本文中で言及した」ことだけでuse:trueにしない旨が明記されている"
      "（v1.53フォローアップ）",
      "「本文中でこの記事の内容に言及・参照した」" in generate_post.NEWS_SELECTION
      and "だけを\n        理由にuse:trueにしないこと" in generate_post.NEWS_SELECTION)

print("=== generate_post.py: decisionのtier・use・pairs_with_candidate_idからの導出"
      "（v1.53フォローアップ・オーナー指示・C21の構造的解消） ===")

_pair_candidates = {
    1: {"source": "SEC", "title": "Regulator announces new rule", "candidate_id": 1, "tier": 1},
    2: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "candidate_id": 2, "tier": 3},
    3: {"source": "Cointelegraph", "title": "Company A files BTC ETF approval application",
        "candidate_id": 3, "tier": 3},
    4: {"source": "CoinDesk", "title": "Unrelated topic entirely", "candidate_id": 4, "tier": 3},
    5: {"source": "Google News", "title": "Company A files BTC ETF approval", "candidate_id": 5, "tier": 4},
    6: {"source": "Reuters", "title": "US launches new strikes on Iran", "candidate_id": 6, "tier": 2},
    7: {"source": "Reuters", "title": "Unrelated Reuters wire story", "candidate_id": 7, "tier": 2},
}
_pair_llm_out = [
    {"candidate_id": 1, "use": True, "reason": "一次情報"},
    {"candidate_id": 2, "use": True, "pairs_with_candidate_id": 3, "reason": "独立2媒体一致"},
    {"candidate_id": 3, "use": True, "reason": "独立2媒体一致"},  # 3は2を指さない（片方向の申告で成立）
    {"candidate_id": 4, "use": False, "reason": "C: 無関係"},
    {"candidate_id": 5, "use": True, "reason": "候補発見のみ"},
    {"candidate_id": 6, "use": True, "reason": "Reutersによる独立報道"},
    {"candidate_id": 7, "use": False, "reason": "C: 無関係"},
]
_pair_rebuilt = generate_post._reconstruct_audit_ledger(_pair_llm_out, _pair_candidates, 0.4)
check("_derive_decisions: tier1はuse:true→採用", _pair_rebuilt[0]["decision"] == "採用", str(_pair_rebuilt[0]))
check("_derive_decisions: tier3のuse:trueが片方向のpairs_with_candidate_id申告で双方"
      "「採用（独立2ソース）」になる（相互申告は不要・オーナー指示）",
      _pair_rebuilt[1]["decision"] == "採用（独立2ソース）" and _pair_rebuilt[2]["decision"] == "採用（独立2ソース）",
      f"{_pair_rebuilt[1]} / {_pair_rebuilt[2]}")
check("_derive_decisions: tier3のuse:falseは不採用", _pair_rebuilt[3]["decision"] == "不採用", str(_pair_rebuilt[3]))
check("_derive_decisions: tier4はuse:trueでも常に不採用（tier3と同一タイトルでもペア対象外・オーナー指示）",
      _pair_rebuilt[4]["decision"] == "不採用", str(_pair_rebuilt[4]))
check("_derive_decisions: tier2はuse:true→採用（v1.59・オーナー承認・tier1と同じ扱い。"
      "ペア判定を経ずに単独で採用される）",
      _pair_rebuilt[5]["decision"] == "採用", str(_pair_rebuilt[5]))
check("_derive_decisions: tier2はuse:false→不採用",
      _pair_rebuilt[6]["decision"] == "不採用", str(_pair_rebuilt[6]))


def _raises_for_unresolved_pair(entries, candidates, threshold=0.4):
    try:
        generate_post._reconstruct_audit_ledger(entries, candidates, threshold)
        return False
    except generate_post.AuditLedgerReconstructionError as e:
        return "独立2ソースの相方が成立しない" in str(e)


check("_derive_decisions: tier3のuse:trueでpairs_with_candidate_id未申告・相方も無しは例外（リトライ対象）",
      _raises_for_unresolved_pair(
          [{"candidate_id": 1, "use": True, "reason": "x"}],
          {1: {"source": "CoinDesk", "title": "Solo story", "candidate_id": 1, "tier": 3}}))
check("_derive_decisions: pairs_with_candidate_idが存在しないIDを指す場合は妥当性確認に落ちて例外",
      _raises_for_unresolved_pair(
          [{"candidate_id": 1, "use": True, "pairs_with_candidate_id": 99, "reason": "x"}],
          {1: {"source": "CoinDesk", "title": "Solo story", "candidate_id": 1, "tier": 3}}))
check("_derive_decisions: 申告した相方がuse:falseの場合は妥当性確認に落ちて例外",
      _raises_for_unresolved_pair(
          [{"candidate_id": 1, "use": True, "pairs_with_candidate_id": 2, "reason": "x"},
           {"candidate_id": 2, "use": False, "reason": "y"}],
          {1: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "candidate_id": 1, "tier": 3},
           2: {"source": "Cointelegraph", "title": "Company A files BTC ETF approval application",
               "candidate_id": 2, "tier": 3}}))
check("_derive_decisions: 申告した相方が同一sourceの場合は妥当性確認に落ちて例外（同一媒体の2記事は不可）",
      _raises_for_unresolved_pair(
          [{"candidate_id": 1, "use": True, "pairs_with_candidate_id": 2, "reason": "x"},
           {"candidate_id": 2, "use": True, "reason": "y"}],
          {1: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "candidate_id": 1, "tier": 3},
           2: {"source": "CoinDesk", "title": "Company A files BTC ETF approval application",
               "candidate_id": 2, "tier": 3}}))
check("_derive_decisions: 申告した相方のタイトル重なりが閾値未満の場合は妥当性確認に落ちて例外",
      _raises_for_unresolved_pair(
          [{"candidate_id": 1, "use": True, "pairs_with_candidate_id": 2, "reason": "x"},
           {"candidate_id": 2, "use": True, "reason": "y"}],
          {1: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "candidate_id": 1, "tier": 3},
           2: {"source": "Cointelegraph", "title": "Totally different unrelated story here",
               "candidate_id": 2, "tier": 3}}))
check("_derive_decisions: 申告した相方がtier1の場合は妥当性確認に落ちて例外（独立2ソースはtier3同士のみ・オーナー指示）",
      _raises_for_unresolved_pair(
          [{"candidate_id": 1, "use": True, "pairs_with_candidate_id": 2, "reason": "x"},
           {"candidate_id": 2, "use": True, "reason": "y"}],
          {1: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "candidate_id": 1, "tier": 3},
           2: {"source": "SEC", "title": "Company A files BTC ETF approval application",
               "candidate_id": 2, "tier": 1}}))

print("=== generate_post.py: _pair_claim_detail・却下ペアの診断記録（v1.79・オーナー承認） ===")

check("_pair_claim_detail: _validate_pair_claimと同じ入力でvalid=Trueを返す（成立するペア）",
      generate_post._pair_claim_detail(
          1, 2,
          {1: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "tier": 3},
           2: {"source": "Cointelegraph", "title": "Company A files BTC ETF approval application", "tier": 3}},
          {1: True, 2: True}, 0.4)["valid"] is True)
check("_pair_claim_detail: 相手が存在しないIDの場合reason=target_not_found",
      generate_post._pair_claim_detail(1, 99, {1: {"source": "CoinDesk", "title": "x", "tier": 3}},
                                        {1: True}, 0.4)["reason"] == "target_not_found")
check("_pair_claim_detail: 自己参照の場合reason=self_reference",
      generate_post._pair_claim_detail(1, 1, {1: {"source": "CoinDesk", "title": "x", "tier": 3}},
                                        {1: True}, 0.4)["reason"] == "self_reference")
check("_pair_claim_detail: 相手がtier3でない場合reason=target_not_tier3",
      generate_post._pair_claim_detail(
          1, 2, {1: {"source": "CoinDesk", "title": "x", "tier": 3}, 2: {"source": "SEC", "title": "x", "tier": 1}},
          {1: True, 2: True}, 0.4)["reason"] == "target_not_tier3")
check("_pair_claim_detail: 相手がuse:falseの場合reason=target_use_false",
      generate_post._pair_claim_detail(
          1, 2, {1: {"source": "CoinDesk", "title": "x", "tier": 3}, 2: {"source": "Cointelegraph", "title": "x", "tier": 3}},
          {1: True, 2: False}, 0.4)["reason"] == "target_use_false")
check("_pair_claim_detail: 同一sourceの場合reason=same_source",
      generate_post._pair_claim_detail(
          1, 2, {1: {"source": "CoinDesk", "title": "x", "tier": 3}, 2: {"source": "CoinDesk", "title": "x", "tier": 3}},
          {1: True, 2: True}, 0.4)["reason"] == "same_source")
_detail_below = generate_post._pair_claim_detail(
    1, 2,
    {1: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "tier": 3},
     2: {"source": "Cointelegraph", "title": "Totally different unrelated story here", "tier": 3}},
    {1: True, 2: True}, 0.4)
check("_pair_claim_detail: 重なり係数が閾値未満の場合reason=overlap_below_thresholdかつoverlapに実測値が入る",
      _detail_below["reason"] == "overlap_below_threshold" and isinstance(_detail_below["overlap"], float)
      and _detail_below["valid"] is False, str(_detail_below))
check("_pair_claim_detail: claimant_title/claimant_source/target_title/target_sourceが両側の値を保持する",
      _detail_below["claimant_title"] == "Company A files BTC ETF approval"
      and _detail_below["claimant_source"] == "CoinDesk"
      and _detail_below["target_title"] == "Totally different unrelated story here"
      and _detail_below["target_source"] == "Cointelegraph", str(_detail_below))

_rp_candidates = {
    1: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "candidate_id": 1, "tier": 3},
    2: {"source": "CoinDesk", "title": "Totally different unrelated story here", "candidate_id": 2, "tier": 3},
}
_rp_stats: list = []
try:
    generate_post._derive_decisions(
        [{"candidate_id": 1, "use": True, "pairs_with_candidate_id": 2, "reason": "x"},
         {"candidate_id": 2, "use": True, "reason": "y"}],
        _rp_candidates, 0.4, rejected_pairs=_rp_stats)
except generate_post.AuditLedgerReconstructionError:
    pass
check("_derive_decisions: rejected_pairsを渡すと却下されたペア申告の診断（同一source）が記録される（v1.79）",
      len(_rp_stats) == 1 and _rp_stats[0]["reason"] == "same_source"
      and _rp_stats[0]["claimant_id"] == 1 and _rp_stats[0]["target_id"] == 2, str(_rp_stats))
check("_derive_decisions: rejected_pairsを省略しても例外なく動作する（後方互換）",
      _raises_for_unresolved_pair(
          [{"candidate_id": 1, "use": True, "pairs_with_candidate_id": 2, "reason": "x"},
           {"candidate_id": 2, "use": True, "reason": "y"}],
          _rp_candidates))

print("=== generate_post.py: force_drop_unresolvedによる強制不採用（v1.79・オーナー承認・"
      "2026-09-26のcall_A 3連続FAILへの対処） ===")

_fd_candidates = {
    1: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "candidate_id": 1, "tier": 3},
    2: {"source": "CoinDesk", "title": "Totally different unrelated story here", "candidate_id": 2, "tier": 3},
    3: {"source": "SEC", "title": "Regulator announces new rule", "candidate_id": 3, "tier": 1},
}
_fd_entries = [
    {"candidate_id": 1, "use": True, "pairs_with_candidate_id": 2, "reason": "x"},
    {"candidate_id": 2, "use": True, "reason": "y"},
    {"candidate_id": 3, "use": True, "reason": "一次情報"},
]
check("_derive_decisions: force_drop_unresolved未指定（既定False）では従来どおり例外化する",
      _raises_for_unresolved_pair(_fd_entries, _fd_candidates))

_fd_dropped: list = []
_fd_decisions = generate_post._derive_decisions(
    _fd_entries, _fd_candidates, 0.4, force_drop_unresolved=True, force_dropped=_fd_dropped)
check("_derive_decisions: force_drop_unresolved=Trueだと例外化せず、未解決のtier3候補を「不採用」にする",
      _fd_decisions[1] == "不採用" and _fd_decisions[2] == "不採用", str(_fd_decisions))
check("_derive_decisions: force_drop_unresolvedはtier1等の他候補のdecisionには影響しない",
      _fd_decisions[3] == "採用", str(_fd_decisions))
check("_derive_decisions: force_droppedに強制不採用にした候補のcandidate_id・title・source・reasonが記録される",
      {d["candidate_id"] for d in _fd_dropped} == {1, 2}
      and all(d.get("title") and d.get("reason") for d in _fd_dropped), str(_fd_dropped))

_fd_rebuilt = generate_post._reconstruct_audit_ledger(
    _fd_entries, _fd_candidates, 0.4, force_drop_unresolved=True)
check("_reconstruct_audit_ledger: force_drop_unresolvedを渡すと例外化せず完全なaudit_ledgerを返す"
      "（入力の候補順を維持。1・2は強制不採用、3は通常どおり採用）",
      len(_fd_rebuilt) == 3
      and [e["decision"] for e in _fd_rebuilt] == ["不採用", "不採用", "採用"], str(_fd_rebuilt))

print("=== generate_post.py: CallOutcome.rejected_pairs / force_dropped_candidates（v1.79） ===")

check("CallOutcome.to_dict(): rejected_pairs・force_dropped_candidatesが既定で空リスト",
      generate_post.CallOutcome(True, {}, 1, None).to_dict()["rejected_pairs"] == []
      and generate_post.CallOutcome(True, {}, 1, None).to_dict()["force_dropped_candidates"] == [])
check("CallOutcome.to_dict(): rejected_pairs・force_dropped_candidatesを明示指定できる",
      generate_post.CallOutcome(True, {}, 1, None, rejected_pairs=[{"a": 1}],
                                 force_dropped_candidates=[{"b": 2}]).to_dict()
      == {**generate_post.CallOutcome(True, {}, 1, None).to_dict(),
          "rejected_pairs": [{"a": 1}], "force_dropped_candidates": [{"b": 2}]})

print("=== generate_post.py: overlap閾値のconfig化（v1.53フォローアップ・オーナー指示） ===")

_thresh_candidates = {
    1: {"source": "CoinDesk", "title": "Company A files BTC ETF approval", "candidate_id": 1, "tier": 3},
    2: {"source": "Cointelegraph", "title": "Company A discusses BTC outlook today",
        "candidate_id": 2, "tier": 3},
}
_thresh_llm_out = [
    {"candidate_id": 1, "use": True, "pairs_with_candidate_id": 2, "reason": "x"},
    {"candidate_id": 2, "use": True, "reason": "y"},
]
# overlap係数は3/6=0.5（company/a/btcの3語が共通）。閾値0.4なら成立、0.6なら不成立。
check("_derive_decisions: overlap0.5の申告は閾値0.4なら成立する",
      generate_post._reconstruct_audit_ledger(_thresh_llm_out, _thresh_candidates, 0.4)[0]["decision"]
      == "採用（独立2ソース）")
check("_derive_decisions: overlap0.5の申告は閾値0.6なら不成立（例外）・configで調整可能なことの確認",
      _raises_for_unresolved_pair(_thresh_llm_out, _thresh_candidates, 0.6))
check("load_pair_overlap_threshold: config/pair_overlap.jsonが存在しデフォルト0.4を返す",
      generate_post.load_pair_overlap_threshold() == 0.4)

print("=== generate_post.py: audit_ledgerのdecision/reason空欄自動補完（v1.54フォローアップ・オーナー指示） ===")

_fill_candidates = {
    1: {"source": "SEC", "title": "Regulator announces new rule", "candidate_id": 1, "tier": 1},
    2: {"source": "SEC", "title": "Another regulator announcement", "candidate_id": 2, "tier": 1},
}
_fill_stats: dict = {}
_fill_rebuilt = generate_post._reconstruct_audit_ledger(
    [
        {"candidate_id": 1, "use": True, "reason": ""},
        {"candidate_id": 2, "use": True, "reason": "一次情報で確認"},
    ],
    _fill_candidates, generate_post.PAIR_OVERLAP_THRESHOLD_DEFAULT, _fill_stats,
)
check("_reconstruct_audit_ledger: reasonが空文字の場合は定型文で自動補完される",
      _fill_rebuilt[0]["reason"] == "理由が記載されませんでした（自動補完）", str(_fill_rebuilt[0]))
check("_reconstruct_audit_ledger: reasonが記載されている場合は自動補完しない",
      _fill_rebuilt[1]["reason"] == "一次情報で確認", str(_fill_rebuilt[1]))
check("_reconstruct_audit_ledger: reason空欄1件の自動補完件数がstatsへ記録される",
      _fill_stats.get("audit_ledger_auto_filled_count") == 1, str(_fill_stats))

_fill_stats2: dict = {}
_fill_rebuilt2 = generate_post._reconstruct_audit_ledger(
    [
        {"candidate_id": 1, "use": True, "reason": "  "},
        {"candidate_id": 2, "use": True},  # reasonキー自体が無い場合も空扱い
    ],
    _fill_candidates, generate_post.PAIR_OVERLAP_THRESHOLD_DEFAULT, _fill_stats2,
)
check("_reconstruct_audit_ledger: reasonが空白のみ・キー欠落の両方とも自動補完される（2件）",
      _fill_rebuilt2[0]["reason"] == "理由が記載されませんでした（自動補完）"
      and _fill_rebuilt2[1]["reason"] == "理由が記載されませんでした（自動補完）"
      and _fill_stats2.get("audit_ledger_auto_filled_count") == 2,
      f"{_fill_rebuilt2} / {_fill_stats2}")

check("_reconstruct_audit_ledger: stats引数を省略しても例外なく動作する（後方互換）",
      generate_post._reconstruct_audit_ledger(
          [{"candidate_id": 1, "use": True, "reason": ""},
           {"candidate_id": 2, "use": True, "reason": "y"}],
          _fill_candidates,
      )[0]["reason"] == "理由が記載されませんでした（自動補完）")

# decisionの空文字補完は、v1.53フォローアップ以降_derive_decisions()が常に
# 非空文字列を返すため通常経路では到達しない防御的コード（コメント参照）。
# _derive_decisions自体を一時的に差し替え、フォールバックが実際に機能する
# ことを確認する（ホワイトボックス・将来のリグレッション検知用）。
_orig_derive_decisions = generate_post._derive_decisions
generate_post._derive_decisions = lambda entries, id_map, threshold, **kwargs: {1: "", 2: "採用"}
try:
    _fill_stats3: dict = {}
    _fill_rebuilt3 = generate_post._reconstruct_audit_ledger(
        [
            {"candidate_id": 1, "use": True, "reason": "x"},
            {"candidate_id": 2, "use": True, "reason": "y"},
        ],
        _fill_candidates, generate_post.PAIR_OVERLAP_THRESHOLD_DEFAULT, _fill_stats3,
    )
finally:
    generate_post._derive_decisions = _orig_derive_decisions
check("_reconstruct_audit_ledger: decisionが空文字の場合は安全側の「不採用」で自動補完される"
      "（現行設計では到達しない想定の防御的フォールバック。オーナー指示）",
      _fill_rebuilt3[0]["decision"] == "不採用" and _fill_rebuilt3[1]["decision"] == "採用"
      and _fill_stats3.get("audit_ledger_auto_filled_count") == 1,
      f"{_fill_rebuilt3} / {_fill_stats3}")

check("CallOutcome.to_dict(): audit_ledger_auto_filled_countが既定で0",
      generate_post.CallOutcome(True, {}, 1, None).to_dict()["audit_ledger_auto_filled_count"] == 0)
check("CallOutcome.to_dict(): audit_ledger_auto_filled_countを明示指定できる",
      generate_post.CallOutcome(True, {}, 1, None, audit_ledger_auto_filled_count=3)
      .to_dict()["audit_ledger_auto_filled_count"] == 3)
check("NEWS_SELECTIONがcandidate_idの存在とaudit_ledgerでの参照用途を明記している",
      "candidate_id・title・summary" in generate_post.NEWS_SELECTION
      and "audit_ledgerで候補を参照する際に使う" in generate_post.NEWS_SELECTION)

print("=== generate_post.py: tier3候補数上限の確認（v1.21・v1.39でLIMIT=15に変更） ===")
_tier1_fixed = [{"tier": 1, "source": "SEC", "published_at": "Mon, 17 Aug 2026 10:00:00 GMT"} for _ in range(3)]
_tier3_20 = [{"tier": 3, "source": "CoinDesk", "title": f"item{i}",
              "published_at": f"Mon, 17 Aug 2026 {i:02d}:00:00 GMT"} for i in range(20)]
_selected, _stats = generate_post._select_candidates_for_call_a(_tier1_fixed + _tier3_20)
check("tier1は全件（上限なし）で選定される",
      sum(1 for c in _selected if c.get("tier") == 1) == 3, str(_stats))
check(f"tier3は上限{generate_post.TIER3_CANDIDATE_LIMIT}件に絞られる",
      sum(1 for c in _selected if c.get("tier") == 3) == generate_post.TIER3_CANDIDATE_LIMIT, str(_stats))
check("tier3は公開日時の新しい順で選定される（最新のitem19が先頭）",
      [c["title"] for c in _selected if c.get("tier") == 3][0] == "item19",
      [c["title"] for c in _selected if c.get("tier") == 3])
check("truncation_statsが正しく報告される（20件中15件選定・5件除外・ペア救済なし・tier4無し）",
      _stats == {"tier2_total": 0, "tier2_selected": 0, "tier2_dropped": 0,
                 "tier3_total": 20, "tier3_selected": 15, "tier3_dropped": 5,
                 "tier3_pairs_rescued": 0, "tier3_pair_rescued_articles": 0,
                 "tier4_total": 0, "tier4_selected": 0, "tier4_dropped": 0}, str(_stats))

_selected_few, _stats_few = generate_post._select_candidates_for_call_a(_tier1_fixed + _tier3_20[:5])
check("tier3が上限未満なら全件選定され除外0件",
      _stats_few == {"tier2_total": 0, "tier2_selected": 0, "tier2_dropped": 0,
                     "tier3_total": 5, "tier3_selected": 5, "tier3_dropped": 0,
                     "tier3_pairs_rescued": 0, "tier3_pair_rescued_articles": 0,
                     "tier4_total": 0, "tier4_selected": 0, "tier4_dropped": 0}, str(_stats_few))

print("=== generate_post.py: tier2候補数上限の確認（v1.59・オーナー承認・Reuters実体確認済み） ===")
check("TIER2_CANDIDATE_LIMITが15である（tier3と同格・オーナー指定）",
      generate_post.TIER2_CANDIDATE_LIMIT == 15)
_tier2_20 = [{"tier": 2, "source": "Reuters", "title": f"reuters{i}",
              "published_at": f"Mon, 17 Aug 2026 {i:02d}:00:00 GMT"} for i in range(20)]
_selected_t2, _stats_t2 = generate_post._select_candidates_for_call_a(_tier1_fixed + _tier2_20)
check("tier1は全件（上限なし）で選定される（tier2混在時も不変）",
      sum(1 for c in _selected_t2 if c.get("tier") == 1) == 3, str(_stats_t2))
check(f"tier2は上限{generate_post.TIER2_CANDIDATE_LIMIT}件に絞られる（tier1のような無制限にはしない）",
      sum(1 for c in _selected_t2 if c.get("tier") == 2) == generate_post.TIER2_CANDIDATE_LIMIT, str(_stats_t2))
check("tier2は公開日時の新しい順で選定される（最新のreuters19が先頭）",
      [c["title"] for c in _selected_t2 if c.get("tier") == 2][0] == "reuters19",
      [c["title"] for c in _selected_t2 if c.get("tier") == 2])
check("tier2のtruncation_statsが正しく報告される（20件中15件選定・5件除外）",
      _stats_t2 == {"tier2_total": 20, "tier2_selected": 15, "tier2_dropped": 5,
                    "tier3_total": 0, "tier3_selected": 0, "tier3_dropped": 0,
                    "tier3_pairs_rescued": 0, "tier3_pair_rescued_articles": 0,
                    "tier4_total": 0, "tier4_selected": 0, "tier4_dropped": 0}, str(_stats_t2))
_selected_t2_few, _stats_t2_few = generate_post._select_candidates_for_call_a(
    _tier1_fixed + _tier2_20[:5])
check("tier2が上限未満なら全件選定され除外0件",
      _stats_t2_few["tier2_total"] == 5 and _stats_t2_few["tier2_selected"] == 5
      and _stats_t2_few["tier2_dropped"] == 0, str(_stats_t2_few))

print("=== generate_post.py: tier4候補数上限の確認（v1.51・オーナー指示） ===")
check("TIER4_CANDIDATE_LIMITが10である", generate_post.TIER4_CANDIDATE_LIMIT == 10)
_tier4_15 = [{"tier": 4, "source": "Google News (Reuters検索)", "title": f"gnews{i}",
              "published_at": f"Mon, 17 Aug 2026 {i:02d}:00:00 GMT"} for i in range(15)]
_selected_t4, _stats_t4 = generate_post._select_candidates_for_call_a(_tier1_fixed + _tier4_15)
check(f"tier4は上限{generate_post.TIER4_CANDIDATE_LIMIT}件に絞られる",
      sum(1 for c in _selected_t4 if c.get("tier") == 4) == generate_post.TIER4_CANDIDATE_LIMIT, str(_stats_t4))
check("tier4は公開日時の新しい順で選定される（最新のgnews14が先頭）",
      [c["title"] for c in _selected_t4 if c.get("tier") == 4][0] == "gnews14",
      [c["title"] for c in _selected_t4 if c.get("tier") == 4])
check("tier4のtruncation_statsが正しく報告される（15件中10件選定・5件除外）",
      _stats_t4 == {"tier2_total": 0, "tier2_selected": 0, "tier2_dropped": 0,
                    "tier3_total": 0, "tier3_selected": 0, "tier3_dropped": 0,
                    "tier3_pairs_rescued": 0, "tier3_pair_rescued_articles": 0,
                    "tier4_total": 15, "tier4_selected": 10, "tier4_dropped": 5}, str(_stats_t4))
_selected_t4_few, _stats_t4_few = generate_post._select_candidates_for_call_a(
    _tier1_fixed + _tier4_15[:3])
check("tier4が上限未満なら全件選定され除外0件",
      _stats_t4_few["tier4_total"] == 3 and _stats_t4_few["tier4_selected"] == 3
      and _stats_t4_few["tier4_dropped"] == 0, str(_stats_t4_few))

_selected_all, _stats_all = generate_post._select_candidates_for_call_a(
    _tier1_fixed + _tier2_20 + _tier3_20 + _tier4_15)
check("tier1・tier2・tier3・tier4すべて混在時も各tierが独立して選定される（相互に影響しない）",
      _stats_all == {"tier2_total": 20, "tier2_selected": 15, "tier2_dropped": 5,
                     "tier3_total": 20, "tier3_selected": 15, "tier3_dropped": 5,
                     "tier3_pairs_rescued": 0, "tier3_pair_rescued_articles": 0,
                     "tier4_total": 15, "tier4_selected": 10, "tier4_dropped": 5}, str(_stats_all))
check("混在時: 選定結果の内訳件数も一致する（tier1:3 tier2:15 tier3:15 tier4:10=計43件）",
      len(_selected_all) == 43
      and sum(1 for c in _selected_all if c.get("tier") == 1) == 3
      and sum(1 for c in _selected_all if c.get("tier") == 2) == 15
      and sum(1 for c in _selected_all if c.get("tier") == 3) == 15
      and sum(1 for c in _selected_all if c.get("tier") == 4) == 10,
      f"len={len(_selected_all)}")

print("=== collect_news.py: GOOGLE_NEWS_URLのallinurl:→site:演算子修正（v1.51・オーナー指示） ===")
check("GOOGLE_NEWS_URLがsite:演算子を使う（v1.59でurlencode化・コロンは%3Aへ）",
      "site%3Areuters.com" in collect_news.GOOGLE_NEWS_URL)
check("GOOGLE_NEWS_URLがallinurl:を使わない（実測で機能しなくなったため）",
      "allinurl" not in collect_news.GOOGLE_NEWS_URL)
check("GOOGLE_NEWS_URLがロケールパラメータ（hl/gl/ceid）を付与している",
      "hl=en-US" in collect_news.GOOGLE_NEWS_URL and "gl=US" in collect_news.GOOGLE_NEWS_URL
      and "ceid=US%3Aen" in collect_news.GOOGLE_NEWS_URL)

print("=== collect_news.py: GOOGLE_NEWS_URLの金融キーワード絞り込み（v1.59・オーナー指示・実測のうえ適用） ===")
check("GOOGLE_NEWS_URLが金融・マクロキーワードのOR条件を含む（オーナー指定のキーワード）",
      all(kw in collect_news.GOOGLE_NEWS_QUERY_KEYWORDS
          for kw in ("crypto", "bitcoin", "ethereum", "federal reserve", "inflation",
                     "tariff", "oil", "interest rate", "SEC", "stablecoin")))
check("GOOGLE_NEWS_URLがwhen:24hのローリングウィンドウを維持している",
      "when%3A24h" in collect_news.GOOGLE_NEWS_URL)

print("=== generate_post.py: 独立2媒体ペア救済（v1.39フォローアップ・オーナー承認） ===")
check("_overlap_coefficient: 完全一致は1.0",
      generate_post._overlap_coefficient({"a", "b"}, {"a", "b"}) == 1.0)
check("_overlap_coefficient: 重なり無しは0.0",
      generate_post._overlap_coefficient({"a", "b"}, {"c", "d"}) == 0.0)
check("_overlap_coefficient: 小さい方の集合を分母にする（非対称長でも閾値判定できる）",
      generate_post._overlap_coefficient({"a", "b", "c", "d"}, {"a", "b"}) == 1.0)
check("_overlap_coefficient: 空集合は0.0（ゼロ除算しない）",
      generate_post._overlap_coefficient(set(), {"a"}) == 0.0)

_pair_newer = {"tier": 3, "source": "Cointelegraph", "title": "alpha beta gamma delta zeta",
               "published_at": "Mon, 17 Aug 2026 12:20:00 GMT"}  # rank1（最新）
_pair_older = {"tier": 3, "source": "CoinDesk", "title": "alpha beta gamma delta epsilon",
               "published_at": "Mon, 17 Aug 2026 12:00:00 GMT"}  # rank16（上限外）
_rescue_fillers = [{"tier": 3, "source": "CoinDesk", "title": f"filler{i}",
                     "published_at": f"Mon, 17 Aug 2026 12:{1 + i:02d}:00 GMT"} for i in range(14)]
_rescue_pool = [_pair_newer] + _rescue_fillers + [_pair_older]  # 計16件
_rescue_selected, _rescue_stats = generate_post._select_candidates_for_call_a(_rescue_pool)
_rescue_tier3_selected = [c for c in _rescue_selected if c.get("tier") == 3]
check("ペア救済: 上限16位のolder記事が、上限15件に加えて追加選定される",
      any(c is _pair_older for c in _rescue_tier3_selected), [c["title"] for c in _rescue_tier3_selected])
check("ペア救済: newer記事は元々上限内なので二重計上されない（tier3_selected=16件）",
      _rescue_stats["tier3_selected"] == 16, str(_rescue_stats))
check("ペア救済: stats.tier3_pairs_rescued=1・tier3_pair_rescued_articles=1",
      _rescue_stats["tier3_pairs_rescued"] == 1 and _rescue_stats["tier3_pair_rescued_articles"] == 1,
      str(_rescue_stats))

check("_find_independent_pairs: 同一source同士はタイトルが酷似していてもペア扱いしない",
      generate_post._find_independent_pairs([
          {"source": "CoinDesk", "title": "alpha beta gamma delta zeta",
           "published_at": "Mon, 17 Aug 2026 12:20:00 GMT"},
          {"source": "CoinDesk", "title": "alpha beta gamma delta epsilon",
           "published_at": "Mon, 17 Aug 2026 12:00:00 GMT"},
      ]) == [])

_thresh_pair_pool = [
    {"source": "Cointelegraph", "title": "alpha beta gamma delta zeta",
     "published_at": "Mon, 17 Aug 2026 12:20:00 GMT"},
    {"source": "CoinDesk", "title": "alpha beta gamma delta epsilon",
     "published_at": "Mon, 17 Aug 2026 12:00:00 GMT"},
]  # overlap = {alpha,beta,gamma,delta}/5 = 0.8
check("_find_independent_pairs: threshold引数がPAIR_OVERLAP_THRESHOLD_DEFAULT以外でも機能する"
      "（v1.53フォローアップ・config化に伴うシグネチャ変更の確認）",
      len(generate_post._find_independent_pairs(_thresh_pair_pool, 0.7)) == 1
      and len(generate_post._find_independent_pairs(_thresh_pair_pool, 0.9)) == 0)

_cap_pairs = []
for k in range(1, 7):  # 6組作り、PAIR_RESCUE_MAX_PAIRS=5組の上限を確認する
    _cap_pairs.append({"tier": 3, "source": "Cointelegraph", "title": f"p{k}a p{k}b p{k}c p{k}d p{k}e",
                        "published_at": f"Mon, 17 Aug 2026 12:{21 - k:02d}:00 GMT"})  # rank1..6（上限内）
    _cap_pairs.append({"tier": 3, "source": "CoinDesk", "title": f"p{k}a p{k}b p{k}c p{k}d p{k}f",
                        "published_at": f"Mon, 17 Aug 2026 12:{6 - k:02d}:00 GMT"})  # rank16..21（上限外）
_cap_fillers = [{"tier": 3, "source": "CoinDesk", "title": f"capfiller{i}",
                 "published_at": f"Mon, 17 Aug 2026 12:{6 + i:02d}:00 GMT"} for i in range(9)]  # rank7..15
_cap_selected, _cap_stats = generate_post._select_candidates_for_call_a(_cap_pairs + _cap_fillers)
check("ペア救済の上限（PAIR_RESCUE_MAX_PAIRS=5組）: 6組中5組のみ救済される",
      _cap_stats["tier3_pairs_rescued"] == generate_post.PAIR_RESCUE_MAX_PAIRS, str(_cap_stats))
check("ペア救済の上限: 6組目のolder記事（p6a p6b p6c p6d p6f）は救済されず除外されたまま",
      not any(c.get("title") == "p6a p6b p6c p6d p6f" for c in _cap_selected if c.get("tier") == 3),
      [c["title"] for c in _cap_selected if c.get("tier") == 3])
check("ペア救済の上限: tier3_total=21・tier3_selected=20（15+5救済）・tier3_dropped=1",
      _cap_stats == {"tier2_total": 0, "tier2_selected": 0, "tier2_dropped": 0,
                     "tier3_total": 21, "tier3_selected": 20, "tier3_dropped": 1,
                     "tier3_pairs_rescued": 5, "tier3_pair_rescued_articles": 5,
                     "tier4_total": 0, "tier4_selected": 0, "tier4_dropped": 0}, str(_cap_stats))

# render_generation_status(): 除外があった場合のみ目視確認行を表示する
_gen_truncated = {"level": "L0", "call_a": {"ok": True, "attempts": 1, "error": None,
                                             "usage": {"input_tokens": 0, "output_tokens": 0},
                                             "data": CALL_A_DATA, "truncation_stats": _stats},
                   "call_b": {"ok": True, "attempts": 1, "error": None,
                              "usage": {"input_tokens": 0, "output_tokens": 0}, "data": CALL_B_DATA},
                   "news_source_status": {}, "news_candidate_count": 13,
                   "total_usage": {"input_tokens": 0, "output_tokens": 0}}
status_text = compose_post.render_generation_status(_gen_truncated)
check("GENERATION_STATUS.md: tier3除外があれば目視確認行が表示される",
      "tier3候補 20件中 15件を選定" in status_text and "5件を件数上限により除外" in status_text,
      status_text)

_gen_not_truncated = json.loads(json.dumps(_gen_truncated))
_gen_not_truncated["call_a"]["truncation_stats"] = _stats_few
_gen_not_truncated["call_a"]["data"] = CALL_A_DATA
status_text2 = compose_post.render_generation_status(_gen_not_truncated)
check("GENERATION_STATUS.md: tier3除外が無ければ目視確認行を表示しない",
      "件数上限により除外" not in status_text2, status_text2)

print("=== compose_post.py: tier4除外のGENERATION_STATUS.md記録（v1.51・オーナー指示） ===")
_gen_t4 = json.loads(json.dumps(_gen_not_truncated))
_gen_t4["call_a"]["truncation_stats"] = {
    "tier3_total": 0, "tier3_selected": 0, "tier3_dropped": 0,
    "tier3_pairs_rescued": 0, "tier3_pair_rescued_articles": 0,
    "tier4_total": 15, "tier4_selected": 10, "tier4_dropped": 5,
}
_gen_t4_status = compose_post.render_generation_status(_gen_t4)
check("render_generation_status: tier4除外が発生した日は記録される",
      "tier4候補 15件中 10件を選定（5件を件数上限により除外）" in _gen_t4_status, _gen_t4_status)
_gen_t4_none = json.loads(json.dumps(_gen_not_truncated))
_gen_t4_none["call_a"]["truncation_stats"] = {
    "tier3_total": 0, "tier3_selected": 0, "tier3_dropped": 0,
    "tier3_pairs_rescued": 0, "tier3_pair_rescued_articles": 0,
    "tier4_total": 3, "tier4_selected": 3, "tier4_dropped": 0,
}
check("render_generation_status: tier4除外が無い日は記録されない",
      "tier4候補" not in compose_post.render_generation_status(_gen_t4_none))

print("=== compose_post.py: audit_ledger自動補完のGENERATION_STATUS.md記録（v1.54フォローアップ・オーナー指示） ===")
_gen_fill = json.loads(json.dumps(_gen_not_truncated))
_gen_fill["call_a"]["audit_ledger_auto_filled_count"] = 2
_gen_fill_status = compose_post.render_generation_status(_gen_fill)
check("render_generation_status: audit_ledger自動補完が発生した日は件数が記録される",
      "audit_ledger自動補完: 2件" in _gen_fill_status, _gen_fill_status)
_gen_fill_none = json.loads(json.dumps(_gen_not_truncated))
_gen_fill_none["call_a"]["audit_ledger_auto_filled_count"] = 0
check("render_generation_status: audit_ledger自動補完が無い日は記録されない",
      "audit_ledger自動補完" not in compose_post.render_generation_status(_gen_fill_none))
check("render_generation_status: audit_ledger_auto_filled_countキー自体が無くても既定0として扱われエラーにならない",
      "audit_ledger自動補完" not in compose_post.render_generation_status(_gen_not_truncated))

print("=== compose_post.py: リトライ履歴（attempt_errors）のGENERATION_STATUS.mdへの記録（v1.48・オーナー指示） ===")
check("GENERATION_STATUS.md: attempt_errorsが無い（1試行目で成功）場合は試行履歴行を出さない",
      "試行履歴" not in status_text2, status_text2)

_gen_with_retry = json.loads(json.dumps(_gen_truncated))
_gen_with_retry["call_a"]["attempts"] = 2
_gen_with_retry["call_a"]["attempt_errors"] = ["JSONDecodeError: Expecting ',' delimiter: line 255 column 6 (char 13551)"]
status_text3 = compose_post.render_generation_status(_gen_with_retry)
check("GENERATION_STATUS.md: リトライが発生した場合、call_Aの試行履歴が1試行目から記録される",
      "call_A試行履歴" in status_text3
      and "1試行目: JSONDecodeError: Expecting ',' delimiter: line 255 column 6 (char 13551)" in status_text3
      and "2試行目: 成功" in status_text3,
      status_text3)

_gen_b_retry = json.loads(json.dumps(_gen_truncated))
_gen_b_retry["call_b"]["attempts"] = 3
_gen_b_retry["call_b"]["ok"] = False
_gen_b_retry["call_b"]["error"] = "ValueError: 必須キー欠落: ['part2_summary']"
_gen_b_retry["call_b"]["attempt_errors"] = ["ValueError: x", "ValueError: y", "ValueError: 必須キー欠落: ['part2_summary']"]
status_text4 = compose_post.render_generation_status(_gen_b_retry)
check("GENERATION_STATUS.md: call_Bが全試行失敗した場合も全試行の履歴が記録される（成功行は付かない）",
      "call_B試行履歴" in status_text4 and "1試行目: ValueError: x" in status_text4
      and "2試行目: ValueError: y" in status_text4
      and "3試行目: ValueError: 必須キー欠落" in status_text4
      and "試行目: 成功" not in status_text4.split("call_B試行履歴")[1],
      status_text4)

print("=== compose_post.py: force_dropped_candidates・l1_fallback_failing_checksのGENERATION_STATUS.md記録"
      "（v1.79・オーナー承認） ===")

_gen_fd = json.loads(json.dumps(_gen_not_truncated))
_status_fd = compose_post.render_generation_status(
    _gen_fd, force_dropped=[{"candidate_id": 5, "title": "T", "source": "CoinDesk", "reason": "R"}])
check("render_generation_status: force_dropped_candidatesがある場合、候補ごとの詳細が記録される",
      "強制不採用" in _status_fd and "candidate_id=5" in _status_fd and "title='T'" in _status_fd
      and ": R" in _status_fd, _status_fd)
check("render_generation_status: force_dropped_candidatesが空/未指定の場合は記録されない",
      "強制不採用" not in compose_post.render_generation_status(_gen_not_truncated, force_dropped=[])
      and "強制不採用" not in compose_post.render_generation_status(_gen_not_truncated))
_status_l1fb = compose_post.render_generation_status(
    _gen_not_truncated, l1_fallback_failing_checks=["C24_flow_no_unadopted_material"])
check("render_generation_status: l1_fallback_failing_checksがある場合、L1フォールバックの記録が入る",
      "L1へフォールバック" in _status_l1fb and "C24_flow_no_unadopted_material" in _status_l1fb, _status_l1fb)
check("render_generation_status: l1_fallback_failing_checks未指定時は記録されない",
      "L1へフォールバック" not in compose_post.render_generation_status(_gen_not_truncated))

print("=== compose_post.py: L3判定時もGENERATION_STATUS.mdをコミット対象として書く（v1.79・オーナー承認） ===")

_l3_status_path = compose_post._write_l3_status(
    "2026-08-23", "outputs/2026-08-23/daily_data.json が存在しません")
check("_write_l3_status: GENERATION_STATUS.mdファイルを作成する", _l3_status_path.exists())
_l3_status_text = _l3_status_path.read_text(encoding="utf-8")
check("_write_l3_status: level: L3と判定理由を記録する",
      "level: L3" in _l3_status_text
      and "outputs/2026-08-23/daily_data.json が存在しません" in _l3_status_text, _l3_status_text)
check("_write_l3_status: 本文（part1.md/part2.md）は生成していない旨を明記する",
      "part1.md" in _l3_status_text and "生成していません" in _l3_status_text, _l3_status_text)
check("_write_l3_status: draft/ディレクトリ自体は作らない（本文コミット対象を増やさない）",
      not Path("outputs/2026-08-23/draft").exists())

print("=== generate_post.run(): news_candidate_countは渡した件数基準（v1.21） ===")
os.makedirs("outputs/2026-08-21", exist_ok=True)
Path("outputs/2026-08-21/daily_data.json").write_text(
    json.dumps({**DAILY_DATA, "target_date_jst": "2026-08-21"}, ensure_ascii=False), encoding="utf-8")
_news_many = {"collected_at": "2026-08-21T09:00:00+09:00", "target_date_jst": "2026-08-21",
              "source_status": {}, "candidates": _tier1_fixed + _tier3_20}
Path("outputs/2026-08-21/news_candidates.json").write_text(json.dumps(_news_many, ensure_ascii=False), encoding="utf-8")


def _make_run_client_tolerant(a_ok, b_ok):
    def fn(kw, n):
        is_call_a = kw.get("system") == generate_post.SYSTEM_A
        if is_call_a:
            return json_response(_call_a_response(kw)) if a_ok else FakeResponse([FakeTextBlock("bad")])
        return json_response(CALL_B_DATA) if b_ok else FakeResponse([FakeTextBlock("bad")])
    return FakeClient(fn)


_c = _make_run_client_tolerant(True, True)
_result21 = generate_post.run("2026-08-21", client=_c)
# 生の取得総数は 3(tier1) + 20(tier3) = 23件だが、実際に渡すのは 3 + 15(上限) = 18件。
check("run(): news_candidate_countは取得総数(23)ではなく渡した件数(18)を反映する",
      _result21["news_candidate_count"] == 18, str(_result21["news_candidate_count"]))
check("run(): call_a.truncation_statsにtier3の除外情報が記録される",
      _result21["call_a"]["truncation_stats"] == {
          "tier2_total": 0, "tier2_selected": 0, "tier2_dropped": 0,
          "tier3_total": 20, "tier3_selected": 15, "tier3_dropped": 5,
          "tier3_pairs_rescued": 0, "tier3_pair_rescued_articles": 0,
          "tier4_total": 0, "tier4_selected": 0, "tier4_dropped": 0},
      str(_result21["call_a"]["truncation_stats"]))

print("=== generate_post.run() レベル判定 ===")
os.makedirs("outputs/2026-08-17", exist_ok=True)
Path("outputs/2026-08-17/daily_data.json").write_text(json.dumps(DAILY_DATA, ensure_ascii=False), encoding="utf-8")


def make_run_client(a_ok, b_ok):
    def fn(kw, n):
        is_call_a = kw.get("system") == generate_post.SYSTEM_A
        if is_call_a:
            return json_response(_call_a_response(kw)) if a_ok else FakeResponse([FakeTextBlock("bad")])
        return json_response(CALL_B_DATA) if b_ok else FakeResponse([FakeTextBlock("bad")])
    return FakeClient(fn)


for a_ok, b_ok, expected in [(True, True, "L0"), (False, True, "L1"), (True, False, "L1"), (False, False, "L2")]:
    c = make_run_client(a_ok, b_ok)
    result = generate_post.run("2026-08-17", client=c)
    check(f"run() level a_ok={a_ok} b_ok={b_ok} -> {expected}", result["level"] == expected,
          f"got {result['level']}")

# news_candidates.json欠損時、source_statusは空dict（CryptoPanic撤去前の残骸ではないこと・回帰確認）
os.makedirs("outputs/2026-08-19", exist_ok=True)
Path("outputs/2026-08-19/daily_data.json").write_text(
    json.dumps({**DAILY_DATA, "target_date_jst": "2026-08-19"}, ensure_ascii=False), encoding="utf-8")
c = make_run_client(True, True)
result = generate_post.run("2026-08-19", client=c)
check("run(): news_candidates.json欠損時のnews_source_statusは空dict（CryptoPanic残骸ではない）",
      result["news_source_status"] == {}, str(result["news_source_status"]))
check("run(): news_candidates.json欠損時のnews_candidate_countは0",
      result["news_candidate_count"] == 0, str(result["news_candidate_count"]))

# news_candidates.jsonに候補がある日は、news_candidate_countがその件数と一致する（v1.17回帰確認）
os.makedirs("outputs/2026-08-20", exist_ok=True)
Path("outputs/2026-08-20/daily_data.json").write_text(
    json.dumps({**DAILY_DATA, "target_date_jst": "2026-08-20"}, ensure_ascii=False), encoding="utf-8")
Path("outputs/2026-08-20/news_candidates.json").write_text(json.dumps(NEWS_TODAY, ensure_ascii=False), encoding="utf-8")
c = make_run_client(True, True)
result = generate_post.run("2026-08-20", client=c)
check("run(): news_candidates.jsonに1件ある日はnews_candidate_count==1",
      result["news_candidate_count"] == 1, str(result["news_candidate_count"]))

print("=== compose_post.compose() ===")

gen_l0 = {"level": "L0", "call_a": {"ok": True, "data": CALL_A_DATA}, "call_b": {"ok": True, "data": CALL_B_DATA},
          # v1.21: C19が「渡した候補数」とaudit_ledgerの件数を照合するため、
          # CALL_A_DATA["audit_ledger"]の件数（1件）と一致させる。
          "news_candidate_count": len(CALL_A_DATA["audit_ledger"])}
b = compose_post.compose(DAILY_DATA, gen_l0)
check("L0: 見出し3件が前編に順序どおり", all(h in b["part1_md"] for h in verify_post.REQUIRED_HEADINGS_PART1))
check("L0: ヘッドラインは実文言", b["sections"]["part1_headline"] == CALL_A_DATA["part1_headline"])
check("L0: audit_ledger引き継ぎ", b["audit_ledger"] == CALL_A_DATA["audit_ledger"])

print("=== compose_post.py: 【主要指標】【主要指標（詳細）】を投稿本文から外しnumeric_record.mdへ"
      "（v1.81・オーナー承認・運用上の変更） ===")

check("REQUIRED_HEADINGS_PART1に【主要指標】が含まれない",
      "【主要指標】" not in verify_post.REQUIRED_HEADINGS_PART1, verify_post.REQUIRED_HEADINGS_PART1)
check("REQUIRED_HEADINGS_PART2に【主要指標（詳細）】が含まれない",
      "【主要指標（詳細）】" not in verify_post.REQUIRED_HEADINGS_PART2, verify_post.REQUIRED_HEADINGS_PART2)
check("REQUIRED_HEADINGS_PART1は【対象日】【ヘッドライン】【主要なポイント】の3件のみ",
      verify_post.REQUIRED_HEADINGS_PART1 == ["【対象日】", "【ヘッドライン】", "【主要なポイント】"],
      verify_post.REQUIRED_HEADINGS_PART1)
check("REQUIRED_HEADINGS_PART2は【市場のフロー】【LP運用者向けに一言】【総括】の3件のみ",
      verify_post.REQUIRED_HEADINGS_PART2 == ["【市場のフロー】", "【LP運用者向けに一言】", "【総括】"],
      verify_post.REQUIRED_HEADINGS_PART2)

check("compose(): part1_mdに【主要指標】が含まれない（投稿本文から除外）",
      "【主要指標】" not in b["part1_md"], b["part1_md"])
check("compose(): part2_mdに【主要指標（詳細）】が含まれない（投稿本文から除外）",
      "【主要指標（詳細）】" not in b["part2_md"], b["part2_md"])
check("compose(): sections['part1_numeric']/['part2_numeric']自体は引き続き生成される"
      "（numeric_record.md・C16の照合対象として保持）",
      b["sections"]["part1_numeric"].startswith("【主要指標】")
      and b["sections"]["part2_numeric"].startswith("【主要指標（詳細）】"),
      str({k: b["sections"][k] for k in ("part1_numeric", "part2_numeric")}))

check("compose(): numeric_record_mdに【対象日】【主要指標】【主要指標（詳細）】がすべて含まれる",
      "【対象日】" in b["numeric_record_md"] and "【主要指標】" in b["numeric_record_md"]
      and "【主要指標（詳細）】" in b["numeric_record_md"], b["numeric_record_md"])
check("compose(): numeric_record_mdの内容はsections['part1_numeric']/['part2_numeric']と一致する"
      "（別々に再計算せず同じsectionsから組み立てるため、数値の乖離が生じない）",
      b["sections"]["part1_numeric"] in b["numeric_record_md"]
      and b["sections"]["part2_numeric"] in b["numeric_record_md"], b["numeric_record_md"])

_numeric_record_direct = compose_post.render_numeric_record(b["sections"])
check("render_numeric_record(): main()経由と同じ内容を直接呼び出しでも再現できる",
      _numeric_record_direct == b["numeric_record_md"], _numeric_record_direct)

au_numeric = verify_post.run_all(b, DAILY_DATA)
c15_numeric = next(x for x in au_numeric.checks if x["id"] == "C15_heading_order")
c16_numeric = next(x for x in au_numeric.checks if x["id"] == "C16_numeric_match")
check("run_all(): 【主要指標】系見出しが投稿本文に無くてもC15はPASSする（必須リストから除外済み）",
      c15_numeric["result"] == "PASS", str(c15_numeric))
check("run_all(): C16（数値一致）はsectionsを見るため、本文から見出しを外しても引き続きPASSする"
      "（数値算出ロジック自体は変更していないことの確認）",
      c16_numeric["result"] == "PASS", str(c16_numeric))

print("=== compose_post.py: force_drop後の再監査によるL1フォールバック（v1.79・オーナー承認・"
      "「除外後にC12〜C24をすべて再検証し、通らなければ従来どおりL1にしてください」への対応） ===")

_fb_gen_base = json.loads(json.dumps(gen_l0))
_fb_gen_base["call_a"]["force_dropped_candidates"] = [
    {"candidate_id": 2, "title": "Some tier3 story", "source": "CoinDesk", "reason": "test"}]
_fb_gen_base["total_usage"] = {"input_tokens": 100, "output_tokens": 50}
_fb_bundle_ok = compose_post.compose(DAILY_DATA, _fb_gen_base)
check("_final_audit_failing_ids: PASSする本文はFAILしたチェックIDが空リスト",
      compose_post._final_audit_failing_ids(_fb_bundle_ok, DAILY_DATA) == [])

_fb_gen_bad = json.loads(json.dumps(_fb_gen_base))
_fb_gen_bad["call_b"]["data"] = {
    "part2_flow": ["Something → BankChain Alliance was mentioned but never adopted → price moved."],
    "part2_summary": "地合いは総じて改善。継続的な確認が必要。",
}
_fb_bundle_bad = compose_post.compose(DAILY_DATA, _fb_gen_bad)
_fb_failing = compose_post._final_audit_failing_ids(_fb_bundle_bad, DAILY_DATA)
check("_final_audit_failing_ids: part1_pointsに存在しない固有名詞をpart2_flowで持ち出すとC24がFAILする",
      "C24_flow_no_unadopted_material" in _fb_failing, str(_fb_failing))

c_fb = FakeClient(lambda kw, n: json_response(CALL_B_DATA))
_fb_new_gen = compose_post._fallback_to_true_l1(DAILY_DATA, _fb_gen_bad, _fb_failing, client=c_fb)
check("_fallback_to_true_l1: call_Aを失敗扱いへ差し戻す（data=None・ok=False）",
      _fb_new_gen["call_a"]["ok"] is False and _fb_new_gen["call_a"]["data"] is None, str(_fb_new_gen["call_a"]))
check("_fallback_to_true_l1: call_Aのforce_dropped_candidatesは記録として保持される（元の情報を失わない）",
      _fb_new_gen["call_a"]["force_dropped_candidates"] == _fb_gen_bad["call_a"]["force_dropped_candidates"],
      str(_fb_new_gen["call_a"]))
check("_fallback_to_true_l1: call_Bをnews_from_call_a=Noneで再生成する（従来のL1と同じ入力）",
      _fb_new_gen["call_b"]["ok"] is True
      and json.loads(c_fb.messages.calls[0]["messages"][0]["content"]).get("news_from_call_a") is None,
      str(c_fb.messages.calls[0]["messages"][0]["content"])[:200])
check("_fallback_to_true_l1: levelがL1になる（call_Aのみ失敗扱い・call_Bは成功のまま）",
      _fb_new_gen["level"] == "L1", _fb_new_gen["level"])
check("_fallback_to_true_l1: total_usageは_add_usage()で元のusageと再生成した呼び出しBの"
      "usageを合算した値になる（FakeClientはusageを返さないため実際の加算量は0だが、"
      "素の代入ではなく_add_usage()を経由していることを確認）",
      _fb_new_gen["total_usage"] == {"input_tokens": 100, "output_tokens": 50}, str(_fb_new_gen["total_usage"]))

_fb_bundle_after = compose_post.compose(DAILY_DATA, _fb_new_gen)
check("_fallback_to_true_l1: フォールバック後の本文を再度compose()するとC24がもうFAILしない"
      "（part2_flowが従来のL1固定文言に戻るため）",
      compose_post._final_audit_failing_ids(_fb_bundle_after, DAILY_DATA) == [],
      str(compose_post._final_audit_failing_ids(_fb_bundle_after, DAILY_DATA)))

gen_l1a = {"level": "L1", "call_a": {"ok": False, "data": None}, "call_b": {"ok": True, "data": CALL_B_DATA}}
b = compose_post.compose(DAILY_DATA, gen_l1a)
check("L1(A失敗): ヘッドライン固定文言", b["sections"]["part1_headline"] == generate_post.FIXED_HEADLINE)
check("L1(A失敗): headline_for_imageは機械生成（#なし）", "#" not in b["headline_for_image"] and "月" in b["headline_for_image"])
check("L1(A失敗): フローは実文言のまま(Bは成功)", b["sections"]["part2_flow"] != compose_post.FIXED_FLOW)
check("L1(A失敗): audit_ledgerはNone", b["audit_ledger"] is None)

gen_l1b = {"level": "L1", "call_a": {"ok": True, "data": CALL_A_DATA}, "call_b": {"ok": False, "data": None}}
b = compose_post.compose(DAILY_DATA, gen_l1b)
check("L1(B失敗・台本に無い状態): ヘッドラインは実文言のまま", b["sections"]["part1_headline"] == CALL_A_DATA["part1_headline"])
check("L1(B失敗): フローは固定文言", b["sections"]["part2_flow"] == compose_post.FIXED_FLOW)
check("L1(B失敗): 総括は空欄ノート", b["sections"]["part2_summary"] == compose_post.SUMMARY_BLANK_NOTE)

gen_l2 = {"level": "L2", "call_a": {"ok": False, "data": None}, "call_b": {"ok": False, "data": None}}
b = compose_post.compose(DAILY_DATA, gen_l2)
check("L2: 冒頭に未完了ノート", b["part1_md"].startswith(compose_post.L2_TOP_NOTE.rstrip("\n")))
check("L2: LP一言は縮退時も出力される（LLM非依存）", "なお参考APRは" in b["sections"]["lp_comment"])

print("=== compose_post.py: news_candidate_count -1センチネル（v1.20） ===")
gen_no_count = {"level": "L0", "call_a": {"ok": True, "data": CALL_A_DATA}, "call_b": {"ok": True, "data": CALL_B_DATA}}
b_no_count = compose_post.compose(DAILY_DATA, gen_no_count)
check("compose(): news_candidate_count欠落時は-1（フェイルクローズ、v1.20）",
      b_no_count["news_candidate_count"] == -1, str(b_no_count["news_candidate_count"]))

print("=== verify_post: PASS/FAILケース ===")


def bundle_from(daily_data, gen_result):
    b = compose_post.compose(daily_data, gen_result)
    return b


# 正常系: L0で全チェックPASSすること
b_ok = bundle_from(DAILY_DATA, gen_l0)
au = verify_post.run_all(b_ok, DAILY_DATA)
check("L0正常系: 全項目PASS/SKIP（FAILなし）", au.failed == 0, json.dumps(au.checks, ensure_ascii=False))

# L1(A失敗)正常系: 空欄・固定文言を理由にFAILしないこと（C19はSKIP）
b_l1 = bundle_from(DAILY_DATA, gen_l1a)
au = verify_post.run_all(b_l1, DAILY_DATA)
check("L1正常系: 空欄/固定文言を理由にFAILしない", au.failed == 0, json.dumps(au.checks, ensure_ascii=False))
c19 = next(x for x in au.checks if x["id"] == "C19_audit_ledger")
check("L1: C19はSKIP", c19["result"] == "SKIP", str(c19))

# L2正常系
b_l2 = bundle_from(DAILY_DATA, gen_l2)
au = verify_post.run_all(b_l2, DAILY_DATA)
check("L2正常系: 空欄/固定文言を理由にFAILしない", au.failed == 0, json.dumps(au.checks, ensure_ascii=False))

# --- 個別違反ケース ---

# C12
bad = json.loads(json.dumps(b_ok))
bad["sections"]["part1_headline"] = "仮想通貨市場は前日比で上昇"
bad["part1_md"] = bad["part1_md"].replace(b_ok["sections"]["part1_headline"], bad["sections"]["part1_headline"])
au = verify_post.run_all(bad, DAILY_DATA)
check("C12: 禁止語でFAIL", any(x["id"] == "C12_banned_terms" and x["result"] == "FAIL" for x in au.checks))

# C13 (各種)
for bad_text, label in [
    ("#ETH・#USDC", "中黒区切り"),
    ("#ETH/#USDC", "スラッシュ区切り"),
    ("価格は#ETH偏り", "直前が半角スペース/行頭でない"),
    ("#ETH偏りが拡大", "直後が日本語"),
]:
    bad = json.loads(json.dumps(b_ok))
    bad["sections"]["part1_headline"] = bad_text
    bad["part1_md"] = bad["part1_md"].replace(b_ok["sections"]["part1_headline"], bad_text)
    au = verify_post.run_all(bad, DAILY_DATA)
    c13 = next(x for x in au.checks if x["id"] == "C13_hashtag_boundary")
    check(f"C13({label}): FAIL", c13["result"] == "FAIL", str(c13))

# C13 正常系（複数タグを正しく区切る）
ok_bundle = json.loads(json.dumps(b_ok))
ok_bundle["sections"]["part1_headline"] = "#BTC #ETH が上昇。ETH/USDCは横ばい。"
ok_bundle["part1_md"] = ok_bundle["part1_md"].replace(b_ok["sections"]["part1_headline"], ok_bundle["sections"]["part1_headline"])
au = verify_post.run_all(ok_bundle, DAILY_DATA)
c13 = next(x for x in au.checks if x["id"] == "C13_hashtag_boundary")
check("C13: 正しい区切りはPASS", c13["result"] == "PASS", str(c13))

# C14
bad = json.loads(json.dumps(b_ok))
bad["sections"]["part1_headline"] = "BTC | ETH | 比較"
bad["part1_md"] = bad["part1_md"].replace(b_ok["sections"]["part1_headline"], bad["sections"]["part1_headline"])
au = verify_post.run_all(bad, DAILY_DATA)
check("C14: 半角パイプでFAIL", any(x["id"] == "C14_no_table" and x["result"] == "FAIL" for x in au.checks))

# C15
bad = json.loads(json.dumps(b_ok))
bad["part1_md"] = bad["part1_md"].replace("【主要なポイント】", "")
au = verify_post.run_all(bad, DAILY_DATA)
check("C15: 見出し欠落でFAIL", any(x["id"] == "C15_heading_order" and x["result"] == "FAIL" for x in au.checks))

# C16
bad = json.loads(json.dumps(b_ok))
bad["sections"]["part1_numeric"] = bad["sections"]["part1_numeric"].replace("$64,247", "$99,999")
au = verify_post.run_all(bad, DAILY_DATA)
check("C16: テンプレ数値改変でFAIL", any(x["id"] == "C16_numeric_match" and x["result"] == "FAIL" for x in au.checks))

# C16b: 転記あり（隣接数字ガードのfalse-positive回避も同時に確認）
bad = json.loads(json.dumps(b_ok))
bad["sections"]["part1_headline"] = "BTCは$64,247まで上昇した。"
au = verify_post.run_all(bad, DAILY_DATA)
check("C16b: 数値転記でFAIL", any(x["id"] == "C16b_transcription_scan" and x["result"] == "FAIL" for x in au.checks))
# 誤爆回避: "12.72%" は "112.72%" の部分文字列として現れても検知しない
guard_hits = verify_post._find_transcriptions(DAILY_DATA, "本日は112.72%という水準でした", set())
check("C16b: 隣接数字ガードで誤爆しない", "12.72%" not in guard_hits, str(guard_hits))
# allowlist: 登録済みならFAILしない（ファイル経由の統合はcheck_c16b内_load_allowlistで別途担保、
# ここではallowlist集合を受け取った際の除外ロジック自体を検証する）
hits_wo = verify_post._find_transcriptions(DAILY_DATA, "BTCは$64,247まで上昇した。", set())
hits_with = verify_post._find_transcriptions(DAILY_DATA, "BTCは$64,247まで上昇した。", {"$64,247"})
check("C16b: allowlist登録でヒット除外", hits_wo == ["$64,247"] and hits_with == [], f"{hits_wo} / {hits_with}")

print("=== verify_post: C16b ラベルキー除外の確認（v1.27・「name」「label」誤検知の恒久対応） ===")
# プール名（"name"キーの値）に数値表現が含まれていても、ラベルであり
# 「市場データの数値の転記」ではないためFAILしない（2026-08-20実運用で
# 実際に誤検知した事例。DAILY_DATAの"Base 0.3%プール"がそのまま該当する）。
hits_name = verify_post._find_transcriptions(
    DAILY_DATA, "本日はBase 0.3%プールの出来高が急増した点が注目される。", set())
check("C16b: プール名（nameキーの値）はFAILしない", hits_name == [], str(hits_name))

# fear_greedの"label"キーの値（"Neutral"）も同様に候補から除外される。
hits_label = verify_post._find_transcriptions(DAILY_DATA, "市場心理はNeutral圏で推移した。", set())
check("C16b: labelキーの値はFAILしない", hits_label == [], str(hits_label))

# 一方、同じプールの実際の数値（APR・TVL等、nameではないキー配下の値）は
# 引き続き転記としてFAILする——今回の修正がキー名での判定であり、
# 「プール名を含む文は無条件にPASSする」という抜け道になっていないことの確認。
hits_real_numbers = verify_post._find_transcriptions(
    DAILY_DATA, "Base 0.3%プールのAPRは24.00%に達し、TVLは$112.38Mとなった。", set())
check("C16b: プール名文中でも実数値（APR・TVL）の転記はFAILする",
      set(hits_real_numbers) == {"24.00%", "$112.38M"}, str(hits_real_numbers))

candidates_check = set()
verify_post._collect_numeric_strings(DAILY_DATA, candidates_check)
check("C16b: 候補集合にラベル値（プール名・Neutral等）が含まれない",
      not any(c in candidates_check for c in ("Base 0.05%プール", "Base 0.3%プール", "Neutral")),
      str(sorted(candidates_check)))

print("=== verify_post: headline_for_imageの走査（v1.20） ===")
bad = json.loads(json.dumps(b_ok))
bad["headline_for_image"] = "仮想通貨市場が上昇"
au = verify_post.run_all(bad, DAILY_DATA)
check("C12: headline_for_image中の禁止語もFAIL", any(x["id"] == "C12_banned_terms" and x["result"] == "FAIL" for x in au.checks))

bad2 = json.loads(json.dumps(b_ok))
bad2["headline_for_image"] = "BTCは$64,247水準"
au = verify_post.run_all(bad2, DAILY_DATA)
check("C16b: headline_for_image中の数値転記もFAIL",
      any(x["id"] == "C16b_transcription_scan" and x["result"] == "FAIL" for x in au.checks))

# C17
import compose_lp_comment as _clc
bad = json.loads(json.dumps(b_ok))
bad["sections"]["lp_comment"] = b_ok["sections"]["lp_comment"].replace(_clc.FIXED_4, "")
au = verify_post.run_all(bad, DAILY_DATA)
check("C17: 定型文欠落でFAIL", any(x["id"] == "C17_lp_disclaimers" and x["result"] == "FAIL" for x in au.checks))

# C18
bad = json.loads(json.dumps(b_ok))
bad["sections"]["part2_flow"] = "規制強化が原因で下落した。"
au = verify_post.run_all(bad, DAILY_DATA)
check("C18: 断定表現でFAIL", any(x["id"] == "C18_causal_assertion" and x["result"] == "FAIL" for x in au.checks))

print("=== verify_post: C18強化の確認（v1.20・主語を挟む形の検知） ===")
for bad_sentence, label in [
    ("規制緩和によりBTC価格が上昇した。", "により+主語+上昇（限定表現なし）"),
    ("規制強化の発表を受けてBTC価格が下落した。", "を受けて+主語+下落（限定表現なし）"),
    ("金利上昇のためETH価格が下落した。", "のため+主語+下落（限定表現なし）"),
    ("規制緩和が牽引した。", "が牽引した（限定表現なし・従来どおり単独検知）"),
]:
    hits = verify_post._causal_violations_in_sentence(bad_sentence)
    check(f"C18: 「{label}」は検知される", len(hits) > 0, str(hits))

for ok_sentence, label in [
    ("これらの動きが直接的な因果関係にあるとは確認できない。", "マーカー無し"),
    ("規制緩和により市場参加者の関心が高まった可能性がある。", "マーカーありだが価格変動語なし"),
]:
    hits = verify_post._causal_violations_in_sentence(ok_sentence)
    check(f"C18: 「{label}」は誤検知しない", len(hits) == 0, str(hits))

bad = json.loads(json.dumps(b_ok))
bad["sections"]["part2_flow"] = "規制緩和によりBTC価格が上昇した。"
au_no_allow = verify_post.Audit()
verify_post.check_c18(au_no_allow, bad["sections"], bad["llm_section_keys"], set())
c18_no_allow = next(x for x in au_no_allow.checks if x["id"] == "C18_causal_assertion")
check("C18: allowlist無しではFAIL", c18_no_allow["result"] == "FAIL", str(c18_no_allow))

au_with_allow = verify_post.Audit()
verify_post.check_c18(au_with_allow, bad["sections"], bad["llm_section_keys"], {"規制緩和によりBTC価格が上昇した"})
c18_with_allow = next(x for x in au_with_allow.checks if x["id"] == "C18_causal_assertion")
check("C18: allowlist登録でPASS", c18_with_allow["result"] == "PASS", str(c18_with_allow))

print("=== verify_post: C18再設計の確認（v1.22・限定表現による判定へ変更） ===")
# 独立レビュー2巡目が指摘した誤検知5パターン。限定表現があるものはPASS（hits空）を期待。
# 3件目（読点で繋がれた無関係な2つの事象が偶然同一文に共存するケース）は
# 限定表現が無いため今回もFAILのまま——同一文単位判定の構造的な限界として
# DESIGN_CHANGES.mdに明記する（限定表現チェックでは救えないケース）。
for sentence, label, expect_pass in [
    ("規制強化を受けて市場全体のセンチメントが改善した可能性があるが、"
     "BTC価格の上昇との直接的な因果関係は未確認である。", "可能性+未確認", True),
    ("規制強化のためリスク回避的な売りが観測されたが、BTC価格が下落した"
     "複数の要因の一つに過ぎず、単独の原因と断定はできない。", "断定はできない（助詞挿入）", True),
    ("システム障害のため一部ユーザーが取引できない状態が続いたが、この間もBTC価格は"
     "堅調に推移し、後場にかけて上昇した点は特筆に値する。", "読点で繋がれた無関係な2事象（既知の限界）", False),
    ("決算発表を受けて市場心理の改善が意識された可能性はあるが、BTCは緩やかに上昇した。",
     "意識された可能性", True),
    ("ETH価格が牽引した可能性が指摘されているが、同時期に確認された他の材料もあり"
     "因果は未確認である。", "が牽引した+可能性+未確認", True),
]:
    hits = verify_post._causal_violations_in_sentence(sentence)
    ok = (not hits) == expect_pass
    check(f"C18再設計: 誤検知パターン「{label}」が期待どおり{'PASS' if expect_pass else 'FAIL(既知の限界)'}",
          ok, f"hits={hits}")

# 独立レビュー2巡目が指摘した回避7パターン。全て検知されることを期待。
for sentence, label in [
    ("BTC価格が上昇したことは、ETFの資金流入により説明可能である。", "価格語がマーカーより前（語順逆）"),
    ("規制強化によってBTC価格が上昇した。", "によって（拡充マーカー）"),
    ("取引所の障害のせいでBTC価格が下落した。", "せいで（拡充マーカー）"),
    ("ETF承認を機にBTC価格が上昇した。", "を機に（拡充マーカー）"),
    ("規制強化のため暴落した。", "暴落（拡充価格語）"),
    ("好材料を受けて急騰した。", "急騰（拡充価格語）"),
    ("規制強化により反落した。", "反落（拡充価格語）"),
]:
    hits = verify_post._causal_violations_in_sentence(sentence)
    check(f"C18再設計: 回避パターン「{label}」は検知される", len(hits) > 0, str(hits))

print("=== generate_post.py: RULES_CAUSALの帰結明記強化（v1.49・オーナー指示） ===")
check("RULES_CAUSAL: コミット拒否の帰結が明記されている",
      "コミットされない" in generate_post.RULES_CAUSAL)
check("RULES_CAUSAL: notable_moveへの言及がある",
      "notable_move" in generate_post.RULES_CAUSAL)
check("SYSTEM_A: RULES_CAUSALが含まれる（call Aにも因果表現規則が渡る）",
      "コミットされない" in generate_post.SYSTEM_A)
check("SYSTEM_B: RULES_CAUSALが含まれる（call Bにも因果表現規則が渡る）",
      "コミットされない" in generate_post.SYSTEM_B)

# C19: L0でaudit_ledger不備
bad = json.loads(json.dumps(b_ok))
bad["audit_ledger"] = [{"source": "Reuters"}]  # url等欠落
au = verify_post.run_all(bad, DAILY_DATA)
check("C19: L0でフィールド欠落FAIL", any(x["id"] == "C19_audit_ledger" and x["result"] == "FAIL" for x in au.checks))

print("=== verify_post: C19 null誤判定の修正確認（v1.20） ===")
bad = json.loads(json.dumps(b_ok))
bad["audit_ledger"] = [{"source": "金融庁", "url": "https://www.fsa.go.jp/x", "title": "...",
                        "published_at": None, "verified_by": "RSS summary",
                        "decision": "不採用", "reason": "関係なし"}]
bad["news_candidate_count"] = 1
au = verify_post.run_all(bad, DAILY_DATA)
c19 = next(x for x in au.checks if x["id"] == "C19_audit_ledger")
check("C19: published_atがnullの場合はFAIL（str(None)誤判定の修正）", c19["result"] == "FAIL", str(c19))

# C20: 長すぎるheadline_for_image / #混入
bad = json.loads(json.dumps(b_ok))
bad["headline_for_image"] = "あ" * 41
au = verify_post.run_all(bad, DAILY_DATA)
check("C20: 41字でFAIL", any(x["id"] == "C20_image_headline" and x["result"] == "FAIL" for x in au.checks))
bad2 = json.loads(json.dumps(b_ok))
bad2["headline_for_image"] = "#BTC上昇"
au = verify_post.run_all(bad2, DAILY_DATA)
check("C20: #混入でFAIL", any(x["id"] == "C20_image_headline" and x["result"] == "FAIL" for x in au.checks))

# --- C19 v1.17改定: 空配列許容は当日の候補自体が0件の場合のみ ---
bad = json.loads(json.dumps(b_ok))
bad["audit_ledger"] = []
bad["news_candidate_count"] = 0
au = verify_post.run_all(bad, DAILY_DATA)
c19 = next(x for x in au.checks if x["id"] == "C19_audit_ledger")
check("C19: 空配列＋候補0件はPASS", c19["result"] == "PASS", str(c19))

bad = json.loads(json.dumps(b_ok))
bad["audit_ledger"] = []
bad["news_candidate_count"] = 5
au = verify_post.run_all(bad, DAILY_DATA)
c19 = next(x for x in au.checks if x["id"] == "C19_audit_ledger")
check("C19: 空配列だが候補5件存在はFAIL（採否記録漏れを示す・v1.17の主目的）",
      c19["result"] == "FAIL", str(c19))

bad = json.loads(json.dumps(b_ok))
bad["audit_ledger"] = []
bad.pop("news_candidate_count", None)
au = verify_post.run_all(bad, DAILY_DATA)
c19 = next(x for x in au.checks if x["id"] == "C19_audit_ledger")
check("C19: 空配列＋news_candidate_count欠落はFAIL（0件と区別できないためフェイルクローズ）",
      c19["result"] == "FAIL", str(c19))

# v1.21改定: 非空audit_ledgerは「渡した候補数」との件数一致も検査する
# （フィールド充足だけでは一部取りこぼしを検知できないため。オーナー指示）。
bad = json.loads(json.dumps(b_ok))
bad["audit_ledger"] = [{"source": "金融庁", "url": "https://www.fsa.go.jp/x", "title": "...",
                        "published_at": "2026-08-17", "verified_by": "RSS summary",
                        "decision": "不採用", "reason": "暗号通貨市場との関係が確認できない"}]
bad["news_candidate_count"] = 5
au = verify_post.run_all(bad, DAILY_DATA)
c19 = next(x for x in au.checks if x["id"] == "C19_audit_ledger")
check("C19: 候補5件中1件のみ記録は件数不一致でFAIL（v1.21・取りこぼし検知）",
      c19["result"] == "FAIL", str(c19))

good = json.loads(json.dumps(b_ok))
good["audit_ledger"] = [
    {"source": "金融庁", "url": "https://www.fsa.go.jp/a", "title": "...", "published_at": "2026-08-17",
     "verified_by": "RSS summary", "decision": "不採用", "reason": "関係なし"},
    {"source": "日本銀行", "url": "https://www.boj.or.jp/b", "title": "...", "published_at": "2026-08-17",
     "verified_by": "RSS summary", "decision": "不採用", "reason": "関係なし"},
]
good["news_candidate_count"] = 2
au = verify_post.run_all(good, DAILY_DATA)
c19 = next(x for x in au.checks if x["id"] == "C19_audit_ledger")
check("C19: 候補2件・audit_ledger2件で件数一致するとPASS（v1.21）",
      c19["result"] == "PASS", str(c19))

print("=== verify_post: C21 decisionとtierの整合（v1.29・オーナー指示） ===")


def _c21(entries, headline=None, candidate_count=None, level="L0"):
    b = json.loads(json.dumps(b_ok))
    b["audit_ledger"] = entries
    b["level"] = level
    b["news_candidate_count"] = len(entries) if candidate_count is None else candidate_count
    if headline is not None:
        b["sections"]["part1_headline"] = headline
        b["part1_md"] = b["part1_md"].replace(CALL_A_DATA["part1_headline"], headline)
    au = verify_post.run_all(b, DAILY_DATA)
    c21 = next(x for x in au.checks if x["id"] == "C21_decision_tier_consistency")
    c22 = next(x for x in au.checks if x["id"] == "C22_headline_tier1_basis")
    return c21, c22


# tier1の"採用"はPASS
c21, _ = _c21([
    {"source": "SEC", "url": "https://example.com/a", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用", "reason": "一次情報"},
])
check("C21: tier1の採用はPASS", c21["result"] == "PASS", str(c21))

# tier2（Reuters・v1.59オーナー承認）の"採用"もPASS（tier1と同じ扱い）
c21, _ = _c21([
    {"source": "Reuters", "url": "https://news.google.com/rss/articles/FAKE",
     "title": "US launches new strikes on Iran", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用", "reason": "Reutersによる独立報道"},
])
check("C21: tier2（Reuters）の採用はPASS（v1.59・オーナー承認）", c21["result"] == "PASS", str(c21))

# tier3単独の"採用"はFAIL（プロンプトでは防げなかった実際の混入パターン）
c21, _ = _c21([
    {"source": "CoinDesk", "url": "https://example.com/b", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用", "reason": "tier1裏付けなしだが補足採用"},
])
check("C21: tier3単独の採用はFAIL", c21["result"] == "FAIL", str(c21))
check("C21: FAIL理由にtierが明記される", "tier=3" in c21["detail"], c21["detail"])

# 独立2ソース: distinct sourceが2件ならPASS（Laser Digital実例の形）
c21, _ = _c21([
    {"source": "Cointelegraph", "url": "https://example.com/c1", "title": "A社ライセンス取得",
     "published_at": "2026-08-17", "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
    {"source": "CoinDesk", "url": "https://example.com/c2", "title": "A社が認可取得",
     "published_at": "2026-08-17", "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
])
check("C21: distinct source 2件の独立2ソースはPASS", c21["result"] == "PASS", str(c21))

# 独立2ソース: 単独ソースしかないのに独立2ソースを名乗るとFAIL
# （実データでは発生しなかったが、C21が防ぐべき最も直接的な失敗形）
c21, _ = _c21([
    {"source": "CoinDesk", "url": "https://example.com/d", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "裏付けなしで独立2ソースを自称"},
])
check("C21: 単独sourceで独立2ソースを名乗るとFAIL", c21["result"] == "FAIL", str(c21))

# 同一sourceの複数記事は1件と数える（distinct source条件を満たさない）
c21, _ = _c21([
    {"source": "CoinDesk", "url": "https://example.com/e1", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "同一媒体の別記事1"},
    {"source": "CoinDesk", "url": "https://example.com/e2", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "同一媒体の別記事2"},
])
check("C21: 同一sourceの2記事は1件と数えFAIL", c21["result"] == "FAIL", str(c21))

# 未知のdecision値はFAIL
c21, _ = _c21([
    {"source": "SEC", "url": "https://example.com/f", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "保留", "reason": "..."},
])
check("C21: 未知のdecision値はFAIL", c21["result"] == "FAIL", str(c21))

# 不採用は検査しない（tier3単独でも不採用ならFAILにしない）
c21, _ = _c21([
    {"source": "CoinDesk", "url": "https://example.com/g", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "不採用", "reason": "根拠不足"},
])
check("C21: 不採用は検査対象外でPASS", c21["result"] == "PASS", str(c21))

# 候補0件の日はSKIP
c21, _ = _c21([], candidate_count=0)
check("C21: 候補0件の日はSKIP", c21["result"] == "SKIP", str(c21))

# L0以外（呼び出しA失敗）はSKIP（台帳の有無自体はC19が判定）
b_non_l0 = json.loads(json.dumps(b_l1))
au = verify_post.run_all(b_non_l0, DAILY_DATA)
c21_non_l0 = next(x for x in au.checks if x["id"] == "C21_decision_tier_consistency")
check("C21: L0以外はSKIP", c21_non_l0["result"] == "SKIP", str(c21_non_l0))

print("=== verify_post: C22 ヘッドラインのtier1裏付け（v1.29・オーナー指示） ===")

# 定型文ヘッドライン（材料なし）はSKIP
_, c22 = _c21([], headline=generate_post.FIXED_HEADLINE, candidate_count=0)
check("C22: 定型文ヘッドラインはSKIP", c22["result"] == "SKIP", str(c22))

# 実文言ヘッドライン＋tier1採用ありはPASS
_, c22 = _c21([
    {"source": "FRB", "url": "https://example.com/h", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用", "reason": "一次情報"},
], headline="BTCが上昇し、FRBの発表も重なった一日となった。")
check("C22: tier1採用がある実文言ヘッドラインはPASS", c22["result"] == "PASS", str(c22))

# 実文言ヘッドライン＋tier2（Reuters）採用ありはPASS（v1.59・オーナー承認）
# 9/1に実際に取りこぼした「米イラン交戦再開による原油急騰」のような材料が
# tier2として採用された場合、part1_headlineの正当な根拠になることを確認する。
_, c22 = _c21([
    {"source": "Reuters", "url": "https://news.google.com/rss/articles/FAKE",
     "title": "US launches new strikes on Iran", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用", "reason": "Reutersによる独立報道"},
], headline="米イラン間の軍事衝突再開を受け、原油価格が急騰した一日となった。")
check("C22: tier2（Reuters）採用がある実文言ヘッドラインはPASS（v1.59・オーナー承認）",
      c22["result"] == "PASS", str(c22))

# 実文言ヘッドライン＋tier1採用なし・独立2ソース採用のみはPASS（v1.44）
# 従来（v1.29〜v1.43）は独立2ソース単独をFAILとしていたが、8/26実データ
# （BankChain Alliance）で独立2ソース材料単独でも正当な本文材料であることが
# 確認され、NO_CANDIDATES_FALLBACKの②で独立2ソース材料単独をpart1_headline
# の正当な根拠として認めるよう改定された（旧「簡易版のため対応関係は見ない」
# という限界は、この改定によりtier1・独立2ソースいずれの根拠であっても
# 妥当と判定できるようになったことで解消）。
_, c22 = _c21([
    {"source": "Cointelegraph", "url": "https://example.com/i1", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
    {"source": "CoinDesk", "url": "https://example.com/i2", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
], headline="BTCが上昇し、A社のライセンス取得報道も material となった一日。")
check("C22: tier1採用が無く独立2ソース採用のみの実文言ヘッドラインはPASS（v1.44）",
      c22["result"] == "PASS", str(c22))

# 実文言ヘッドラインなのに根拠（tier1採用・独立2ソース採用・notable_move）が
# 皆無ならFAIL（従来どおり・根拠皆無のケース）
_, c22 = _c21([
    {"source": "Cointelegraph", "url": "https://example.com/i3", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "不採用", "reason": "C: 波及経路を説明できない一般ニュース"},
], headline="BTCが上昇し、A社のライセンス取得報道も material となった一日。")
check("C22: 実文言ヘッドラインなのに根拠が皆無ならFAIL（従来どおり）",
      c22["result"] == "FAIL", str(c22))

# 定型文ヘッドラインなのに独立2ソース採用が存在する場合はFAIL（v1.44新設）
# ヘッドラインと本文（part1_points）の矛盾＝8/23（BitMart）・8/24（Bitmine）・
# 8/26（BankChain Alliance）で実測された事象そのものを検出する。
_, c22 = _c21([
    {"source": "Cointelegraph", "url": "https://example.com/i4", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
    {"source": "CoinDesk", "url": "https://example.com/i5", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
], headline=generate_post.FIXED_HEADLINE)
check("C22: 定型文ヘッドラインなのに独立2ソース採用が存在するとFAIL（v1.44・ヘッドラインと本文の矛盾を検出）",
      c22["result"] == "FAIL", str(c22))

print("=== verify_post: C22 notable_moveをヘッドラインの根拠として扱わない（v1.82・オーナー承認。旧v1.42の扱いを廃止） ===")

import inspect as _inspect_c22
check("check_c22: 引数にintraday_rangeが無い（v1.82で廃止）",
      "intraday_range" not in _inspect_c22.signature(verify_post.check_c22).parameters,
      str(_inspect_c22.signature(verify_post.check_c22)))

# 材料なし＋定型文ヘッドラインはnotable_moveの有無に関わらずSKIP（正しい状態）
_au_c22a = verify_post.Audit()
verify_post.check_c22(_au_c22a, generate_post.FIXED_HEADLINE, [], {})
check("check_c22: 材料なし＋定型文ヘッドラインはSKIP（notable_move日でも定型文が正しい・v1.82）",
      _au_c22a.checks[0]["result"] == "SKIP", str(_au_c22a.checks[0]))

# 材料なしなのに実文言（値動きを主題にした文）のヘッドラインはFAIL（根拠が皆無）
_au_c22b = verify_post.Audit()
verify_post.check_c22(_au_c22b, "BTCは一時上昇したのち上げ幅を縮小した。", [], {})
check("check_c22: 材料なしで値動きを主題にした非定型文ヘッドラインはFAIL（notable_moveは根拠にならない・v1.82）",
      _au_c22b.checks[0]["result"] == "FAIL", str(_au_c22b.checks[0]))

_au_c22d = verify_post.Audit()
verify_post.check_c22(
    _au_c22d, "BTCが上昇し、FRBの発表も重なった一日となった。",
    [{"source": "FRB", "url": "https://example.com/h", "title": "...", "published_at": "2026-08-17",
      "verified_by": "v", "decision": "採用", "reason": "一次情報"}],
    {"FRB": 1})
check("check_c22: tier1採用がある場合はPASS",
      _au_c22d.checks[0]["result"] == "PASS", str(_au_c22d.checks[0]))

# run_all()経由: notable_move:trueのdaily_dataでも、材料なし＋定型文ならC22はSKIP
_dd_notable = json.loads(json.dumps(DAILY_DATA))
_dd_notable["intraday_range"] = {
    "BTC": {"high": "$81,265", "low": "$78,100", "source": "coinbase",
            "retrieved_at": "2026-08-26T10:20:24+09:00", "representative": True, "notable_move": True},
}
_b_notable = json.loads(json.dumps(b_ok))
_b_notable["audit_ledger"] = [
    {"source": "Cointelegraph", "url": "https://example.com/j1", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "不採用", "reason": "C: 波及経路を説明できない一般ニュース"},
]
_b_notable["reusable_for_summary"] = []
_b_notable["news_candidate_count"] = 1
_b_notable["sections"]["part1_headline"] = generate_post.FIXED_HEADLINE
au_notable = verify_post.run_all(_b_notable, _dd_notable)
c22_notable = next(x for x in au_notable.checks if x["id"] == "C22_headline_tier1_basis")
check("run_all(): notable_move:trueの日でも材料なし＋定型文ヘッドラインならC22はSKIP（v1.82）",
      c22_notable["result"] == "SKIP", str(c22_notable))

# run_all()経由: notable_move:trueの日に値動きを主題にした非定型文ヘッドライン（材料なし）はC22 FAIL
_b_notable2 = json.loads(json.dumps(_b_notable))
_b_notable2["sections"]["part1_headline"] = "BTCは一時上昇したのち上げ幅を縮小した。"
au_notable2 = verify_post.run_all(_b_notable2, _dd_notable)
c22_notable2 = next(x for x in au_notable2.checks if x["id"] == "C22_headline_tier1_basis")
check("run_all(): notable_move:trueの日でも値動き主題の非定型文ヘッドライン（材料なし）はC22 FAIL（v1.82）",
      c22_notable2["result"] == "FAIL", str(c22_notable2))

# run_all()経由で独立2ソース採用がcheck_c22へ正しく伝播しPASSになることも確認（v1.44）
_b_pair = json.loads(json.dumps(b_ok))
_b_pair["audit_ledger"] = [
    {"source": "Cointelegraph", "url": "https://example.com/k1", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
    {"source": "CoinDesk", "url": "https://example.com/k2", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
]
_b_pair["reusable_for_summary"] = []
_b_pair["news_candidate_count"] = 2
_b_pair["sections"]["part1_headline"] = "A社が提携を発表し、BTCが反応した一日。"
au_pair = verify_post.run_all(_b_pair, DAILY_DATA)
c22_pair = next(x for x in au_pair.checks if x["id"] == "C22_headline_tier1_basis")
check("run_all(): 独立2ソース採用がcheck_c22へ正しく伝播しPASSになる（v1.44）",
      c22_pair["result"] == "PASS", str(c22_pair))

print("=== verify_post: C23 総括の固有名詞バックリファレンス（v1.44・オーナー指示） ===")

_au_c23a = verify_post.Audit()
verify_post.check_c23(_au_c23a, "", "・材料A", [])
check("check_c23: part2_summaryが空文字ならSKIP",
      _au_c23a.checks[0]["result"] == "SKIP", str(_au_c23a.checks[0]))

_au_c23b = verify_post.Audit()
verify_post.check_c23(_au_c23b, "地合いは総じて改善。継続的な確認が必要。", "・材料A", [])
check("check_c23: ASCII固有名詞候補が無ければPASS",
      _au_c23b.checks[0]["result"] == "PASS", str(_au_c23b.checks[0]))

_au_c23c = verify_post.Audit()
verify_post.check_c23(_au_c23c, "BTC・ETHともに軟調。USDドミナンスは横ばい。", "・材料A", [])
check("check_c23: allowlist内の一般語彙（BTC・ETH・USD）はPASS（固有名詞候補として扱わない）",
      _au_c23c.checks[0]["result"] == "PASS", str(_au_c23c.checks[0]))

# 8/26実データの実チェックで発見した誤検知（Fear & Greed指数の分類ラベルは
# daily_data.json由来の固定語彙であり本文材料ではないが、初期実装では
# 「Fear&Greed」「Extreme」が固有名詞候補として誤検知された）。
_au_c23g = verify_post.Audit()
verify_post.check_c23(
    _au_c23g, "Fear&Greed指数がExtreme greedを示しており、過熱感には留意が必要です。",
    "・材料A", [])
check("check_c23: Fear&Greed指数の分類ラベル（Fear&Greed・Extreme）は誤検知しない（8/26実データで発見・回帰確認）",
      _au_c23g.checks[0]["result"] == "PASS", str(_au_c23g.checks[0]))

# 9/8実データの実例（「Fear & Greed Index」という英語表記の「Index」が
# 固有名詞候補として誤検知され、C23がFAILしフェイルクローズにより
# 本文が一度もコミットされなかった事象）。
_au_c23h = verify_post.Audit()
verify_post.check_c23(
    _au_c23h, "市場心理を示す指数（Fear & Greed Index）は「Greed（強欲）」圏を維持しており。",
    "・材料A", [])
check("check_c23: 「Fear & Greed Index」の「Index」は誤検知しない（9/8実データで発見・回帰確認）",
      _au_c23h.checks[0]["result"] == "PASS", str(_au_c23h.checks[0]))

# 8/26実データの実例（米PCEインフレ指標が本文未確認のまま総括に持ち出された事象）。
# 「PCE」は片仮名・漢字に前後を挟まれた埋め込み形だが、findallは文字クラスの
# 連続部分だけを抽出するため単語境界に依存せず正しく抽出できる。
_au_c23d = verify_post.Audit()
verify_post.check_c23(
    _au_c23d, "米PCEインフレ指標への警戒感が続いています。",
    "・BTCが上昇（CoinDesk、2026-08-26）", [])
check("check_c23: part1_pointsに無いASCII固有名詞（PCE。片仮名・漢字に埋め込まれた形でも抽出）はFAIL",
      _au_c23d.checks[0]["result"] == "FAIL", str(_au_c23d.checks[0]))
check("check_c23: FAIL detailにPCEが列挙される",
      "PCE" in _au_c23d.checks[0]["detail"], _au_c23d.checks[0]["detail"])

_au_c23e = verify_post.Audit()
verify_post.check_c23(
    _au_c23e, "SECの規則見直しが意識されています。",
    "・SECが規則見直しを提案（Reuters、2026-08-26）", [])
check("check_c23: part1_pointsに同一文字列があればPASS",
      _au_c23e.checks[0]["result"] == "PASS", str(_au_c23e.checks[0]))

_au_c23f = verify_post.Audit()
verify_post.check_c23(
    _au_c23f, "Bitmineの動向は今後も継続監視の対象です。",
    "・材料A", ["Bitmineの株式取得は継続審議中、新展開なし"])
check("check_c23: reusable_for_summaryに同一文字列があればPASS（part1_pointsに無くてもよい）",
      _au_c23f.checks[0]["result"] == "PASS", str(_au_c23f.checks[0]))

# run_all()経由での配線確認（8/26実データの実例＝BankChain Allianceが総括に
# 持ち出されたがpart1_points・reusable_for_summaryのいずれにも無い形を再現）
_b_c23 = json.loads(json.dumps(b_ok))
_b_c23["sections"]["part2_summary"] = "BankChainの動向が注目されています。"
_b_c23["reusable_for_summary"] = []
au_c23 = verify_post.run_all(_b_c23, DAILY_DATA)
c23_check = next(x for x in au_c23.checks if x["id"] == "C23_summary_no_new_entities")
check("run_all(): C23がpart1_points/reusable_for_summaryを参照して正しくFAILになる",
      c23_check["result"] == "FAIL", str(c23_check))

print("=== verify_post: C23 scheduled_eventsのバックリファレンス許可対象への追加"
      "（v1.79・オーナー承認・2026-09-25分「BOE」誤検知への対処） ===")

# 2026-09-25実データの再現: BOE総裁講演がその日のscheduled_events（経済カレンダー）に
# 実在する予定であり、統合運用基準§3.1が【総括】に許容する「翌日に確認すべき対象」の
# 記述として正当だったにもかかわらず、scheduled_eventsが未参照だったためFAILしていた。
_boe_scheduled_events = [
    {"title": "BOE Gov Bailey Speaks", "country": "GBP", "impact": "High",
     "time_jst": "2026-09-26T01:00:00+09:00"},
]
_au_c23_boe_before = verify_post.Audit()
verify_post.check_c23(_au_c23_boe_before, "明日のBOE総裁講演の内容が注目されます。", "・材料A", [])
check("check_c23: scheduled_events未指定（省略）の場合は従来どおりFAILする（後方互換の確認）",
      _au_c23_boe_before.checks[0]["result"] == "FAIL", str(_au_c23_boe_before.checks[0]))

_au_c23_boe_after = verify_post.Audit()
verify_post.check_c23(_au_c23_boe_after, "明日のBOE総裁講演の内容が注目されます。", "・材料A", [],
                       scheduled_events=_boe_scheduled_events)
check("check_c23: scheduled_eventsにtitleが実在すればPASSする（2026-09-25実例の再現）",
      _au_c23_boe_after.checks[0]["result"] == "PASS", str(_au_c23_boe_after.checks[0]))

_au_c23_boe_other = verify_post.Audit()
verify_post.check_c23(_au_c23_boe_other, "FOMCの結果を受けた反応が注目されます。", "・材料A", [],
                       scheduled_events=_boe_scheduled_events)
check("check_c23: scheduled_eventsに存在しない固有名詞（FOMC）は従来どおりFAILする"
      "（scheduled_eventsが無条件の免罪符にならないことの確認）",
      _au_c23_boe_other.checks[0]["result"] == "FAIL", str(_au_c23_boe_other.checks[0]))

_au_c23_malformed = verify_post.Audit()
verify_post.check_c23(_au_c23_malformed, "明日のBOE総裁講演の内容が注目されます。", "・材料A", [],
                       scheduled_events="not-a-list")
check("check_c23: scheduled_eventsがlist型でない場合は無視して従来どおり動作する（防御的）",
      _au_c23_malformed.checks[0]["result"] == "FAIL", str(_au_c23_malformed.checks[0]))

# run_all()経由の配線確認
_b_c23_boe = json.loads(json.dumps(b_ok))
_b_c23_boe["sections"]["part2_summary"] = "明日のBOE総裁講演の内容が注目されます。"
_b_c23_boe["reusable_for_summary"] = []
_dd_c23_boe = json.loads(json.dumps(DAILY_DATA))
_dd_c23_boe["scheduled_events"] = _boe_scheduled_events
au_c23_boe = verify_post.run_all(_b_c23_boe, _dd_c23_boe)
c23_boe_check = next(x for x in au_c23_boe.checks if x["id"] == "C23_summary_no_new_entities")
check("run_all(): daily_data.scheduled_eventsがC23へ実際に配線されPASSになる",
      c23_boe_check["result"] == "PASS", str(c23_boe_check))

print("=== verify_post: C24 市場のフローの固有名詞バックリファレンス（v1.56・オーナー指示） ===")

_au_c24a = verify_post.Audit()
verify_post.check_c24(_au_c24a, "", "・材料A")
check("check_c24: part2_flowが空文字ならSKIP",
      _au_c24a.checks[0]["result"] == "SKIP", str(_au_c24a.checks[0]))

_au_c24b = verify_post.Audit()
verify_post.check_c24(_au_c24b, "BTC・ETHともに軟調な値動きとなりました。", "・材料A")
check("check_c24: ASCII固有名詞候補が無ければPASS",
      _au_c24b.checks[0]["result"] == "PASS", str(_au_c24b.checks[0]))

# 2026-08-29実データ（土曜）の実例。呼び出しAがtier1裏付け・独立2ソースいずれも
# 無く不採用としreusable_for_summaryへ回した材料（ETF資金流出・Polygon脆弱性）を、
# 呼び出しBがpart2_flowで因果連鎖の材料として使ってしまった実際の事象を再現する。
_au_c24c = verify_post.Audit()
verify_post.check_c24(
    _au_c24c,
    "ビットコインETFが9日連続の資金流入を終えて純流出に転じたとの報道が伝わっており、"
    "Polygonが修正済みハードフォークにおいてDoSなど複数の脆弱性を開示したとの報道があります。",
    "・補足できる検証済み材料は確認できない。")
check("check_c24: part1_pointsに無いASCII固有名詞（2026-08-29実データ再現・Polygon/DoS）はFAIL",
      _au_c24c.checks[0]["result"] == "FAIL", str(_au_c24c.checks[0]))
check("check_c24: FAIL detailにPolygon・DoSが列挙される",
      "Polygon" in _au_c24c.checks[0]["detail"] and "DoS" in _au_c24c.checks[0]["detail"],
      _au_c24c.checks[0]["detail"])

# C23との最重要の違い: reusable_for_summaryに材料があってもC24はpart1_pointsのみを
# 見るため、reusable_for_summary一致では救済されない（引数自体を受け取らない）。
_au_c24d = verify_post.Audit()
verify_post.check_c24(
    _au_c24d, "Bitmineの動向を受けて市場心理が改善したとみられます。", "・材料A")
check("check_c24: part1_pointsに無いASCII固有名詞（Bitmine）はFAIL"
      "（C23と異なりreusable_for_summaryでは救済されない設計）",
      _au_c24d.checks[0]["result"] == "FAIL", str(_au_c24d.checks[0]))

_au_c24e = verify_post.Audit()
verify_post.check_c24(
    _au_c24e, "SECの規則見直しを受けて規制明確化への期待が意識された可能性があります。",
    "・SECが規則見直しを提案（Reuters、2026-08-26）")
check("check_c24: part1_pointsに同一文字列があればPASS",
      _au_c24e.checks[0]["result"] == "PASS", str(_au_c24e.checks[0]))

# 2026-08-26実データの実例（ニュースが無い日のpart2_flow第2文の定型パターン。
# CALL_B_INSTRUCTIONSが明示的に許容する「国内取引所とDEXの出来高動向」の言及で、
# bitFlyer・Coincheck・Baseが誤検知したため専用allowlistへ追加した）。
_au_c24f = verify_post.Audit()
verify_post.check_c24(
    _au_c24f,
    "国内ではbitFlyerとCoincheckを合わせたETH取引が一定の水準で推移しており、"
    "Base上のDEX出来高やTVLも大きな崩れのない値動きとなりました。",
    "・材料A")
check("check_c24: 国内取引所・L2の一般語彙（bitFlyer→Flyer・Coincheck・Base）は誤検知しない"
      "（2026-08-26実データで発見・回帰確認）",
      _au_c24f.checks[0]["result"] == "PASS", str(_au_c24f.checks[0]))

# run_all()経由の配線確認（2026-08-29実データそのままの形を再現）
_b_c24 = json.loads(json.dumps(b_ok))
_b_c24["sections"]["part1_points"] = generate_post.FIXED_POINTS
_b_c24["sections"]["part2_flow"] = (
    "・Polygonが修正済みハードフォークにおいて複数の脆弱性を開示したとの報道が伝わっています。")
_b_c24["reusable_for_summary"] = ["Polygonが脆弱性を修正済みハードフォークで開示したとの報道"]
au_c24 = verify_post.run_all(_b_c24, DAILY_DATA)
c24_check = next(x for x in au_c24.checks if x["id"] == "C24_flow_no_unadopted_material")
check("run_all(): C24はreusable_for_summaryに材料があってもpart1_points未確認ならFAILになる"
      "（2026-08-29実データの実例を再現）",
      c24_check["result"] == "FAIL", str(c24_check))

print("=== verify_post: C18をheadline_for_imageにも適用（v1.79・オーナー承認・"
      "2026-09-24分「米金利上昇でBTC・ETHは軟調推移」がPASSしていた事象への対処） ===")

_au_c18_hfi_none = verify_post.Audit()
verify_post.check_c18(_au_c18_hfi_none, b_ok["sections"], b_ok["llm_section_keys"], set())
check("check_c18: headline_for_image省略時（既定""）は従来どおり動作する（後方互換）",
      _au_c18_hfi_none.checks[0]["result"] == "PASS", str(_au_c18_hfi_none.checks[0]))

_au_c18_hfi_bad = verify_post.Audit()
verify_post.check_c18(
    _au_c18_hfi_bad, b_ok["sections"], b_ok["llm_section_keys"], set(),
    headline_for_image="米金利上昇を受けてBTCが急落した")
check("check_c18: headline_for_imageに因果マーカー＋価格変動語（限定表現なし）があればFAILする"
      "（sections自体は正常でもheadline_for_image側の違反を拾う）",
      _au_c18_hfi_bad.checks[0]["result"] == "FAIL", str(_au_c18_hfi_bad.checks[0]))

_au_c18_hfi_hedged = verify_post.Audit()
verify_post.check_c18(
    _au_c18_hfi_hedged, b_ok["sections"], b_ok["llm_section_keys"], set(),
    headline_for_image="米金利上昇を受けてBTCが急落した可能性")
check("check_c18: headline_for_imageに限定表現があればPASS（既存ロジックと同じ基準）",
      _au_c18_hfi_hedged.checks[0]["result"] == "PASS", str(_au_c18_hfi_hedged.checks[0]))

_c18_hfi_violations = verify_post._find_c18_violations(
    b_ok["sections"], b_ok["llm_section_keys"], set(), headline_for_image="米金利上昇を受けてBTCが急落した")
check("_find_c18_violations: headline_for_image由来の違反はsection=\"headline_for_image\"で帰属される"
      "（repair_post.pyの局所修正対象特定と同じ形式）",
      len(_c18_hfi_violations) == 1 and _c18_hfi_violations[0]["section"] == "headline_for_image",
      str(_c18_hfi_violations))

# run_all()経由の配線確認
_b_c18_hfi = json.loads(json.dumps(b_ok))
_b_c18_hfi["headline_for_image"] = "米金利上昇を受けてBTCが急落した"
au_c18_hfi = verify_post.run_all(_b_c18_hfi, DAILY_DATA)
c18_hfi_check = next(x for x in au_c18_hfi.checks if x["id"] == "C18_causal_assertion")
check("run_all(): headline_for_imageの断定表現がC18としてFAILに反映される",
      c18_hfi_check["result"] == "FAIL", str(c18_hfi_check))
check("run_all(): 2026-09-24分の実例そのもの「米金利上昇でBTC・ETHは軟調推移」は、"
      "既存のCAUSAL_MARKERS（により/を受けて/が原因で等）に「単純な『で』」が含まれないため、"
      "本拡張後もPASSのままである（既知の限界。CAUSAL_MARKERSの拡張は別途承認が必要——"
      "「で」は日本語の大半の文に現れる助詞であり、全セクションへの影響が大きすぎるため）",
      verify_post._causal_violations_in_sentence("米金利上昇でBTC・ETHは軟調推移") == [])

print("=== verify_post: C26 市場のフローの役割分離（v1.79・オーナー承認・"
      "統合運用基準§3.1「記載しない内容」の機械監査） ===")

_au_c26a = verify_post.Audit()
verify_post.check_c26(_au_c26a, "")
check("check_c26: part2_flowが空文字ならSKIP", _au_c26a.checks[0]["result"] == "SKIP", str(_au_c26a.checks[0]))

_au_c26b = verify_post.Audit()
verify_post.check_c26(_au_c26b, generate_post.FIXED_FLOW)
check("check_c26: 縮退時の固定文言（FIXED_FLOW）はSKIP", _au_c26b.checks[0]["result"] == "SKIP",
      str(_au_c26b.checks[0]))

_au_c26c = verify_post.Audit()
verify_post.check_c26(_au_c26c, CALL_B_DATA["part2_flow"][0])
check("check_c26: 既存フィクスチャ（CALL_B_DATA）の市場のフローはPASS",
      _au_c26c.checks[0]["result"] == "PASS", str(_au_c26c.checks[0]))

for _bad_text, _label in [
    ("LP流動性の状況を踏まえると、市場のフローは堅調でした。", "英字LP（単語境界）"),
    ("Base上のAPRの動向が意識された可能性があります。", "英字APR"),
    ("DEXの出来高が増加し値動きに反映された可能性があります。", "英字DEX"),
    ("Fear & Greedが強気圏で推移したことが意識された可能性があります。", "英字Fear & Greed"),
    ("市場のGreedが強まったことが意識された可能性があります。", "英字Greed"),
    ("投資家心理の強欲さが値動きに影響した可能性があります。", "日本語:強欲"),
    ("市場の恐怖心理が高まったことが意識された可能性があります。", "日本語:恐怖"),
    ("分散型取引所の出来高増加が意識された可能性があります。", "日本語:分散型取引所"),
    ("年率換算の利回りが上昇したことが意識された可能性があります。", "日本語:年率換算"),
    ("流動性提供の増加が意識された可能性があります。", "日本語:流動性提供"),
    ("LPプールの状況が値動きに影響した可能性があります。", "日本語:LPプール"),
    ("参考APRの上昇が意識された可能性があります。", "日本語:参考APR"),
]:
    _au = verify_post.Audit()
    verify_post.check_c26(_au, _bad_text)
    check(f"check_c26: 記載しない語句（{_label}）を含む市場のフローはFAILする",
          _au.checks[0]["result"] == "FAIL", f"{_label}: {_au.checks[0]}")

_au_c26_yield = verify_post.Audit()
verify_post.check_c26(_au_c26_yield, "米国債利回りの上昇が意識された可能性があります。")
check("check_c26: 「利回り」単独は対象外（「米国債利回り」は正当な記述のため誤検知しない・オーナー指示）",
      _au_c26_yield.checks[0]["result"] == "PASS", str(_au_c26_yield.checks[0]))

_au_c26_boundary = verify_post.Audit()
verify_post.check_c26(_au_c26_boundary, "APRILの決算発表が意識された可能性があります。")
check("check_c26: 単語境界つき判定により「APR」が「APRIL」の部分一致として誤検知しない",
      _au_c26_boundary.checks[0]["result"] == "PASS", str(_au_c26_boundary.checks[0]))

_au_c26_jp_boundary = verify_post.Audit()
verify_post.check_c26(_au_c26_jp_boundary, "LP流動性の状況が値動きに影響した可能性があります。")
check("check_c26: 英字と日本語が空白なしで連結する実際の生成パターン（例:「LP流動性」）でも正しく検知する"
      "（\\bだと日本語をwordとみなすため一致しない実装上の落とし穴に注意。lookaround方式で対処）",
      _au_c26_jp_boundary.checks[0]["result"] == "FAIL", str(_au_c26_jp_boundary.checks[0]))

print("=== verify_post: C27 総括の役割分離（価格表記・文数超過。v1.79・オーナー承認） ===")

_au_c27a = verify_post.Audit()
verify_post.check_c27(_au_c27a, "")
check("check_c27: part2_summaryが空文字ならSKIP", _au_c27a.checks[0]["result"] == "SKIP", str(_au_c27a.checks[0]))

_au_c27b = verify_post.Audit()
verify_post.check_c27(_au_c27b, generate_post.SUMMARY_BLANK_NOTE)
check("check_c27: 縮退時の固定文言（SUMMARY_BLANK_NOTE）はSKIP"
      "（この定型文は「。」区切りで3文相当になるが、人が補う前提の定型文であり対象外）",
      _au_c27b.checks[0]["result"] == "SKIP", str(_au_c27b.checks[0]))

_au_c27c = verify_post.Audit()
verify_post.check_c27(_au_c27c, CALL_B_DATA["part2_summary"])
check("check_c27: 既存フィクスチャ（CALL_B_DATA）の総括はPASS（2文・価格表記なし・禁止語句なし）",
      _au_c27c.checks[0]["result"] == "PASS", str(_au_c27c.checks[0]))

_au_c27d = verify_post.Audit()
verify_post.check_c27(_au_c27d, "地合いは総じて改善。BTCは$64,247まで上昇。継続的な確認が必要。")
check("check_c27: 価格表記（$＋数値）が混入した総括はFAILする",
      _au_c27d.checks[0]["result"] == "FAIL" and "$64,247" in _au_c27d.checks[0]["detail"],
      str(_au_c27d.checks[0]))

_au_c27e = verify_post.Audit()
verify_post.check_c27(_au_c27e, "円建てではETHは¥30.3万円まで上昇。地合いは改善。")
check("check_c27: 価格表記（¥＋数値）が混入した総括もFAILする",
      _au_c27e.checks[0]["result"] == "FAIL", str(_au_c27e.checks[0]))

_au_c27f = verify_post.Audit()
verify_post.check_c27(_au_c27f, "地合いは改善。不確実性は残る。明日も注視が必要。")
check("check_c27: 「。」区切りで3文以上（価格表記・禁止語句なし）はFAILする（文数超過ルール）",
      _au_c27f.checks[0]["result"] == "FAIL" and "3文" in _au_c27f.checks[0]["detail"],
      str(_au_c27f.checks[0]))

_au_c27g = verify_post.Audit()
verify_post.check_c27(_au_c27g, "地合いは改善したが、不確実性は残る。")
check("check_c27: 読点で区切られた1文（。は1個のみ）は文数超過にならずPASS",
      _au_c27g.checks[0]["result"] == "PASS", str(_au_c27g.checks[0]))

_au_c27h = verify_post.Audit()
verify_post.check_c27(_au_c27h, "Fear & Greedの改善が意識された可能性があります。")
check("check_c27: C26と同じ語句一覧（Fear & Greed等）を総括にも適用する",
      _au_c27h.checks[0]["result"] == "FAIL", str(_au_c27h.checks[0]))

print("=== verify_post: C28 ヘッドライン・主要なポイントの役割分離（v1.79・オーナー承認） ===")

_au_c28a = verify_post.Audit()
verify_post.check_c28(_au_c28a, "", "", DAILY_DATA)
check("check_c28: ヘッドライン・主要なポイントともに空文字ならSKIP",
      _au_c28a.checks[0]["result"] == "SKIP", str(_au_c28a.checks[0]))

_au_c28b = verify_post.Audit()
verify_post.check_c28(_au_c28b, CALL_A_DATA["part1_headline"],
                       "\n".join(f"・{p}" for p in CALL_A_DATA["part1_points"]), DAILY_DATA)
check("check_c28: 既存フィクスチャ（CALL_A_DATA）のヘッドライン・主要なポイントはPASS",
      _au_c28b.checks[0]["result"] == "PASS", str(_au_c28b.checks[0]))

_au_c28c = verify_post.Audit()
verify_post.check_c28(_au_c28c, "米規制当局の発言を受けて24時間比で上昇しました。", "・材料A", DAILY_DATA)
check("check_c28: ヘッドラインに「24時間比」の文字列があればFAILする",
      _au_c28c.checks[0]["result"] == "FAIL" and "24時間比" in _au_c28c.checks[0]["detail"],
      str(_au_c28c.checks[0]))

_au_c28d = verify_post.Audit()
verify_post.check_c28(_au_c28d, "米規制当局の発言が確認されました。", f"・BTCは{DAILY_DATA['assets'][0]['usd']}まで上昇", DAILY_DATA)
check("check_c28: 主要なポイントにdaily_data.jsonの実際の表示値（BTCのusd）が再掲されるとFAILする",
      _au_c28d.checks[0]["result"] == "FAIL" and DAILY_DATA["assets"][0]["usd"] in _au_c28d.checks[0]["detail"],
      str(_au_c28d.checks[0]))

_au_c28e = verify_post.Audit()
verify_post.check_c28(
    _au_c28e, f"Fear & Greed指数は{DAILY_DATA['market']['fear_greed']['value']}を記録しました。", "・材料A", DAILY_DATA)
check("check_c28: ヘッドラインにFear & Greedの実際の値が再掲されるとFAILする",
      _au_c28e.checks[0]["result"] == "FAIL", str(_au_c28e.checks[0]))

_au_c28f = verify_post.Audit()
verify_post.check_c28(_au_c28f, "Fear & Greed指数の動向が注目されています。", "・材料A", DAILY_DATA)
check("check_c28: ヘッドラインにC26と同じ語句一覧（Fear & Greed）があればFAILする",
      _au_c28f.checks[0]["result"] == "FAIL", str(_au_c28f.checks[0]))

_au_c28g = verify_post.Audit()
verify_post.check_c28(_au_c28g, "米規制当局の発言が確認されました。",
                       "・LPプールの動向が注目されています。", DAILY_DATA)
check("check_c28: 主要なポイントはC26と同じ語句一覧の対象外（ヘッドラインのみに適用。オーナー指示）",
      _au_c28g.checks[0]["result"] == "PASS", str(_au_c28g.checks[0]))

_au_c28h = verify_post.Audit()
verify_post.check_c28(
    _au_c28h, "取引所ハッキングにより3億8,750万ドル相当の被害が確認されました。", "・材料A", DAILY_DATA)
check("check_c28: ニュース中の正当な金額表記（取引所被害額等）はdaily_data.jsonの表示値と一致しないため"
      "誤検知しない（「$・¥＋数値」の一律判定にしなかった理由そのものの確認・オーナー指示）",
      _au_c28h.checks[0]["result"] == "PASS", str(_au_c28h.checks[0]))

# run_all()経由の配線確認
_b_c26 = json.loads(json.dumps(b_ok))
_b_c26["sections"]["part2_flow"] = "APRの動向が意識された可能性があります。"
au_c26_wired = verify_post.run_all(_b_c26, DAILY_DATA)
c26_check_wired = next(x for x in au_c26_wired.checks if x["id"] == "C26_flow_role_separation")
check("run_all(): C26が実際に配線されFAILを返す", c26_check_wired["result"] == "FAIL", str(c26_check_wired))

_b_c27 = json.loads(json.dumps(b_ok))
_b_c27["sections"]["part2_summary"] = f"BTCは{DAILY_DATA['assets'][0]['usd']}まで上昇。地合いは改善。"
au_c27_wired = verify_post.run_all(_b_c27, DAILY_DATA)
c27_check_wired = next(x for x in au_c27_wired.checks if x["id"] == "C27_summary_role_separation")
check("run_all(): C27が実際に配線されFAILを返す", c27_check_wired["result"] == "FAIL", str(c27_check_wired))

_b_c28 = json.loads(json.dumps(b_ok))
_b_c28["sections"]["part1_headline"] = "米規制当局の発言を受けて24時間比で上昇しました。"
au_c28_wired = verify_post.run_all(_b_c28, DAILY_DATA)
c28_check_wired = next(x for x in au_c28_wired.checks if x["id"] == "C28_headline_points_role_separation")
check("run_all(): C28が実際に配線されFAILを返す", c28_check_wired["result"] == "FAIL", str(c28_check_wired))

print("=== verify_post: C23/C24 ISO4217通貨コードのallowlist追加（v1.62・オーナー指示） ===")

# 9/2実データの実例（['CAD', 'NZD']誤検知の再現・回帰確認）。v1.53の
# scheduled_events導入以降、経済カレンダー由来で通貨コードが本文に出やすく
# なり、v1.56（Base/Coincheck/Flyer）・v1.57（Base/DeFi）に続く3回目の
# 同種誤検知だった。個別追加ではなくISO4217全体を基底allowlistへ登録する
# 構造対応で解消することを確認する。
_au_c23_iso = verify_post.Audit()
verify_post.check_c23(
    _au_c23_iso, "対ドルでCADとNZDがともに下落し、コモディティ通貨全般が弱含みました。",
    "・材料A", [])
check("check_c23: ISO4217通貨コード（CAD・NZD）は誤検知しない（9/2実データで発見・回帰確認）",
      _au_c23_iso.checks[0]["result"] == "PASS", str(_au_c23_iso.checks[0]))

_au_c24_iso = verify_post.Audit()
verify_post.check_c24(
    _au_c24_iso, "為替市場ではCADとNZDが対ドルで軟調に推移しています。", "・材料A")
check("check_c24: ISO4217通貨コード（CAD・NZD）は誤検知しない（C24側でも回帰確認）",
      _au_c24_iso.checks[0]["result"] == "PASS", str(_au_c24_iso.checks[0]))

# 主要通貨に限らず、マイナー通貨コードも含めてISO4217全体が対象であることを
# 確認する（オーナー指示：scheduled_eventsには想定外の国が現れ得るため）。
check("_ISO4217_CURRENCY_CODES: 主要通貨（USD/EUR/JPY/GBP/AUD/CAD/CHF/NZD）を含む",
      {"USD", "EUR", "JPY", "GBP", "AUD", "CAD", "CHF", "NZD"} <= verify_post._ISO4217_CURRENCY_CODES,
      str(sorted(verify_post._ISO4217_CURRENCY_CODES)[:10]))
check("_ISO4217_CURRENCY_CODES: マイナー通貨コード（例: ZAR南ア・THB タイ・MXN メキシコ）も含む",
      {"ZAR", "THB", "MXN"} <= verify_post._ISO4217_CURRENCY_CODES,
      str(sorted(verify_post._ISO4217_CURRENCY_CODES)))
check("_PROPER_NOUN_ALLOWLIST: ISO4217コード全体を包含する（C23基底）",
      verify_post._ISO4217_CURRENCY_CODES <= verify_post._PROPER_NOUN_ALLOWLIST,
      "ISO4217コードが基底allowlistに欠けている")
check("_PROPER_NOUN_ALLOWLIST_C24: ISO4217コード全体を包含する（C24もC23基底を継承）",
      verify_post._ISO4217_CURRENCY_CODES <= verify_post._PROPER_NOUN_ALLOWLIST_C24,
      "ISO4217コードがC24側allowlistに欠けている")

# ISO4217コードに実在しないASCII固有名詞は引き続きFAILとして検知されることを
# 確認する（通貨コード追加によって検知精度そのものが損なわれていないか）。
_au_c23_stillfail = verify_post.Audit()
verify_post.check_c23(
    _au_c23_stillfail, "Bitmineの動向が総括で新たに持ち出されています。", "・材料A", [])
check("check_c23: ISO4217追加後もpart1_points未確認の非通貨固有名詞（Bitmine）は引き続きFAILする",
      _au_c23_stillfail.checks[0]["result"] == "FAIL", str(_au_c23_stillfail.checks[0]))

print("=== collect_news.py（RSS方式・CryptoPanic撤去後） ===")

# v1.38: 対象日=2026-08-17のウィンドウは [2026-08-16T21:00:00Z, 2026-08-17T21:00:00Z)
# （8月は夏時間・NY 17:00=UTC-4）。
#   item a: ウィンドウ内（旧JST暦日基準でも対象日=8/17・挙動不変の基準ケース）
#   item b: ウィンドウ内（新規に含まれるようになったケース——旧JST暦日基準では
#           JST換算が8/18 05:00になり翌日扱いで除外されていた。米国日中の
#           発表が翌JST暦日へ流れる問題そのものの再現）
#   item c: ウィンドウ外・start未満（新たに除外されるようになったケース——
#           旧JST暦日基準ではJST換算が8/17 01:00で対象日扱いされていたが、
#           実際にはNY時間で見ると前日の日中であり、正しくは前日分の材料）
#   item d: ウィンドウ外・明確に前日以前
RSS_TODAY_ONLY = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>a: well within window</title><link>https://example.gov/a</link><pubDate>Mon, 17 Aug 2026 10:00:00 GMT</pubDate></item>
<item><title>b: newly included (late US hours, used to roll to next JST day)</title><link>https://example.gov/b</link><pubDate>Mon, 17 Aug 2026 20:00:00 GMT</pubDate></item>
<item><title>c: newly excluded (early JST morning, actually prior NY day)</title><link>https://example.gov/c</link><pubDate>Sun, 16 Aug 2026 16:00:00 GMT</pubDate></item>
<item><title>d: clearly before window</title><link>https://example.gov/d</link><pubDate>Sat, 15 Aug 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""

RSS_WITH_SUMMARY = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Item with summary</title><link>https://example.gov/d</link><pubDate>Mon, 17 Aug 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;Some &lt;b&gt;detail&lt;/b&gt; text.&lt;/p&gt;</description></item>
</channel></rss>"""


class _FakeRssResp:
    def __init__(self, status_code, content: bytes):
        self.status_code = status_code
        self.content = content

    @property
    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self):
        # v1.53: fetch_economic_calendar()のJSONレスポンス検証用に追加
        # （既存のRSS/XML用途には影響しない・呼ばれなければ使われないだけ）。
        return json.loads(self.content.decode("utf-8"))


def _patch_requests_get(fn):
    orig = collect_news.requests.get
    collect_news.requests.get = fn
    return orig


print("=== collect_news.py: collection_window_ny（v1.38・オーナー指示） ===")
_ws_summer, _we_summer = collect_news.collection_window_ny(_date(2026, 8, 17))
check("collection_window_ny: 夏時間はNY 17:00=UTC-4",
      _we_summer.utcoffset() == _timedelta(hours=-4) and _ws_summer.utcoffset() == _timedelta(hours=-4),
      f"we_off={_we_summer.utcoffset()} ws_off={_ws_summer.utcoffset()}")
check("collection_window_ny: window_endは対象日のNY 17:00",
      (_we_summer.year, _we_summer.month, _we_summer.day, _we_summer.hour, _we_summer.minute) == (2026, 8, 17, 17, 0))
check("collection_window_ny: window_startは対象日前日のNY 17:00",
      (_ws_summer.year, _ws_summer.month, _ws_summer.day, _ws_summer.hour, _ws_summer.minute) == (2026, 8, 16, 17, 0))

_ws_winter, _we_winter = collect_news.collection_window_ny(_date(2026, 1, 17))
check("collection_window_ny: 冬時間はNY 17:00=UTC-5（時刻をハードコードせずzoneinfoで自動判定）",
      _we_winter.utcoffset() == _timedelta(hours=-5) and _ws_winter.utcoffset() == _timedelta(hours=-5),
      f"we_off={_we_winter.utcoffset()} ws_off={_ws_winter.utcoffset()}")

# DST切替日の真の経過時間はwindow_end - window_startを直接引き算すると求まらない
# （同一tzinfoオブジェクト同士の引き算はPythonが素の日時フィールドで計算し、
# 常に24時間ちょうどを返す落とし穴——collection_window_ny()のdocstring参照）。
# UTCへ変換してから引き算することで真の経過時間を確認する。
_ws_spring, _we_spring = collect_news.collection_window_ny(_date(2026, 3, 8))  # 2026年の夏時間開始日
_span_spring_h = (_we_spring.astimezone(_timezone.utc) - _ws_spring.astimezone(_timezone.utc)).total_seconds() / 3600
check("collection_window_ny: 夏時間切替日（3/8）はUTC変換後の真の経過時間が23時間",
      _span_spring_h == 23.0, f"span={_span_spring_h}")
check("collection_window_ny: 夏時間切替日でも同一tzinfo同士の直接引き算は24時間を返す（Pythonの仕様・落とし穴の実演）",
      (_we_spring - _ws_spring).total_seconds() / 3600 == 24.0)

_ws_fall, _we_fall = collect_news.collection_window_ny(_date(2026, 11, 1))  # 2026年の冬時間開始日
_span_fall_h = (_we_fall.astimezone(_timezone.utc) - _ws_fall.astimezone(_timezone.utc)).total_seconds() / 3600
check("collection_window_ny: 冬時間切替日（11/1）はUTC変換後の真の経過時間が25時間",
      _span_fall_h == 25.0, f"span={_span_fall_h}")

# 実際のフィルタ処理（_collect_from_feed）で使うpub_dtはJST固定オフセット
# （collection_window_nyのNY_TZとは別のtzinfoオブジェクト）のため、上記の
# 「同一tzinfo引き算」の落とし穴の影響を受けず、DST切替日でも境界判定が
# 正しく機能することを実データに近い形で確認する。
_JST = _timezone(_timedelta(hours=9))
_edge_included = _datetime(2026, 3, 9, 5, 59, 59, tzinfo=_JST)   # window_endの1秒前
_edge_excluded = _datetime(2026, 3, 9, 6, 0, 0, tzinfo=_JST)     # window_endちょうど（半開区間なので含まない）
check("collection_window_ny: DST切替日でもwindow_end直前は正しく含まれる（同一tzinfoの落とし穴が実フィルタに波及しないことの確認）",
      _ws_spring <= _edge_included < _we_spring)
check("collection_window_ny: DST切替日でもwindow_endちょうどは正しく除外される（半開区間）",
      not (_ws_spring <= _edge_excluded < _we_spring))

print("=== collect_news.py: fetch_economic_calendar（v1.53・オーナー指示） ===")
_ff_ws, _ff_we = collect_news.collection_window_ny(_date(2026, 8, 28))


def _ff_event(title, country, impact, dt_iso):
    return {"title": title, "country": country, "impact": impact, "date": dt_iso,
            "forecast": "", "previous": ""}


_FF_EVENTS = [
    _ff_event("Fed Chairman Warsh Speaks", "USD", "High", "2026-08-28T10:00:00-04:00"),  # 窓内・High・採用
    _ff_event("Jackson Hole Symposium", "All", "High", "2026-08-28T12:15:00-04:00"),  # 窓内・High・All国・採用
    _ff_event("Core PCE Price Index m/m", "USD", "Medium", "2026-08-28T08:30:00-04:00"),  # 窓内だがMedium・除外
    _ff_event("Some Low Impact Data", "USD", "Low", "2026-08-28T09:00:00-04:00"),  # 窓内だがLow・除外
    _ff_event("SEK-only High Event", "SEK", "High", "2026-08-28T09:00:00-04:00"),  # 窓内・Highだが対象通貨外・除外
    _ff_event("Outside Window Before", "USD", "High", "2026-08-26T10:00:00-04:00"),  # 窓外（前）・除外
    _ff_event("Outside Window After", "USD", "High", "2026-08-29T10:00:00-04:00"),  # 窓外（後）・除外
]
orig_get_ff = _patch_requests_get(
    lambda url, **kw: _FakeRssResp(200, json.dumps(_FF_EVENTS).encode("utf-8")))
_ff_result = collect_news.fetch_economic_calendar(_ff_ws, _ff_we)
collect_news.requests.get = orig_get_ff
check("fetch_economic_calendar: 窓内・High・対象通貨のイベントのみ採用される（2件）",
      len(_ff_result) == 2, str(_ff_result))
check("fetch_economic_calendar: country=='All'のイベントも採用される（EA-Risk-Monitor元実装との差分・オーナー承認）",
      any(e["title"] == "Jackson Hole Symposium" for e in _ff_result), str(_ff_result))
check("fetch_economic_calendar: Medium/Lowインパクトは除外される",
      not any(e["title"] in ("Core PCE Price Index m/m", "Some Low Impact Data") for e in _ff_result),
      str(_ff_result))
check("fetch_economic_calendar: 対象通貨外（SEK）は除外される",
      not any(e["title"] == "SEK-only High Event" for e in _ff_result), str(_ff_result))
check("fetch_economic_calendar: 窓外（前後とも）のイベントは除外される",
      not any(e["title"] in ("Outside Window Before", "Outside Window After") for e in _ff_result),
      str(_ff_result))
check("fetch_economic_calendar: 時刻順（昇順）で返される",
      [e["title"] for e in _ff_result] == ["Fed Chairman Warsh Speaks", "Jackson Hole Symposium"],
      [e["title"] for e in _ff_result])
check("fetch_economic_calendar: time_jstがJSTへ変換されている（14:00 EDT=23:00 JST）",
      "23:00:00" in _ff_result[0]["time_jst"], _ff_result[0]["time_jst"])

# 境界値: window_endちょうど（半開区間なので除外）・window_startちょうど（含む）
_ff_boundary_events = [
    _ff_event("At window_end exactly", "USD", "High", _ff_we.isoformat()),
    _ff_event("At window_start exactly", "USD", "High", _ff_ws.isoformat()),
]
orig_get_ffb = _patch_requests_get(
    lambda url, **kw: _FakeRssResp(200, json.dumps(_ff_boundary_events).encode("utf-8")))
_ff_boundary_result = collect_news.fetch_economic_calendar(_ff_ws, _ff_we)
collect_news.requests.get = orig_get_ffb
check("fetch_economic_calendar: window_endちょうどは除外・window_startちょうどは含む（半開区間、他の窓判定と同じ扱い）",
      [e["title"] for e in _ff_boundary_result] == ["At window_start exactly"], str(_ff_boundary_result))

# フェイルオープン確認: 非200・JSON不正・空リストのいずれも例外を送出せず空リストを返す
orig_get_ff404 = _patch_requests_get(lambda url, **kw: _FakeRssResp(404, b""))
check("fetch_economic_calendar: HTTP非200は例外を送出せず空リストを返す（フェイルオープン）",
      collect_news.fetch_economic_calendar(_ff_ws, _ff_we) == [])
collect_news.requests.get = orig_get_ff404

orig_get_ffbad = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, b"not valid json {{{"))
check("fetch_economic_calendar: JSON不正は例外を送出せず空リストを返す（フェイルオープン）",
      collect_news.fetch_economic_calendar(_ff_ws, _ff_we) == [])
collect_news.requests.get = orig_get_ffbad

orig_get_ffempty = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, b"[]"))
check("fetch_economic_calendar: 空配列レスポンスは空リストを返す（0件は正常系・停止しない）",
      collect_news.fetch_economic_calendar(_ff_ws, _ff_we) == [])
collect_news.requests.get = orig_get_ffempty

print("=== generate_post.py: SCHEDULED_EVENTS_GUIDANCE（v1.53・オーナー指示） ===")
check("SCHEDULED_EVENTS_GUIDANCEがオーナー指定の文言を含む",
      "「探すべき材料」のヒントであり" in generate_post.SCHEDULED_EVENTS_GUIDANCE
      and "それ自体を材料として本文に" in generate_post.SCHEDULED_EVENTS_GUIDANCE
      and "予定はあったが候補が無い場合は、その旨を書かず" in generate_post.SCHEDULED_EVENTS_GUIDANCE)
check("SYSTEM_AにSCHEDULED_EVENTS_GUIDANCEが含まれる",
      "daily_data.scheduled_events" in generate_post.SYSTEM_A)

check("parse_pubdate_jst: タイムゾーン情報を持たないpubDateはNone（フェイルクローズ・v1.38オーナー指示）",
      collect_news.parse_pubdate_jst("Mon, 17 Aug 2026 10:00:00") is None)
check("parse_pubdate_jst: タイムゾーン付きは従来どおり解析できる（回帰確認）",
      collect_news.parse_pubdate_jst("Mon, 17 Aug 2026 10:00:00 GMT") is not None)

RSS_NO_TZ = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>e: no timezone info (fail-closed, excluded)</title><link>https://example.gov/e</link><pubDate>Mon, 17 Aug 2026 10:00:00</pubDate></item>
</channel></rss>"""
orig_get_notz = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_NO_TZ.encode("utf-8")))
st_notz, kept_notz = collect_news._collect_from_feed("TESTNOTZ", "https://example.gov/notz.rss",
                                                       *collect_news.collection_window_ny(_date(2026, 8, 17)),
                                                       tier=1, kind="official")
collect_news.requests.get = orig_get_notz
check("_collect_from_feed: タイムゾーン不明なpubDateは窓の内外を問わず除外される（フェイルクローズ）",
      st_notz["status"] == "ok" and st_notz["raw_count"] == 1 and st_notz["kept_count"] == 0 and kept_notz == [],
      f"{st_notz} kept={kept_notz}")

# 1) 正常フィード: 対象日フィルタが機能する（NY 17:00基準ウィンドウでの境界ケース込み）
orig_get = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_TODAY_ONLY.encode("utf-8")))
status, cands, detail = collect_news.fetch_rss("https://example.gov/feed.rss")
collect_news.requests.get = orig_get
check("fetch_rss: 正常時はok・4件取得", status == "ok" and len(cands) == 4, f"{status} {len(cands)}")

_window_1707 = collect_news.collection_window_ny(_date(2026, 8, 17))
orig_get2 = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_TODAY_ONLY.encode("utf-8")))
st, kept = collect_news._collect_from_feed("TESTGOV", "https://example.gov/feed.rss",
                                            *_window_1707, tier=1, kind="official")
collect_news.requests.get = orig_get2
check("_collect_from_feed: NY 17:00基準ウィンドウで2件（a・b）のみ残る（cは新たに除外・dは変わらず除外）",
      st["status"] == "ok" and st["raw_count"] == 4 and st["kept_count"] == 2 and len(kept) == 2,
      f"{st} kept={kept}")
check("_collect_from_feed: 新たに含まれるようになった項目bを含む（旧JST暦日基準では翌日扱いで除外されていた）",
      any(c["url"] == "https://example.gov/b" for c in kept), str(kept))
check("_collect_from_feed: tier/kindが付与される", all(c["tier"] == 1 and c["kind"] == "official" for c in kept))

# 2) 404フィード: 単体はfailedだが例外にならない
origf = _patch_requests_get(lambda url, **kw: _FakeRssResp(404, b""))
status, cands, detail = collect_news.fetch_rss("https://example.gov/broken.rss")
collect_news.requests.get = origf
check("fetch_rss: 404はfailed・詳細にHTTPコードを含む", status == "failed" and "404" in detail, f"{status} {detail}")

# 3) 不正XML: クラッシュせずfailedに縮退
origx = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, b"not xml at all <<<"))
status, cands, detail = collect_news.fetch_rss("https://example.gov/malformed.rss")
collect_news.requests.get = origx
check("fetch_rss: 不正XMLはfailedに縮退（例外を伝播しない）", status == "failed", f"{status} {detail}")

# 4) 複数フィードの独立性: 1件404でも他は生き残り、collect_news()全体は例外なく完了する
_sources_backup = collect_news._load_sources
def _fake_sources():
    return [{"name": "GOOD", "url": "https://example.gov/good.rss"},
            {"name": "BAD", "url": "https://example.gov/bad.rss"}]
collect_news._load_sources = _fake_sources

def _multi_get(url, **kw):
    if "good" in url:
        return _FakeRssResp(200, RSS_TODAY_ONLY.encode("utf-8"))
    return _FakeRssResp(404, b"")

origm = _patch_requests_get(_multi_get)
result = collect_news.collect_news("2026-08-17")
collect_news.requests.get = origm
collect_news._load_sources = _sources_backup

check("collect_news(): 1フィード404でも例外を伝播せず完了", isinstance(result, dict))
check("collect_news(): 生存フィードの候補は保持される", result["source_status"]["GOOD"]["status"] == "ok"
      and result["source_status"]["GOOD"]["kept_count"] == 2)
check("collect_news(): 失敗フィードもsource_statusに記録される", result["source_status"]["BAD"]["status"] == "failed")
check("collect_news(): Google News(任意層)もsource_statusに含まれる",
      "Google News (Reuters検索)" in result["source_status"])

# 5) 情報源設定が空/存在しない日でもクラッシュしない（1件も候補が無い日は正常）
collect_news._load_sources = lambda: []
orig_none = _patch_requests_get(lambda url, **kw: _FakeRssResp(404, b""))
result0 = collect_news.collect_news("2026-08-17")
collect_news.requests.get = orig_none
collect_news._load_sources = _sources_backup
check("collect_news(): 情報源ゼロでも候補ゼロで正常終了", result0["candidates"] == []
      and "Google News (Reuters検索)" in result0["source_status"])

# 6) summary抽出（v1.15・task#18）: descriptionからHTMLタグ除去・空白正規化・呼び出しAへの伝播経路
check("_clean_summary: HTMLタグ除去と空白正規化",
      collect_news._clean_summary("<p>Hello   <b>world</b></p>\n\n") == "Hello world",
      collect_news._clean_summary("<p>Hello   <b>world</b></p>\n\n"))
long_summary = collect_news._clean_summary("x" * 600)
check("_clean_summary: 上限長で省略記号付き切り詰め",
      len(long_summary) == collect_news.SUMMARY_MAX_LEN + 1 and long_summary.endswith("…"),
      f"len={len(long_summary)}")

orig_get3 = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_WITH_SUMMARY.encode("utf-8")))
status, cands, detail = collect_news.fetch_rss("https://example.gov/summary.rss")
collect_news.requests.get = orig_get3
check("fetch_rss: descriptionからsummaryを抽出しHTMLタグを除去する",
      status == "ok" and cands[0]["summary"] == "Some detail text.", f"{status} {cands}")

orig_get4 = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_WITH_SUMMARY.encode("utf-8")))
st2, kept2 = collect_news._collect_from_feed("TESTGOV2", "https://example.gov/summary.rss",
                                              *_window_1707, tier=1, kind="official")
collect_news.requests.get = orig_get4
check("_collect_from_feed: candidateにsummaryが含まれる（呼び出しAの根拠として渡る）",
      len(kept2) == 1 and kept2[0]["summary"] == "Some detail text.", str(kept2))

print("=== collect_news.py: <source>要素のパース・tier4→tier2昇格（v1.59・オーナー承認） ===")

RSS_WITH_SOURCE_TAG = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Reuters item via Google News</title>
<link>https://news.google.com/rss/articles/FAKE123</link>
<pubDate>Mon, 17 Aug 2026 10:00:00 GMT</pubDate>
<source url="https://www.reuters.com">Reuters</source></item>
</channel></rss>"""

orig_get_src = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_WITH_SOURCE_TAG.encode("utf-8")))
status_src, cands_src, detail_src = collect_news.fetch_rss("https://news.google.com/fake")
collect_news.requests.get = orig_get_src
check("fetch_rss: <source>要素のtext・url属性をsource_name/source_urlとして抽出する",
      status_src == "ok" and cands_src[0]["source_name"] == "Reuters"
      and cands_src[0]["source_url"] == "https://www.reuters.com", f"{status_src} {cands_src}")

orig_get_nosrc = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_TODAY_ONLY.encode("utf-8")))
status_nosrc, cands_nosrc, detail_nosrc = collect_news.fetch_rss("https://example.gov/feed.rss")
collect_news.requests.get = orig_get_nosrc
check("fetch_rss: <source>要素が無いフィード（通常のtier1等）はsource_name/source_urlが空文字になる（実害なし）",
      all(c["source_name"] == "" and c["source_url"] == "" for c in cands_nosrc), str(cands_nosrc))

check("_is_reuters_source: source_name='Reuters'を実体Reutersと判定する",
      collect_news._is_reuters_source({"source_name": "Reuters", "source_url": "https://www.reuters.com"}))
check("_is_reuters_source: source_urlのみでもreuters.comを含めば実体Reutersと判定する",
      collect_news._is_reuters_source({"source_name": "", "source_url": "https://www.reuters.com/world"}))
check("_is_reuters_source: Reuters以外のsourceは実体Reutersと判定しない（site:reuters.com検索への混入への防御）",
      not collect_news._is_reuters_source({"source_name": "Bloomberg", "source_url": "https://www.bloomberg.com"}))
check("_is_reuters_source: <source>要素が無い（空文字）場合はReutersと判定しない",
      not collect_news._is_reuters_source({"source_name": "", "source_url": ""}))

RSS_GOOGLE_NEWS_MIXED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Reuters story - Reuters</title>
<link>https://news.google.com/rss/articles/REUTERSFAKE</link>
<pubDate>Mon, 17 Aug 2026 10:00:00 GMT</pubDate>
<source url="https://www.reuters.com">Reuters</source></item>
<item><title>Non-Reuters story slipped through</title>
<link>https://news.google.com/rss/articles/OTHERFAKE</link>
<pubDate>Mon, 17 Aug 2026 11:00:00 GMT</pubDate>
<source url="https://www.example.com">Example News</source></item>
</channel></rss>"""

orig_get_mixed = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_GOOGLE_NEWS_MIXED.encode("utf-8")))
st_mixed, kept_mixed = collect_news._collect_from_feed(
    collect_news.GOOGLE_NEWS_NAME, "https://news.google.com/fake", *_window_1707,
    tier=4, kind="candidate_discovery")
collect_news.requests.get = orig_get_mixed
_reuters_item = next(c for c in kept_mixed if "Reuters story" in c["title"])
_other_item = next(c for c in kept_mixed if "Non-Reuters" in c["title"])
check("_collect_from_feed: 実体Reutersの記事はsource='Reuters'・tier=2へ昇格する",
      _reuters_item["source"] == "Reuters" and _reuters_item["tier"] == 2, str(_reuters_item))
check("_collect_from_feed: 実体Reutersの記事はkindがindependent_reportになる",
      _reuters_item["kind"] == "independent_report", str(_reuters_item))
check("_collect_from_feed: Reuters以外の記事はtier4・Google News名のまま据え置かれる（誤って昇格させない）",
      _other_item["source"] == collect_news.GOOGLE_NEWS_NAME and _other_item["tier"] == 4, str(_other_item))
check("_collect_from_feed: tier1候補にはtier2昇格ロジックが適用されない（tier==4限定の確認）",
      all(c.get("tier") != 2 for c in kept2))

print("=== collect_news.py: fetch_article_body（v1.39・オーナー指示） ===")

_LONG_PARA = "This is a real press release paragraph with substantial content. " * 5  # >200字

HTML_WITH_MAIN = f"""<html><head><script>var x = 1;</script></head>
<body><nav>Home | About | Contact</nav><header>Site Header Banner</header>
<main><h1>Press Release Title</h1><p>{_LONG_PARA}</p></main>
<footer>Copyright 2026. All rights reserved.</footer></body></html>"""

HTML_WITH_ARTICLE = f"""<html><body><nav>NavNavNav</nav>
<article><p>{_LONG_PARA}</p></article>
<footer>FooterFooterFooter</footer></body></html>"""

HTML_NO_MAIN = """<html><body><nav>Skip to main content</nav>
<header>An official website of the United States Government</header>
<div class="content">Some text that is not wrapped in main or article tags at all,
simulating a government site like FRB that lacks this structure.</div>
<footer>Stay Connected. Federal Reserve Facebook Page. Federal Reserve X Page.</footer>
</body></html>"""

HTML_MAIN_TOO_SHORT = "<html><body><nav>nav</nav><main>short</main></body></html>"


def _patch_get_by_url(url_to_resp):
    def fn(url, **kw):
        return url_to_resp[url]
    return _patch_requests_get(fn)


orig_a1 = _patch_get_by_url({"https://example.gov/main-test": _FakeRssResp(200, HTML_WITH_MAIN.encode("utf-8"))})
body1 = collect_news.fetch_article_body("https://example.gov/main-test")
collect_news.requests.get = orig_a1
check("fetch_article_body: <main>要素から本文を抽出する",
      body1 is not None and "Press Release Title" in body1 and "This is a real press release" in body1, body1)
check("fetch_article_body: <nav>/<header>/<footer>の内容は含まれない",
      body1 is not None and "Home | About | Contact" not in body1 and "Copyright 2026" not in body1, body1)
check("fetch_article_body: 上限未満の本文には切り詰めマーカーを付さない（v1.47）",
      body1 is not None and not body1.endswith(collect_news.ARTICLE_BODY_TRUNCATION_MARKER), body1)

orig_a2 = _patch_get_by_url({"https://example.gov/article-test": _FakeRssResp(200, HTML_WITH_ARTICLE.encode("utf-8"))})
body2 = collect_news.fetch_article_body("https://example.gov/article-test")
collect_news.requests.get = orig_a2
check("fetch_article_body: <article>要素からも本文を抽出する",
      body2 is not None and "This is a real press release" in body2 and "NavNavNav" not in body2, body2)

orig_a3 = _patch_get_by_url({"https://example.gov/no-main-test": _FakeRssResp(200, HTML_NO_MAIN.encode("utf-8"))})
body3 = collect_news.fetch_article_body("https://example.gov/no-main-test")
collect_news.requests.get = orig_a3
check("fetch_article_body: <main>/<article>が無いページ（FRB相当）はNone（全文フォールバックしない）",
      body3 is None, body3)

orig_a4 = _patch_get_by_url({"https://example.gov/short-main": _FakeRssResp(200, HTML_MAIN_TOO_SHORT.encode("utf-8"))})
body4 = collect_news.fetch_article_body("https://example.gov/short-main")
collect_news.requests.get = orig_a4
check("fetch_article_body: <main>があっても200字以下ならNone", body4 is None, body4)

orig_a5 = _patch_get_by_url({"https://example.gov/404-test": _FakeRssResp(404, b"")})
body5 = collect_news.fetch_article_body("https://example.gov/404-test")
collect_news.requests.get = orig_a5
check("fetch_article_body: HTTP非200はNone", body5 is None, body5)


def _raise_get(url, **kw):
    raise collect_news.requests.exceptions.ConnectionError("boom")


orig_a6 = _patch_requests_get(_raise_get)
body6 = collect_news.fetch_article_body("https://example.gov/error-test")
collect_news.requests.get = orig_a6
check("fetch_article_body: 例外発生時もクラッシュせずNoneを返す（フェイルクローズ不要・summary補強に過ぎない）",
      body6 is None, body6)

check("collect_news.py: ARTICLE_BODY_CHAR_LIMITは1500（v1.47・8/27の入力トークン膨張を受け2000から引き下げ）",
      collect_news.ARTICLE_BODY_CHAR_LIMIT == 1500)

_over_limit = "<main><p>" + ("x" * 3000) + "</p></main>"
orig_a7 = _patch_get_by_url({"https://example.gov/long-test": _FakeRssResp(200, ("<html><body>" + _over_limit + "</body></html>").encode("utf-8"))})
body7 = collect_news.fetch_article_body("https://example.gov/long-test")
collect_news.requests.get = orig_a7
_expected_len = collect_news.ARTICLE_BODY_CHAR_LIMIT + len(collect_news.ARTICLE_BODY_TRUNCATION_MARKER)
check(f"fetch_article_body: {collect_news.ARTICLE_BODY_CHAR_LIMIT}字＋切り詰めマーカー長で切り詰める（v1.47）",
      body7 is not None and len(body7) == _expected_len, len(body7) if body7 else body7)
check("fetch_article_body: 切り詰め時は本文が指定字数ちょうどで切られ、末尾にマーカーが付く（v1.47）",
      body7 is not None
      and body7 == ("x" * collect_news.ARTICLE_BODY_CHAR_LIMIT) + collect_news.ARTICLE_BODY_TRUNCATION_MARKER,
      body7[-30:] if body7 else body7)

print("=== collect_news.py: _collect_from_feedのtier1本文補強・tier3は対象外（v1.39） ===")

RSS_TIER1_ONE_ITEM = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Tier1 item</title><link>https://example.gov/t1-main</link><pubDate>Mon, 17 Aug 2026 10:00:00 GMT</pubDate><description>thin summary</description></item>
</channel></rss>"""


def _multi_url_get(rss_body, article_url, article_body_resp):
    def fn(url, **kw):
        if url == article_url:
            return article_body_resp
        return _FakeRssResp(200, rss_body.encode("utf-8"))
    return fn


orig_b1 = _patch_requests_get(_multi_url_get(
    RSS_TIER1_ONE_ITEM, "https://example.gov/t1-main", _FakeRssResp(200, HTML_WITH_MAIN.encode("utf-8"))))
st_t1, kept_t1 = collect_news._collect_from_feed("TESTTIER1", "https://example.gov/t1feed.rss",
                                                   *_window_1707, tier=1, kind="official")
collect_news.requests.get = orig_b1
check("_collect_from_feed: tier1候補はsummaryが本文取得結果に置き換わる",
      len(kept_t1) == 1 and "This is a real press release" in kept_t1[0]["summary"]
      and kept_t1[0]["summary"] != "thin summary", str(kept_t1))

orig_b2 = _patch_requests_get(_multi_url_get(
    RSS_TIER1_ONE_ITEM, "https://example.gov/t1-main", _FakeRssResp(200, HTML_NO_MAIN.encode("utf-8"))))
st_t1b, kept_t1b = collect_news._collect_from_feed("TESTTIER1B", "https://example.gov/t1feed2.rss",
                                                     *_window_1707, tier=1, kind="official")
collect_news.requests.get = orig_b2
check("_collect_from_feed: tier1候補で本文取得がNoneの場合は元のRSS summaryのまま",
      len(kept_t1b) == 1 and kept_t1b[0]["summary"] == "thin summary", str(kept_t1b))

_tier3_calls = []


def _tracking_get(url, **kw):
    _tier3_calls.append(url)
    return _FakeRssResp(200, RSS_TIER1_ONE_ITEM.replace("https://example.gov/t1-main",
                                                         "https://example.gov/t3-main").encode("utf-8"))


orig_b3 = _patch_requests_get(_tracking_get)
st_t3, kept_t3 = collect_news._collect_from_feed("TESTTIER3B", "https://example.com/t3feed.rss",
                                                   *_window_1707, tier=3, kind="supplementary")
collect_news.requests.get = orig_b3
check("_collect_from_feed: tier3候補は本文取得を行わない（RSSフィード取得の1回のみ）",
      len(kept_t3) == 1 and kept_t3[0]["summary"] == "thin summary" and len(_tier3_calls) == 1,
      f"calls={_tier3_calls}")

print("=== generate_post.py: TIER3_CANDIDATE_LIMIT引き上げ（v1.39・オーナー指示） ===")
check("TIER3_CANDIDATE_LIMITが15である（8/25実データでのペア分断・トークン予算の実測に基づく）",
      generate_post.TIER3_CANDIDATE_LIMIT == 15, generate_post.TIER3_CANDIDATE_LIMIT)

print("=== collect_news.py: tier 3情報源の追加確認（v1.20） ===")

def _fake_sources_tier3():
    return [{"name": "TESTCOINDESK", "url": "https://example.com/coindesk.rss", "tier": 3}]
collect_news._load_sources = _fake_sources_tier3
orig_get5 = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_TODAY_ONLY.encode("utf-8")))
result_t3 = collect_news.collect_news("2026-08-17")
collect_news.requests.get = orig_get5
collect_news._load_sources = _sources_backup
t3_cands = [c for c in result_t3["candidates"] if c["source"] == "TESTCOINDESK"]
check("collect_news(): tier=3指定の情報源はcandidateにtier=3・kind=supplementaryが付与される",
      len(t3_cands) > 0 and all(c["tier"] == 3 and c["kind"] == "supplementary" for c in t3_cands),
      str(t3_cands))

def _fake_sources_default_tier():
    return [{"name": "TESTGOVNOTIER", "url": "https://example.com/gov.rss"}]  # tierフィールド省略
collect_news._load_sources = _fake_sources_default_tier
orig_get6 = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_TODAY_ONLY.encode("utf-8")))
result_default = collect_news.collect_news("2026-08-17")
collect_news.requests.get = orig_get6
collect_news._load_sources = _sources_backup
default_cands = [c for c in result_default["candidates"] if c["source"] == "TESTGOVNOTIER"]
check("collect_news(): tierフィールド省略時は既定でtier=1・kind=official",
      len(default_cands) > 0 and all(c["tier"] == 1 and c["kind"] == "official" for c in default_cands),
      str(default_cands))

real_sources = collect_news._load_sources()
tier3_names = {s["name"] for s in real_sources if s.get("tier") == 3}
check("config/news_sources.json: CoinDesk/Cointelegraph(EN/JP)がtier=3で登録されている",
      {"CoinDesk", "Cointelegraph", "Cointelegraph Japan"}.issubset(tier3_names), str(tier3_names))

print("=== config/news_sources.json: The Blockの追加確認（v1.79・オーナー承認・"
      "2026-09-28にオーナー側でRSSの有効性を確認済み） ===")
check("The Blockがtier=3で登録されている", "The Block" in tier3_names, str(tier3_names))
_news_sources_raw_tb = json.loads((REPO / "config" / "news_sources.json").read_text(encoding="utf-8"))
_the_block_entry = next((s for s in _news_sources_raw_tb["sources"] if s["name"] == "The Block"), None)
check("The BlockのURLがオーナー確認済みのものと一致する",
      _the_block_entry is not None and _the_block_entry.get("url") == "https://www.theblock.co/rss.xml",
      str(_the_block_entry))
check("The Blockがcollect_news._load_sources()経由で通常フェッチ対象に含まれる",
      "The Block" in {s["name"] for s in real_sources})
check("verify_post._load_source_tier_map()がThe Blockをtier=3として認識する（C21/C22で使う経路）",
      verify_post._load_source_tier_map().get("The Block") == 3)

print("=== collect_news.py: /sponsored/を含むURLの候補除外（v1.79・オーナー承認・"
      "統合運用基準§2「スポンサー記事は主根拠にしない」への対応） ===")
RSS_WITH_SPONSORED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Normal article</title><link>https://www.theblock.co/post/12345/normal-article</link>
<pubDate>Mon, 17 Aug 2026 10:00:00 GMT</pubDate></item>
<item><title>Sponsored article</title><link>https://www.theblock.co/sponsored/67890/paid-placement</link>
<pubDate>Mon, 17 Aug 2026 11:00:00 GMT</pubDate></item>
</channel></rss>"""


def _fake_sources_sponsored():
    return [{"name": "TESTTHEBLOCK", "url": "https://example.com/theblock.rss", "tier": 3}]


collect_news._load_sources = _fake_sources_sponsored
_orig_get_sponsored = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_WITH_SPONSORED.encode("utf-8")))
_result_sponsored = collect_news.collect_news("2026-08-17")
collect_news.requests.get = _orig_get_sponsored
collect_news._load_sources = _sources_backup
_sponsored_cands = [c for c in _result_sponsored["candidates"] if c["source"] == "TESTTHEBLOCK"]
check("collect_news(): URLに/sponsored/を含む記事は候補から除外される",
      len(_sponsored_cands) == 1 and _sponsored_cands[0]["title"] == "Normal article",
      str(_sponsored_cands))
check("collect_news(): /sponsored/を含まない記事は通常どおり候補に残る（誤って両方除外しない）",
      any(c["title"] == "Normal article" for c in _sponsored_cands), str(_sponsored_cands))

print("=== config/news_sources.json: 米財務省・USTR・ホワイトハウスの追加確認（v1.31・オーナー指示） ===")
tier1_names = {s["name"] for s in real_sources if s.get("tier") == 1}
check("米財務省・USTR・ホワイトハウス（2本）がtier=1で登録されている",
      {"米財務省", "USTR", "ホワイトハウス", "ホワイトハウス（大統領令等）"}.issubset(tier1_names), str(tier1_names))
_new_source_urls = {s["name"]: s["url"] for s in real_sources
                     if s["name"] in ("米財務省", "USTR", "ホワイトハウス", "ホワイトハウス（大統領令等）")}
check("追加した4件のURLが実測で確認済みのものと一致する",
      _new_source_urls == {
          "米財務省": "https://home.treasury.gov/rss.xml",
          "USTR": "https://ustr.gov/rss.xml",
          "ホワイトハウス": "https://www.whitehouse.gov/news/feed/",
          "ホワイトハウス（大統領令等）": "https://www.whitehouse.gov/presidential-actions/feed/",
      }, str(_new_source_urls))
_tier_map_check = verify_post._load_source_tier_map()
check("verify_post._load_source_tier_map()が新規4件をtier=1として認識する（C21/C22で使う経路）",
      all(_tier_map_check.get(n) == 1 for n in
          ("米財務省", "USTR", "ホワイトハウス", "ホワイトハウス（大統領令等）")),
      str(_tier_map_check))

print("=== config/news_sources.json: Reutersの追加確認（v1.59・オーナー承認） ===")
_news_sources_raw = json.loads((REPO / "config" / "news_sources.json").read_text(encoding="utf-8"))
_reuters_entry = next((s for s in _news_sources_raw["sources"] if s["name"] == "Reuters"), None)
check("Reutersがtier=2で登録されている（config/news_sources.jsonの生データ）",
      _reuters_entry is not None and _reuters_entry.get("tier") == 2, str(_reuters_entry))
check("Reutersのエントリにurlが無い（公開RSSが無いため。collect_news._load_sources()の"
      "通常フェッチループでは使われず、C21/C22のtier参照専用）",
      _reuters_entry is not None and "url" not in _reuters_entry, str(_reuters_entry))
check("collect_news._load_sources()はurlの無いReutersエントリを除外する（誤って空URLへの"
      "フェッチを試みない・real_sourcesにReutersが含まれないことの確認）",
      "Reuters" not in {s["name"] for s in real_sources})
check("verify_post._load_source_tier_map()がReutersをtier=2として認識する（C21/C22で使う経路）",
      verify_post._load_source_tier_map().get("Reuters") == 2)

print("=== config/news_sources.json: ADPの追加確認（v1.61・オーナー承認） ===")
check("ADPがtier=1で登録されている", "ADP" in tier1_names, str(tier1_names))
_adp_entry = next((s for s in _news_sources_raw["sources"] if s["name"] == "ADP"), None)
check("ADPのURLが実測確認済みのものと一致する（mediacenter.adp.comの投資家向けRSS）",
      _adp_entry is not None
      and _adp_entry.get("url") == "https://mediacenter.adp.com/press-releases?pagetemplate=rss",
      str(_adp_entry))
check("ADPがcollect_news._load_sources()経由で通常フェッチ対象に含まれる（urlありのtier1）",
      "ADP" in {s["name"] for s in real_sources})
check("verify_post._load_source_tier_map()がADPをtier=1として認識する（C21/C22で使う経路）",
      verify_post._load_source_tier_map().get("ADP") == 1)

print("=== config/news_sources.json: FRB speeches/testimonyの追加確認（v1.52・オーナー指示） ===")
check("FRB（speeches）・FRB（testimony）がtier=1で登録されている",
      {"FRB（speeches）", "FRB（testimony）"}.issubset(tier1_names), str(tier1_names))
_frb_new_urls = {s["name"]: s["url"] for s in real_sources
                 if s["name"] in ("FRB（speeches）", "FRB（testimony）")}
check("追加した2件のURLが実測で確認済みのものと一致する",
      _frb_new_urls == {
          "FRB（speeches）": "https://www.federalreserve.gov/feeds/speeches.xml",
          "FRB（testimony）": "https://www.federalreserve.gov/feeds/testimony.xml",
      }, str(_frb_new_urls))
check("verify_post._load_source_tier_map()がFRB新規2件をtier=1として認識する（C21/C22で使う経路）",
      all(_tier_map_check.get(n) == 1 for n in ("FRB（speeches）", "FRB（testimony）")),
      str(_tier_map_check))

print("=== post_draft.yml: フェイルクローズ・冪等性ガードの確認（v1.20） ===")
post_draft_yml = (REPO / ".github" / "workflows" / "post_draft.yml").read_text(encoding="utf-8")
check("post_draft.yml: continue-on-errorが除去されている（フェイルクローズ化）",
      "continue-on-error" not in post_draft_yml)
check("post_draft.yml: force_redispatch入力がある", "force_redispatch" in post_draft_yml)
check("post_draft.yml: 冪等性ガードのステップがある",
      "冪等性ガード" in post_draft_yml and "steps.guard.outputs.skip" in post_draft_yml)

print("=== fetch_data.py: 日中高値・安値（v1.41・オーナー承認・Coinbase主/Bitstamp副） ===")


class _FakeJsonResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise fetch_data.requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


check("_parse_coinbase_candles: フィールド順[time,low,high,open,close,volume]を正しく解釈する",
      fetch_data._parse_coinbase_candles([[1000, 10.0, 20.0, 15.0, 18.0, 100.0]]) ==
      [{"time": 1000, "low": 10.0, "high": 20.0, "open": 15.0, "close": 18.0, "volume": 100.0}])

check("_parse_bitstamp_candles: 文字列の数値をfloatへ変換する",
      fetch_data._parse_bitstamp_candles(
          {"data": {"ohlc": [{"timestamp": "1000", "open": "15", "high": "20",
                               "low": "10", "close": "18", "volume": "100"}]}}) ==
      [{"time": 1000, "low": 10.0, "high": 20.0, "open": 15.0, "close": 18.0, "volume": 100.0}])

_ws = _datetime(2026, 8, 25, 21, 0, tzinfo=_timezone.utc)   # NY 17:00 EDT = UTC 21:00
_we = _datetime(2026, 8, 26, 21, 0, tzinfo=_timezone.utc)
_candles_in_out = [
    {"time": int(_ws.timestamp()) - 3600, "high": 999.0, "low": 1.0},        # 窓の外（前）
    {"time": int(_ws.timestamp()), "high": 100.0, "low": 90.0},              # 窓の境界（含む）
    {"time": int(_ws.timestamp()) + 3600, "high": 120.0, "low": 80.0},       # 窓内・最高値/最安値
    {"time": int(_we.timestamp()) - 3600, "high": 110.0, "low": 85.0},       # 窓内
    {"time": int(_we.timestamp()), "high": 999.0, "low": 1.0},               # 窓の境界（含まない・半開区間）
]
check("_range_from_candles: 半開区間[window_start, window_end)でhigh最大・low最小を集計する",
      fetch_data._range_from_candles(_candles_in_out, _ws, _we) == (120.0, 80.0))
check("_range_from_candles: 窓内に1本も無ければNone",
      fetch_data._range_from_candles([], _ws, _we) is None)

_orig_fd_get = fetch_data.requests.get
_fd_calls = []


def _cb_payload(offset_high_low):
    return [[int(_ws.timestamp()) + off, lo, hi, (hi + lo) / 2, (hi + lo) / 2, 1.0]
            for off, hi, lo in offset_high_low]


_bs_ok_payload = {"data": {"ohlc": [
    {"timestamp": str(int(_ws.timestamp()) + 3600), "open": "80000", "high": "81255.06",
     "low": "78720.41", "close": "80500", "volume": "1"},
]}}


def _fd_get_coinbase_ok(url, headers=None, params=None, timeout=None):
    _fd_calls.append(url)
    if "api.exchange.coinbase.com" in url:
        return _FakeJsonResp(200, _cb_payload([(3600, 81255.06, 78720.41)]))
    raise AssertionError(f"Bitstampが呼ばれてはいけない: {url}")


fetch_data.requests.get = _fd_get_coinbase_ok
_fd_calls.clear()
_r1 = fetch_data.fetch_intraday_range("BTC", "BTC-USD", "btcusd", _ws, _we)
fetch_data.requests.get = _orig_fd_get
check("fetch_intraday_range: Coinbase成功時はcoinbaseのhigh/lowを返す",
      _r1["high"] == "$81,255" and _r1["low"] == "$78,720" and _r1["source"] == "coinbase", str(_r1))
check("fetch_intraday_range: Coinbase成功時はBitstampを呼ばない",
      all("bitstamp" not in c for c in _fd_calls), _fd_calls)
check("fetch_intraday_range: representativeキーは呼び出し元(main)が付与するためここには含まれない",
      "representative" not in _r1)


def _fd_get_fallback_to_bitstamp(url, headers=None, params=None, timeout=None):
    _fd_calls.append(url)
    if "api.exchange.coinbase.com" in url:
        return _FakeJsonResp(500, None)
    if "bitstamp.net" in url:
        return _FakeJsonResp(200, _bs_ok_payload)
    raise AssertionError(f"想定外のURL: {url}")


fetch_data.requests.get = _fd_get_fallback_to_bitstamp
_fd_calls.clear()
_r2 = fetch_data.fetch_intraday_range("BTC", "BTC-USD", "btcusd", _ws, _we)
fetch_data.requests.get = _orig_fd_get
check("fetch_intraday_range: Coinbase失敗（HTTPエラー）時はBitstampへフォールバックする",
      _r2["high"] == "$81,255" and _r2["low"] == "$78,720" and _r2["source"] == "bitstamp", str(_r2))


def _fd_get_coinbase_out_of_window(url, headers=None, params=None, timeout=None):
    _fd_calls.append(url)
    if "api.exchange.coinbase.com" in url:
        return _FakeJsonResp(200, _cb_payload([(-7200, 999.0, 1.0)]))  # 窓の2時間前のみ＝窓内0件
    if "bitstamp.net" in url:
        return _FakeJsonResp(200, _bs_ok_payload)
    raise AssertionError(f"想定外のURL: {url}")


fetch_data.requests.get = _fd_get_coinbase_out_of_window
_r3 = fetch_data.fetch_intraday_range("BTC", "BTC-USD", "btcusd", _ws, _we)
fetch_data.requests.get = _orig_fd_get
check("fetch_intraday_range: Coinbaseが200でも窓内の足が0件ならBitstampへフォールバックする",
      _r3["source"] == "bitstamp", str(_r3))


def _fd_get_both_fail(url, headers=None, params=None, timeout=None):
    return _FakeJsonResp(503, None)


fetch_data.requests.get = _fd_get_both_fail
_r4 = fetch_data.fetch_intraday_range("BTC", "BTC-USD", "btcusd", _ws, _we)
fetch_data.requests.get = _orig_fd_get
check("fetch_intraday_range: 両方失敗した場合はUNCONFIRMED（BTC/JPY等の代替はしない）",
      _r4["high"] == fetch_data.UNCONFIRMED and _r4["low"] == fetch_data.UNCONFIRMED
      and _r4["source"] == fetch_data.UNCONFIRMED and bool(_r4.get("retrieved_at")), str(_r4))

check("INTRADAY_SYMBOLS: BTC・ETHはrepresentative=True、BNBはFalse",
      fetch_data.INTRADAY_SYMBOLS["BTC"][2] is True
      and fetch_data.INTRADAY_SYMBOLS["ETH"][2] is True
      and fetch_data.INTRADAY_SYMBOLS["BNB"][2] is False,
      str(fetch_data.INTRADAY_SYMBOLS))

print("=== fetch_data.py: notable_move判定・閾値のconfig化（v1.41フォローアップ・オーナー承認） ===")
check("compute_notable_move: 8/25のBTC実例（高値$81,265／当日価格$78,895）は閾値3%以上でTrue",
      fetch_data.compute_notable_move(81265.0, 78895.0, 0.03) is True)
check("compute_notable_move: 乖離が閾値未満ならFalse",
      fetch_data.compute_notable_move(80000.0, 78895.0, 0.03) is False)
check("compute_notable_move: high_rawがNoneなら判定不能（None、Falseで固定しない）",
      fetch_data.compute_notable_move(None, 78895.0, 0.03) is None)
check("compute_notable_move: close_priceがNone/0なら判定不能（None）",
      fetch_data.compute_notable_move(81265.0, None, 0.03) is None
      and fetch_data.compute_notable_move(81265.0, 0, 0.03) is None)

check("load_notable_move_threshold: config/intraday_range.jsonが存在しキーがあればその値を読む",
      fetch_data.load_notable_move_threshold() == 0.03, fetch_data.load_notable_move_threshold())

_orig_intraday_config_path = fetch_data.INTRADAY_RANGE_CONFIG_PATH
_missing_config = Path("no_such_intraday_range.json")
fetch_data.INTRADAY_RANGE_CONFIG_PATH = _missing_config
check("load_notable_move_threshold: 設定ファイルが存在しない場合はデフォルト0.03へフェイルクローズ",
      fetch_data.load_notable_move_threshold() == fetch_data.NOTABLE_MOVE_THRESHOLD_DEFAULT)

_custom_config = Path("custom_intraday_range.json")
_custom_config.write_text(json.dumps({"notable_move_threshold": 0.05}), encoding="utf-8")
fetch_data.INTRADAY_RANGE_CONFIG_PATH = _custom_config
check("load_notable_move_threshold: 設定ファイルのnotable_move_thresholdを読む（コードのハードコード値ではない）",
      fetch_data.load_notable_move_threshold() == 0.05)
fetch_data.INTRADAY_RANGE_CONFIG_PATH = _orig_intraday_config_path

print("=== fetch_data.py: 終値とレンジの矛盾検出（v1.44・オーナー指示） ===")
check("compute_inconsistent: 8/26のETH実例（終値$2,492がレンジ$2,415〜$2,484の外）はTrue",
      fetch_data.compute_inconsistent(2484.0, 2415.0, 2492.0) is True)
check("compute_inconsistent: 終値がレンジ内ならFalse",
      fetch_data.compute_inconsistent(81265.0, 78100.0, 78895.0) is False)
check("compute_inconsistent: 終値がレンジの境界値（high・low）ちょうどならFalse（[low, high]は閉区間）",
      fetch_data.compute_inconsistent(100.0, 90.0, 100.0) is False
      and fetch_data.compute_inconsistent(100.0, 90.0, 90.0) is False)
check("compute_inconsistent: high_raw/low_rawのいずれかがNoneなら判定不能（None）",
      fetch_data.compute_inconsistent(None, 78100.0, 78895.0) is None
      and fetch_data.compute_inconsistent(81265.0, None, 78895.0) is None)
check("compute_inconsistent: close_priceがNone/0なら判定不能（None）",
      fetch_data.compute_inconsistent(81265.0, 78100.0, None) is None
      and fetch_data.compute_inconsistent(81265.0, 78100.0, 0) is None)

print("=== fetch_data.py: Base TVL 24時間比の自前計算（v1.77・オーナー承認・9/19実データの乖離への対処） ===")
from datetime import date as _date_cls, timedelta as _timedelta_cls  # noqa: E402


def _write_raw(day: str, base_tvl, fetched_at: str) -> None:
    os.makedirs(f"outputs/{day}", exist_ok=True)
    Path(f"outputs/{day}/raw_data.json").write_text(
        json.dumps({"run_id": "test", "fetched_at": fetched_at, "base_tvl": base_tvl}, ensure_ascii=False),
        encoding="utf-8")


# 正常系: ちょうど24時間後・レベルどおりの変化率になること
_write_raw("2099-01-10", 1000.0, "2099-01-10T07:37:00+09:00")
_chg_normal = fetch_data.compute_base_tvl_change(
    _date_cls(2099, 1, 11), 1100.0, fetch_data._parse_fetched_at("2099-01-11T07:37:00+09:00"))
check("compute_base_tvl_change: 24時間後・TVL1000→1100なら+10.0%",
      _chg_normal is not None and abs(_chg_normal - 10.0) < 1e-9, _chg_normal)

# 9/18→9/19の実データと同一パターンの合成値（実際の乖離事例を単体テストとしても固定化）
_write_raw("2099-01-20", 5868312588.046856, "2099-01-20T07:37:50.401693+09:00")
_chg_repro = fetch_data.compute_base_tvl_change(
    _date_cls(2099, 1, 21), 5912757305.448482,
    fetch_data._parse_fetched_at("2099-01-21T07:37:46.729469+09:00"))
check("compute_base_tvl_change: 9/18→9/19と同一の生値パターンで+0.757%付近になる（旧実装の+5.93%は再現しない）",
      _chg_repro is not None and abs(_chg_repro - 0.757368) < 1e-3, _chg_repro)

# 異常系: 当日TVLがNone
check("compute_base_tvl_change: 当日TVLがNoneなら比較不可（None）",
      fetch_data.compute_base_tvl_change(_date_cls(2099, 1, 11), None,
                                          fetch_data._parse_fetched_at("2099-01-11T07:37:00+09:00")) is None)

# 異常系: 前日raw_data.jsonが無い
check("compute_base_tvl_change: 前日raw_data.jsonが無ければ比較不可（None）",
      fetch_data.compute_base_tvl_change(_date_cls(2099, 1, 1), 1000.0,
                                          fetch_data._parse_fetched_at("2099-01-01T07:37:00+09:00")) is None)

# 異常系: 前日base_tvlが未確認(None)・0
_write_raw("2099-01-31", None, "2099-01-31T07:37:00+09:00")
check("compute_base_tvl_change: 前日base_tvlがNoneなら比較不可（None）",
      fetch_data.compute_base_tvl_change(_date_cls(2099, 2, 1), 1000.0,
                                          fetch_data._parse_fetched_at("2099-02-01T07:37:00+09:00")) is None)
_write_raw("2099-02-09", 0, "2099-02-09T07:37:00+09:00")
check("compute_base_tvl_change: 前日base_tvlが0なら比較不可（ゼロ除算を避ける）",
      fetch_data.compute_base_tvl_change(_date_cls(2099, 2, 10), 1000.0,
                                          fetch_data._parse_fetched_at("2099-02-10T07:37:00+09:00")) is None)

# 異常系: 前日fetched_atが壊れている
os.makedirs("outputs/2099-02-19", exist_ok=True)
Path("outputs/2099-02-19/raw_data.json").write_text(
    json.dumps({"run_id": "test", "fetched_at": "not-a-timestamp", "base_tvl": 1000.0}), encoding="utf-8")
check("compute_base_tvl_change: 前日fetched_atが解釈不能なら比較不可（None）",
      fetch_data.compute_base_tvl_change(_date_cls(2099, 2, 20), 1100.0,
                                          fetch_data._parse_fetched_at("2099-02-20T07:37:00+09:00")) is None)

# 異常系: 取得間隔が許容範囲(20〜28時間)の外（短すぎる・長すぎる）
_write_raw("2099-03-01", 1000.0, "2099-03-01T07:37:00+09:00")
check("compute_base_tvl_change: 取得間隔が19時間（範囲外・短すぎ）なら比較不可（None）",
      fetch_data.compute_base_tvl_change(
          _date_cls(2099, 3, 2), 1100.0,
          fetch_data._parse_fetched_at("2099-03-01T07:37:00+09:00") + _timedelta_cls(hours=19)) is None)
check("compute_base_tvl_change: 取得間隔が29時間（範囲外・長すぎ）なら比較不可（None）",
      fetch_data.compute_base_tvl_change(
          _date_cls(2099, 3, 2), 1100.0,
          fetch_data._parse_fetched_at("2099-03-01T07:37:00+09:00") + _timedelta_cls(hours=29)) is None)
check("compute_base_tvl_change: 取得間隔がちょうど20時間・28時間（境界値）は比較可能",
      fetch_data.compute_base_tvl_change(
          _date_cls(2099, 3, 2), 1100.0,
          fetch_data._parse_fetched_at("2099-03-01T07:37:00+09:00") + _timedelta_cls(hours=20)) is not None
      and fetch_data.compute_base_tvl_change(
          _date_cls(2099, 3, 2), 1100.0,
          fetch_data._parse_fetched_at("2099-03-01T07:37:00+09:00") + _timedelta_cls(hours=28)) is not None)

print("=== fetch_data.py: LPプールchange_vs_prevの分母を生値へ変更（v1.78・オーナー承認・9/26実データの乖離への対処） ===")
# 正常系: 生値同士の変化率になること（前日$9.62M表示・生値9,615,410.635 → 当日9,661,485.5513
# の場合、表示値ベースなら+0.43%だが生値ベースでは+0.48%になるはず——9/25→9/26実データと同一パターン）
_prev_raw_005 = {"apr": 39.27029337886918, "tvl": 9615410.635, "vol": 20690410.772315}
_curr_g005 = {"apr": 10.344741107436814, "tvl": 9661485.5513, "vol": 5476469.41048986}
_prev_raw_full = {"gecko_005": _prev_raw_005, "gecko_03": {"apr": 1.0, "tvl": 2.0, "vol": 3.0}}
_pc = fetch_data.compute_pool_changes("gecko_005", _curr_g005, _prev_raw_full)
check("compute_pool_changes: 9/25→9/26と同一パターンでtvl_changeが生値ベースの+0.48%になる（表示値ベースの+0.43%ではない）",
      _pc["tvl_change"] == "+0.48%", _pc)
check("compute_pool_changes: volume_24h_changeも生値ベースで算出される",
      _pc["volume_24h_change"] == fetch_data.fmt_change((_curr_g005["vol"] / _prev_raw_005["vol"] - 1) * 100),
      _pc)
check("compute_pool_changes: apr_changeも生値ベースで算出される",
      _pc["apr_change"] == fetch_data.fmt_change((_curr_g005["apr"] / _prev_raw_005["apr"] - 1) * 100),
      _pc)

# 異常系: 前日raw_data.json自体が無い（prev_raw=None）→ 比較不可（推測値を置かない）
check("compute_pool_changes: prev_rawがNoneなら3指標とも「比較不可（前日データなし）」",
      fetch_data.compute_pool_changes("gecko_005", _curr_g005, None) ==
      {"apr_change": fetch_data.NO_PREV_DATA, "volume_24h_change": fetch_data.NO_PREV_DATA,
       "tvl_change": fetch_data.NO_PREV_DATA})

# 異常系: 該当プールのキー自体が前日raw_data.jsonに無い（例: v1.78適用前の古い形式）
check("compute_pool_changes: 前日raw_dataに該当プールキーが無ければ「比較不可（前日値未確認）」",
      fetch_data.compute_pool_changes("gecko_005", _curr_g005, {"gecko_03": {"apr": 1.0, "tvl": 2.0, "vol": 3.0}})
      == {"apr_change": fetch_data.NO_PREV_VALUE, "volume_24h_change": fetch_data.NO_PREV_VALUE,
          "tvl_change": fetch_data.NO_PREV_VALUE})

# 異常系: 当日値が無い（g=None、フェッチ失敗時と同じ形）
check("compute_pool_changes: 当日g=Noneなら3指標とも「比較不可（当日値未確認）」",
      fetch_data.compute_pool_changes("gecko_005", None, _prev_raw_full) ==
      {"apr_change": fetch_data.NO_CURR_VALUE, "volume_24h_change": fetch_data.NO_CURR_VALUE,
       "tvl_change": fetch_data.NO_CURR_VALUE})

# 異常系: 前日値が数値でない（壊れたraw_data.json）→ 表示値へのフォールバックはしない
check("compute_pool_changes: 前日tvlが数値でない（文字列等）場合は比較不可（表示値パースへフォールバックしない）",
      fetch_data.compute_pool_changes(
          "gecko_005", _curr_g005, {"gecko_005": {"apr": 39.27, "tvl": "$9.62M", "vol": 20690410.77}}
      )["tvl_change"] == fetch_data.NO_PREV_VALUE)

# 再現テスト（オーナー指示）: 実データ（outputs/2026-09-25, 2026-09-26。REPO直下の
# 本物のコミット済みファイルを絶対パスで直接読む・読み取り専用・書き換えなし。
# テスト全体はos.chdir(SCRATCH)しているためload_prev_raw()の相対パスは使わない）で
# 0.05%プールのtvl_changeが+0.48%になることを確認する。
_real_prev_path = REPO / "outputs/2026-09-25/raw_data.json"
_real_curr_path = REPO / "outputs/2026-09-26/raw_data.json"
if _real_prev_path.exists() and _real_curr_path.exists():
    _real_prev_raw = json.loads(_real_prev_path.read_text(encoding="utf-8"))
    _real_curr_raw = json.loads(_real_curr_path.read_text(encoding="utf-8"))
    _real_pc = fetch_data.compute_pool_changes("gecko_005", _real_curr_raw["gecko_005"], _real_prev_raw)
    check("再現テスト（実データ）: 2026-09-26分0.05%プールのtvl_changeが+0.48%になる（旧実装の+0.43%は再現しない）",
          _real_pc["tvl_change"] == "+0.48%", _real_pc)
else:
    check("再現テスト（実データ）: outputs/2026-09-25・2026-09-26/raw_data.jsonからの再現", False,
          "実データファイルが見つからなかった（テスト環境の問題）")

print("=== compose_numeric.py: 前編【主要指標】への24時間レンジ行の追加（v1.41フォローアップ・オーナー承認） ===")
_dd_with_range = json.loads(json.dumps(DAILY_DATA))
_dd_with_range["intraday_range"] = {
    "BTC": {"high": "$81,265", "low": "$78,100", "source": "coinbase",
            "retrieved_at": "2026-08-26T10:20:24+09:00", "representative": True, "notable_move": True},
    "ETH": {"high": "$2,533", "low": "$2,433", "source": "coinbase",
            "retrieved_at": "2026-08-26T10:20:25+09:00", "representative": True},
    "BNB": {"high": "$719", "low": "$691", "source": "coinbase",
            "retrieved_at": "2026-08-26T10:20:26+09:00", "representative": False},
}
_p1_range = compose_numeric.compose_part1_numeric(_dd_with_range)
check("compose_part1_numeric: BTCの24時間レンジ行が出る",
      "　（24時間レンジ $78,100〜$81,265）" in _p1_range, _p1_range)
check("compose_part1_numeric: ETHの24時間レンジ行が出る",
      "　（24時間レンジ $2,433〜$2,533）" in _p1_range, _p1_range)
check("compose_part1_numeric: BNBの24時間レンジ行は出ない（representative=falseのため）",
      "$691〜$719" not in _p1_range and "$719〜$691" not in _p1_range, _p1_range)
check("_intraday_range_line: representative=falseの銘柄は常にNone",
      compose_numeric._intraday_range_line(_dd_with_range, "BNB") is None)

_intraday_hits = verify_post._find_transcriptions(
    _dd_with_range, "BTCは一時$81,265まで上昇した。", set())
check("C16b: intraday_rangeの数値（高値・安値）も既存の汎用スキャンで転記検知の対象になる（コード変更不要）",
      "$81,265" in _intraday_hits, str(_intraday_hits))

_dd_unconfirmed_range = json.loads(json.dumps(DAILY_DATA))
_dd_unconfirmed_range["intraday_range"] = {
    "BTC": {"high": compose_numeric.UNCONFIRMED, "low": compose_numeric.UNCONFIRMED,
            "source": compose_numeric.UNCONFIRMED, "retrieved_at": "...", "representative": True},
}
_p1_unconf = compose_numeric.compose_part1_numeric(_dd_unconfirmed_range)
check("compose_part1_numeric: intraday_rangeが未確認の日は行自体を省略する（「未確認」とは書かない）",
      "24時間レンジ" not in _p1_unconf, _p1_unconf)

check("compose_part1_numeric: intraday_range自体が無い日（従来のdaily_data.json）でも24時間レンジ行は出ない・既存行に影響しない",
      compose_numeric.compose_part1_numeric(DAILY_DATA).count("24時間レンジ") == 0)

print("=== compose_numeric.py: inconsistent:trueの銘柄は24時間レンジ行を省略（v1.44・オーナー指示） ===")
_dd_inconsistent = json.loads(json.dumps(DAILY_DATA))
_dd_inconsistent["intraday_range"] = {
    "BTC": {"high": "$81,265", "low": "$78,100", "source": "coinbase",
            "retrieved_at": "2026-08-26T10:20:24+09:00", "representative": True},
    "ETH": {"high": "$2,484", "low": "$2,415", "source": "coinbase",
            "retrieved_at": "2026-08-26T10:20:25+09:00", "representative": True, "inconsistent": True},
}
_p1_inconsistent = compose_numeric.compose_part1_numeric(_dd_inconsistent)
check("compose_part1_numeric: inconsistent:trueの銘柄（ETH）は24時間レンジ行を省略する（「未確認」とも書かない）",
      "24時間レンジ" not in _p1_inconsistent.split("#ETH")[1].split("#BNB")[0], _p1_inconsistent)
check("compose_part1_numeric: inconsistent:falseの銘柄（BTC）は従来どおり24時間レンジ行が出る",
      "　（24時間レンジ $78,100〜$81,265）" in _p1_inconsistent, _p1_inconsistent)
check("_intraday_range_line: inconsistent:trueならNone（representative:trueでも）",
      compose_numeric._intraday_range_line(_dd_inconsistent, "ETH") is None)

print("=== compose_post.py: 24時間レンジ不整合をGENERATION_STATUS.mdへ記録（v1.44・オーナー指示） ===")
_gen_for_status = json.loads(json.dumps(_gen_not_truncated))
_gen_status_inconsistent = compose_post.render_generation_status(_gen_for_status, _dd_inconsistent)
check("render_generation_status: inconsistentな銘柄（ETH）を検出した旨が記録される",
      "24時間レンジ不整合検出: ETH" in _gen_status_inconsistent, _gen_status_inconsistent)
_gen_status_no_daily_data = compose_post.render_generation_status(_gen_for_status)
check("render_generation_status: daily_data省略時（後方互換）は不整合検出行を出さない",
      "24時間レンジ不整合検出" not in _gen_status_no_daily_data)
_gen_status_consistent = compose_post.render_generation_status(_gen_for_status, DAILY_DATA)
check("render_generation_status: 不整合な銘柄が無い日は不整合検出行を出さない",
      "24時間レンジ不整合検出" not in _gen_status_consistent)

print("=== compose_post.py: reusable_for_summaryのbundleへの伝播（v1.44・C23が参照するため追加） ===")
_b_reusable = compose_post.compose(DAILY_DATA, gen_l0)
check("compose(): reusable_for_summaryがbundleに含まれる（L0・呼び出しA成功）",
      _b_reusable["reusable_for_summary"] == CALL_A_DATA["reusable_for_summary"],
      str(_b_reusable.get("reusable_for_summary")))
_b_a_failed = compose_post.compose(DAILY_DATA, gen_l1a)
check("compose(): 呼び出しA失敗時のreusable_for_summaryは空配列（Noneではない・C23側でjoinしやすくするため）",
      _b_a_failed["reusable_for_summary"] == [])

print("=== generate_post.py: notable_moveのプロンプト指示（v1.41フォローアップ・オーナー承認。v1.82でヘッドライン例外を廃止・オーナー承認） ===")
_IMG = generate_post.INTRADAY_MOVE_GUIDANCE
check("SYSTEM_AにINTRADAY_MOVE_GUIDANCEが含まれる（数値を書かない旨・形状のみ記述の旨）",
      _IMG in generate_post.SYSTEM_A
      and "あなたは数値を書かないこと" in generate_post.SYSTEM_A
      and "値動きの形状のみを" in generate_post.SYSTEM_A.replace("\n", ""))
check("SYSTEM_BにもINTRADAY_MOVE_GUIDANCEが含まれる（呼び出しBの【暗号通貨価格】段階で使うため・v1.82）",
      _IMG in generate_post.SYSTEM_B)
check("INTRADAY_MOVE_GUIDANCE: 【ヘッドライン】【主要なポイント】に価格・24時間比・値動きを書かない旨と"
      "notable_moveを理由にした例外を設けない旨が明記される（v1.82・オーナー承認）",
      "【ヘッドライン】【主要なポイント】には価格・" in _IMG.replace("\n", "")
      and "24時間比・値動きを書かない" in _IMG.replace("\n", "")
      and "例外も設けない" in _IMG)
check("INTRADAY_MOVE_GUIDANCE: 値動きを伝える先がheadline_for_image（呼び出しA）と"
      "【市場のフロー】最終段階（呼び出しB）の2か所に限定される（v1.82）",
      "headline_for_image（呼び出しA）" in _IMG and "最終段階【暗号通貨価格】（呼び出しB）" in _IMG)
check("INTRADAY_MOVE_GUIDANCE: 旧「ヘッドラインの主題にしてよい」旨の記述が残っていない（v1.82）",
      "ヘッドラインの主題" not in _IMG and "part1_headlineの主題" not in _IMG)

print("=== verify_post._find_c18_violations: セクション帰属付き検知が旧実装と同値（v1.76） ===")
_v18 = json.loads(json.dumps(b_ok))
_v18["sections"]["part2_flow"] = "規制強化を受けてBTC価格が下落した。"
_violations = verify_post._find_c18_violations(_v18["sections"], _v18["llm_section_keys"], set())
check("_find_c18_violations: 違反1件をpart2_flowへ正しく帰属",
      len(_violations) == 1 and _violations[0]["section"] == "part2_flow", str(_violations))
check("_find_c18_violations: sentenceは句点を含まない元の部分文字列（置換用に非stripのまま）",
      _violations[0]["sentence"] == "規制強化を受けてBTC価格が下落した", repr(_violations[0]["sentence"]))
_au_via_helper = verify_post.Audit()
verify_post.check_c18(_au_via_helper, _v18["sections"], _v18["llm_section_keys"], set())
check("check_c18: _find_c18_violations経由でも従来どおりFAILする",
      next(c for c in _au_via_helper.checks if c["id"] == "C18_causal_assertion")["result"] == "FAIL")

print("=== repair_post.py: C13機械修正（LLM非依存・v1.76） ===")
check("_fix_c13_missing_space: '。#BTC'をスペース挿入で修正",
      repair_post._fix_c13_missing_space("市場は上昇しました。#BTC") == ("市場は上昇しました。 #BTC", 1))
check("_fix_c13_missing_space: 文字列先頭の'#'は変更しない（行頭扱い・verify_post.pyの判定と一致）",
      repair_post._fix_c13_missing_space("#BTC上昇") == ("#BTC上昇", 0))
check("_fix_c13_missing_space: 既に半角スペースがある場合は変更しない（冪等）",
      repair_post._fix_c13_missing_space("上昇しました。 #BTC") == ("上昇しました。 #BTC", 0))
check("_fix_c13_missing_space: 改行の直後は変更しない",
      repair_post._fix_c13_missing_space("上昇しました。\n#BTC") == ("上昇しました。\n#BTC", 0))
check("_split_bullet_prefix: 箇条書き記号を分離できる",
      repair_post._split_bullet_prefix("・規制強化により下落した") == ("・", "規制強化により下落した"))
check("_split_bullet_prefix: 記号が無い場合は空文字を返す",
      repair_post._split_bullet_prefix("規制強化により下落した") == ("", "規制強化により下落した"))

print("=== repair_post.py: 合成テスト（9/9・9/11・9/15の実監査ログと同一パターン、v1.76） ===")
# 9/16運用観察報告（DESIGN_CHANGES.md v1.75）でジョブログに残っていた実際の
# 検知根拠と同一パターンの文を合成する。実際の違反文そのものは、フェイル
# クローズにより本文が一度もコミットされておらず、デバッグ用アーティファクトも
# このセッションのネットワーク許可リスト外(Azure Blob Storage・403)のため
# 取得できなかった。オーナー承認により、検知根拠が一致する合成文での検証に
# 限定する。
SYNTH_C18_SENTENCES = {
    "9/9-1（を受けて＋上昇）": "米国の経済指標発表を受けてBTC価格が上昇した。",
    "9/9-2（を受けて＋下落）": "規制強化の発表を受けてETH価格が下落した。",
    "9/11（を受けて＋上昇）": "米中央銀行の発言を受けてBTC価格が上昇した。",
    "9/15（を受けて＋下落）": "供給懸念の高まりを受けてBTC価格が下落した。",
}
for _label, _sentence in SYNTH_C18_SENTENCES.items():
    _hits = verify_post._causal_violations_in_sentence(_sentence)
    check(f"合成文[{_label}]はC18の実際の検知根拠と同一パターン（を受けて＋価格変動語・限定表現なし）",
          len(_hits) > 0, f"{_sentence!r} -> {_hits}")

REPAIR_REWRITE_MAP = {
    "米国の経済指標発表を受けてBTC価格が上昇した": "米国の経済指標発表を受けてBTC価格が上昇した可能性がある",
    "規制強化の発表を受けてETH価格が下落した": "規制強化の発表を受けてETH価格が下落したとみられる",
}


def _repair_fn_rescue(kw, n):
    user_text = kw["messages"][0]["content"]
    rewritten = REPAIR_REWRITE_MAP.get(user_text)
    check(f"repair(): call_rへ渡されるuser_contentは句点なしの元文({n}回目)", rewritten is not None, user_text)
    return json_response({"rewritten_sentence": rewritten or (user_text + "可能性がある")})


# 9/9型: 同一セクション(part2_flow)内に2件同時（1ラウンドでまとめて修正する
# 設計＝オーナー承認済みのラウンド定義）。あわせてpart1_headlineにC13
# （'#'直前のスペース欠落。9/9で実際に同時発生していたパターン）も仕込む。
b_repair_src = json.loads(json.dumps(b_ok))
b_repair_src["sections"]["part2_flow"] = (
    "米国の経済指標発表を受けてBTC価格が上昇した。"
    "規制強化の発表を受けてETH価格が下落した。"
)
b_repair_src["sections"]["part1_headline"] = CALL_A_DATA["part1_headline"] + "#BTC #ETH #BNB"
b_repair_src["part1_md"], b_repair_src["part2_md"] = compose_post.render_markdown(
    b_repair_src["sections"], b_repair_src["level"])
_pre_au = verify_post.run_all(b_repair_src, DAILY_DATA)
_pre_failing = {c["id"] for c in _pre_au.checks if c["result"] == "FAIL"}
check("合成テスト前提: 修正前はC18・C13の両方がFAILする（9/9型の複合違反）",
      _pre_failing == {"C18_causal_assertion", "C13_hashtag_boundary"}, json.dumps(_pre_au.checks, ensure_ascii=False))

REPAIR_TEST_DATE = "2026-08-17"  # 既存テストでdaily_data.jsonを書き出し済みの日付を再利用
os.makedirs(f"outputs/{REPAIR_TEST_DATE}/draft", exist_ok=True)
Path(f"outputs/{REPAIR_TEST_DATE}/draft/post_bundle.json").write_text(
    json.dumps(b_repair_src, ensure_ascii=False), encoding="utf-8")

_fake_rescue = FakeClient(_repair_fn_rescue)
_result = repair_post.repair(REPAIR_TEST_DATE, client=_fake_rescue)

check("repair(): 1ラウンドで救済できる（C18・C13とも解消）",
      _result["rounds_used"] == 1 and _result["rescued"], json.dumps(_result, ensure_ascii=False))
check("repair(): C18の呼び出し回数は違反文の数と一致する（2回。C13はLLMを使わない）",
      len(_fake_rescue.messages.calls) == 2, len(_fake_rescue.messages.calls))

_repaired_bundle = json.loads(Path(f"outputs/{REPAIR_TEST_DATE}/draft/post_bundle.json").read_text(encoding="utf-8"))
_final_au = verify_post.run_all(_repaired_bundle, DAILY_DATA)
check("repair(): 修正後はC18・C13ともPASSする",
      all(c["result"] != "FAIL" for c in _final_au.checks if c["id"] in
          ("C18_causal_assertion", "C13_hashtag_boundary")), json.dumps(_final_au.checks, ensure_ascii=False))
check("repair(): 修正後もC12〜C24の他チェックに新たな違反を生まない（全PASS/SKIP）",
      _final_au.failed == 0, json.dumps(_final_au.checks, ensure_ascii=False))
check("repair(): 修正後の文がBTC/上昇・ETH/下落という元の事実を保持している",
      all(w in _repaired_bundle["sections"]["part2_flow"] for w in ("BTC", "上昇", "ETH", "下落")),
      _repaired_bundle["sections"]["part2_flow"])
check("repair(): 句点の二重化（「。。」）が発生していない",
      "。。" not in _repaired_bundle["sections"]["part2_flow"], _repaired_bundle["sections"]["part2_flow"])
check("repair(): C13は半角スペース挿入のみで修正されている（元の文言はそのまま）",
      _repaired_bundle["sections"]["part1_headline"] == CALL_A_DATA["part1_headline"] + " #BTC #ETH #BNB",
      _repaired_bundle["sections"]["part1_headline"])

_status_note = repair_post.render_status_note(_result)
check("render_status_note: 修正前後の文言が両方記録される",
      "米国の経済指標発表を受けてBTC価格が上昇した" in _status_note
      and "米国の経済指標発表を受けてBTC価格が上昇した可能性がある" in _status_note, _status_note)
check("render_status_note: トークン増分(input=/output=)が記録される",
      "input=" in _status_note and "output=" in _status_note, _status_note)
check("render_status_note: 最終結果が「救済」と記録される", "救済" in _status_note, _status_note)
print(f"  [トークン増分] 合成テスト（2文同時修正・1ラウンド）: {_result['total_usage']}")

print("=== repair_post.py: 2ラウンドでも救済できない場合は従来どおりFAILのまま（v1.76） ===")


def _repair_fn_never_hedges(kw, n):
    # 限定表現を一切含めない書き直し（実質そのまま）を返し続け、C18が
    # 解消されない状況を再現する。
    return json_response({"rewritten_sentence": "米国の経済指標発表を受けてBTC価格が上昇した"})


b_repair_stuck = json.loads(json.dumps(b_ok))
b_repair_stuck["sections"]["part2_flow"] = "米国の経済指標発表を受けてBTC価格が上昇した。"
b_repair_stuck["part1_md"], b_repair_stuck["part2_md"] = compose_post.render_markdown(
    b_repair_stuck["sections"], b_repair_stuck["level"])
os.makedirs(f"outputs/{REPAIR_TEST_DATE}/draft", exist_ok=True)
Path(f"outputs/{REPAIR_TEST_DATE}/draft/post_bundle.json").write_text(
    json.dumps(b_repair_stuck, ensure_ascii=False), encoding="utf-8")

_fake_stuck = FakeClient(_repair_fn_never_hedges)
_result_stuck = repair_post.repair(REPAIR_TEST_DATE, client=_fake_stuck)
check("repair(): 限定表現が付かない書き直しが続く場合、最大2ラウンドで打ち切る",
      _result_stuck["rounds_used"] == 2, json.dumps(_result_stuck, ensure_ascii=False))
check("repair(): 2ラウンド後も未救済の場合はrescued=False",
      not _result_stuck["rescued"], json.dumps(_result_stuck, ensure_ascii=False))
check("repair(): 未救済時、C18は残存FAILとして報告される（従来どおりFAIL）",
      "C18_causal_assertion" in _result_stuck["final_failing_checks"], _result_stuck["final_failing_checks"])
check("repair(): 未救済でも呼び出し回数は2ラウンド×1文=2回（無限リトライしない）",
      len(_fake_stuck.messages.calls) == 2, len(_fake_stuck.messages.calls))
_stuck_note = repair_post.render_status_note(_result_stuck)
check("render_status_note: 未救済時は「未救済」「FAILのまま」と明記される",
      "未救済" in _stuck_note and "FAIL" in _stuck_note, _stuck_note)

print("=== repair_post.py: 修正対象が無い日は何もしない（v1.76） ===")
Path(f"outputs/{REPAIR_TEST_DATE}/draft/post_bundle.json").write_text(
    json.dumps(b_ok, ensure_ascii=False), encoding="utf-8")
_fake_noop = FakeClient(lambda kw, n: json_response({"rewritten_sentence": "呼ばれないはず"}))
_result_noop = repair_post.repair(REPAIR_TEST_DATE, client=_fake_noop)
check("repair(): 初回検証でC18・C13ともPASSの日はラウンドを実行しない",
      _result_noop["rounds_used"] == 0, json.dumps(_result_noop, ensure_ascii=False))
check("repair(): 対象違反が無ければLLMを一度も呼ばない（コストゼロ）",
      len(_fake_noop.messages.calls) == 0, len(_fake_noop.messages.calls))
check("render_status_note: 対象違反が無い日は空文字列（GENERATION_STATUS.mdへ何も追記しない）",
      repair_post.render_status_note(_result_noop) == "", repair_post.render_status_note(_result_noop))

print("=== repair_post.py: render_final_audit_note・GENERATION_STATUS.mdへの最終監査結果の常時記録"
      "（v1.79・オーナー承認・「本文をコミットしない日でもGENERATION_STATUS.mdだけはコミットされる"
      "ようにしてください」への対応） ===")

_final_note_pass = repair_post.render_final_audit_note(_result_noop)
check("render_final_audit_note: 局所修正の対象が無い日（rounds_used==0）でも非空文字列を返す"
      "（render_status_noteは空文字列を返すのと対照的）",
      _final_note_pass != "", repr(_final_note_pass))
check("render_final_audit_note: 全項目PASSの場合はoverall=PASSと明記される",
      "overall=PASS" in _final_note_pass and "FAILしたチェックはありません" in _final_note_pass,
      _final_note_pass)

_final_note_fail = repair_post.render_final_audit_note(_result_stuck)
check("render_final_audit_note: FAILが残る場合はoverall=FAILと、FAILしたチェックID・詳細が記録される",
      "overall=FAIL" in _final_note_fail and "FAIL: C18_causal_assertion" in _final_note_fail
      and _result_stuck["final_failing_check_details"][0]["detail"] in _final_note_fail,
      _final_note_fail)

check("repair(): final_failing_check_detailsはfinal_failing_checksと同じチェックIDを持つ",
      {c["id"] for c in _result_stuck["final_failing_check_details"]} == set(_result_stuck["final_failing_checks"]),
      str(_result_stuck["final_failing_check_details"]))

# main()相当の経路: GENERATION_STATUS.mdへの実際の追記を確認する
_status_e2e_path = Path(f"outputs/{REPAIR_TEST_DATE}/GENERATION_STATUS.md")
_status_e2e_path.write_text("level: L0\n", encoding="utf-8")
Path(f"outputs/{REPAIR_TEST_DATE}/draft/post_bundle.json").write_text(
    json.dumps(b_ok, ensure_ascii=False), encoding="utf-8")
_orig_argv = sys.argv
sys.argv = ["repair_post.py", REPAIR_TEST_DATE]
_orig_anthropic_client = repair_post.anthropic.Anthropic
repair_post.anthropic.Anthropic = lambda: FakeClient(lambda kw, n: json_response({"rewritten_sentence": "x"}))
try:
    repair_post.main()
finally:
    sys.argv = _orig_argv
    repair_post.anthropic.Anthropic = _orig_anthropic_client
_status_e2e_text = _status_e2e_path.read_text(encoding="utf-8")
check("repair_post.main(): 修正対象が無い日（PASS）でもGENERATION_STATUS.mdへ最終監査結果が追記される"
      "（見出しは実際に評価したチェックから作る。v1.85: C12〜C24・C26〜C28・計17項目）",
      "本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS" in _status_e2e_text, _status_e2e_text)
check("repair_post.main(): 警告が無い日はファイル先頭に警告ブロックを置かず、「警告なし」と1行で示す（v1.85）",
      _status_e2e_text.startswith("level: L0") and "向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告なし（" + _wk() + "）" in _status_e2e_text,
      _status_e2e_text)

print("=== generate_post: 呼び出しBへのdaily_data除外（v1.82・オーナー承認） ===")

import copy as _copy_v182
_dd_before_excl = _copy_v182.deepcopy(DAILY_DATA)
_dd_b = generate_post._daily_data_for_call_b(DAILY_DATA)
check("_daily_data_for_call_b: 元のdaily_dataを変更しない",
      DAILY_DATA == _dd_before_excl)
check("_daily_data_for_call_b: market.fear_greedを除く", "fear_greed" not in _dd_b["market"])
check("_daily_data_for_call_b: btc_dominance・eth_dominanceを除く",
      "btc_dominance" not in _dd_b["market"] and "eth_dominance" not in _dd_b["market"])
check("_daily_data_for_call_b: base・lp・domesticを除く",
      "base" not in _dd_b and "lp" not in _dd_b and "domestic" not in _dd_b)
check("_daily_data_for_call_b: market.market_cap・volume_24hは残す（オーナー承認の解釈）",
      _dd_b["market"].get("market_cap") == DAILY_DATA["market"]["market_cap"]
      and _dd_b["market"].get("volume_24h") == DAILY_DATA["market"]["volume_24h"])
check("_daily_data_for_call_b: assets（価格・24時間比）・target_date_jst等は残す",
      _dd_b["assets"] == DAILY_DATA["assets"] and _dd_b["target_date_jst"] == DAILY_DATA["target_date_jst"])
check("_daily_data_for_call_b: 存在しないパスがあっても例外にならない（空dict・marketだけのdict）",
      generate_post._daily_data_for_call_b({}) == {}
      and generate_post._daily_data_for_call_b({"market": {"market_cap": "x"}}) == {"market": {"market_cap": "x"}})
check("_daily_data_for_call_b: marketがdictでない場合も例外にならない",
      generate_post._daily_data_for_call_b({"market": None, "base": {"a": 1}}) == {"market": None})

_ub = json.loads(generate_post._build_call_b_user_content(DAILY_DATA, CALL_A_DATA))
check("_build_call_b_user_content: 呼び出しBへ渡すdaily_dataにFear&Greed・ドミナンス・base・lp・domesticが無い",
      "fear_greed" not in _ub["daily_data"]["market"]
      and "btc_dominance" not in _ub["daily_data"]["market"]
      and not ({"base", "lp", "domestic"} & set(_ub["daily_data"])))
check("_build_call_b_user_content: 除外項目の値が文字列としても混入していない",
      "Neutral" not in json.dumps(_ub, ensure_ascii=False)
      and "58.79%" not in json.dumps(_ub, ensure_ascii=False)
      and "Base 0.05%プール" not in json.dumps(_ub, ensure_ascii=False))
_ua, _, _ = generate_post._build_call_a_user_content(DAILY_DATA, NEWS_TODAY, None, 0.5)
_ua_dd = json.loads(_ua)["daily_data"]
check("_build_call_a_user_content: 呼び出しA側のdaily_dataは除外しない（変更対象外・v1.82）",
      "fear_greed" in _ua_dd["market"] and "base" in _ua_dd and "lp" in _ua_dd)

print("=== generate_post: 材料が無い日のpart2_flowを定型文へ確定（v1.82・オーナー承認） ===")

check("_has_adopted_material: 呼び出しA失敗（None）は材料なし", generate_post._has_adopted_material(None) is False)
check("_has_adopted_material: 定型文ヘッドライン＋定型文pointsのみは材料なし",
      generate_post._has_adopted_material(
          {"part1_headline": generate_post.FIXED_HEADLINE, "part1_points": [generate_post.FIXED_POINTS]}) is False)
check("_has_adopted_material: 実文言ヘッドラインがあれば材料あり",
      generate_post._has_adopted_material(CALL_A_DATA) is True)
check("_has_adopted_material: ヘッドラインが定型文でも実文言のpointsがあれば材料あり",
      generate_post._has_adopted_material(
          {"part1_headline": generate_post.FIXED_HEADLINE, "part1_points": ["A社が提携を発表（Reuters、2026-08-17）"]}) is True)

_model_flow = {"part2_flow": ["市場データから作文した流れ。"], "part2_summary": "地合いは不透明。"}
_c_nomat = FakeClient(lambda kw, n: json_response(_model_flow))
_o_nomat = generate_post.call_b(_c_nomat, DAILY_DATA, None)
check("call_b: 呼び出しA失敗（None）ならモデルが作文しても part2_flow を定型文1件へ確定する",
      _o_nomat.ok and _o_nomat.data["part2_flow"] == [generate_post.FIXED_FLOW], str(_o_nomat.data))
check("call_b: 定型文へ確定してもpart2_summaryはモデル出力のまま",
      _o_nomat.data["part2_summary"] == "地合いは不透明。")

_a_fixed = {"part1_headline": generate_post.FIXED_HEADLINE, "part1_points": [generate_post.FIXED_POINTS],
            "reusable_for_summary": []}
_c_fixed = FakeClient(lambda kw, n: json_response(_model_flow))
_o_fixed = generate_post.call_b(_c_fixed, DAILY_DATA, _a_fixed)
check("call_b: 呼び出しAが定型文のみ（材料なし）ならpart2_flowを定型文1件へ確定する",
      _o_fixed.data["part2_flow"] == [generate_post.FIXED_FLOW], str(_o_fixed.data))

_c_mat = FakeClient(lambda kw, n: json_response(CALL_B_DATA))
_o_mat = generate_post.call_b(_c_mat, DAILY_DATA, CALL_A_DATA)
check("call_b: 材料がある日はモデルのpart2_flowをそのまま使う（定型文へ上書きしない）",
      _o_mat.data["part2_flow"] == CALL_B_DATA["part2_flow"], str(_o_mat.data))
check("call_b: 実際のリクエストに除外項目（Fear&Greed値・ドミナンス）が含まれない",
      "Neutral" not in _c_mat.messages.calls[0]["messages"][0]["content"]
      and "58.79%" not in _c_mat.messages.calls[0]["messages"][0]["content"])

print("=== generate_post.py: CALL_B_INSTRUCTIONS（v1.82・統合運用基準§3.3書式・材料なしの定型文。オーナー承認） ===")
_CBI = generate_post.CALL_B_INSTRUCTIONS
check("CALL_B_INSTRUCTIONS: 材料が無い日はFIXED_FLOWのみとし市場データから流れを作文しない旨が明記される",
      "市場データから流れを作文しない" in _CBI and generate_post.FIXED_FLOW in _CBI)
check("CALL_B_INSTRUCTIONS: 定型文が統合運用基準の指定どおりの文言である",
      generate_post.FIXED_FLOW == "価格変動との関係を確認できる主要材料は確認できない。")
check("CALL_B_INSTRUCTIONS: §3.3の4段階の書式（【出来事・ニュース】→【地政学・マクロの変化】→"
      "【中間市場指標・市場心理】→【暗号通貨価格】）が指定される",
      "【出来事・ニュース】" in _CBI and "【地政学・マクロの変化】" in _CBI
      and "【中間市場指標・市場心理】" in _CBI and "【暗号通貨価格】" in _CBI
      and _CBI.index("【出来事・ニュース】") < _CBI.index("【地政学・マクロの変化】")
      < _CBI.index("【中間市場指標・市場心理】"))
check("CALL_B_INSTRUCTIONS: 複数の連鎖を①②③で区切る旨と最大3本の旨が明記される",
      "①②③" in _CBI and "最大3本" in _CBI)
check("CALL_B_INSTRUCTIONS: 各連鎖の末尾に「可能性」「因果は未確認」等の限定を置く旨が明記される",
      "各連鎖の末尾" in _CBI and "因果は未確認" in _CBI and "可能性" in _CBI)
check("CALL_B_INSTRUCTIONS: 根拠が1系統の日は無理に数を埋めない旨が明記される",
      "無理に数を埋めず" in _CBI)
check("CALL_B_INSTRUCTIONS: part2_summaryは1〜2文・価格等に触れない旨が明記される（提案どおり承認）",
      "1〜2文" in _CBI and "価格・24時間比・" in _CBI and "Fear & Greed・DEX・APR・LP助言には触れない" in _CBI)
check("CALL_B_INSTRUCTIONS: 入力のdaily_dataから除外項目を除いた旨が説明される",
      "除外したもの" in _CBI)
check("CALL_B_INSTRUCTIONS: 出力形式のJSON例が正しい（f-string化後も波括弧が壊れていない）",
      '{ "part2_flow": ["...", "..."], "part2_summary": "..." }' in _CBI)

print("=== compose_post._render_flow（v1.82・①②③区切りの描画・オーナー承認） ===")
check("_render_flow: 定型文1件のみは箇条書き記号なしの定型文そのものを返す",
      compose_post._render_flow([generate_post.FIXED_FLOW]) == generate_post.FIXED_FLOW)
check("_render_flow: ①で始まる連鎖には「・」を付けない",
      compose_post._render_flow(["①A → B → C（因果は未確認）。", "②D → E（可能性）。"])
      == "①A → B → C（因果は未確認）。\n②D → E（可能性）。")
check("_render_flow: ①②③を持たない従来形式の連鎖には従来どおり「・」を付ける",
      compose_post._render_flow(["規制当局の発言 → 上昇（因果は未確認）。"])
      == "・規制当局の発言 → 上昇（因果は未確認）。")
check("_render_flow: 定型文と同じ文言でも複数件の一部なら通常の箇条書き",
      compose_post._render_flow([generate_post.FIXED_FLOW, "X。"])
      == f"・{generate_post.FIXED_FLOW}\n・X。")

_gen_fixedflow = {"level": "L0", "call_a": {"ok": True, "data": {**CALL_A_DATA, "part1_headline": generate_post.FIXED_HEADLINE,
                                                                   "part1_points": [generate_post.FIXED_POINTS]}},
                  "call_b": {"ok": True, "data": {"part2_flow": [generate_post.FIXED_FLOW], "part2_summary": "地合いは不透明。"}}}
_b_fixedflow = compose_post.compose(DAILY_DATA, _gen_fixedflow)
check("compose(): 材料が無い日の【市場のフロー】は定型文のみで描画される（「・」が付かない）",
      f"【市場のフロー】\n{generate_post.FIXED_FLOW}" in _b_fixedflow["part2_md"]
      and f"・{generate_post.FIXED_FLOW}" not in _b_fixedflow["part2_md"], _b_fixedflow["part2_md"])
_gen_numbered = {"level": "L0", "call_a": {"ok": True, "data": CALL_A_DATA},
                 "call_b": {"ok": True, "data": {"part2_flow": ["①【出来事・ニュース】A → 【暗号通貨価格】BTCは同時期に上昇（因果は未確認）。",
                                                                "②【出来事・ニュース】B → 【暗号通貨価格】ETHは同時期に軟調（可能性）。"],
                                                 "part2_summary": "地合いは不透明。"}}}
_b_numbered = compose_post.compose(DAILY_DATA, _gen_numbered)
check("compose(): ①②③で始まる連鎖は「・①」にならず「①」で始まる行として描画される",
      "\n①【出来事・ニュース】" in _b_numbered["part2_md"] and "・①" not in _b_numbered["part2_md"]
      and "\n②【出来事・ニュース】" in _b_numbered["part2_md"], _b_numbered["part2_md"])

print("=== verify_post: C24 バックリファレンス先にpart1_headlineを含める（v1.82・オーナー承認） ===")
_au_c24h = verify_post.Audit()
verify_post.check_c24(_au_c24h, "①SECが規則を発表 → BTCは同時期に上昇（因果は未確認）。",
                      generate_post.FIXED_POINTS, "SECが規則見直しを発表しました。")
check("check_c24: 材料が1件でpart1_pointsが定型文でも、固有名詞がpart1_headlineにあればPASS（v1.82）",
      _au_c24h.checks[0]["result"] == "PASS", str(_au_c24h.checks[0]))
_au_c24i = verify_post.Audit()
verify_post.check_c24(_au_c24i, "①SECが規則を発表 → BTCは同時期に上昇（因果は未確認）。",
                      generate_post.FIXED_POINTS, generate_post.FIXED_HEADLINE)
check("check_c24: part1_headline・part1_pointsのどちらにも無い固有名詞はFAIL（従来どおり）",
      _au_c24i.checks[0]["result"] == "FAIL", str(_au_c24i.checks[0]))
_au_c24j = verify_post.Audit()
verify_post.check_c24(_au_c24j, "SECが規則を発表 → BTCは上昇（因果は未確認）。", "・SECが規則見直しを提案")
check("check_c24: part1_headline省略（既定None）でも従来どおり動く（後方互換）",
      _au_c24j.checks[0]["result"] == "PASS", str(_au_c24j.checks[0]))

print("=== verify_post: C28 ヘッドラインの銘柄名×値動き語の同一文判定（v1.82・オーナー承認） ===")
_c28_cases = [
    ("BTC・ETHは軟調に推移した。", False),  # 値動き語なし（「軟調」は語一覧外）→PASS（限界として開示）
    ("BTCが上昇した。", True),
    ("ETHは反発した。", True),
    ("BNBが下落した。", True),
    ("ビットコインは横ばいとなった。", True),
    ("イーサリアムが反落した。", True),
    ("米金利上昇でBTCは軟調推移。", True),  # 「上昇」と「BTC」が同一文
    ("米規制当局の発言が確認されました。", False),
    ("米金利が上昇した。BTCは静かな一日だった。", False),  # 文が分かれていれば対象外
]
for _hl, _expect in _c28_cases:
    _au = verify_post.Audit()
    verify_post.check_c28(_au, _hl, "・材料A", DAILY_DATA)
    check(f"check_c28: ヘッドライン「{_hl}」→ {'FAIL' if _expect else 'PASS'}",
          (_au.checks[0]["result"] == "FAIL") == _expect, str(_au.checks[0]))

_au_c28s = verify_post.Audit()
verify_post.check_c28(_au_c28s, "BTCが上昇した。", "・材料A", DAILY_DATA)
check("check_c28: 銘柄×値動き語FAILのdetailに理由（同一文・allowlist登録案内）が含まれる",
      "銘柄名と値動き語" in _au_c28s.checks[0]["detail"] and "c28_allowlist.json" in _au_c28s.checks[0]["detail"],
      _au_c28s.checks[0]["detail"])

_au_c28t = verify_post.Audit()
verify_post.check_c28(_au_c28t, "米規制当局の発言が確認されました。", "・BTCが上昇した（Reuters）", DAILY_DATA)
check("check_c28: 銘柄×値動き語の判定はヘッドラインのみに適用し、主要なポイントには適用しない（オーナー指示）",
      _au_c28t.checks[0]["result"] == "PASS", str(_au_c28t.checks[0]))

_au_c28u = verify_post.Audit()
verify_post.check_c28(_au_c28u, "ABTCDEが上昇した。", "・材料A", DAILY_DATA)
check("check_c28: 英字の一部一致（ABTCDE内のBTC）は銘柄名として扱わない（ASCII英数字との連結は除外）",
      _au_c28u.checks[0]["result"] == "PASS", str(_au_c28u.checks[0]))

check("_find_headline_symbol_move_sentences: allowlistの文字列を含む文は除外される（日付限定allowlistの仕組み）",
      verify_post._find_headline_symbol_move_sentences("BTCが上昇した。", {"BTCが上昇"}) == []
      and len(verify_post._find_headline_symbol_move_sentences("BTCが上昇した。", set())) == 1)

_c28_allow_path = REPO / "config" / "c28_allowlist.json"
check("config/c28_allowlist.json が存在し有効なJSON（exceptionsは空配列）",
      _c28_allow_path.exists() and json.loads(_c28_allow_path.read_text(encoding="utf-8")).get("exceptions") == [])
check("_load_allowlist: c28_allowlist.jsonを読み込める（該当日の登録が無ければ空集合）",
      verify_post._load_allowlist("2026-08-17", "c28_allowlist.json") == set())

_b_c28h = json.loads(json.dumps(b_ok))
_b_c28h["sections"]["part1_headline"] = "米金利上昇でBTCは軟調推移。"
_au_c28h = verify_post.run_all(_b_c28h, DAILY_DATA)
_c28h_check = next(x for x in _au_c28h.checks if x["id"] == "C28_headline_points_role_separation")
check("run_all(): ヘッドラインの銘柄×値動き語がC28 FAILとして配線される",
      _c28h_check["result"] == "FAIL", str(_c28h_check))

print("=== verify_post: C23 バックリファレンス先にpart1_headlineを含める（v1.82・オーナー承認） ===")
_au_c23h = verify_post.Audit()
verify_post.check_c23(_au_c23h, "FRBの動向を注視していきます。", "・某社が提携を発表（Reuters）", [], [],
                      "FRBが利上げに動く可能性が報じられました。")
check("check_c23: 総括の固有名詞がヘッドラインにのみ存在する場合はPASS（9/23試験のFRB型・v1.82）",
      _au_c23h.checks[0]["result"] == "PASS", str(_au_c23h.checks[0]))
_au_c23i = verify_post.Audit()
verify_post.check_c23(_au_c23i, "FRBの動向を注視していきます。", "・某社が提携を発表（Reuters）", [], [],
                      generate_post.FIXED_HEADLINE)
check("check_c23: ヘッドラインにも本文にも無い固有名詞は従来どおりFAIL（新規持ち出しの検知は維持）",
      _au_c23i.checks[0]["result"] == "FAIL" and "FRB" in _au_c23i.checks[0]["detail"], str(_au_c23i.checks[0]))
_au_c23j = verify_post.Audit()
verify_post.check_c23(_au_c23j, "FRBの動向を注視していきます。", "・某社が提携を発表（Reuters）", [], [])
check("check_c23: part1_headline省略（既定None）でも従来どおり動く（後方互換・FRBが無ければFAIL）",
      _au_c23j.checks[0]["result"] == "FAIL", str(_au_c23j.checks[0]))
_au_c23k = verify_post.Audit()
verify_post.check_c23(_au_c23k, "BitMartの動向を注視。", "・某社が提携を発表（Reuters）", [], [], "FRBが利上げに動く可能性が報じられました。")
check("check_c23: ヘッドラインに別の固有名詞があっても、総括の別の未確認固有名詞（BitMart）はFAIL",
      _au_c23k.checks[0]["result"] == "FAIL" and "BitMart" in _au_c23k.checks[0]["detail"], str(_au_c23k.checks[0]))

# run_all()経由の配線確認（ヘッドラインのみにFRBがある構成）
_b_c23h = json.loads(json.dumps(b_ok))
_b_c23h["sections"]["part1_headline"] = "FRBが利上げに動く可能性が報じられました。暗号通貨価格への直接因果は未確認です。"
_b_c23h["sections"]["part2_summary"] = "地合いは不透明です。今後はFRBの動向を確認していく必要があります。"
_au_c23run = verify_post.run_all(_b_c23h, DAILY_DATA)
_c23run = next(x for x in _au_c23run.checks if x["id"] == "C23_summary_no_new_entities")
check("run_all(): part1_headlineがcheck_c23へ配線され、ヘッドラインのみのFRBを総括で言及してもPASS（v1.82）",
      _c23run["result"] == "PASS", str(_c23run))
_b_c23h2 = json.loads(json.dumps(b_ok))
_b_c23h2["sections"]["part1_headline"] = generate_post.FIXED_HEADLINE
_b_c23h2["sections"]["part2_summary"] = "地合いは不透明です。今後はFRBの動向を確認していく必要があります。"
_au_c23run2 = verify_post.run_all(_b_c23h2, DAILY_DATA)
_c23run2 = next(x for x in _au_c23run2.checks if x["id"] == "C23_summary_no_new_entities")
check("run_all(): ヘッドライン・本文とも根拠が無いFRBの総括はFAIL（従来どおり）",
      _c23run2["result"] == "FAIL", str(_c23run2))

print("=== verify_post: C23 機関名の同義語照合（案C・v1.83・オーナー承認。案B〈無条件の許可リスト〉は不採用） ===")

def _c23(summary, points="・某社が提携を発表（Reuters）", reusable=None, sched=None, headline=None):
    au = verify_post.Audit()
    verify_post.check_c23(au, summary, points, reusable or [], sched or [], headline)
    return au.checks[0]

# オーナー指定の同義語（少なくとも含める）を機関ごとに定義（日本語表記は「本文側の表記」として使う）
_OWNER_ALIASES = {
    "Fed": ["Fed", "FRB", "FOMC", "連邦準備制度", "米連邦準備理事会"],
    "SEC": ["SEC", "証券取引委員会"],
    "CFTC": ["CFTC", "商品先物取引委員会"],
    "BOJ": ["BOJ", "日銀", "日本銀行"],
    "ECB": ["ECB", "欧州中央銀行"],
    "BOE": ["BOE", "英中銀", "イングランド銀行"],
}
# 総括側（ASCII略称）: 同義グループごとの略称
_SUMMARY_ABBRS = {"Fed": ["Fed", "FRB", "FOMC"], "SEC": ["SEC"], "CFTC": ["CFTC"], "BOJ": ["BOJ"], "ECB": ["ECB"], "BOE": ["BOE"]}

_bad = []
for _grp, _terms in _OWNER_ALIASES.items():
    for _abbr in _SUMMARY_ABBRS[_grp]:
        for _term in _terms:
            _r = _c23(f"今後は{_abbr}の動向を確認します。", points=f"・{_term}が発表しました（Reuters）")
            if _r["result"] != "PASS":
                _bad.append((_abbr, _term, _r["detail"][:60]))
check("C23同義語: オーナー指定の同義語（Fed・FRB・FOMC・連邦準備制度・米連邦準備理事会／SEC・証券取引委員会／"
      "CFTC・商品先物取引委員会／BOJ・日銀・日本銀行／ECB・欧州中央銀行／BOE・英中銀・イングランド銀行）が"
      "同じ機関の表記として照合先で確認済みになる（総括の略称×本文の表記の全組合せ）", not _bad, str(_bad))

_bad = []
_groups = list(_OWNER_ALIASES)
for _g1 in _groups:
    for _g2 in _groups:
        if _g1 == _g2:
            continue
        for _abbr in _SUMMARY_ABBRS[_g1]:
            for _term in _OWNER_ALIASES[_g2]:
                _r = _c23(f"今後は{_abbr}の動向を確認します。", points=f"・{_term}が発表しました（Reuters）")
                if _r["result"] != "FAIL":
                    _bad.append((_abbr, _term))
check("C23同義語: 別の機関の表記では確認済みにならない（例: 本文がFRB・日銀等の日に総括がSEC・ECB等と書けばFAIL。全組合せ）",
      not _bad, str(_bad[:5]))

for _abbr in ("Fed", "FRB", "SEC", "CFTC", "BOJ", "ECB", "BOE", "FOMC"):
    _r = _c23(f"今後は{_abbr}の動向を確認します。")
    check(f"C23同義語: 案B不採用の回帰確認——本文に同じ機関の記述が無ければ{_abbr}は従来どおりFAIL（無条件の許可リストではない）",
          _r["result"] == "FAIL" and _abbr in _r["detail"], str(_r))

_r = _c23("SECの動向と米PCEインフレ指標を確認します。")
check("C23同義語: 8/26型（本文に無いSECとPCEを総括が持ち出す）はSEC・PCEともFAIL（真の新規持ち出しの検知を維持）",
      _r["result"] == "FAIL" and "SEC" in _r["detail"] and "PCE" in _r["detail"], str(_r))

_r = _c23("FRBの動向を確認します。", points="・FedExが提携を発表（Reuters）")
check("C23同義語: 英字の同義語はASCII英数字に挟まれない場合のみ一致（FedEx内のFedはFRBの根拠にならない）",
      _r["result"] == "FAIL", str(_r))
# 注意: 総括の略称が本文の英語正式名称の部分文字列になる組（Fed⊂Federal）は、従来の部分一致だけでも
# PASSするため同義語の検証にならない。部分文字列にならない組で検証する（独立レビューの指摘: 旧テストは空虚）。
_ENG_FULL = {"FRB": "Federal Reserve", "SEC": "Securities and Exchange Commission",
             "CFTC": "Commodity Futures Trading Commission", "BOJ": "Bank of Japan",
             "ECB": "European Central Bank", "BOE": "Bank of England", "FOMC": "Federal Reserve"}
_bad = [(a, t) for a, t in _ENG_FULL.items()
        if _c23(f"{a}の動向を確認します。", points=f"・{t}が声明を発表（Reuters）")["result"] != "PASS"]
check("C23同義語: 英語の正式名称（Federal Reserve・Securities and Exchange Commission・Bank of Japan等）も"
      "本文側の同義語として確認済みにできる（略称が正式名称の部分文字列にならない組で検証）", not _bad, str(_bad))
check("C23同義語: 「連邦公開市場委員会」（FOMCの日本語表記）で総括のFOMCが確認済みになる",
      _c23("FOMCの動向を確認します。", points="・連邦公開市場委員会が声明を発表（Reuters）")["result"] == "PASS")
_bad = [(a, t) for a, t in (("BOE", "BoE"), ("BOJ", "BoJ"), ("Fed", "FED"), ("FED", "FRB"), ("BoE", "BOE"), ("BoJ", "日銀"))
        if _c23(f"{a}の動向を確認します。", points=f"・{t}が発表（Reuters）")["result"] != "PASS"]
check("C23同義語: 英語報道で一般的な大文字小文字の表記ゆれ（BoJ・BoE・FED）も同義語として扱う（独立レビューの指摘への対処）",
      not _bad, str(_bad))
_r = _c23("BOEの動向を確認します。", points="・sec 秒あたり fed された（Reuters）")
_r2 = _c23("SECの動向を確認します。", points="・fed と sec と frb の小文字")
check("C23同義語: 本文の小文字（sec＝秒・fed＝動詞・frb）はSEC・BOE等の根拠にならない（全面的なIGNORECASEにしていない理由の回帰確認）",
      _r["result"] == "FAIL" and _r2["result"] == "FAIL", f"{_r} {_r2}")
_r = _c23("FRBXの動向を確認します。", points="・FRBが声明を発表（Reuters）")
check("C23同義語: 総括側の候補が別語（FRBX）なら同義語の対象外（候補のキーは完全一致・境界を守る）",
      _r["result"] == "FAIL" and "FRBX" in _r["detail"], str(_r))
_r = _c23("SECとCFTCの動向を確認します。", points="・米証券取引委員会が規則案を公表（Reuters）")
check("C23同義語: 混在ケース——SECは同義語で確認済み・CFTCは根拠なしなら、CFTCだけがFAIL詳細に列挙される",
      _r["result"] == "FAIL" and "CFTC" in _r["detail"] and "SEC'" not in _r["detail"].replace("CFTC'", ""), str(_r))
_r = _c23("FRBの動向を確認します。", points="・FRBXが提携（Reuters）")
check("C23同義語: 英字の同義語はASCII英数字に挟まれる場合は一致しない（FRBXはFRBの根拠にならないが、候補FRBの従来の部分一致は成立）",
      _r["result"] == "PASS" and verify_post._alias_in_text("FRB", "FRBX") is False
      and verify_post._alias_in_text("FRB", "x FRB。") is True and verify_post._alias_in_text("FRB", "9FRB") is False)


check("C23同義語: ヘッドラインの別表記（連邦準備制度理事会）でも総括のFedが確認済みになる（9/29型の仮説(a)+(b)）",
      _c23("Fedの動向を確認します。", headline="米連邦準備制度理事会（FRB）が利上げに動く可能性が報じられました。")["result"] == "PASS")
check("C23同義語: 継続監視材料（reusable_for_summary）の別表記でも確認済みになる",
      _c23("SECの動向を確認します。", reusable=["米証券取引委員会が規則案を公表（CoinDesk、継続監視）"])["result"] == "PASS")
check("C23同義語: 経済カレンダー（scheduled_events）のtitleの別表記でも確認済みになる",
      _c23("BOEの動向を確認します。", sched=[{"title": "イングランド銀行 総裁講演"}])["result"] == "PASS")

check("C23同義語: 従来の判定（候補の文字列そのものが照合先に部分一致）は維持される（既存より厳しくならない）",
      _c23("Bitmineの動向を確認します。", points="・Bitmineが発表（Bloomberg）")["result"] == "PASS"
      and _c23("Bitmineの動向を確認します。")["result"] == "FAIL")
check("C23同義語: 同義語グループに無い固有名詞（BitMart等）は従来どおり同義語で救済されない",
      _c23("BitMartの動向を確認します。", points="・FRBが声明を発表（Reuters）")["result"] == "FAIL")
check("C23同義語: 末尾に句読点相当（. - &）が付いた候補（SEC.）も同義語で照合できる",
      verify_post._is_backed("SEC.", "・米証券取引委員会が提案") is True
      and verify_post._is_backed("XYZ.", "・米証券取引委員会が提案") is False)

_al = verify_post._INSTITUTION_ALIAS_GROUPS
check("C23同義語: 同義語グループの定義にオーナー指定の表記がすべて含まれる（連邦準備は連邦準備制度・"
      "米連邦準備理事会を部分一致で包含）",
      all(any(t in a or a in t for a in g) for gname, terms in _OWNER_ALIASES.items() for t in terms
          for g in _al if gname in g), str(_al))

# run_all()経由の配線確認（総括のFedを、本文の日本語表記で確認）
_b_alias = json.loads(json.dumps(b_ok))
_b_alias["sections"]["part1_points"] = "・米連邦準備制度理事会が声明を発表しました（Reuters、2026-08-17）"
_b_alias["sections"]["part1_headline"] = generate_post.FIXED_HEADLINE
_b_alias["sections"]["part2_summary"] = "地合いは不透明です。今後はFedの動向を確認していく必要があります。"
_au_alias = verify_post.run_all(_b_alias, DAILY_DATA)
_c23_alias = next(x for x in _au_alias.checks if x["id"] == "C23_summary_no_new_entities")
check("run_all(): 総括のFedが本文の日本語表記（米連邦準備制度理事会）で確認済みになりC23 PASS（v1.83）",
      _c23_alias["result"] == "PASS", str(_c23_alias))
_b_alias2 = json.loads(json.dumps(_b_alias))
_b_alias2["sections"]["part1_points"] = "・某社が提携を発表しました（Reuters、2026-08-17）"
_au_alias2 = verify_post.run_all(_b_alias2, DAILY_DATA)
_c23_alias2 = next(x for x in _au_alias2.checks if x["id"] == "C23_summary_no_new_entities")
check("run_all(): 本文にFRB系の記述が無ければ総括のFedは従来どおりC23 FAIL（v1.83）",
      _c23_alias2["result"] == "FAIL", str(_c23_alias2))

print("=== capture_apr.py: 失敗時の診断と追加試行（v1.83・オーナー承認。9/29のAPR撮影失敗への対処。独立レビューの指摘を反映） ===")

import io as _io_apr
import contextlib as _ctx_apr
import re as _re_apr
import subprocess as _sp_apr
import capture_apr  # noqa: E402
import playwright.sync_api as _pw_sync_api  # noqa: E402

_OK_BODY = "ETH / USDC\n" + "\n".join("Card TODAY" for _ in range(6))
_FAIL_BODY = "ETH / USDC V3\nError: HTTP 503\nDefiLlama APIへの接続に失敗しました。"


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Boom:
    def __str__(self):
        return "boom"


class _FakePage:
    """Playwright同期APIのpageのフェイク。実際のAPIと同様に、ブラウザのイベントは「APIを呼んだ時」に
    まとめて通知する（time.sleep中には通知されない）。screenshot/inner_textを呼ぶたびに次のスクリプト
    （body・その時点で届いているイベント）を消費する。"""

    def __init__(self, script, initial_events=(), goto_failures=(), on_raises=False,
                 screenshot_raises_at=None, timeline=None):
        self.script = list(script)
        self.initial_events = list(initial_events)
        self.handlers = {}
        self.pending = []           # 届いているが、まだ通知されていないイベント
        self.goto_calls = []
        self.goto_failures = set(goto_failures)
        self.on_raises = on_raises
        self.shots = 0
        self.clicks = 0
        self.flushes = 0
        self.closed = 0
        self.screenshot_raises_at = screenshot_raises_at
        self.timeline = timeline if timeline is not None else []
        self._current = None

    def _dispatch(self):
        ev, self.pending = self.pending, []
        for name, obj in ev:
            if name in self.handlers:
                self.handlers[name](obj)

    def on(self, name, handler):
        if self.on_raises:
            raise RuntimeError("listener registration unsupported")
        self.handlers[name] = handler

    def goto(self, url, **kw):
        self.timeline.append("goto")
        self.goto_calls.append(url)
        if len(self.goto_calls) in self.goto_failures:
            raise RuntimeError("net::ERR_TIMED_OUT")
        if len(self.goto_calls) == 1:
            self.pending += self.initial_events
        self._dispatch()

    def locator(self, sel):
        page = self

        class _L:
            def click(self, timeout=None):
                page.timeline.append("click")
                page.clicks += 1
                page._dispatch()

        return _L()

    def wait_for_timeout(self, ms):
        self.flushes += 1
        self._dispatch()

    def screenshot(self, path):
        self.timeline.append("shot")
        self.shots += 1
        if self.screenshot_raises_at == self.shots:
            raise RuntimeError("browser crashed")
        self._current = self.script.pop(0) if self.script else (_FAIL_BODY, [])
        Path(path).write_bytes(b"PNG")

    def inner_text(self, sel):
        body, events = self._current
        self.pending += events
        self._dispatch()
        return body


def _run_capture(page, tag, diag=True, on_sleep=None):
    """フェイクplaywrightでcapture_apr.capture()を実行し、(戻り値, 出力, sleep記録, diagディレクトリ, browser)を返す。
    on_sleep(sec)は待機のたびに呼ばれる（待機中にブラウザへイベントが届く状況を再現する）。"""
    sleeps = []
    real_pw, real_sleep = _pw_sync_api.sync_playwright, capture_apr.time.sleep
    closed = {"n": 0}

    class _Browser:
        def new_page(self, viewport=None):
            return page

        def close(self):
            closed["n"] += 1

    class _PW:
        firefox = _Obj(launch=lambda headless=True: _Browser())

    class _CM:
        def __enter__(self):
            return _PW()

        def __exit__(self, *a):
            return False

    def _sleep(sec):
        sleeps.append(sec)
        page.timeline.append(("sleep", sec))
        if on_sleep:
            on_sleep(sec)

    _pw_sync_api.sync_playwright = lambda: _CM()
    capture_apr.time.sleep = _sleep
    buf = _io_apr.StringIO()
    d = Path(SCRATCH) / f"apr_diag_{tag}"
    try:
        with _ctx_apr.redirect_stdout(buf):
            res = capture_apr.capture(str(Path(SCRATCH) / f"apr_full_{tag}.png"), d if diag else None)
    except Exception as e:  # noqa: BLE001
        res = e
    finally:
        _pw_sync_api.sync_playwright, capture_apr.time.sleep = real_pw, real_sleep
    return res, buf.getvalue(), sleeps, d, closed["n"]


def _snaps(d):
    return json.loads((d / "apr_diagnostics.json").read_text(encoding="utf-8"))["snapshots"]


check("capture_apr: オーナー承認の定数（標準3試行・追加2試行・追加前の待機60秒・Refresh後8/12/16秒）",
      capture_apr.MAX_RETRY == 3 and capture_apr.EXTRA_ATTEMPTS == 2 and capture_apr.EXTRA_COOLDOWN == 60
      and capture_apr.WAIT_AFTER_REFRESH_SCHEDULE == (8, 12, 16))

# 1) 1回目で成功
_pg = _FakePage([(_OK_BODY, [])])
_res, _out, _sl, _d, _cl = _run_capture(_pg, "ok1")
check("capture: 1回目で成功なら(True,'',1)・60秒待機なし・再読み込みなし・診断ファイルなし・browser.closeが1回",
      _res == (True, "", 1) and 60 not in _sl and len(_pg.goto_calls) == 1 and not _d.exists() and _cl == 1
      and _pg.clicks == 1, f"{_res} {_sl} {_pg.goto_calls} close={_cl}")

# 2) 標準の2回失敗→3回目で成功
_pg = _FakePage([(_FAIL_BODY, []), (_FAIL_BODY, []), (_OK_BODY, [])])
_res, _out, _sl, _d, _cl = _run_capture(_pg, "ok3")
check("capture: 標準の3回目で成功なら(True,'',3)・60秒待機なし・再読み込みなし・Refreshクリック3回・browser.closeが1回",
      _res == (True, "", 3) and 60 not in _sl and len(_pg.goto_calls) == 1 and _pg.clicks == 3 and _cl == 1, f"{_res} {_sl}")
check("capture: 失敗した試行の画像と診断JSONだけが診断ディレクトリへ保存される（成功した試行の画像は保存しない）",
      sorted(x.name for x in _d.glob("*")) == ["apr_diagnostics.json", "apr_failed_attempt1.png", "apr_failed_attempt2.png"],
      str(sorted(x.name for x in _d.glob("*"))))

# 3) 標準3回失敗→追加1回目で成功
_pg = _FakePage([(_FAIL_BODY, [])] * 3 + [(_OK_BODY, [])])
_res, _out, _sl, _d, _cl = _run_capture(_pg, "extra1")
check("capture: 標準3回失敗→追加1回目で成功なら(True,'',4)・60秒待機が1回・再読み込み(goto)が追加で1回・browser.closeが1回",
      _res == (True, "", 4) and _sl.count(60) == 1 and len(_pg.goto_calls) == 2 and _cl == 1, f"{_res} {_sl} {_pg.goto_calls}")
check("capture: 追加試行の出力に「追加試行 1/2」と「4回目の試行で成功」が出る",
      "[追加試行 1/2] 60秒空けてページを再読み込み" in _out and "4回目の試行で成功" in _out, _out[-400:])

# 4) 全5回失敗: 待機・操作の順序（60秒待機→再読み込み→3秒→Refreshクリック→16秒待機→撮影）を厳密に検証
_pg = _FakePage([(_FAIL_BODY, [])] * 5)
_res, _out, _sl, _d, _cl = _run_capture(_pg, "allfail")
check("capture: 標準3＋追加2の全5回失敗なら(False, 判定内訳, 5)・browser.closeが1回・Refreshクリック5回",
      isinstance(_res, tuple) and _res[0] is False and _res[2] == 5 and "TODAY件数: 0/6" in _res[1] and _cl == 1 and _pg.clicks == 5, f"{_res}")
_expected = ["goto", ("sleep", 3), "click", ("sleep", 8), "shot", ("sleep", 3),
             "click", ("sleep", 12), "shot", ("sleep", 3),
             "click", ("sleep", 16), "shot",
             ("sleep", 60), "goto", ("sleep", 3), "click", ("sleep", 16), "shot",
             ("sleep", 60), "goto", ("sleep", 3), "click", ("sleep", 16), "shot"]
check("capture: 操作の順序と待機秒が承認内容どおり（初回読込→3秒→[Refresh→8/12/16秒→撮影→標準間3秒]×3→"
      "[60秒→再読み込み→3秒→Refresh→16秒→撮影]×2）", _pg.timeline == _expected, str(_pg.timeline))
check("capture: 全失敗時は失敗画像5枚と診断JSON（スナップショット5件）を診断ディレクトリへ保存する",
      sorted(x.name for x in _d.glob("*.png")) == [f"apr_failed_attempt{i}.png" for i in range(1, 6)] and len(_snaps(_d)) == 5)
check("capture: 失敗画像・診断JSONは撮影画像の保存先（outputs/に相当するディレクトリ）へ漏れない（コミット禁止の不変条件）",
      not list(Path(SCRATCH).glob("apr_failed_attempt*.png")) and not (Path(SCRATCH) / "apr_diagnostics.json").exists()
      and _d.parent == Path(SCRATCH) and _d != Path(SCRATCH))

# 5) 診断の内容とログ出力
_events = [
    ("response", _Obj(url="https://yields.llama.fi/pools?x=1", status=503,
                      headers={"server": "cloudflare", "retry-after": "120", "x-other": "ignored"})),
    ("response", _Obj(url="https://api.geckoterminal.com/api/v2/networks/base/pools/0xabc", status=429, headers={"retry-after": "30"})),
    ("response", _Obj(url="https://example.com/ignored", status=200, headers={})),
    ("requestfailed", _Obj(url="https://cdnjs.cloudflare.com/x.js", failure={"errorText": "net::ERR_BLOCKED"})),
    ("requestfailed", _Obj(url="https://yields.llama.fi/pools", failure="net::ERR_CONNECTION_RESET")),
    ("console", _Obj(type="error", text="Failed to load resource: 503")),
    ("console", _Obj(type="log", text="not recorded")),
    ("pageerror", _Boom()),
]
_pg = _FakePage([(_FAIL_BODY, _events)] + [(_OK_BODY, [])])
_res, _out, _sl, _d, _cl = _run_capture(_pg, "diag")
_snap = _snaps(_d)[0]
_evs = _snap["events"]
check("診断: 画面の文字（先頭）とエラー表示（Error: HTTP 503…）を記録しログへ出す",
      "Error: HTTP 503" in (_snap["error_banner"] or "") and "ETH / USDC V3" in _snap["body_head"]
      and "エラー表示: Error: HTTP 503" in _out and "画面の文字(先頭500字): ETH / USDC V3" in _out, str(_snap)[:300])
check("診断: yields.llama.fiの応答（HTTPステータス・関連ヘッダーのみ）と要求失敗を記録しログへ出す（他ホストの応答・関係ないヘッダーは除く）",
      [e.get("status") for e in _snap["yields_llama_fi"] if e["kind"] == "response"] == [503]
      and _snap["yields_llama_fi"][0]["headers"] == {"server": "cloudflare", "retry-after": "120"}
      and any(e["kind"] == "requestfailed" and "ERR_CONNECTION_RESET" in e["failure"] for e in _snap["yields_llama_fi"])
      and "yields.llama.fi の応答: HTTP 503" in _out and "retry-after=120" in _out and "要求失敗 net::ERR_CONNECTION_RESET" in _out,
      _out[-700:])
check("診断: api.geckoterminal.comの応答も記録し、yields以外の外部要求（geckoterminal・CDNの失敗）はログの「その他の外部要求」へ出す",
      any(e["kind"] == "response" and e["status"] == 429 for e in _evs) and "その他の外部要求" in _out
      and "api.geckoterminal.com/api/v2/networks/base/pools/0xabc → HTTP 429" in _out and "ERR_BLOCKED" in _out
      and not any("example.com" in e.get("url", "") for e in _evs), _out[-700:])
check("診断: console error・ページ内例外を記録しログの「コンソール・ページ内エラー」へ出し、consoleのlog等は記録しない",
      any(e["kind"] == "console" and "503" in e["text"] for e in _evs) and any(e["kind"] == "pageerror" and e["text"] == "boom" for e in _evs)
      and "コンソール・ページ内エラー: [error] Failed to load resource: 503 / [pageerror] boom" in _out
      and not any("not recorded" in json.dumps(e, ensure_ascii=False) for e in _evs), _out[-700:])

# 応答イベントが無い場合は明記する
_pg = _FakePage([(_FAIL_BODY, [])] + [(_OK_BODY, [])])
_res, _out, _sl, _d, _cl = _run_capture(_pg, "noevt")
check("診断: yields.llama.fiの応答・失敗イベントが無い試行は「記録された応答・失敗イベントなし」とログに明記する",
      "yields.llama.fi の応答: 記録された応答・失敗イベントなし（要求が発行されていない" in _out, _out[-500:])

# 6) 試行ごとのイベントの切り分け（初回読み込みのイベントは試行1へ含め、試行2には含めない）
_init_ev = [("response", _Obj(url="https://yields.llama.fi/pools", status=502, headers={}))]
_pg = _FakePage([(_FAIL_BODY, [])] * 2 + [(_OK_BODY, [])], initial_events=_init_ev)
_res, _out, _sl, _d, _cl = _run_capture(_pg, "slice")
_sn = _snaps(_d)
check("診断: 最初のページ読み込み（attempt 0）の応答は試行1のスナップショットに含め、試行2には含めない",
      [e["status"] for e in _sn[0]["yields_llama_fi"]] == [502] and _sn[1]["yields_llama_fi"] == [], str(_sn)[:400])

# 7) 待機中に届いたイベントは直前の試行のものとして受け取る（試行間の帰属・flush）
_late = [("response", _Obj(url="https://yields.llama.fi/pools", status=504, headers={}))]
_late_state = {"c": 0}
def _on_sleep_late(sec):
    # WAIT_INITIAL（最初のページ読み込み後）とWAIT_BETWEEN（標準試行間）は同じ3秒。2回目の3秒待機
    # ＝試行1の後の標準間待機の最中に、yields.llama.fiの応答がブラウザへ届く状況を再現する
    if sec == capture_apr.WAIT_BETWEEN:
        _late_state["c"] += 1
        if _late_state["c"] == 2:
            _pg_late.pending += _late
_pg_late = _FakePage([(_FAIL_BODY, [])] * 2 + [(_OK_BODY, [])])
_res, _out, _sl, _d, _cl = _run_capture(_pg_late, "late", on_sleep=_on_sleep_late)
_sn = _snaps(_d)
check("診断: 標準間の待機中に届いたイベントは、次の試行（試行2）ではなく直前の試行のものとして受け取る（flush。試行2の診断に混入しない）",
      _late_state["c"] >= 2 and _pg_late.flushes >= 1 and _sn[1]["yields_llama_fi"] == [],
      f"c={_late_state['c']} flushes={_pg_late.flushes} {_sn[1]['yields_llama_fi']}")

# 8) 種別ごと・試行ごとの上限: 雑音（consoleや他ホストの失敗）が肝心のyields応答を押し出さない・省略は明記する
_noise = [("console", _Obj(type="error", text=f"noise {i}")) for i in range(30)] + \
         [("requestfailed", _Obj(url=f"https://cdn{i}.example.com/x", failure="net::ERR")) for i in range(25)]
_noise += [("response", _Obj(url="https://yields.llama.fi/pools", status=503, headers={}))]
_pg = _FakePage([(_FAIL_BODY, _noise)] + [(_OK_BODY, [])])
_res, _out, _sl, _d, _cl = _run_capture(_pg, "caps")
_sn = _snaps(_d)[0]
check("診断: consoleの雑音が上限（20件）を超えても、yields.llama.fiの応答は別枠で記録される（押し出されない）",
      [e["status"] for e in _sn["yields_llama_fi"] if e["kind"] == "response"] == [503]
      and sum(1 for e in _sn["events"] if e["kind"] == "console") == capture_apr.DIAG_CAPS["console"], str(_sn["dropped_events"]))
check("診断: 上限超過で省略したイベントの件数をスナップショットとログに明記する",
      _sn["dropped_events"].get("console") == 10 and _sn["dropped_events"].get("requestfailed") == 5
      and "省略されたイベント（種別ごとの上限超過）: console=10件, requestfailed=5件" in _out, _out[-500:])
_full = [("requestfailed", _Obj(url=f"https://cdn{i}.example.com/x", failure="net::ERR")) for i in range(25)] + \
        [("requestfailed", _Obj(url="https://yields.llama.fi/pools", failure="net::ERR_X"))]
_pg = _FakePage([(_FAIL_BODY, _full)] + [(_OK_BODY, [])])
_res, _out, _sl, _d, _cl = _run_capture(_pg, "capsy")
check("診断: 上限超過でyieldsのイベントが省略された試行は、「要求が発行されていない」と誤誘導せず「断定できない」と明記する",
      "上限超過で6件のイベントを省略しているため、要求が無かったとは断定できない" in _out
      and "要求が発行されていない" not in _out, _out[-600:])

# 9) 診断は撮影を妨げない
_pg = _FakePage([(_FAIL_BODY, []), (_OK_BODY, [])], on_raises=True)
_res, _out, _sl, _d, _cl = _run_capture(_pg, "onraise")
check("診断: リスナー登録が失敗（page.onが例外）しても撮影は続行し成功する",
      _res == (True, "", 2) and "リスナーを登録できません" in _out, f"{_res} {_out[:200]}")
_diag_obj = capture_apr._Diagnostics(None)
_raised = False
try:
    _diag_obj._on_response(_Obj())          # 属性が欠けた不正なイベントでも例外を出さない
    _diag_obj._on_requestfailed(_Obj())
    _diag_obj._on_console(_Obj())
    _diag_obj._on_pageerror(None)
    _diag_obj.flush(_Obj())                 # wait_for_timeoutが無いオブジェクトでも例外を出さない
except Exception:  # noqa: BLE001
    _raised = True
check("診断: 不正なイベントオブジェクト・flush対象でもハンドラは例外を外へ出さない", not _raised)

_blocker = Path(SCRATCH) / "apr_diag_blocker"
_blocker.write_text("file, not a directory", encoding="utf-8")
_pg = _FakePage([(_FAIL_BODY, []), (_OK_BODY, [])])
_res, _out_b, _sl_b, _d_b, _cl_b = (None, "", [], None, 0)
_real_pw, _real_sleep = _pw_sync_api.sync_playwright, capture_apr.time.sleep
class _B2:
    def new_page(self, viewport=None): return _pg
    def close(self): pass
class _PW2: firefox = _Obj(launch=lambda headless=True: _B2())
class _CM2:
    def __enter__(self): return _PW2()
    def __exit__(self, *a): return False
_pw_sync_api.sync_playwright = lambda: _CM2()
capture_apr.time.sleep = lambda sec: None
_buf = _io_apr.StringIO()
try:
    with _ctx_apr.redirect_stdout(_buf):
        _res = capture_apr.capture(str(Path(SCRATCH) / "apr_full_blocker.png"), _blocker / "sub")  # 保存先が作れない
finally:
    _pw_sync_api.sync_playwright, capture_apr.time.sleep = _real_pw, _real_sleep
check("診断: 診断の保存先を作れなくても（ディレクトリ作成の失敗）撮影は続行し成功する",
      _res == (True, "", 2) and "診断の記録に失敗しました" in _buf.getvalue(), f"{_res} {_buf.getvalue()[-300:]}")

# 10) 追加試行中の例外は失敗した試行として扱い、診断（例外文）を残す。標準試行中の例外は従来どおり呼び出し元へ
_pg = _FakePage([(_FAIL_BODY, [])] * 5, goto_failures={2, 3})
_res, _out, _sl, _d, _cl = _run_capture(_pg, "gotofail")
check("capture: 追加試行の再読み込み(goto)が失敗してもクラッシュせず、失敗した試行として扱い(False,詳細,5)を返す・browser.closeは1回",
      isinstance(_res, tuple) and _res[0] is False and _res[2] == 5 and "追加試行" in _res[1] and "ERR_TIMED_OUT" in _res[1] and _cl == 1, f"{_res}")
_sn = _snaps(_d)
check("診断: 例外で終わった追加試行も診断（例外文の備考）をログと診断JSONへ残す（デッドコードだったnoteの出力）",
      "備考: 追加試行1で例外: RuntimeError: net::ERR_TIMED_OUT" in _out
      and any(e["kind"] == "note" and "ERR_TIMED_OUT" in e["text"] for s_ in _sn for e in s_["events"]), _out[-500:])
_pg = _FakePage([(_FAIL_BODY, [])] * 5, screenshot_raises_at=1)
_res, _out, _sl, _d, _cl = _run_capture(_pg, "stdcrash")
check("capture: 標準試行中の例外は従来どおり呼び出し元へ送出される（挙動を変えない）",
      isinstance(_res, RuntimeError), str(_res))

# 11) 状態ファイル（C25が読む）
_st_dir = Path(SCRATCH) / "apr_status_test" / "2026-09-30"
_st_dir.mkdir(parents=True, exist_ok=True)
capture_apr._write_incomplete_status(str(_st_dir / "apr_screenshot.jpg"), "TODAY件数: 0/6", 5)
_st = json.loads((_st_dir / "apr_capture_status.json").read_text(encoding="utf-8"))
check("_write_incomplete_status: attemptsに追加試行を含む実際の試行回数を記録する（既存キーstatus/attempts/detailは維持）",
      _st["status"] == "incomplete" and _st["attempts"] == 5 and _st["detail"] == "TODAY件数: 0/6"
      and _st["standard_attempts"] == 3 and _st["extra_attempts"] == 2, str(_st))

# 12) main(): 失敗時は画像なしで正常終了・状態ファイル記録・診断先はoutputs/の外
_main_dir = Path(SCRATCH) / "apr_main_test" / "outputs" / "2026-09-30"
_main_dir.mkdir(parents=True, exist_ok=True)
_out_jpg = str(_main_dir / "apr_screenshot.jpg")
_real_capture, _real_crop = capture_apr.capture, capture_apr.crop_apr_cards
_calls = {}
def _fake_capture_fail(tmp, diag_dir=None):
    _calls["diag_dir"] = diag_dir
    Path(tmp).write_bytes(b"PNG")
    return False, "TODAY件数: 0/6", 5
capture_apr.capture = _fake_capture_fail
_buf = _io_apr.StringIO()
try:
    with _ctx_apr.redirect_stdout(_buf):
        _rc = capture_apr.main([_out_jpg])
finally:
    capture_apr.capture = _real_capture
check("main(): 全試行失敗でも終了コード0（画像なしの正常終了。フェイルクローズ方針(b)は不変）・apr_screenshot.jpgは作らず一時画像は削除",
      _rc == 0 and not Path(_out_jpg).exists() and not Path(_out_jpg).with_suffix(".full.png").exists(), _buf.getvalue()[-300:])
check("main(): 失敗時はapr_capture_status.jsonへ実際の試行回数（5）を記録する",
      json.loads((_main_dir / "apr_capture_status.json").read_text(encoding="utf-8"))["attempts"] == 5)
check("main(): 診断の保存先はoutputs/の外（apr_diagnostics/<対象日>）で、outputs/配下ではない（⑤コミットの対象外）",
      Path(_calls["diag_dir"]) == Path("apr_diagnostics") / "2026-09-30"
      and "outputs" not in Path(_calls["diag_dir"]).parts, str(_calls))
_cropped = {}
def _fake_capture_ok(tmp, diag_dir=None):
    Path(tmp).write_bytes(b"PNG")
    return True, "", 1
capture_apr.capture = _fake_capture_ok
capture_apr.crop_apr_cards = lambda tmp, out: _cropped.update(tmp=tmp, out=out)
_main_dir2 = Path(SCRATCH) / "apr_main_test2" / "outputs" / "2026-09-30"
_main_dir2.mkdir(parents=True, exist_ok=True)
try:
    with _ctx_apr.redirect_stdout(_io_apr.StringIO()):
        _rc2 = capture_apr.main([str(_main_dir2 / "apr_screenshot.jpg")])
finally:
    capture_apr.capture, capture_apr.crop_apr_cards = _real_capture, _real_crop
check("main(): 成功時は従来どおりクロップして終了コード0・状態ファイルは作らない",
      _rc2 == 0 and _cropped.get("out", "").endswith("apr_screenshot.jpg")
      and not (_main_dir2 / "apr_capture_status.json").exists(), str(_cropped))

# 13) リポジトリ側の配線: gitignore・ワークフロー（YAMLライブラリに依存しないテキスト検査。無い環境で素通りしない）
_gi = _sp_apr.run(["git", "-C", str(REPO), "check-ignore", "-q", "apr_diagnostics/2026-09-30/apr_failed_attempt1.png"])
check("gitignore: リポジトリ直下のapr_diagnostics/配下はgit管理の対象外（誤ってコミットされない）", _gi.returncode == 0, str(_gi))
_gi2 = _sp_apr.run(["git", "-C", str(REPO), "check-ignore", "-q", "outputs/2026-09-30/apr_diagnostics/x.png"])
check("gitignore: 無視するのはリポジトリ直下のみ（outputs/配下の同名ディレクトリは無視しない）", _gi2.returncode == 1, str(_gi2))

_wf_text = (REPO / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
_blocks = _re_apr.split(r"(?m)^      - (?=name:|uses:)", _wf_text)
_dblock = next((b for b in _blocks if "APR撮影の診断アーティファクト" in b.split("\n", 1)[0]), None)
check("daily.yml: APR診断アーティファクトのステップが存在する", _dblock is not None)
if _dblock:
    _path_line = _re_apr.search(r"(?m)^\s+path:\s*(.+?)\s*$", _dblock)
    _date_tpl = "${{ steps.target.outputs.date }}"
    check("daily.yml: 診断アーティファクトのパスは capture_apr の保存先（_diag_dir_for）と一致する（ずれると診断が無言で失われる）",
          _path_line is not None
          and _path_line.group(1).replace(_date_tpl, "2026-09-30").rstrip("/")
          == str(capture_apr._diag_dir_for("outputs/2026-09-30/apr_screenshot.jpg")), str(_path_line and _path_line.group(1)))
    check("daily.yml: 診断ステップはフェーズ1が実行された日のみ・失敗時も実行・非致命・ファイル無しは無視・別名アーティファクト・outputs/の外",
          "always() && steps.need.outputs.phase1 == 'true'" in _dblock and "continue-on-error: true" in _dblock
          and "if-no-files-found: ignore" in _dblock and "apr-diagnostics-" in _dblock
          and _path_line is not None and not _path_line.group(1).startswith("outputs/"), _dblock[:400])
    _pos = {k: _wf_text.find(k) for k in ("③ APR実画面撮影", "APR撮影の診断アーティファクト", "⑤ コミット")}
    check("daily.yml: ステップ順は ③撮影 → ⑤コミット → 診断アーティファクト（診断は⑤コミットの後で保存）",
          0 < _pos["③ APR実画面撮影"] < _pos["⑤ コミット"] < _pos["APR撮影の診断アーティファクト"], str(_pos))
_commit_block = next((b for b in _blocks if b.startswith("name: ⑤ コミット")), "")
check("daily.yml: フェーズ1の⑤コミットは outputs/ のみをgit addする（診断ディレクトリはコミット対象外であることの前提）",
      "git add outputs/" in _commit_block and "apr_diagnostics" not in _commit_block, _commit_block[:200])
try:
    import yaml as _yaml_apr
    _wf = _yaml_apr.safe_load(_wf_text)
    check("daily.yml: YAMLとして正しく読み込める（PyYAMLがある環境での追加検査）", isinstance(_wf["jobs"]["build"]["steps"], list))
except ImportError:
    pass  # 上のテキスト検査が主。PyYAML未導入でも検査は素通りしない

print("=== capture_apr.py: 診断が壊れていても撮影・後続ステップを止めない／通常日の挙動はv1.82以前と同じ（v1.84・オーナー指示） ===")

# ---- 通常日（1回目で成功）: v1.82以前と同じ操作順序・待機・出力（診断・追加待機・flushは一切動かない）----
_pg = _FakePage([(_OK_BODY, [])])
_res, _out, _sl, _d, _cl = _run_capture(_pg, "normalday")
check("通常日: 操作の順序と待機がv1.82以前と同じ（初回読込→3秒→Refresh→8秒→撮影。合計待機11秒）・追加の待機/再読み込み/flushなし",
      _pg.timeline == ["goto", ("sleep", 3), "click", ("sleep", 8), "shot"] and sum(_sl) == 11 and _pg.flushes == 0
      and len(_pg.goto_calls) == 1, f"{_pg.timeline} flushes={_pg.flushes}")
check("通常日: 結果と出力メッセージがv1.82以前と同一（(True,'',1)・3行の出力のみ・診断ファイルなし）",
      _res == (True, "", 1)
      and _out.strip().split("\n") == ["[試行 1/3] Refreshクリック...", "  8秒待機（GeckoTerminal/DefiLlamaロード待ち）...",
                                       "  ✓ 撮影画像の完了を確認。"] and not _d.exists(), _out)

# ---- 診断が壊れていても、診断なし（正常）の実行と「結果・操作順序・出力（診断行を除く）」が同一 ----
def _outcome(page, tag, patch=None):
    """patch: 実行中だけ適用する診断側の破壊（コンテキストマネージャ）。"""
    ctx = patch() if patch else _ctx_apr.nullcontext()
    with ctx:
        res, out, sl, d, cl = _run_capture(page, tag)
    non_diag = [ln for ln in out.split("\n") if "診断" not in ln and "（診断" not in ln and ln.strip()]
    return res, list(page.timeline), non_diag, cl


class _HostileObj:
    """属性へのアクセスがすべて例外になるイベントオブジェクト（Firefoxで未対応・想定外の形のイベント）。"""
    def __getattr__(self, name):
        raise RuntimeError(f"unsupported attribute {name}")


@_ctx_apr.contextmanager
def _patch_snapshot_raises():
    real = capture_apr._Diagnostics.snapshot
    capture_apr._Diagnostics.snapshot = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("snapshot broken"))
    try:
        yield
    finally:
        capture_apr._Diagnostics.snapshot = real


@_ctx_apr.contextmanager
def _patch_format_raises():
    real = capture_apr._Diagnostics.format_lines
    capture_apr._Diagnostics.format_lines = staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("format broken")))
    try:
        yield
    finally:
        capture_apr._Diagnostics.format_lines = real


@_ctx_apr.contextmanager
def _patch_caps_broken():
    real = capture_apr.DIAG_CAPS
    capture_apr.DIAG_CAPS = None          # DIAG_CAPS.get(...) が例外になる（記録処理の内部エラー）
    try:
        yield
    finally:
        capture_apr.DIAG_CAPS = real


def _scenarios():
    """(名前, page生成関数(script), パッチ) の一覧。すべて診断側だけを壊す。"""
    hostile_events = [("response", _HostileObj()), ("requestfailed", _HostileObj()), ("console", _HostileObj()),
                      ("pageerror", _HostileObj()), ("response", _Obj(url="https://yields.llama.fi/pools", status=503,
                                                                     headers=_HostileObj()))]
    return [
        ("page.onが全イベントで例外（リスナー登録不可）", lambda sc: _FakePage(sc, on_raises=True), None),
        ("イベントオブジェクトの属性アクセスが例外", lambda sc: _FakePage([(b, hostile_events) for b, _e in sc]), None),
        ("wait_for_timeout（flush）が例外", None, "flush"),
        ("snapshot()が例外", lambda sc: _FakePage(sc), _patch_snapshot_raises),
        ("format_lines()が例外", lambda sc: _FakePage(sc), _patch_format_raises),
        ("記録上限の設定が壊れている（_addの内部エラー）", lambda sc: _FakePage(sc), _patch_caps_broken),
    ]


class _NoFlushPage(_FakePage):
    def wait_for_timeout(self, ms):
        raise RuntimeError("wait_for_timeout unsupported")


_diag_scripts = {
    "1回目で成功": [(_OK_BODY, [])],
    "標準3回目で成功": [(_FAIL_BODY, []), (_FAIL_BODY, []), (_OK_BODY, [])],
    "全5回失敗": [(_FAIL_BODY, [])] * 5,
}
_broken = []
for _sc_name, _sc_script in _diag_scripts.items():
    _base_page = _FakePage(_sc_script)
    _base = _outcome(_base_page, f"eq_base_{abs(hash(_sc_name)) % 10000}")
    for _name, _mk, _patch in _scenarios():
        _pg2 = _NoFlushPage(_sc_script) if _patch == "flush" else _mk(_sc_script)
        _got = _outcome(_pg2, f"eq_{abs(hash((_sc_name, _name))) % 100000}", None if _patch == "flush" else _patch)
        if _got != _base:
            _broken.append((_sc_name, _name, _got[0], _base[0], _got[1] == _base[1], _got[2] == _base[2]))
check("診断が壊れていても（リスナー登録不可・イベント属性が例外・flush例外・snapshot/format例外・記録処理の内部エラー）、"
      "撮影の結果・操作順序・診断以外の出力は、診断が正常な実行と完全に同一（撮影と後続が止まらない）。3つの進行×6つの故障",
      not _broken, str(_broken))

# ---- main(): 診断の保存先の決定が失敗しても撮影は続行し、失敗時も終了コード0 ----
_real_diag_for = capture_apr._diag_dir_for
_main_dir3 = Path(SCRATCH) / "apr_main_test3" / "outputs" / "2026-09-30"
_main_dir3.mkdir(parents=True, exist_ok=True)
capture_apr._diag_dir_for = lambda out: (_ for _ in ()).throw(OSError("path resolution failed"))
_real_capture = capture_apr.capture
_seen = {}
def _fake_capture_none(tmp, diag_dir=None):
    _seen["diag_dir"] = diag_dir
    Path(tmp).write_bytes(b"PNG")
    return False, "TODAY件数: 0/6", 5
capture_apr.capture = _fake_capture_none
_buf = _io_apr.StringIO()
try:
    with _ctx_apr.redirect_stdout(_buf):
        _rc3 = capture_apr.main([str(_main_dir3 / "apr_screenshot.jpg")])
finally:
    capture_apr._diag_dir_for, capture_apr.capture = _real_diag_for, _real_capture
check("main(): 診断の保存先を決定できなくても（例外）診断を無効化して撮影を続行し、全試行失敗でも終了コード0・状態ファイルを記録する",
      _rc3 == 0 and _seen["diag_dir"] is None
      and json.loads((_main_dir3 / "apr_capture_status.json").read_text(encoding="utf-8"))["attempts"] == 5
      and "診断ファイルなしで続行します" in _buf.getvalue() and "診断（失敗画像・診断JSON）:" not in _buf.getvalue(), _buf.getvalue()[-300:])

print("=== verify_post: C24 機関名の同義語照合（C23と同じ案C。v1.84・オーナー承認。案Bは不採用） ===")

def _c24(flow, points="・某社が提携を発表（Reuters）", headline=None):
    au = verify_post.Audit()
    verify_post.check_c24(au, flow, points, headline)
    return au.checks[0]

# オーナー指定の同義語を、C23と同じ全組合せで検証（フローの略称×本文の表記）
_bad = []
for _grp, _terms in _OWNER_ALIASES.items():
    for _abbr in _SUMMARY_ABBRS[_grp]:
        for _term in _terms:
            _r = _c24(f"・{_abbr}の動向が意識された可能性があります。", points=f"・{_term}が発表しました（Reuters）")
            if _r["result"] != "PASS":
                _bad.append((_abbr, _term, _r["detail"][:60]))
check("C24同義語: オーナー指定の同義語（Fed・FRB・FOMC・連邦準備制度・米連邦準備理事会／SEC・証券取引委員会／CFTC・"
      "商品先物取引委員会／BOJ・日銀・日本銀行／ECB・欧州中央銀行／BOE・英中銀・イングランド銀行）が"
      "同じ機関の表記として本文で確認済みになる（フローの略称×本文の表記の全組合せ）", not _bad, str(_bad))

_bad = []
for _g1 in _groups:
    for _g2 in _groups:
        if _g1 == _g2:
            continue
        for _abbr in _SUMMARY_ABBRS[_g1]:
            for _term in _OWNER_ALIASES[_g2]:
                _r = _c24(f"・{_abbr}の動向が意識された可能性があります。", points=f"・{_term}が発表しました（Reuters）")
                if _r["result"] != "FAIL":
                    _bad.append((_abbr, _term))
check("C24同義語: 別の機関の表記では確認済みにならない（全組合せ）", not _bad, str(_bad[:5]))

for _abbr in ("Fed", "FRB", "SEC", "CFTC", "BOJ", "ECB", "BOE", "FOMC"):
    _r = _c24(f"・{_abbr}の動向が意識された可能性があります。")
    check(f"C24同義語: 案B不採用の回帰確認——本文に同じ機関の記述が無ければ{_abbr}は従来どおりFAIL（無条件の許可リストではない）",
          _r["result"] == "FAIL" and _abbr in _r["detail"], str(_r))

_bad = [(a, t) for a, t in _ENG_FULL.items()
        if _c24(f"・{a}の動向が意識された可能性があります。", points=f"・{t}が声明を発表（Reuters）")["result"] != "PASS"]
check("C24同義語: 英語の正式名称（Federal Reserve等）・大文字小文字の表記ゆれ（BoJ・BoE・FED）・連邦公開市場委員会も本文側の同義語として確認済みにできる",
      not _bad and _c24("・BOEの動向が意識されました。", points="・BoEが据え置き（Reuters）")["result"] == "PASS"
      and _c24("・Fedの動向が意識されました。", points="・FEDが示唆（Reuters）")["result"] == "PASS"
      and _c24("・FOMCの動向が意識されました。", points="・連邦公開市場委員会が声明を発表（Reuters）")["result"] == "PASS", str(_bad))
check("C24同義語: 本文の小文字（sec＝秒・fed＝動詞）はSEC・BOEの根拠にならない（全面的なIGNORECASEにしていない）",
      _c24("・SECの動向が意識されました。", points="・fed と sec と frb の小文字")["result"] == "FAIL")

check("C24同義語: 同義語の確認先はヘッドラインも含む（ヘッドラインのみに日本語表記がある日）",
      _c24("・Fedの動向が意識された可能性があります。", points=generate_post.FIXED_POINTS,
           headline="米連邦準備制度理事会が利上げに動く可能性が報じられました。")["result"] == "PASS")
check("C24同義語: 継続監視材料（reusable_for_summary）は照合先に含めない（従来どおり。C24はreusableでは救済されない）",
      _c24("・SECの動向が意識された可能性があります。", points=generate_post.FIXED_POINTS, headline=generate_post.FIXED_HEADLINE)["result"] == "FAIL")

_r = _c24("・SECとCFTCの動向が意識された可能性があります。", points="・米証券取引委員会が規則案を公表（Reuters）")
check("C24同義語: 混在ケース——SECは同義語で確認済み・CFTCは根拠なしなら、CFTCだけがFAIL詳細に列挙される",
      _r["result"] == "FAIL" and "CFTC" in _r["detail"] and "SEC'" not in _r["detail"].replace("CFTC'", ""), str(_r))
_r = _c24("・SECの動向と米PCEインフレ指標が意識された可能性があります。", points="・某社が提携を発表（Reuters）")
check("C24同義語: 8/26型（本文に無いSECとPCEをフローが持ち出す）はSEC・PCEともFAIL（真の新規持ち出しの検知を維持）",
      _r["result"] == "FAIL" and "SEC" in _r["detail"] and "PCE" in _r["detail"], str(_r))
_r = _c24("・Polygonが脆弱性を開示したとの報道が伝わっています。", points="・FRBが声明を発表（Reuters）")
check("C24同義語: 同義語グループに無い固有名詞（Polygon等。8/29型）は従来どおり同義語で救済されずFAIL",
      _r["result"] == "FAIL" and "Polygon" in _r["detail"], str(_r))
check("C24: 従来の判定（候補の文字列そのものが本文に部分一致）は維持される（既存より厳しくならない）",
      _c24("・Bitmineの動向が意識されました。", points="・Bitmineが発表（Bloomberg）")["result"] == "PASS"
      and _c24("・Bitmineの動向が意識されました。")["result"] == "FAIL")

# run_all()経由の配線確認: フローのFed（本文は日本語表記）でC24がPASS・総括のFedと合わせてC23もPASS
_b_c24alias = json.loads(json.dumps(b_ok))
_b_c24alias["sections"]["part1_points"] = "・米連邦準備制度理事会が声明を発表しました（Reuters、2026-08-17）"
_b_c24alias["sections"]["part1_headline"] = generate_post.FIXED_HEADLINE
_b_c24alias["sections"]["part2_flow"] = "・【出来事・ニュース】Fedが声明を発表 → 【暗号通貨価格】BTCは同時期に軟調（因果は未確認）。"
_b_c24alias["sections"]["part2_summary"] = "地合いは不透明です。今後はFedの動向を確認していく必要があります。"
_au_c24alias = verify_post.run_all(_b_c24alias, DAILY_DATA)
_r24 = next(x for x in _au_c24alias.checks if x["id"] == "C24_flow_no_unadopted_material")
_r23 = next(x for x in _au_c24alias.checks if x["id"] == "C23_summary_no_new_entities")
check("run_all(): フローのFedが本文の日本語表記（米連邦準備制度理事会）で確認済みになりC24 PASS（総括のC23もPASS。v1.84）",
      _r24["result"] == "PASS" and _r23["result"] == "PASS", f"{_r24} {_r23}")
_b_c24alias2 = json.loads(json.dumps(_b_c24alias))
_b_c24alias2["sections"]["part1_points"] = "・某社が提携を発表しました（Reuters、2026-08-17）"
_au_c24alias2 = verify_post.run_all(_b_c24alias2, DAILY_DATA)
_r24b = next(x for x in _au_c24alias2.checks if x["id"] == "C24_flow_no_unadopted_material")
check("run_all(): 本文にFRB系の記述が無ければフローのFedは従来どおりC24 FAIL（v1.84）", _r24b["result"] == "FAIL", str(_r24b))

print("=== 向きの食い違いの警告（WARN。FAILにしない）（v1.85・オーナー承認）・GENERATION_STATUSの監査表記 ===")

# ---- 9/30の実際の本文（本番の自動生成。向きの食い違いが実際に起きた事例）を逐語で再現 ----
_D930_POINTS = ("・Reutersによると、米国の8月分インフレ指標（PCE）が市場予想を下回る伸びとなり、FRBの利上げ観測が後退したと報じられました。"
                "暗号通貨市場への直接因果は未確認です（Reuters、9月30日）。\n"
                "・Reutersによると、米国・イラン間の協議停滞と燃料市場の逼迫を背景に原油価格が上昇したと報じられました。"
                "原油・リスク選好経由の波及は考えられますが、暗号通貨価格への直接因果は未確認です（Reuters、9月30日）。")
_D930_HEADLINE = "米国の8月分Core PCE物価指数が市場予想を下回る伸びにとどまり、Fedの利下げ観測を巡る思惑が意識されました。 #BTC #ETH"
_D930_FLOW = ("①【出来事・ニュース】Reutersによると、米国の8月分Core PCE物価指数が市場予想を下回る伸びにとどまったと報じられました → "
              "【地政学・マクロの変化】FRBの利下げ観測が後退し得るとの思惑が意識された可能性があります → "
              "【中間市場指標・市場心理】インフレ鈍化を受けたリスク選好の心理が一部で強まった可能性があります → "
              "【暗号通貨価格】BTC・ETHは24時間比でともに上昇し、値動きはおおむね限定的な範囲にとどまったとみられます。 #BTC #ETH\n"
              "②【出来事・ニュース】Reutersによると、米国・イラン間の協議停滞と燃料市場の逼迫を背景に原油価格が上昇したと報じられました → "
              "【地政学・マクロの変化】地政学リスクの高まりが市場で意識された可能性があります → "
              "【中間市場指標・市場心理】原油高を受けたリスク回避的な心理が一部で強まった可能性があります → "
              "【暗号通貨価格】BTC・ETHは24時間比で底堅い推移を見せたものの、原油高との直接因果は断定できません。 #BTC #ETH")
_h930 = verify_post.find_direction_mismatches(
    _D930_POINTS, {"ヘッドライン": _D930_HEADLINE, "市場のフロー": _D930_FLOW, "headline_for_image": "BTC・ETH・BNBともに堅調に推移"})
check("向きの食い違い: 9/30の実例（本文は利上げ観測の後退・ヘッドラインとフロー①は利下げ）を、ヘッドラインと市場のフローの2件として検知する"
      "（headline_for_imageは警告なし・フロー②の原油上昇は本文と一致するため警告なし）",
      sorted(h["section"] for h in _h930) == ["ヘッドライン", "市場のフロー"]
      and all(h["pair"] == "利上げ/利下げ" and h["section_directions"] == ["利下げ"] and h["points_directions"] == ["利上げ"] for h in _h930),
      str(_h930))
check("向きの食い違い: 警告に、食い違いのある文（対象側・本文側）が根拠として含まれる",
      all("利下げ" in h["section_sentence"] and "利上げ" in h["points_sentence"] for h in _h930), str(_h930))

# ---- 語の対ごとの検知（対象はヘッドライン・市場のフロー・headline_for_image）----
def _dm(points, **targets):
    return verify_post.find_direction_mismatches(points, targets)

check("向きの食い違い: 利上げ／利下げ（本文が利下げ・対象が利上げ。逆向きも）",
      len(_dm("・FRBの利下げ観測が強まった（Reuters）", ヘッドライン="FRBの利上げ観測が意識されました。")) == 1
      and len(_dm("・FRBの利上げ観測が強まった（Reuters）", ヘッドライン="FRBの利下げ観測が意識されました。")) == 1)
check("向きの食い違い: 上昇／下落（同じ主語＝原油で、本文が上昇・フローが下落）",
      [h["subject"] for h in _dm("・原油価格が上昇したと報じられました（Reuters）", 市場のフロー="→ 原油価格が下落したことで意識された可能性があります。")] == ["原油"])
check("向きの食い違い: 流入／流出（同じ主語＝資金〔ETF含む〕で、本文が流入・対象が流出）",
      [h["subject"] for h in _dm("・ビットコインETFへの資金流入が報じられました（CoinDesk）", ヘッドライン="ETFから資金が流出したことが意識されました。")] == ["資金"])
check("向きの食い違い: headline_for_imageも対象（短い見出しでも主語＝金利を取り出す）",
      [h["section"] for h in _dm("・米長期金利が上昇しました（Reuters）", headline_for_image="長期金利が下落し暗号通貨は堅調")] == ["headline_for_image"])

# ---- 警告しないケース（誤検知の抑制）----
check("向きの食い違い: 同じ向きなら警告しない",
      _dm("・原油価格が上昇しました（Reuters）", ヘッドライン="原油価格の上昇が意識されました。") == []
      and _dm("・FRBの利上げ観測が後退しました（Reuters）", ヘッドライン="FRBの利上げ観測の後退が意識されました。") == [])
check("向きの食い違い: 本文が両方の向きを書いている（上昇した後に下落等）場合は警告しない",
      _dm("・原油価格は上昇した後に下落しました（Reuters）", ヘッドライン="原油価格の下落が意識されました。") == []
      and _dm("・利上げ観測が後退し、利下げ観測が強まりました（Reuters）", ヘッドライン="FRBの利下げ観測が意識されました。") == [])
check("向きの食い違い: 対象側が両方の向きを書いている場合は警告しない",
      _dm("・原油価格が上昇しました（Reuters）", 市場のフロー="原油価格は上昇の後、下落に転じました。") == [])
check("向きの食い違い: 主語が違えば警告しない（本文は原油の上昇・フローはBTCの下落／株式の下落）",
      _dm("・原油価格が上昇しました（Reuters）", 市場のフロー="→ 【暗号通貨価格】BTC・ETHは24時間比で下落しました。") == []
      and _dm("・原油価格が上昇し、米国株式市場は下落しました（Reuters）", ヘッドライン="原油価格の上昇が意識されました。") == [])
check("向きの食い違い: 同じ文の中でも節ごとに主語を分ける（「原油価格が上昇し、米国株式市場は下落」→原油:上昇・株式:下落）",
      verify_post._direction_map("原油価格が上昇し、米国株式市場は下落しました")[("上昇/下落", "原油")] == {"上昇"}
      and verify_post._direction_map("原油価格が上昇し、米国株式市場は下落しました")[("上昇/下落", "株式")] == {"下落"})
check("向きの食い違い: 主語が一覧に無い・方向語が無い・空欄・定型文・文字列でない場合は警告しない（見逃しは限界として開示）",
      _dm("・某社の株主総会で議案が可決（Reuters）", ヘッドライン="BTCは上昇しました。") == []
      and _dm(generate_post.FIXED_POINTS, ヘッドライン=generate_post.FIXED_HEADLINE, 市場のフロー=generate_post.FIXED_FLOW) == []
      and _dm("", ヘッドライン="利上げ観測が意識されました。") == [] and _dm(None, ヘッドライン=None, 市場のフロー=123) == [])

# ---- run_all(): WARNはFAILにしない（checks・failed・overall・終了コードに影響しない）----
_b_dir = json.loads(json.dumps(b_ok))
_b_dir["sections"]["part1_points"] = "・FRBの利上げ観測が後退したと報じられました（Reuters、2026-08-17）"
_b_dir["sections"]["part1_headline"] = "FRBの利下げ観測が意識されました。暗号通貨価格への直接因果は未確認です。"
_b_base = json.loads(json.dumps(_b_dir))
_b_base["sections"]["part1_headline"] = "FRBの利上げ観測の後退が意識されました。暗号通貨価格への直接因果は未確認です。"
_au_dir, _au_base = verify_post.run_all(_b_dir, DAILY_DATA), verify_post.run_all(_b_base, DAILY_DATA)
check("run_all(): 向きの食い違いは警告（au.warnings）に入り、警告が無い場合は空のまま",
      len(_au_dir.warnings) == 1 and _au_dir.warnings[0]["id"] == "W_direction_mismatch" and _au_base.warnings == [],
      str(_au_dir.warnings))
check("run_all(): 警告はchecksに入らず、failedを増やさない（FAILにしない）。チェック項目の構成・件数は警告の有無で変わらない",
      [c["id"] for c in _au_dir.checks] == [c["id"] for c in _au_base.checks]
      and _au_dir.failed == _au_base.failed and not any(c["id"].startswith("W_") for c in _au_dir.checks), str(_au_dir.failed))
_real_find = verify_post.find_direction_mismatches
_stderr_buf = _io_apr.StringIO()
try:
    verify_post.find_direction_mismatches = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("detector broken"))
    with _ctx_apr.redirect_stderr(_stderr_buf):
        _au_broken = verify_post.run_all(_b_dir, DAILY_DATA)
finally:
    verify_post.find_direction_mismatches = _real_find
check("run_all(): 警告の検知自体が失敗しても監査全体は止めず（警告なしとして続行）、ログに残す",
      _au_broken.warnings == [] and _au_broken.failed == _au_base.failed and "detector broken" in _stderr_buf.getvalue(), _stderr_buf.getvalue())

# ---- verify_post.main(): post_audit JSONにwarningsが入り、WARNだけでは終了コード0・overall PASS ----
_vm_date = "2026-08-17"
Path(f"outputs/{_vm_date}/draft").mkdir(parents=True, exist_ok=True)
Path(f"outputs/{_vm_date}/daily_data.json").write_text(json.dumps(DAILY_DATA, ensure_ascii=False), encoding="utf-8")
_b_main = json.loads(json.dumps(_b_dir)); _b_main["target_date_jst"] = _vm_date
_bp = Path(f"outputs/{_vm_date}/draft/post_bundle.json")
_bp.write_text(json.dumps(_b_main, ensure_ascii=False), encoding="utf-8")
_orig_argv = sys.argv
sys.argv = ["verify_post.py", str(_bp)]
_buf_main = _io_apr.StringIO()
try:
    with _ctx_apr.redirect_stdout(_buf_main):
        _rc_main = verify_post.main()
finally:
    sys.argv = _orig_argv
_audit_json = json.loads(Path(f"outputs/{_vm_date}/draft/post_audit_{_vm_date.replace('-', '')}.json").read_text(encoding="utf-8"))
check("verify_post.main(): 警告があってもoverallはPASS・終了コード0（FAILにしない）。post_audit JSONに警告が記録され、ログに「⚠ WARN」が出る",
      _rc_main == 0 and _audit_json["overall"] == "PASS" and _audit_json["failed"] == 0 and len(_audit_json["warnings"]) == 1
      and "⚠ WARN（FAILではない）: W_direction_mismatch" in _buf_main.getvalue(), _buf_main.getvalue()[:300])

# ---- GENERATION_STATUS.md: 先頭の警告ブロック・見出しの表記・コスト記録のgrepを壊さない ----
_REPAIR_RES = {"final_failing_checks": [], "final_failing_check_details": [], "checked_ids": "C12〜C24・C26〜C28・計17項目",
               "warnings": _au_dir.warnings}
_blk = repair_post.render_warning_block(_REPAIR_RES)
check("警告ブロック: 先頭に「⚠⚠ 警告」・件数・FAILではない旨・警告の内容を含み、警告が無ければ空文字列",
      _blk.startswith("⚠⚠ 警告1件（" + _wk(direction=1) + "） — FAILではありません") and "投稿前に本文を見直してください" in _blk
      and "⚠ [向きの食い違い] " in _blk and "向きが食い違っています" in _blk and repair_post.render_warning_block({**_REPAIR_RES, "warnings": []}) == "", _blk)
check("警告ブロック: コスト記録のステップが抽出する「input=」「output=」の文字列を含まない（daily.ymlのgrep -oPを壊さない）",
      "input=" not in _blk and "output=" not in _blk)
_note = repair_post.render_final_audit_note(_REPAIR_RES)
check("最終監査の表記: 見出しは実際に評価したチェックのID（C12〜C24・C26〜C28・計17項目）から作り、警告の件数とファイル先頭に表示する旨を示す",
      "本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS" in _note
      and "警告1件（" + _wk(direction=1) + "）（ファイル先頭に表示）" in _note, _note)
check("最終監査の表記: 古い固定文言（C12〜C24のみ）が残っていない／結果dictにchecked_idsが無い旧形式でも例外にならない",
      "（C12〜C24）" not in _note
      and "本文機械監査（C12〜C24）" in repair_post.render_final_audit_note({"final_failing_checks": [], "final_failing_check_details": []}))

# main()経由: 警告がある日はGENERATION_STATUS.mdの先頭に警告ブロックが置かれ、コスト記録の抽出結果は変わらない
_status_w_path = Path(f"outputs/{REPAIR_TEST_DATE}/GENERATION_STATUS.md")
_status_w_path.write_text("level: L0\ntoken_usage（実消費量）: input=12345, output=678 (call_A: in=1 out=2 / call_B: in=3 out=4)\n", encoding="utf-8")
Path(f"outputs/{REPAIR_TEST_DATE}/draft/post_bundle.json").write_text(json.dumps(_b_dir, ensure_ascii=False), encoding="utf-8")
_orig_argv = sys.argv
sys.argv = ["repair_post.py", REPAIR_TEST_DATE]
_orig_anthropic_client = repair_post.anthropic.Anthropic
repair_post.anthropic.Anthropic = lambda: FakeClient(lambda kw, n: json_response({"rewritten_sentence": "x"}))
try:
    with _ctx_apr.redirect_stdout(_io_apr.StringIO()):
        repair_post.main()
finally:
    sys.argv = _orig_argv
    repair_post.anthropic.Anthropic = _orig_anthropic_client
_status_w = _status_w_path.read_text(encoding="utf-8")
check("repair_post.main(): 警告がある日はGENERATION_STATUS.mdの先頭に警告ブロックを置き、最終監査の記録（警告N件）も追記する",
      _status_w.startswith("⚠⚠ 警告1件（" + _wk(direction=1) + "）") and "level: L0" in _status_w
      and "向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告1件（" + _wk(direction=1) + "）" in _status_w, _status_w[:400])
check("repair_post.main(): 警告ブロックを先頭に置いても、コスト記録の抽出（grep -oP '(?<=input=)[0-9]+' | head -1）は従来どおり12345・678",
      __import__("re").findall(r"(?<=input=)[0-9]+", _status_w)[0] == "12345"
      and __import__("re").findall(r"(?<=output=)[0-9]+", _status_w)[0] == "678", _status_w[:300])

# ---- summarize_check_ids ----
check("summarize_check_ids: 連続する番号は範囲にまとめ、飛ぶ所は分け、枝番つき（C16b）は親番号に含めて項目数に数える",
      verify_post.summarize_check_ids([{"id": i} for i in ("C12_a", "C13_a", "C14_a", "C16_a", "C16b_a", "C18_a", "C19_a", "C20_a")])
      == "C12〜C14・C16・C18〜C20・計8項目")
check("summarize_check_ids: 単独の番号・空・C以外のIDでも例外にならない",
      verify_post.summarize_check_ids([{"id": "C26_x"}]) == "C26・計1項目" and verify_post.summarize_check_ids([]) == "計0項目"
      and verify_post.summarize_check_ids([{"id": "X1"}, {"id": "Y"}]) == "計2項目")
check("固定文言の整合: compose_postの利用者向け文言（force_drop後の再監査）もC12〜C28になっている",
      "（C12〜C28）" in (REPO / "scripts" / "compose_post.py").read_text(encoding="utf-8")
      and "再監査(C12〜C24)がFAIL" not in (REPO / "scripts" / "compose_post.py").read_text(encoding="utf-8"))

print("=== generate_post.py: 米連邦準備制度の表記を「FRB」に統一する指示（v1.85・オーナー承認） ===")
_RA = generate_post.RULES_ABSOLUTE
check("RULES_ABSOLUTE: 米連邦準備制度の略称を「FRB」に統一する規則（7番）がある・「Fed」「FED」を「FRB」に書き換え・混在させない旨が明記される",
      "7. 米連邦準備制度（連邦準備制度理事会）の略称は「FRB」に統一する" in _RA
      and "「Fed」「FED」も「FRB」と書き換え" in _RA and "「Fed」と「FRB」を混在させない" in _RA, _RA[-420:])
check("RULES_ABSOLUTE: 規則の対象に前編（ヘッドライン・主要なポイント）・後編（市場のフロー・総括）・headline_for_imageのすべてが含まれる",
      all(k in _RA for k in ("ヘッドライン", "主要なポイント", "市場のフロー", "総括", "headline_for_image")))
check("RULES_ABSOLUTE: FOMCは会合・委員会そのものを指す場合に限って使ってよい／地区連銀（ダラス連銀等）は日本語表記のままでよい旨が明記される",
      "FOMC（連邦公開市場委員会）は、会合・委員会" in _RA and "地区連銀は" in _RA.replace("\n   ", ""), _RA[-300:])
check("SYSTEM_A・SYSTEM_BのどちらにもFRB表記統一の規則が含まれる（呼び出しA=前編・headline_for_image／呼び出しB=後編）",
      "7. 米連邦準備制度" in generate_post.SYSTEM_A and "7. 米連邦準備制度" in generate_post.SYSTEM_B)
check("RULES_ABSOLUTE: 既存の規則1〜6は変更されていない（規則7の追加のみ）",
      all(f"{i}. " in _RA for i in range(1, 7)) and "3. 「暗号通貨」と表記する。「仮想通貨」は使わない。" in _RA
      and "4. 変化率のラベルは「24時間比」。「前日比」は使わない。" in _RA)

print("=== 案G（v1.86・オーナー承認）: 失敗試行の診断保存／1・2試行目の相方不成立の理由／STATUSにFAIL詳細 ===")

# ---- 1) generate_post._explain_unresolved: 理由コード（6種類＋表示専用no_claim）と他候補からの申告 ----
_eu_cands = {
    1: {"candidate_id": 1, "title": "NEAR Intents hit by $3.8 million exploit", "source": "CoinDesk", "tier": 3},
    2: {"candidate_id": 2, "title": "NEAR Intents suffers $3.8M exploit", "source": "Cointelegraph", "tier": 3},
    3: {"candidate_id": 3, "title": "Hackers drain NEAR cross-chain protocol", "source": "The Block", "tier": 3},
    4: {"candidate_id": 4, "title": "SEC press release", "source": "SEC", "tier": 1},
    5: {"candidate_id": 5, "title": "Another CoinDesk story about exploit", "source": "CoinDesk", "tier": 3},
}
_eu_use = {1: True, 2: True, 3: False, 4: True, 5: True}


def _eu(unres, claims, use=None, thr=0.4):
    return generate_post._explain_unresolved(unres, claims, _eu_cands, use or _eu_use, thr)


_r = _eu([1], {1: None})
check("_explain_unresolved: 申告なしは表示専用のno_claim（own_claim）として記録される（理由欄が空白にならない）",
      _r[0]["reasons"] == [{"role": "own_claim", "code": "no_claim"}]
      and _r[0]["title"].startswith("NEAR Intents") and _r[0]["source"] == "CoinDesk" and _r[0]["tier"] == 3, str(_r))
_codes = {
    "target_not_found": _eu([1], {1: 99}), "self_reference": _eu([1], {1: 1}),
    "target_not_tier3": _eu([1], {1: 4}), "target_use_false": _eu([1], {1: 3}),
    "same_source": _eu([1], {1: 5}), "overlap_below_threshold": _eu([1], {1: 2}, thr=0.99),
}
for _code, _res in _codes.items():
    check(f"_explain_unresolved: 自身の申告の却下理由{_code}が記録される（_pair_claim_detailの理由コードそのもの）",
          _res[0]["reasons"][0]["code"] == _code and _res[0]["reasons"][0]["role"] == "own_claim"
          and _code in generate_post.PAIR_REJECT_REASON_LABELS, str(_res))
check("_explain_unresolved: overlap_below_thresholdは重なり係数・閾値・申告先のタイトル/媒体を持つ",
      _codes["overlap_below_threshold"][0]["reasons"][0]["overlap"] is not None
      and _codes["overlap_below_threshold"][0]["reasons"][0]["threshold"] == 0.99
      and _codes["overlap_below_threshold"][0]["reasons"][0]["other_source"] == "Cointelegraph"
      and _codes["overlap_below_threshold"][0]["reasons"][0]["other_id"] == 2, str(_codes["overlap_below_threshold"]))
_inc = _eu([2], {1: 2, 2: None}, thr=0.99)
check("_explain_unresolved: 他のtier3・use:true候補からの申告（incoming_claim）の却下理由も記録される",
      any(r["role"] == "incoming_claim" and r["other_id"] == 1 and r["code"] == "overlap_below_threshold"
          for r in _inc[0]["reasons"])
      and any(r["role"] == "own_claim" and r["code"] == "no_claim" for r in _inc[0]["reasons"]), str(_inc))
_inc_skip = _eu([2], {3: 2, 2: None})
check("_explain_unresolved: use:falseの候補からの申告は成立判定の対象外なので理由に含めない",
      not any(r["role"] == "incoming_claim" for r in _inc_skip[0]["reasons"]), str(_inc_skip))
check("_explain_unresolved: 理由コードの表示ラベルは6種類＋no_claimの計7つ",
      set(generate_post.PAIR_REJECT_REASON_LABELS) == {
          "target_not_found", "self_reference", "target_not_tier3", "target_use_false", "same_source",
          "overlap_below_threshold", "no_claim"})

# ---- 2) call_a(): 試行ごとの診断（1・2試行目を含む） ----
check("callA: attempt_diagnosticsは各試行（1・2・3試行目）の相方不成立を残す（最終試行の分だけでない）",
      [d["attempt"] for d in out_strict.attempt_diagnostics] == [1, 2, generate_post.MAX_ATTEMPTS]
      and [d["force_drop"] for d in out_strict.attempt_diagnostics] == [False, False, True],
      str([(d["attempt"], d["force_drop"]) for d in out_strict.attempt_diagnostics]))
_d1 = out_strict.attempt_diagnostics[0]
check("callA: 1試行目の診断に候補ID・タイトル・媒体・申告先・却下理由・重なり係数・閾値が入る",
      {u["candidate_id"] for u in _d1["unresolved"]} == {1, 2}
      and any(r["code"] == "overlap_below_threshold" and r["overlap"] is not None and r["threshold"] == 0.6
              for u in _d1["unresolved"] for r in u["reasons"])
      and all(u["title"] and u["source"] for u in _d1["unresolved"])
      and any(r["code"] == "no_claim" for u in _d1["unresolved"] for r in u["reasons"]),
      str(_d1["unresolved"]))
check("callA: rejected_pairs（却下ペア診断）も試行ごとにattempt_diagnosticsへ保持される（1試行目の分が消えない）",
      all(len(d["rejected_pairs"]) == 1 and d["rejected_pairs"][0]["reason"] == "overlap_below_threshold"
          for d in out_strict.attempt_diagnostics), str([d["rejected_pairs"] for d in out_strict.attempt_diagnostics]))
check("callA: 従来のrejected_pairs（最終試行の分のみ）は変わらない（後方互換）",
      len(out_strict.rejected_pairs) == 1)
check("callA: 相方が成立する日（1回目で成功）はattempt_diagnosticsが空",
      out_loose.attempt_diagnostics == [], str(out_loose.attempt_diagnostics))
check("CallOutcome.to_dict()にattempt_diagnosticsが含まれ、既定は空リスト",
      generate_post.CallOutcome(True, {}, 1, None).to_dict()["attempt_diagnostics"] == []
      and generate_post.CallOutcome(True, {}, 1, None, attempt_diagnostics=[{"x": 1}]).to_dict()["attempt_diagnostics"] == [{"x": 1}])

# 1試行目だけ失敗して2試行目で成功: 診断は1試行目のみ
_state_g = {"n": 0}


def _g_retry_fn(kw, n):
    content = _parse_leading_json(kw["messages"][0]["content"])
    ids = sorted(c["candidate_id"] for c in content.get("news_candidates_today", []))
    if n == 1:
        entries = [{"candidate_id": ids[0], "use": True, "reason": "x"}, {"candidate_id": ids[1], "use": False, "reason": "y"}]
    else:
        entries = [{"candidate_id": ids[0], "use": False, "reason": "x"}, {"candidate_id": ids[1], "use": False, "reason": "y"}]
    return json_response({**CALL_A_DATA, "audit_ledger": entries})


_g_out = generate_post.call_a(FakeClient(_g_retry_fn), DAILY_DATA, NEWS_PAIR_CANDIDATES, None, 0.4)
check("callA: 1試行目に相方不成立（申告なし）→2試行目で成功した場合、診断は1試行目の分だけが残り強制不採用は無い",
      _g_out.ok and _g_out.attempts == 2 and len(_g_out.attempt_diagnostics) == 1
      and _g_out.attempt_diagnostics[0]["attempt"] == 1 and _g_out.force_dropped_candidates == []
      and _g_out.attempt_diagnostics[0]["unresolved"][0]["reasons"][0]["code"] == "no_claim",
      str(_g_out.attempt_diagnostics))

# ---- 3) STATUSの表示（1・2試行目の理由・3試行目の行・FAILの中身） ----
_gen_g = {
    "level": "L1", "news_candidate_count": 51,
    "total_usage": {"input_tokens": 10, "output_tokens": 5},
    "call_a": {"ok": False, "data": None, "attempts": 3, "usage": {"input_tokens": 9, "output_tokens": 4},
               "error": "force_dropで続行したが再監査FAIL", "truncation_stats": {},
               "attempt_errors": ["AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [43, 46]",
                                  "AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [43, 46]"],
               "attempt_diagnostics": [
                   {"attempt": 1, "force_drop": False, "rejected_pairs": [], "unresolved": [
                       {"candidate_id": 43, "title": "NEAR Intents exploit story from Cointelegraph", "source": "Cointelegraph",
                        "tier": 3, "own_claim_target_id": 46, "reasons": [
                            {"role": "own_claim", "code": "overlap_below_threshold", "other_id": 46,
                             "other_title": "NEAR Intents hit by $3.8 million exploit", "other_source": "CoinDesk",
                             "overlap": 0.31, "threshold": 0.4}]},
                       {"candidate_id": 46, "title": "NEAR Intents hit by $3.8 million exploit", "source": "CoinDesk",
                        "tier": 3, "own_claim_target_id": None, "reasons": [
                            {"role": "own_claim", "code": "no_claim"},
                            {"role": "incoming_claim", "code": "overlap_below_threshold", "other_id": 43,
                             "other_title": "NEAR Intents exploit story from Cointelegraph", "other_source": "Cointelegraph",
                             "overlap": 0.31, "threshold": 0.4}]}]},
                   {"attempt": 3, "force_drop": True, "rejected_pairs": [], "unresolved": [
                       {"candidate_id": 46, "title": "NEAR Intents hit by $3.8 million exploit", "source": "CoinDesk",
                        "tier": 3, "own_claim_target_id": 7, "reasons": [
                            {"role": "own_claim", "code": "same_source", "other_id": 7, "other_title": "x", "other_source": "CoinDesk",
                             "overlap": None, "threshold": 0.4}]}]}],
               "force_dropped_candidates": [{"candidate_id": 46, "title": "NEAR Intents hit by $3.8 million exploit",
                                             "source": "CoinDesk", "reason": "R"}]},
    "call_b": {"ok": True, "data": CALL_B_DATA, "attempts": 1, "error": None, "usage": {"input_tokens": 1, "output_tokens": 1}},
}
_fail_detail = [{"id": "C18_causal_assertion", "detail": "検出: [...]", "evidence": [
    {"check": "C18_causal_assertion", "section": "part1_points", "origin": "call_A", "words": ["を受けて", "上昇"],
     "sentence": "A社の発表を受けてBTCが上昇しました"}]}]
_st_g = compose_post.render_generation_status(
    _gen_g, force_dropped=_gen_g["call_a"]["force_dropped_candidates"],
    l1_fallback_failing_checks=["C18_causal_assertion"], l1_fallback_details=_fail_detail)
check("STATUS: 1試行目の下に、相方が成立しなかった候補ID・媒体・タイトルが記録される",
      "1試行目: AuditLedgerReconstructionError" in _st_g and "相方が成立しなかった候補の内訳（1試行目）" in _st_g
      and "候補ID43 [Cointelegraph]" in _st_g and "候補ID46 [CoinDesk]" in _st_g, _st_g)
check("STATUS: 理由コードとその意味（6種類のどれか）・重なり係数と閾値が読める",
      "overlap_below_threshold（タイトルの重なり係数が閾値未満・重なり係数0.31＜閾値0.4）" in _st_g
      and "自身の申告→ID46 [CoinDesk]" in _st_g and "自身の申告: no_claim（相方の申告なし" in _st_g
      and "ID43 [Cointelegraph] 「NEAR Intents exploit story from Cointelegraph」からの申告" in _st_g
      and "same_source（申告先が同じ媒体）" in _st_g, _st_g)
check("STATUS: 3試行目（強制不採用）の行が必ず出る（従来は欠落）。L1フォールバックも同じ行に示す",
      "3試行目: 強制不採用（候補ID [46]）で続行 → 再監査FAILのためL1へフォールバック" in _st_g
      and "相方が成立しなかった候補の内訳（3試行目）" in _st_g, _st_g)
check("STATUS: 再監査でFAILしたチェックの詳細に、チェックID・セクション・由来・該当語・該当文が出る",
      "FAIL: C18_causal_assertion — 検出" in _st_g
      and "└ セクション=part1_points（由来: call_A）／該当語: を受けて・上昇／該当文: 「A社の発表を受けてBTCが上昇しました」" in _st_g, _st_g)
_st_g_ok = compose_post.render_generation_status(
    {**_gen_g, "call_a": {**_gen_g["call_a"], "ok": True, "data": CALL_A_DATA}},
    force_dropped=_gen_g["call_a"]["force_dropped_candidates"])
check("STATUS: 強制不採用で続行しL1へ落ちなかった日は「3試行目: 成功（強制不採用で続行）」と示す",
      "3試行目: 成功（強制不採用（候補ID [46]）で続行）" in _st_g_ok and "L1へフォールバック" not in _st_g_ok, _st_g_ok)
_st_g_plain = compose_post.render_generation_status(
    {**_gen_g, "call_a": {**_gen_g["call_a"], "ok": True, "data": CALL_A_DATA, "attempt_errors": [], "attempts": 1,
                          "attempt_diagnostics": [], "force_dropped_candidates": []}})
check("STATUS: リトライも強制不採用も無い通常日は試行履歴・内訳を出さない（従来どおり）",
      "試行履歴" not in _st_g_plain and "相方が成立しなかった" not in _st_g_plain, _st_g_plain)

# ---- 4) verify_post.collect_fail_evidence: セクション・由来・該当語・該当文（先頭100字） ----

def _mk_bundle(**overrides):
    bb = json.loads(json.dumps(compose_post.compose(DAILY_DATA, gen_l0)))
    for k, v in overrides.items():
        if k == "headline_for_image":
            bb["headline_for_image"] = v
        else:
            bb["sections"][k] = v
    bb["part1_md"], bb["part2_md"] = compose_post.render_markdown(bb["sections"], bb["level"])
    return bb


def _ev(bb, cid=None):
    au_ = verify_post.run_all(bb, DAILY_DATA)
    return au_, verify_post.collect_fail_evidence(bb, au_.checks)


_long = "A社の発表を受けて" + "市場参加者の見方が広がり、" * 12 + "BTCが上昇しました"
_bb = _mk_bundle(part1_points="・" + _long + "。\n・別の文です")
_au, _evs = _ev(_bb)
_e18 = [e for e in _evs if e["check"] == "C18_causal_assertion"]
check("evidence C18: セクション（part1_points）・由来（call_A）・該当語（マーカーと価格変動語）・該当文が取れる",
      len(_e18) == 1 and _e18[0]["section"] == "part1_points" and _e18[0]["origin"] == "call_A"
      and "を受けて" in _e18[0]["words"] and "上昇" in _e18[0]["words"] and "A社の発表を受けて" in _e18[0]["sentence"], str(_e18))
check("evidence: 該当文は先頭100字で切り、超える場合は「…」を付ける",
      len(_e18[0]["sentence"]) == verify_post.EVIDENCE_SENTENCE_CHARS + 1 and _e18[0]["sentence"].endswith("…"),
      str(len(_e18[0]["sentence"])))
_bb = _mk_bundle(headline_for_image="米金利の上昇を受けてBTC・ETHは軟調")
_au, _evs = _ev(_bb)
_e18h = [e for e in _evs if e["check"] == "C18_causal_assertion"]
check("evidence C18: headline_for_image由来の違反はセクション名headline_for_image（由来call_A）で特定できる"
      "（案Dの要否を判断するための記録）",
      len(_e18h) == 1 and _e18h[0]["section"] == "headline_for_image" and _e18h[0]["origin"] == "call_A", str(_e18h))
_bb = _mk_bundle(part2_flow="好感 → 買い戻しのため上昇が確認された。")
_au, _evs = _ev(_bb)
_e18f = [e for e in _evs if e["check"] == "C18_causal_assertion"]
check("evidence C18: part2_flow由来の違反は由来call_Bとして特定できる（call_A由来とは限らないことの区別）",
      len(_e18f) == 1 and _e18f[0]["section"] == "part2_flow" and _e18f[0]["origin"] == "call_B", str(_e18f))
_bb = _mk_bundle(part2_summary="仮想通貨市場は落ち着いた。確認が必要。")
_au, _evs = _ev(_bb)
_e12 = [e for e in _evs if e["check"] == "C12_banned_terms"]
check("evidence C12: 禁止語（仮想通貨）を含むセクションと文を特定できる",
      len(_e12) == 1 and _e12[0]["section"] == "part2_summary" and _e12[0]["words"] == ["仮想通貨"]
      and "仮想通貨市場" in _e12[0]["sentence"], str(_e12))
_bb = _mk_bundle(part1_points="・Reutersの報道#BTCは上昇、とみられる")
_au, _evs = _ev(_bb)
_e13 = [e for e in _evs if e["check"] == "C13_hashtag_boundary"]
check("evidence C13: ハッシュタグ境界違反のセクションと文を特定できる",
      len(_e13) >= 1 and _e13[0]["section"] == "part1_points" and "#BTC" in _e13[0]["sentence"], str(_e13))
_bb = _mk_bundle(part2_flow="Something → BankChain Alliance was mentioned → price moved.")
_au, _evs = _ev(_bb)
_e24 = [e for e in _evs if e["check"] == "C24_flow_no_unadopted_material"]
check("evidence C24: 未確認の固有名詞を含む市場のフローの文を特定できる（由来call_B）",
      len(_e24) == 1 and _e24[0]["section"] == "part2_flow" and _e24[0]["origin"] == "call_B"
      and "BankChain" in _e24[0]["words"] and "BankChain Alliance" in _e24[0]["sentence"], str(_e24))
_bb = _mk_bundle(part2_summary="総じて堅調。BankChain Allianceの動向に注目。")
_au, _evs = _ev(_bb)
_e23 = [e for e in _evs if e["check"] == "C23_summary_no_new_entities"]
check("evidence C23: 総括中の未確認の固有名詞の文を特定できる（由来call_B）",
      len(_e23) == 1 and _e23[0]["section"] == "part2_summary" and "BankChain" in _e23[0]["words"], str(_e23))
_bb = _mk_bundle(part2_flow="Fear & Greedが改善した可能性があります。")
_au, _evs = _ev(_bb)
_e26 = [e for e in _evs if e["check"] == "C26_flow_role_separation"]
check("evidence C26: 役割分離の禁止語句を含む文を特定できる",
      len(_e26) >= 1 and _e26[0]["section"] == "part2_flow" and "Greed" in _e26[0]["sentence"], str(_e26))
_bb = _mk_bundle(part2_summary="BTCは$64,247で推移。LP運用に注意。確認を続ける。")
_au, _evs = _ev(_bb)
_e27 = [e for e in _evs if e["check"] == "C27_summary_role_separation"]
check("evidence C27: 総括の役割分離違反（価格表記・禁止語句）の文を特定できる",
      len(_e27) >= 1 and all(e["section"] == "part2_summary" for e in _e27)
      and any("$64,247" in e["sentence"] for e in _e27), str(_e27))
_bb = _mk_bundle(headline_for_image="市況" * 30)
_au, _evs = _ev(_bb)
_e20 = [e for e in _evs if e["check"] == "C20_image_headline"]
check("evidence: 位置を特定できないFAIL（例: C20の字数超過）はsection=Noneの1件で、detailのみで示す",
      len(_e20) == 1 and _e20[0]["section"] is None, str(_e20))
_au_p, _evs_p = _ev(compose_post.compose(DAILY_DATA, gen_l0))
check("evidence: FAILが無い本文では証拠は空",
      _evs_p == [], str(_evs_p))
_lines = verify_post.format_fail_evidence_lines(_e18)
check("format_fail_evidence_lines: セクション特定済みの証拠だけを1件1行で整形する",
      len(_lines) == 1 and _lines[0].startswith("    └ セクション=part1_points（由来: call_A）／該当語: ")
      and verify_post.format_fail_evidence_lines(_e20) == [], str(_lines))
_det = verify_post.failing_check_details(_mk_bundle(part1_points="・" + _long), verify_post.run_all(_mk_bundle(part1_points="・" + _long), DAILY_DATA).checks)
check("failing_check_details: FAILごとにid・detail・evidence（セクション特定済みのみ）を返す",
      any(d["id"] == "C18_causal_assertion" and d["evidence"] and d["evidence"][0]["section"] == "part1_points" for d in _det), str(_det))
_orig_run_all_checks = verify_post.run_all(_mk_bundle(part1_points="・" + _long), DAILY_DATA)
check("Audit.add: 構造化extras（hits/names等）は判定result・detailに影響しない（既存のPASS/FAIL・件数は不変）",
      _orig_run_all_checks.failed == sum(1 for c in _orig_run_all_checks.checks if c["result"] == "FAIL")
      and verify_post.run_all(compose_post.compose(DAILY_DATA, gen_l0), DAILY_DATA).failed == 0)

# ---- 5) repair_post: 最終監査の記録にもFAILの中身が入る ----
_res_g = {"final_failing_checks": ["C18_causal_assertion"],
          "final_failing_check_details": _fail_detail, "checked_ids": "C12〜C24・C26〜C28・計17項目", "warnings": []}
_note_g = repair_post.render_final_audit_note(_res_g)
check("repair_post.render_final_audit_note: FAIL行の下にセクション・由来・該当語・該当文が出る（draftがコミットされない日でも判断できる）",
      "FAIL: C18_causal_assertion — 検出" in _note_g
      and "└ セクション=part1_points（由来: call_A）／該当語: を受けて・上昇／該当文: 「A社の発表を受けてBTCが上昇しました」" in _note_g, _note_g)
check("repair_post.render_final_audit_note: evidenceキーが無い旧形式の入力でも例外にならず従来どおり出る",
      "FAIL: C18_causal_assertion — x" in repair_post.render_final_audit_note(
          {"final_failing_checks": ["C18_causal_assertion"],
           "final_failing_check_details": [{"id": "C18_causal_assertion", "detail": "x"}]}))

# ---- 6) compose_post.main() end-to-end: force_drop→再監査FAIL→L1。成果物（CI成果物のみ）とSTATUS ----
_G_DATE = "2026-08-17"
_g_out_dir = Path(f"outputs/{_G_DATE}")
(_g_out_dir).mkdir(parents=True, exist_ok=True)
(_g_out_dir / "daily_data.json").write_text(json.dumps(DAILY_DATA, ensure_ascii=False), encoding="utf-8")
(_g_out_dir / f"final_audit_{_G_DATE.replace('-', '')}.json").write_text(json.dumps({"overall": "PASS"}), encoding="utf-8")
_g_call_a_data = {**CALL_A_DATA, "part1_points": ["規制当局の発表を受けてBTCが上昇しました（Reuters、2026-08-17）"]}
_g_gen = {
    "level": "L0", "news_candidate_count": 1, "news_source_status": {"BLS": {"status": "failed", "detail": "HTTP 403"}},
    "total_usage": {"input_tokens": 100, "output_tokens": 50},
    "call_a": {"ok": True, "data": _g_call_a_data, "attempts": 3, "error": None,
               "usage": {"input_tokens": 90, "output_tokens": 40}, "truncation_stats": {},
               "attempt_errors": ["AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [43, 46]"] * 2,
               "attempt_diagnostics": _gen_g["call_a"]["attempt_diagnostics"], "rejected_pairs": [],
               "force_dropped_candidates": [{"candidate_id": 46, "title": "T46", "source": "CoinDesk", "reason": "R"}]},
    "call_b": {"ok": True, "data": CALL_B_DATA, "attempts": 1, "error": None, "usage": {"input_tokens": 10, "output_tokens": 10}},
}
_orig_run, _orig_anth = generate_post.run, generate_post.anthropic.Anthropic
generate_post.run = lambda target_date, **kw: _g_gen
generate_post.anthropic.Anthropic = lambda: FakeClient(lambda kw, n: json_response(CALL_B_DATA))
_orig_argv = sys.argv
sys.argv = ["compose_post.py", _G_DATE]
try:
    _rc_main = compose_post.main()
finally:
    sys.argv = _orig_argv
    generate_post.run, generate_post.anthropic.Anthropic = _orig_run, _orig_anth
_g_status = (_g_out_dir / "GENERATION_STATUS.md").read_text(encoding="utf-8")
_g_failed = json.loads((_g_out_dir / "failed_attempt.json").read_text(encoding="utf-8"))
_g_diag = json.loads((_g_out_dir / "attempt_diagnostics.json").read_text(encoding="utf-8"))
check("compose_post.main(): 強制不採用後の再監査FAILでL1へ落ちる（従来どおり最終ゲートは不変）",
      _rc_main == 0 and _g_status.startswith("level: L1") and "L1へフォールバックしました" in _g_status, _g_status[:300])
check("compose_post.main(): STATUSにFAILしたチェックID・セクション・該当語・該当文（先頭100字）が出る",
      "FAIL: C18_causal_assertion" in _g_status and "└ セクション=part1_points（由来: call_A）" in _g_status
      and "該当語: を受けて・上昇" in _g_status and "規制当局の発表を受けてBTCが上昇しました" in _g_status, _g_status)
check("compose_post.main(): STATUSに1・2・3試行目の相方不成立の内訳と3試行目の行が出る",
      "相方が成立しなかった候補の内訳（1試行目）" in _g_status and "候補ID43 [Cointelegraph]" in _g_status
      and "3試行目: 強制不採用（候補ID [46]）で続行 → 再監査FAILのためL1へフォールバック" in _g_status, _g_status)
check("compose_post.main(): failed_attempt.jsonに破棄された本文（sections・headline_for_image）・検出内容・由来が保存される",
      _g_failed["failing_checks"] == ["C18_causal_assertion"]
      and "規制当局の発表を受けてBTCが上昇しました" in _g_failed["bundle"]["sections"]["part1_points"]
      and _g_failed["failing_details"][0]["evidence"][0]["section"] == "part1_points"
      and _g_failed["section_origin"]["part2_flow"] == "call_B"
      and any(c["id"] == "C18_causal_assertion" and c["result"] == "FAIL" for c in _g_failed["checks"]), str(_g_failed.keys()))
check("compose_post.main(): attempt_diagnostics.jsonに全試行の診断（1・2試行目を含む）が保存される",
      [d["attempt"] for d in _g_diag["attempt_diagnostics"]] == [1, 3] and len(_g_diag["attempt_errors"]) == 2
      and _g_diag["force_dropped_candidates"][0]["candidate_id"] == 46, str(_g_diag.keys()))
check("compose_post.main(): コミットされるdraft/にはフォールバック後（L1）の本文が書かれ、失敗した本文は含まれない",
      "BTCが上昇しました" not in (_g_out_dir / "draft" / "part1.md").read_text(encoding="utf-8")
      and "BTCが上昇しました" not in (_g_out_dir / "draft" / "post_bundle.json").read_text(encoding="utf-8")
      and json.loads((_g_out_dir / "draft" / "post_bundle.json").read_text(encoding="utf-8"))["level"] == "L1", "")
_yml = (REPO / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
check("daily.yml: attempt_diagnostics.json・failed_attempt.jsonがCI成果物（post-draft）の対象に入る（コミットはしない）",
      "outputs/${{ steps.target.outputs.date }}/attempt_diagnostics.json" in _yml
      and "outputs/${{ steps.target.outputs.date }}/failed_attempt.json" in _yml
      and not any(("failed_attempt" in ln or "attempt_diagnostics" in ln) for ln in _yml.splitlines()
                  if ln.strip().startswith("git add")), "")

print("=== 図版案a（v1.87・オーナー承認）: 第3パネルの主値を幅制限（幅218px）。通常日は画像不変・重なる日だけ縮小 ===")
import importlib
import infographic_renderer
from PIL import Image as _PILImage, ImageDraw as _PILDraw, ImageChops as _PILChops
import numpy as _np

_FONTS_OK = any(Path(p).exists() for p in infographic_renderer.FONT_CANDIDATES["bold"][:2]) and \
    any(Path(p).exists() for p in infographic_renderer.FONT_CANDIDATES["regular"][:2])
if not _FONTS_OK:
    print("  （Noto Sans CJKが無いため、図版の画像比較テストを省略）")
else:
    R_ = infographic_renderer

    def _ink_extent(value, size, bold, x):
        im = _PILImage.new("L", (1400, 100), 0)
        _PILDraw.Draw(im).text((x, 50), value, font=R_.font(size, bold), fill=255, anchor="lm")
        cols = _np.where((_np.array(im) > 0).any(axis=0))[0]
        return int(cols.min()), int(cols.max())

    def _chosen_size(value):
        probe = _PILImage.new("RGB", (10, 10))
        return R_.fitted_text(_PILDraw.Draw(probe), (0, 0), value, R_.BASE_MAIN_MAX_WIDTH, R_.BASE_MAIN_FONT_SIZE,
                              R_.NAVY, True, "lm", R_.BASE_MAIN_MIN_FONT_SIZE)

    def _width_at(value, size):
        probe = _PILDraw.Draw(_PILImage.new("RGB", (10, 10)))
        b = probe.textbbox((0, 0), value, font=R_.font(size, True), anchor="lm")
        return b[2] - b[0]

    def _ink_gap(main, sub):
        """主値（描画原点x=620）と円換算（x=830。「（」の字形が右寄りのためインク左端は約847）のインクの
        すき間（px）。0以下なら重なっている。"""
        m = _ink_extent(main, _chosen_size(main), True, 620)
        s = _ink_extent(f"（{sub}）", 25, False, 830)
        return s[0] - m[1] - 1

    # ---- 境界の固定（幅の判定） ----
    check("図版a: 定数が承認どおり（最大幅218px・通常のフォントサイズ51・下限36）",
          R_.BASE_MAIN_MAX_WIDTH == 218 and R_.BASE_MAIN_FONT_SIZE == 51 and R_.BASE_MAIN_MIN_FONT_SIZE == 36,
          f"{R_.BASE_MAIN_MAX_WIDTH},{R_.BASE_MAIN_FONT_SIZE},{R_.BASE_MAIN_MIN_FONT_SIZE}")
    _normal_vals = ["$9.999億", "$9.979億", "$4.950億", "$0.123億", "$63.48億", "$99.99億", "$47.11億", "84.7%", "未確認"]
    check("図版a（境界）: 通常の主値（4桁の数字までの$X.XXX億・$XX.XX億・USDCドミナンス・未確認）は幅218px以内で、従来と同じ51pxで描く",
          all(_chosen_size(v) == 51 and _width_at(v, 51) <= R_.BASE_MAIN_MAX_WIDTH for v in _normal_vals),
          str({v: (_chosen_size(v), _width_at(v, 51)) for v in _normal_vals}))
    _long_vals = ["$10.000億", "$14.909億", "$16.705億", "$100.00億", "$100.000億"]
    check("図版a（境界）: 5桁以上の主値（$10.000億・$14.909億・$100.00億等）は51pxでは幅218pxを超え、縮小して218px以内に収める",
          all(_width_at(v, 51) > R_.BASE_MAIN_MAX_WIDTH and R_.BASE_MAIN_MIN_FONT_SIZE <= _chosen_size(v) < 51
              and _width_at(v, _chosen_size(v)) <= R_.BASE_MAIN_MAX_WIDTH for v in _long_vals),
          str({v: (_width_at(v, 51), _chosen_size(v)) for v in _long_vals}))
    check("図版a（境界）: 4桁の数字の最大（$9.999億）と5桁の最小（$10.000億）の間に境界がある（DEX出来高が約10億ドルを超えると縮小）",
          _width_at("$9.999億", 51) <= 218 < _width_at("$10.000億", 51),
          f"{_width_at('$9.999億', 51)} / {_width_at('$10.000億', 51)}")
    check("図版a: $14.909億は44pxに縮小される（調査時の実測と同じ）",
          _chosen_size("$14.909億") == 44, str(_chosen_size("$14.909億")))

    # ---- 重なりの解消（インクのすき間） ----
    check("図版a: 修正前の描画（幅制限なし・51px）では$14.909億と「（¥2,345億）」のインクが重なる（再発防止テストの前提＝バグの再現）",
          (lambda m, s: s[0] - m[1] - 1)(_ink_extent("$14.909億", 51, True, 620), _ink_extent("（¥2,345億）", 25, False, 830)) < 0)
    for _main, _sub in [("$14.909億", "¥2,345億"), ("$12.404億", "¥1,959億"), ("$16.705億", "¥2,655億"),
                         ("$10.000億", "¥1,579億"), ("$100.00億", "¥1.57兆"), ("$9.999億", "¥1,579億"), ("$63.48億", "¥9,985億")]:
        check(f"図版a: {_main}＋（{_sub}）は主値と円換算のインクが重ならない（すき間>0px）",
              _ink_gap(_main, _sub) > 0, str(_ink_gap(_main, _sub)))

    # ---- 実データ全日：通常日は画像不変・重なる日は主値の領域だけが変わり、重なりが残らない ----
    _same, _changed, _remaining = [], [], []
    for _dp in sorted((REPO / "outputs").glob("2026-*/daily_data.json")):
        _day = _dp.parent.name
        _png = _dp.parent / "infographic.png"
        if not _png.exists():
            continue
        _data = json.loads(_dp.read_text(encoding="utf-8"))
        _img = R_.render(_data).convert("RGB")
        _old = _PILImage.open(_png).convert("RGB")
        _bbox = _PILChops.difference(_img, _old).getbbox()
        _b = _data["base"]
        for _k in ("tvl", "dex_volume"):
            if _ink_gap(_b[_k], _b[_k + "_jpy"]) <= 0:
                _remaining.append((_day, _k))
        if _bbox is None:
            _same.append(_day)
        else:
            _changed.append((_day, _bbox, _b["dex_volume"]))
    check("図版a（実データ）: コミット済みの全日（52日以上）で、修正後の描画に主値と円換算の重なりが残らない",
          len(_same) + len(_changed) >= 52 and not _remaining, f"days={len(_same) + len(_changed)} remaining={_remaining}")
    check("図版a（実データ）: 修正前に重なっていなかった33日の画像は、修正後もコミット済み画像とピクセル完全一致（通常日は不変）",
          len(_same) >= 33, f"same={len(_same)}")
    check("図版a（実データ）: 変わった日は、すべてDEX出来高が$10億（表示$10.000億）以上の日で、変化は第3パネルDEX行の主値の領域（x622〜868・y981〜1032）に限られる",
          len(_changed) >= 19 and all(float(d[2].lstrip('$').rstrip('億')) >= 10 for d in _changed)
          and all(d[1][0] >= 600 and d[1][2] <= 900 and 960 <= d[1][1] and d[1][3] <= 1045 for d in _changed),
          str(_changed[:3]))
    check("図版a（実データ）: 修正前に重なっていた19日（2026-08-20〜10-01）と10/2が、変わった日と一致する",
          {d[0] for d in _changed} >= {"2026-08-20", "2026-09-29", "2026-09-30", "2026-10-01"}, str([d[0] for d in _changed]))

    # ---- 他の描画箇所は不変（fitted_text化は第3パネルの主値だけ） ----
    _src = (REPO / "scripts" / "infographic_renderer.py").read_text(encoding="utf-8")
    check("図版a: 第3パネルの主値は幅制限つき（fitted_text・BASE_MAIN_MAX_WIDTH）で描く。円換算の位置（x1+770・25px）は変えていない",
          "fitted_text(draw, (x1 + 560, y), main, BASE_MAIN_MAX_WIDTH, BASE_MAIN_FONT_SIZE" in _src
          and 'text(draw, (x1 + 770, y), f"（{sub}）", 25, NAVY, False, "lm")' in _src
          and 'text(draw, (x1 + 165, y), label, 37, NAVY, True, "lm")' in _src)


print("=== 本文機械監査のPASS／SKIP／FAIL件数の併記（v1.88・オーナー承認・表示のみの変更） ===")
_l1_bundle = compose_post.compose(DAILY_DATA, {"level": "L1", "call_a": {"ok": False, "data": None},
                                                "call_b": {"ok": True, "data": CALL_B_DATA}, "news_candidate_count": 1})
_au_l1 = verify_post.run_all(_l1_bundle, DAILY_DATA)
_cnt_l1 = verify_post.summarize_check_results(_au_l1.checks)
check("summarize_check_results: L1の本文はPASS・SKIP・FAILの件数と合計（計17項目）、SKIPしたチェック番号が取れる",
      _cnt_l1["total"] == 17 and _cnt_l1["PASS"] + _cnt_l1["SKIP"] + _cnt_l1["FAIL"] == 17
      and _cnt_l1["FAIL"] == 0 and _cnt_l1["SKIP"] >= 3 and "C19" in _cnt_l1["skip_ids"] and "C21" in _cnt_l1["skip_ids"],
      str(_cnt_l1))
_cnt_l0 = verify_post.summarize_check_results(verify_post.run_all(compose_post.compose(DAILY_DATA, gen_l0), DAILY_DATA).checks)
check("summarize_check_results: L0（全チェック評価）ではSKIPが0件・skip_idsは空",
      _cnt_l0["SKIP"] == 0 and _cnt_l0["skip_ids"] == [] and _cnt_l0["PASS"] == _cnt_l0["total"] - _cnt_l0["FAIL"], str(_cnt_l0))
check("summarize_check_results: C16bのような枝番つきIDは親番号の形（C16b）で、同じ番号は重複して数えない",
      verify_post.summarize_check_results([
          {"id": "C16b_transcription_scan", "result": "SKIP"}, {"id": "C16b_x", "result": "SKIP"},
          {"id": "C19_audit_ledger", "result": "SKIP"}, {"id": "C12_x", "result": "PASS"}, {"id": "C13_x", "result": "FAIL"}])
      == {"PASS": 1, "SKIP": 3, "FAIL": 1, "total": 5, "skip_ids": ["C16b", "C19"]})
check("summarize_check_results: 空・想定外のresultでも例外にならない",
      verify_post.summarize_check_results([]) == {"PASS": 0, "SKIP": 0, "FAIL": 0, "total": 0, "skip_ids": []}
      and verify_post.summarize_check_results([{"id": "X", "result": "?"}])["total"] == 1)
check("format_check_counts: 「PASS13・SKIP4〔C19・C21・C22・C26〕・FAIL0」の形（SKIPが無ければ番号を出さない）",
      verify_post.format_check_counts({"PASS": 13, "SKIP": 4, "FAIL": 0, "total": 17, "skip_ids": ["C19", "C21", "C22", "C26"]})
      == "PASS13・SKIP4〔C19・C21・C22・C26〕・FAIL0"
      and verify_post.format_check_counts({"PASS": 17, "SKIP": 0, "FAIL": 0, "total": 17, "skip_ids": []}) == "PASS17・SKIP0・FAIL0")
_res_cnt = {"final_failing_checks": [], "final_failing_check_details": [], "checked_ids": "C12〜C24・C26〜C28・計17項目",
            "check_counts": {"PASS": 13, "SKIP": 4, "FAIL": 0, "total": 17, "skip_ids": ["C19", "C21", "C22", "C26"]}, "warnings": []}
_note_cnt = repair_post.render_final_audit_note(_res_cnt)
check("render_final_audit_note: overall=PASSの横に件数（内訳 PASS13・SKIP4〔C19・C21・C22・C26〕・FAIL0）が併記される",
      "本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS（内訳 PASS13・SKIP4〔C19・C21・C22・C26〕・FAIL0）" in _note_cnt, _note_cnt)
_res_cnt_fail = {"final_failing_checks": ["C18_causal_assertion"], "final_failing_check_details": [{"id": "C18_causal_assertion", "detail": "x"}],
                 "checked_ids": "C12〜C28・計17項目", "check_counts": {"PASS": 15, "SKIP": 1, "FAIL": 1, "total": 17, "skip_ids": ["C26"]}}
check("render_final_audit_note: FAILの日もoverall=FAILの横に件数が出る",
      "overall=FAIL（内訳 PASS15・SKIP1〔C26〕・FAIL1）" in repair_post.render_final_audit_note(_res_cnt_fail))
check("render_final_audit_note: check_countsが無い旧形式の入力では従来どおりの表記（後方互換）",
      "overall=PASS\n" in repair_post.render_final_audit_note({"final_failing_checks": [], "final_failing_check_details": []})
      and "内訳" not in repair_post.render_final_audit_note({"final_failing_checks": [], "final_failing_check_details": []}))
_orig_checks_note = repair_post.render_final_audit_note(_res_cnt)
check("render_final_audit_note: 件数の併記は表示のみ（FAILしたチェックの詳細行・警告行は従来どおり）",
      "FAILしたチェックはありません。" in _orig_checks_note
      and "向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告なし（" + _wk() + "）" in _orig_checks_note)
# repair()の結果にも件数が入る（実際のrun_allの結果から）。L1の本文でrepair()を通す
_REPAIR_CNT_DATE = "2026-08-17"
Path(f"outputs/{_REPAIR_CNT_DATE}/draft").mkdir(parents=True, exist_ok=True)
Path(f"outputs/{_REPAIR_CNT_DATE}/daily_data.json").write_text(json.dumps(DAILY_DATA, ensure_ascii=False), encoding="utf-8")
Path(f"outputs/{_REPAIR_CNT_DATE}/draft/post_bundle.json").write_text(json.dumps(_l1_bundle, ensure_ascii=False), encoding="utf-8")
_rep_cnt = repair_post.repair(_REPAIR_CNT_DATE, client=FakeClient(lambda kw, n: json_response({"rewritten_sentence": "x"})))
check("repair(): 結果のcheck_countsは実際の最終監査の件数（L1の本文はSKIPあり・FAIL0）で、render_final_audit_noteに併記される",
      _rep_cnt["check_counts"] == _cnt_l1
      and f"（内訳 {verify_post.format_check_counts(_cnt_l1)}）" in repair_post.render_final_audit_note(_rep_cnt),
      str(_rep_cnt["check_counts"]))
check("repair(): 件数の追加は判定に影響しない（final_failing_checks・rescuedは従来どおり）",
      _rep_cnt["final_failing_checks"] == [] and _rep_cnt["rounds_used"] == 0)

print("=== 案A（v1.89・オーナー承認・v1.79の条件の拡張）: 強制不採用後の再監査がC18・C13のみFAILなら、L1へ落とす前に局所修正→再監査 ===")
import shutil as _shutil


def _usage_resp(obj, i=111, o=22):
    r = json_response(obj)
    r.usage = type("U", (), {"input_tokens": i, "output_tokens": o})()
    return r


def _run_force_drop_main(gen_call_a_data, call_b_data=CALL_B_DATA, client_fn=None, patch_repair=None):
    """compose_post.main()を強制不採用ありのgenで実行し、(rc, status, files, call_log)を返す。"""
    _d = Path(f"outputs/{_G_DATE}")
    for sub in ("draft",):
        _shutil.rmtree(_d / sub, ignore_errors=True)
    for f in ("GENERATION_STATUS.md", "failed_attempt.json", "attempt_diagnostics.json", "rejected_pairs.json"):
        (_d / f).unlink(missing_ok=True)
    (_d / "daily_data.json").write_text(json.dumps(DAILY_DATA, ensure_ascii=False), encoding="utf-8")
    (_d / f"final_audit_{_G_DATE.replace('-', '')}.json").write_text(json.dumps({"overall": "PASS"}), encoding="utf-8")
    gen = json.loads(json.dumps(_g_gen))
    gen["call_a"]["data"] = gen_call_a_data
    gen["call_b"]["data"] = call_b_data
    calls = []

    def _default_client_fn(kw, n):
        sysm = str(kw.get("system", ""))
        if "rewritten_sentence" in sysm:
            return _usage_resp({"rewritten_sentence": "規制当局の発表を受けてBTCが上昇した可能性があります（Reuters、2026-08-17）"})
        return json_response(CALL_B_DATA)

    _inner_fn = client_fn or _default_client_fn

    def fn(kw, n):
        sysm = str(kw.get("system", ""))
        calls.append("repair" if "rewritten_sentence" in sysm else ("call_b" if "part2_flow" in sysm else "other"))
        return _inner_fn(kw, n)
    _o_run, _o_anth = generate_post.run, generate_post.anthropic.Anthropic
    _o_rb = None
    generate_post.run = lambda target_date, **kw: gen
    generate_post.anthropic.Anthropic = lambda: FakeClient(fn)
    if patch_repair is not None:
        _o_rb = repair_post.repair_bundle
        repair_post.repair_bundle = patch_repair
    _argv = sys.argv
    sys.argv = ["compose_post.py", _G_DATE]
    try:
        rc = compose_post.main()
    finally:
        sys.argv = _argv
        generate_post.run, generate_post.anthropic.Anthropic = _o_run, _o_anth
        if _o_rb is not None:
            repair_post.repair_bundle = _o_rb
    status = (_d / "GENERATION_STATUS.md").read_text(encoding="utf-8")
    files = {"failed": (_d / "failed_attempt.json").exists(),
             "bundle": json.loads((_d / "draft" / "post_bundle.json").read_text(encoding="utf-8")),
             "part1": (_d / "draft" / "part1.md").read_text(encoding="utf-8")}
    if files["failed"]:
        files["failed_json"] = json.loads((_d / "failed_attempt.json").read_text(encoding="utf-8"))
    return rc, status, files, calls


# S1: 修正に成功 → L0のまま続行
_rc1, _st1, _f1, _calls1 = _run_force_drop_main(_g_call_a_data)
check("案A（S1）: 強制不採用後の再監査がC18のみFAILのとき、局所修正を適用して再監査PASS→L0のまま続行する（L1へ落ちない）",
      _rc1 == 0 and _st1.startswith("level: L0") and _f1["bundle"]["level"] == "L0"
      and "可能性があります" in _f1["bundle"]["sections"]["part1_points"], _st1[:200])
check("案A（S1）: 修正は違反文のcall_Rだけ（call_Aの再試行・call_Bの再生成は行わない）",
      _calls1 == ["repair"], str(_calls1))
check("案A（S1）: STATUSに局所修正の前後の文（修正前・修正後）が記載される",
      "局所修正（repair_postと同じ処理・v1.89）を適用しました" in _st1
      and "修正前: ・規制当局の発表を受けてBTCが上昇しました（Reuters、2026-08-17）" in _st1
      and "修正後: ・規制当局の発表を受けてBTCが上昇した可能性があります（Reuters、2026-08-17）" in _st1
      and "局所修正後の再監査: 全項目PASS → L0のまま続行します" in _st1 and "[C18_causal_assertion / part1_points] OK" in _st1, _st1)
check("案A（S1）: L1フォールバックの記録は出ず、failed_attempt.jsonも作られない（破棄された本文が無いため）",
      "L1へフォールバックしました" not in _st1 and not _f1["failed"], str(_f1["failed"]))
check("案A（S1）: 修正呼び出しのトークンがtoken_usage（合計）に加算される（元の合計 in=100/out=50 に修正分 in=111/out=22）",
      "input=211, output=72" in _st1, _st1.split("token_usage")[1].split("\n")[0])
check("案A（S1）: コミットされるdraft/part1.mdは修正後の文（post_bundle.jsonと一致）",
      "可能性があります" in _f1["part1"] and "BTCが上昇しました（Reuters" not in _f1["part1"], _f1["part1"])
check("案A（S1）: 修正後のbundleは全チェックPASS（最終ゲート相当のrun_allでFAIL0）",
      verify_post.run_all(_f1["bundle"], DAILY_DATA).failed == 0)

# S2: 修正しても違反が残る → 従来どおりL1
_rc2, _st2, _f2, _calls2 = _run_force_drop_main(
    _g_call_a_data,
    client_fn=lambda kw, n: _usage_resp({"rewritten_sentence": "規制当局の発表を受けてBTCが上昇しました"})
    if "rewritten_sentence" in str(kw.get("system", "")) else json_response(CALL_B_DATA))
check("案A（S2）: 修正後もC18が残る場合は、従来どおりL1へフォールバックする（最終ゲートは不変）",
      _rc2 == 0 and _st2.startswith("level: L1") and "L1へフォールバックしました" in _st2
      and "局所修正後の再監査: なおFAIL ['C18_causal_assertion']" in _st2, _st2[:300])
check("案A（S2）: 修正の試行（修正前の文・修正後の文）と、残ったFAILの中身（セクション・該当語・該当文）がSTATUSに残る",
      "修正前: ・規制当局の発表を受けてBTCが上昇しました" in _st2 and "└ セクション=part1_points（由来: call_A）" in _st2
      and "最終結果: 未救済" in _st2, _st2)
check("案A（S2）: failed_attempt.jsonに修正前の本文・修正の記録（rounds_log）・修正後のbundleが保存される。コミット対象のdraft/はL1の本文",
      _f2["failed"] and "BTCが上昇しました" in _f2["failed_json"]["bundle"]["sections"]["part1_points"]
      and _f2["failed_json"]["local_repair"]["rounds_log"] and "bundle_after_repair" in _f2["failed_json"]["local_repair"]
      and _f2["bundle"]["level"] == "L1", str(_f2.get("failed_json", {}).keys()))
check("案A（S2）: 修正が最大2ラウンドで打ち切られ、その呼び出し＋L1用のcall_B再生成が行われる（repair×2→call_b）",
      _calls2 == ["repair", "repair", "call_b"], str(_calls2))
check("案A（S2）: 修正のトークン（2ラウンド分）もtoken_usageに加算される（in=100+111×2、out=50+22×2）",
      "input=322, output=94" in _st2, _st2.split("token_usage")[1].split("\n")[0])

# S3: C18以外もFAIL → 修正しない
_cb_bad = {"part2_flow": ["Something → BankChain Alliance was mentioned but never adopted → price moved。"],
           "part2_summary": "地合いは総じて改善。継続的な確認が必要。"}
_rc3, _st3, _f3, _calls3 = _run_force_drop_main(_g_call_a_data, call_b_data=_cb_bad)
check("案A（S3）: FAILがC18・C13以外を含む（C24もFAIL）場合は局所修正を試みず、従来どおりL1へ落ちる（call_Rを呼ばない）",
      _rc3 == 0 and _st3.startswith("level: L1") and "repair" not in _calls3 and "局所修正" not in _st3
      and "C24_flow_no_unadopted_material" in _st3, str(_calls3))

# S4: 修正が例外 → L1
def _boom(bundle, daily_data, client):
    raise RuntimeError("boom")


_rc4, _st4, _f4, _calls4 = _run_force_drop_main(_g_call_a_data, patch_repair=_boom)
check("案A（S4）: 局所修正が例外を出しても、日を止めずL1へフォールバックし、例外をSTATUSに記録する",
      _rc4 == 0 and _st4.startswith("level: L1") and "局所修正は例外で失敗しました（RuntimeError: boom）" in _st4
      and _f4["failed"], _st4[:300])

# S5: headline_for_image由来のC18のみ → 局所修正の対象外（案D保留）なのでL1。STATUSで由来が分かる
_ca_hfi = {**CALL_A_DATA, "headline_for_image": "米金利の上昇を受けてBTC・ETHは軟調"}
_rc5, _st5, _f5, _calls5 = _run_force_drop_main(_ca_hfi)
check("案A（S5）: headline_for_image由来のC18は局所修正の対象外（案Dは保留）なので修正されずL1へ落ちる（call_Rを呼ばない）",
      _rc5 == 0 and _st5.startswith("level: L1") and "repair" not in _calls5, str(_calls5))
check("案A（S5）: STATUSに、FAILの由来がheadline_for_imageであること（案Dの要否の判断材料）と、対象文が無かった旨が記録される",
      "セクション=headline_for_image（由来: call_A）" in _st5 and "局所修正後の再監査: なおFAIL ['C18_causal_assertion']" in _st5, _st5)

# S6: 強制不採用が無い日は、compose_postでは局所修正しない（従来どおりrepair_postの担当）
_g_gen_nofd = json.loads(json.dumps(_g_gen))
_g_gen_nofd["call_a"]["force_dropped_candidates"] = []
_g_gen_nofd["call_a"]["data"] = _g_call_a_data
_d6 = Path(f"outputs/{_G_DATE}")
_shutil.rmtree(_d6 / "draft", ignore_errors=True)
_o_run6 = generate_post.run
generate_post.run = lambda target_date, **kw: _g_gen_nofd
_calls6 = []
_o_anth6 = generate_post.anthropic.Anthropic
generate_post.anthropic.Anthropic = lambda: FakeClient(lambda kw, n: (_calls6.append(1), json_response(CALL_B_DATA))[1])
_argv6 = sys.argv
sys.argv = ["compose_post.py", _G_DATE]
try:
    compose_post.main()
finally:
    sys.argv = _argv6
    generate_post.run, generate_post.anthropic.Anthropic = _o_run6, _o_anth6
_b6 = json.loads((_d6 / "draft" / "post_bundle.json").read_text(encoding="utf-8"))
check("案A（S6）: 強制不採用が無い日は、compose_postでは修正もフォールバックもしない（C18違反を含むL0のまま。従来どおり後段のrepair_postが担当）",
      _b6["level"] == "L0" and not _calls6 and "BTCが上昇しました" in _b6["sections"]["part1_points"], str(_calls6))

# 単体: 修正の対象判定
_bd = compose_post.compose(DAILY_DATA, gen_l0)
check("_apply_local_repair_after_force_drop: FAILが空・修正対象外のチェックを含む場合はNone（修正を試みない）",
      compose_post._apply_local_repair_after_force_drop(_bd, DAILY_DATA, []) is None
      and compose_post._apply_local_repair_after_force_drop(_bd, DAILY_DATA, ["C18_causal_assertion", "C24_flow_no_unadopted_material"]) is None
      and compose_post._apply_local_repair_after_force_drop(_bd, DAILY_DATA, ["C23_summary_no_new_entities"]) is None)
_before_copy = json.dumps(_bd, sort_keys=True)
_bd2 = json.loads(json.dumps(_bd))
_bd2["sections"]["part1_points"] = "・規制当局の発表を受けてBTCが上昇しました（Reuters、2026-08-17）"
_bd2["part1_md"], _bd2["part2_md"] = compose_post.render_markdown(_bd2["sections"], _bd2["level"])
_snap2 = json.dumps(_bd2, sort_keys=True)
_info = compose_post._apply_local_repair_after_force_drop(
    _bd2, DAILY_DATA, ["C18_causal_assertion"],
    client=FakeClient(lambda kw, n: _usage_resp({"rewritten_sentence": "規制当局の発表を受けてBTCが上昇した可能性があります（Reuters、2026-08-17）"})))
check("_apply_local_repair_after_force_drop: 元のbundleは変更せず、修正後のコピーを返す（L1フォールバック時に元の本文を保存できる）",
      json.dumps(_bd2, sort_keys=True) == _snap2 and _info["bundle"] is not _bd2
      and "可能性があります" in _info["bundle"]["sections"]["part1_points"] and _info["result"]["final_failing_checks"] == [], str(_info["result"]["final_failing_checks"]))
# repair_bundleとrepair()の同値性（ファイル経由と同じ結果）
_R_DATE = "2026-08-17"
Path(f"outputs/{_R_DATE}/draft").mkdir(parents=True, exist_ok=True)
Path(f"outputs/{_R_DATE}/draft/post_bundle.json").write_text(json.dumps(_bd2, ensure_ascii=False), encoding="utf-8")
_fc = lambda: FakeClient(lambda kw, n: _usage_resp({"rewritten_sentence": "規制当局の発表を受けてBTCが上昇した可能性があります（Reuters、2026-08-17）"}))
_file_res = repair_post.repair(_R_DATE, client=_fc())
_mem = json.loads(json.dumps(_bd2))
_mem_res = repair_post.repair_bundle(_mem, DAILY_DATA, _fc())
check("repair_bundle（メモリ）とrepair()（ファイル経由）は同じ結果を返す（抽出前後で挙動が変わらない）",
      {k: v for k, v in _file_res.items() if k != "target_date_jst"} == _mem_res
      and json.loads(Path(f"outputs/{_R_DATE}/draft/post_bundle.json").read_text(encoding="utf-8"))["sections"] == _mem["sections"], "")

print("=== ニュース取得の「連続○日」表示（v1.90・オーナー承認：現状維持＋表示。取得の挙動・判定は変えない） ===")
_SR = Path("streak_outputs")


def _write_status(day, sources, body=None):
    d = _SR / day
    d.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = "level: L0\nnews_sources:\n" + "".join(f"  - {n}: {st}\n" for n, st in sources) + "news_candidates_today: 3件\n"
    (d / "GENERATION_STATUS.md").write_text(body, encoding="utf-8")


_ok = "ok（対象日1件／取得25件）"
_BLS403 = "failed（HTTP 403）"
_NS = {"BLS": {"status": "failed", "detail": "HTTP 403"}, "SEC": {"status": "ok", "kept_count": 1, "raw_count": 25}}
check("_parse_news_sources_block: ok／failedを情報源ごとに読む（件数表記・括弧の中身は無視）",
      compose_post._parse_news_sources_block("level: L0\nnews_sources:\n  - SEC: ok（対象日1件／取得25件）\n"
                                              "  - Google News (Reuters検索): ok（対象日0件／取得0件）\n  - BLS: failed（HTTP 403）\n"
                                              "news_candidates_today: 3件\n")
      == {"SEC": "ok", "Google News (Reuters検索)": "ok", "BLS": "failed"})
check("_parse_news_sources_block: ブロックが無い（L3の最小STATUS）・「（情報源未実行）」のときはNone（取得状況は不明）",
      compose_post._parse_news_sources_block("level: L3\n判定理由: x\n") is None
      and compose_post._parse_news_sources_block("level: L0\nnews_sources:\n  （情報源未実行）\nnews_candidates_today: 0件\n") is None)

# 連続: 8日前=ok、7〜1日前=failed（途中2日はSTATUSなし・1日はL3）→ 本日を含め、STATUSのある日だけ数える
_write_status("2026-09-20", [("BLS", _ok), ("SEC", _ok)])
_write_status("2026-09-21", [("BLS", _BLS403), ("SEC", _ok)])
_write_status("2026-09-22", [("BLS", _BLS403), ("SEC", _ok)])
# 2026-09-23: STATUSなし（数えず・途切れさせない）
_write_status("2026-09-24", None, body="level: L3\n判定理由: x\n")  # 取得状況の記載なし（数えず・途切れさせない）
_write_status("2026-09-25", [("BLS", _BLS403), ("SEC", _ok)])
(_SR / "2026-09-26").mkdir(parents=True, exist_ok=True)  # STATUSファイルの無いディレクトリ
_write_status("2026-09-27", [("BLS", _BLS403), ("SEC", _ok)])
_st = compose_post._news_failure_streaks("2026-09-28", _NS, outputs_root=_SR)
check("連続日数: 本日を含め、STATUSのある連続failed日を数え、okの日で止まる（9/27・9/25・9/22・9/21＋本日＝5日。STATUS無し・L3の日は数えず途切れさせない）",
      _st == {"BLS": (5, False)}, str(_st))
check("連続日数: okの情報源・本日failedでない情報源は対象外（SECは出ない）", "SEC" not in _st)
check("連続日数: 本日の対象日より後の日付ディレクトリは数えない（未来日・当日の既存STATUSは無視）",
      (_write_status("2026-09-28", [("BLS", _BLS403)]) or True)
      and compose_post._news_failure_streaks("2026-09-28", _NS, outputs_root=_SR) == {"BLS": (5, False)}
      and (_write_status("2026-09-29", [("BLS", _BLS403)]) or True)
      and compose_post._news_failure_streaks("2026-09-28", _NS, outputs_root=_SR) == {"BLS": (5, False)})
# 昨日がok → 新規（1日）
_write_status("2026-10-01", [("BLS", _ok)])
_st1 = compose_post._news_failure_streaks("2026-10-02", _NS, outputs_root=_SR)
check("連続日数: 昨日の記録がokなら連続1日・回復を確認済み（＝新規）", _st1 == {"BLS": (1, False)}, str(_st1))
# 過去の記録がその情報源を並べていない → その情報源がまだ無かった日なので止める
_write_status("2026-10-03", [("SEC", _ok)])
_st2 = compose_post._news_failure_streaks("2026-10-04", _NS, outputs_root=_SR)
check("連続日数: 昨日の記録に情報源が無い（他の情報源は並ぶ）なら、その日で止める（まだ無かった日）", _st2 == {"BLS": (1, False)}, str(_st2))
# 回復が見つからないまま最古の記録に達する → 以上（open_ended）
_SR2 = Path("streak_outputs2")
for _d in ("2026-09-01", "2026-09-02", "2026-09-03"):
    (_SR2 / _d).mkdir(parents=True, exist_ok=True)
    (_SR2 / _d / "GENERATION_STATUS.md").write_text(f"level: L0\nnews_sources:\n  - BLS: {_BLS403}\n", encoding="utf-8")
_st3 = compose_post._news_failure_streaks("2026-09-04", _NS, outputs_root=_SR2)
check("連続日数: 回復が見つからないまま最も古い記録まで達したら open_ended=True（それ以前は不明）", _st3 == {"BLS": (4, True)}, str(_st3))
check("連続日数: 過去の記録が1件も無ければ（1, True）＝本日だけ・過去不明",
      compose_post._news_failure_streaks("2026-09-04", _NS, outputs_root=Path("no_such_dir")) == {"BLS": (1, True)})
check("連続日数: 全情報源がokの日は何も数えない（空dict）",
      compose_post._news_failure_streaks("2026-09-04", {"SEC": {"status": "ok"}}, outputs_root=_SR2) == {}
      and compose_post._news_failure_streaks("2026-09-04", {}, outputs_root=_SR2) == {})
check("連続日数: 読めない・壊れたSTATUSがあっても例外にならず、その日は数えない",
      (_SR2 / "2026-09-02" / "GENERATION_STATUS.md").write_bytes(b"\xff\xfe\x00") is not None
      and compose_post._news_failure_streaks("2026-09-04", _NS, outputs_root=_SR2) == {"BLS": (3, True)})

# 表示
_lines = compose_post._render_news_source_lines(_NS, {"BLS": (5, False)})
check("表示: failedの行に「・連続N日」が付き、okの行は従来どおり", "  - BLS: failed（HTTP 403）・連続5日" in _lines
      and "  - SEC: ok（対象日1件／取得25件）" in _lines, "\n".join(_lines))
check("表示: 注記（本日を含む・STATUSのある日だけ数える）が連続日数を出す日だけ付く",
      any("本日を含み" in ln and "GENERATION_STATUS.mdが残っている日だけ" in ln for ln in _lines)
      and not any("本日を含み" in ln for ln in compose_post._render_news_source_lines(_NS)), "\n".join(_lines))
check("表示: 連続1日は、回復確認済みなら（新規）／過去の記録が無ければ（過去の記録なし）",
      "  - BLS: failed（HTTP 403）・連続1日（新規）" in compose_post._render_news_source_lines(_NS, {"BLS": (1, False)})
      and "  - BLS: failed（HTTP 403）・連続1日（過去の記録なし）" in compose_post._render_news_source_lines(_NS, {"BLS": (1, True)}))
check("表示: 回復が見つからないままの長期連続は「N日以上」",
      "  - BLS: failed（HTTP 403）・連続37日以上" in compose_post._render_news_source_lines(_NS, {"BLS": (37, True)}))
check("後方互換: news_streaksを渡さなければ従来の表示のまま（連続・注記なし）",
      compose_post._render_news_source_lines(_NS) == ["  - BLS: failed（HTTP 403）", "  - SEC: ok（対象日1件／取得25件）"]
      and compose_post._render_news_source_lines({}) == ["  （情報源未実行）"])

# main()の統合: 前日のSTATUSがBLS failedなら、本日のSTATUSに「連続2日」が出る（判定・終了コードは不変）
_prev = Path("outputs/2026-08-16")
_prev.mkdir(parents=True, exist_ok=True)
(_prev / "GENERATION_STATUS.md").write_text(f"level: L0\nnews_sources:\n  - BLS: {_BLS403}\n", encoding="utf-8")
_rc_s, _st_s, _f_s, _calls_s = _run_force_drop_main(_g_call_a_data)
check("main()統合: STATUSのnews_sourcesに「BLS: failed（HTTP 403）・連続2日」が出る（前日分のSTATUS＋本日）。levelや終了コードは連続日数表示の影響を受けない",
      "  - BLS: failed（HTTP 403）・連続2日" in _st_s and _rc_s == 0 and _st_s.startswith("level: L0"), _st_s[:600])
(_prev / "GENERATION_STATUS.md").unlink()
_rc_s2, _st_s2, _f_s2, _c_s2 = _run_force_drop_main(_g_call_a_data)
check("main()統合: 過去のSTATUSが無い場合は「連続1日（過去の記録なし）」（本日分だけ）",
      "  - BLS: failed（HTTP 403）・連続1日（過去の記録なし）" in _st_s2 and _rc_s2 == 0, _st_s2[:600])

print("=== v1.91（オーナー承認）: 見出しのタグ不要（プロンプトからタグ指示を外す）＋見出しのタグのWARN＋WARN欄の種類別件数 ===")
check("find_headline_hashtags: ヘッドラインのタグ（#BTC #ETH）を検出し、タグの無い文・C#のような語・空は検出しない",
      verify_post.find_headline_hashtags("FRBが発表しました。 #BTC #ETH") == ["#BTC", "#ETH"]
      and verify_post.find_headline_hashtags("FRBが発表しました。") == []
      and verify_post.find_headline_hashtags("C#の話") == [] and verify_post.find_headline_hashtags(None) == [])
_hb = json.loads(json.dumps(_b_dir))
_hb["sections"]["part1_headline"] = "FRBが申請の承認を発表しました。 #BTC #ETH"
_au_h = verify_post.run_all(_hb, DAILY_DATA)
_hw = [w for w in _au_h.warnings if w["id"] == "W_headline_hashtag"]
check("見出しのタグのWARN: ヘッドラインにタグがあると1件の警告（タグ・ヘッドラインを含む）。FAILにはならない（checks・failed・overallに影響しない）",
      len(_hw) == 1 and _hw[0]["tags"] == ["#BTC", "#ETH"] and "見出しにタグは付けない" in _hw[0]["detail"]
      and "FRBが申請の承認を発表しました" in _hw[0]["detail"]
      and _au_h.failed == verify_post.run_all(json.loads(json.dumps(_b_dir)), DAILY_DATA).failed, str(_hw))
_hb2 = json.loads(json.dumps(_hb)); _hb2["sections"]["part1_headline"] = "FRBが申請の承認を発表しました。"
check("見出しのタグのWARN: タグが無ければ警告なし",
      not [w for w in verify_post.run_all(_hb2, DAILY_DATA).warnings if w["id"] == "W_headline_hashtag"])
_hb3 = json.loads(json.dumps(_hb2)); _hb3["sections"]["part2_flow"] = "①【出来事・ニュース】a → 【暗号通貨価格】BTC・ETHは下落しました。 #BTC #ETH"
check("見出しのタグのWARN: 市場のフローの連鎖末尾のタグは対象外（従来どおり許容）",
      not [w for w in verify_post.run_all(_hb3, DAILY_DATA).warnings if w["id"] == "W_headline_hashtag"])
check("format_warning_counts: 登録済みの種類は0件でも毎回表示し、未登録IDは「その他」にまとめる（0件なら出さない）",
      verify_post.format_warning_counts([]) == _wk()
      and verify_post.format_warning_counts([{"id": "W_headline_hashtag"}, {"id": "W_direction_mismatch"}, {"id": "W_direction_mismatch"}])
      == _wk(direction=2, hashtag=1)
      and verify_post.format_warning_counts([{"id": "W_unknown"}]) == _wk() + "・その他1"
      and verify_post.format_warning_counts(None) == _wk())
_res_two = {"final_failing_checks": [], "final_failing_check_details": [], "checked_ids": "C12〜C24・C26〜C28・計17項目",
            "warnings": _au_dir.warnings + _hw}
_blk2 = repair_post.render_warning_block(_res_two)
check("警告ブロック: 種類別の件数が見出しに出て、各警告の先頭に種類名が付く（向きの食い違いと見出しのタグが同じ欄に並ぶ）。input=／output=は含まない",
      _blk2.startswith("⚠⚠ 警告2件（" + _wk(direction=1, hashtag=1) + "）") and "⚠ [向きの食い違い] " in _blk2
      and "⚠ [見出しのタグ] ヘッドラインにハッシュタグ（#BTC #ETH）" in _blk2 and "input=" not in _blk2 and "output=" not in _blk2, _blk2)
check("最終監査の表記: 警告の種類別件数が1行に出る（件数0の種類も表示）",
      "向きの食い違い・その他の警告チェック（警告のみ・FAILにしない）: 警告2件（" + _wk(direction=1, hashtag=1) + "）（ファイル先頭に表示）"
      in repair_post.render_final_audit_note(_res_two), repair_post.render_final_audit_note(_res_two))
# 実データ（本番にコミット済みのbundle）: v1.70（9/8）より前の日はタグ無しで警告なし、タグ付きの日は警告になる（読み取りのみ）
_tag_days, _pre_days = [], []
for _bp in sorted((REPO / "outputs").glob("2026-*/draft/post_bundle.json")):
    _bb = json.loads(_bp.read_text(encoding="utf-8"))
    _day = _bp.parent.parent.name
    _has = bool(verify_post.find_headline_hashtags(_bb["sections"].get("part1_headline")))
    (_tag_days if _has else _pre_days).append(_day)
check("実データ: タグ付きの見出しの日（9/8以降の材料つき日・10/2を含む）が警告対象になり、9/8より前の日は1日も対象にならない",
      len(_tag_days) >= 14 and "2026-10-02" in _tag_days and all(d >= "2026-09-08" for d in _tag_days), str(_tag_days))

print("=== v1.92（オーナー承認）: reusable_for_summaryを「前日以前の投稿本文で扱った材料のうち、新しい動きがないもの」だけにする（R1プロンプト＋R2機械フィルタ） ===")
_PR = Path("prev_posts_outputs")


def _write_post(day, headline, points, level="L0"):
    d = _PR / day / "draft"
    d.mkdir(parents=True, exist_ok=True)
    (d / "post_bundle.json").write_text(json.dumps({"level": level, "sections": {
        "part1_headline": headline, "part1_points": points}}, ensure_ascii=False), encoding="utf-8")


_write_post("2026-09-25", "FRBがFleur Capitalの申請を承認しました。", "・FRBはFleur Capital Corporationによる申請を承認したと発表しました（FRB、9月25日）。")
_write_post("2026-09-26", generate_post.FIXED_HEADLINE, generate_post.FIXED_POINTS)  # 定型文だけの日（材料なし）→飛ばす
# 2026-09-27: ファイル無し
(_PR / "2026-09-28" / "draft").mkdir(parents=True, exist_ok=True)
(_PR / "2026-09-28" / "draft" / "post_bundle.json").write_text("{broken", encoding="utf-8")  # 壊れたファイル→飛ばす
_write_post("2026-09-29", "米ホワイトハウスがStablecoin Clarity法案への支持を表明しました。",
            "・Hana Bank（韓国）がEuroclearの基盤でデジタル債券を発行しました（CoinDesk、9月29日）。\n・Tetherを巡るイラン関連資金の報告書が公表されました（Reuters、9月29日）。")
_write_post("2026-09-30", "G7が備蓄放出に合意しました。", "・原油価格が低下しました（Reuters、9月30日）。")
_write_post("2026-10-01", "SECがトークン化株式の免除を公表しました。", "・SECの発表を受け市場が反応しました（SEC、10月1日）。")
_write_post("2026-09-20", "古い投稿（7日より前）です。", "・古い項目です（CoinDesk、9月20日）。")
_write_post("2026-10-01", "SECがトークン化株式の免除を公表しました。 #BTC #ETH", "・SECの発表を受け市場が反応しました（SEC、10月1日）。")
_pp = generate_post._load_previous_posts("2026-10-02", outputs_root=_PR)
check("_load_previous_posts: 過去の見出しに残るハッシュタグ（v1.91より前の「 #BTC #ETH」）はpayloadから除く（モデルが真似てタグを付けないため）",
      _pp[0]["part1_headline"] == "SECがトークン化株式の免除を公表しました。" and "#" not in json.dumps(_pp, ensure_ascii=False), str(_pp[0]))
check("_load_previous_posts: 対象日より前の投稿を新しい順に最大3件、7日以内から集める（定型文だけ・ファイル無し・壊れたファイルの日は飛ばす）",
      [p["date"] for p in _pp] == ["2026-10-01", "2026-09-30", "2026-09-29"], str([p["date"] for p in _pp]))
check("_load_previous_posts: 各要素はdate・part1_headline・part1_points（「・」始まりの行のリスト）",
      _pp[2]["part1_headline"].startswith("米ホワイトハウス") and len(_pp[2]["part1_points"]) == 2
      and _pp[2]["part1_points"][0].startswith("・Hana Bank"))
check("_load_previous_posts: 7日より前の投稿・対象日以降は含めない／不正な日付・存在しないディレクトリは空（例外にしない）",
      all(p["date"] >= "2026-09-25" for p in generate_post._load_previous_posts("2026-10-02", outputs_root=_PR))
      and generate_post._load_previous_posts("2026-10-02", outputs_root=Path("no_such")) == []
      and generate_post._load_previous_posts("not-a-date", outputs_root=_PR) == []
      and [p["date"] for p in generate_post._load_previous_posts("2026-09-26", outputs_root=_PR)] == ["2026-09-25", "2026-09-20"]
      and [p["date"] for p in generate_post._load_previous_posts("2026-09-28", outputs_root=_PR)] == ["2026-09-25"])

_norm = generate_post._normalize_reusable_for_summary
_pp_norm = [{"date": "2026-10-01", "part1_headline": "CircleがTazapayを買収しました。",
             "part1_points": ["・Hana Bank（韓国）がEuroclearの基盤でデジタル債券を発行しました（CoinDesk、10月1日）。"]},
            {"date": "2026-09-30", "part1_headline": "G7が備蓄放出に合意しました。", "part1_points": ["・原油価格が低下しました（Reuters、9月30日）。"]}]
_ok_item = {"text": "Hana Bank（韓国）のEuroclearを用いたデジタル債券発行は新しい動きがありません（CoinDesk、10月1日）。",
            "carried_from": "2026-10-01", "candidate_ids": []}
_k, _d = _norm([_ok_item], _pp_norm)
check("R2: 前日以前の投稿本文と題材が対応する（特徴語が2つ以上共通）項目は保持される",
      _k == [_ok_item["text"]] and _d == [], str((_k, _d)))
_k, _d = _norm(["Hana Bankのデジタル債券は継続監視（CoinDesk）"], _pp_norm)
check("R2: 文字列だけの旧形式（carried_fromが無い）は除外される（理由に形式不正を記録）",
      _k == [] and len(_d) == 1 and "形式不正" in _d[0]["reason"], str(_d))
_k, _d = _norm([{**_ok_item, "carried_from": "2026-09-15"}], _pp_norm)
check("R2: carried_fromが、渡した前日以前の投稿の日付に無い項目は除外される",
      _k == [] and "carried_from" in _d[0]["reason"] and "2026-10-01" in _d[0]["reason"], str(_d))
_k, _d = _norm([{"text": "イーサリアムのレイヤー2「Blast」が撤退を発表したと報じられています（CoinDesk、10月2日）。",
                 "carried_from": "2026-10-01", "candidate_ids": []}], _pp_norm)
check("R2（10/2のBlast型）: 前日以前の投稿本文に対応する語が無い当日初出の材料は、carried_fromを付けても除外される",
      _k == [] and "対応する語が見つからない" in _d[0]["reason"], str(_d))
_k, _d = _norm([{"text": "ビットコインについてCoinDeskが報じています。", "carried_from": "2026-10-01"}],
               [{"date": "2026-10-01", "part1_headline": "ビットコインが話題でCoinDeskも報じました。", "part1_points": []}])
check("R2: 媒体名（CoinDesk等）・汎用語（ビットコイン等）だけの共通は「同じ題材」の根拠にならず除外される",
      _k == [] and len(_d) == 1, str(_d))
_k, _d = _norm([{"text": "トークン化証券ロードマップは新しい動きがありません。", "carried_from": "2026-10-01"}],
               [{"date": "2026-10-01", "part1_headline": "韓国がトークン化証券ロードマップを発表しました。", "part1_points": []}])
check("R2: 共通の特徴語が1つでも7文字以上（トークン化証券ロードマップ）なら保持される",
      len(_k) == 1 and _d == [], str((_k, _d)))
_ic = {1: {"tier": 1}, 2: {"tier": 3}, 3: {"tier": 4}}
_dec = {1: "採用", 2: "不採用", 3: "不採用"}
_k, _d = _norm([{**_ok_item, "candidate_ids": [3]}], _pp_norm, _ic, _dec)
check("R2: candidate_idsにtier4の候補を含む項目は除外される（tier4は本文・総括のどこにも書かない）",
      _k == [] and "tier4" in _d[0]["reason"], str(_d))
_k, _d = _norm([{**_ok_item, "candidate_ids": [1]}], _pp_norm, _ic, _dec)
check("R2: candidate_idsに当日採用済みの候補を含む項目は除外される（採用した材料は主要なポイントへ載せる）",
      _k == [] and "採用済み" in _d[0]["reason"], str(_d))
_k, _d = _norm([{**_ok_item, "candidate_ids": [2, 99, True, "x"]}], _pp_norm, _ic, _dec)
check("R2: 当日の不採用候補・存在しないID・不正な型のIDは除外理由にならない（前日以前の投稿と対応していれば保持）",
      len(_k) == 1 and _d == [], str((_k, _d)))
_many = [{**_ok_item, "text": f"Hana Bank（韓国）のEuroclearのデジタル債券は継続（{i}）"} for i in range(4)]
_k, _d = _norm(_many, _pp_norm)
check("R2: 保持は最大2件（超過分は除外として記録）", len(_k) == 2 and len(_d) == 2 and "上限2件" in _d[0]["reason"], str((_k, _d)))
check("R2: 想定外の入力（None・dict・数値・None要素）でも例外を出さず、すべて除外または空になる",
      _norm(None, _pp_norm) == ([], []) and _norm({"a": 1}, _pp_norm) == ([], [])
      and _norm([1, None, 2.5], _pp_norm)[0] == [] and len(_norm([1, None, 2.5], _pp_norm)[1]) == 3
      and _norm([_ok_item], None)[0] == [] and _norm([_ok_item], [])[0] == [])

# call_aの結合: previous_postsがpayloadに入り、出力のreusable_for_summaryが機械フィルタを通って文字列のリストになる
_news_r = {"candidates": [
    {"tier": 1, "source": "FRB", "title": "Fed approves Fleur", "summary": "x", "url": "https://e/1", "published_at": "2026-10-02T01:00:00+09:00"},
    {"tier": 3, "source": "CoinDesk", "title": "Blast to wind down", "summary": "y", "url": "https://e/2", "published_at": "2026-10-02T02:00:00+09:00"},
], "source_status": {}}


def _client_reusable(items):
    def fn(kw, n):
        ledger = [{"candidate_id": c["candidate_id"], "use": c.get("tier") == 1, "verified_by": "", "reason": "x"}
                  for c in _parse_leading_json(kw["messages"][0]["content"]).get("news_candidates_today", [])]
        return json_response({**CALL_A_DATA, "reusable_for_summary": items, "audit_ledger": ledger})
    return FakeClient(fn)


_good = {"text": "Hana Bank（韓国）のEuroclearを用いたデジタル債券は新しい動きがありません（CoinDesk、10月1日）。",
         "carried_from": "2026-10-01", "candidate_ids": []}
_bad_new = {"text": "イーサリアムのレイヤー2「Blast」が撤退を発表したと報じられています（CoinDesk、10月2日）。",
            "carried_from": "2026-10-01", "candidate_ids": [2]}
_c_r = _client_reusable([_good, _bad_new, "文字列だけの旧形式"])
_out_r = generate_post.call_a(_c_r, DAILY_DATA, _news_r, None, previous_posts=_pp_norm)
_sent = _parse_leading_json(_c_r.messages.calls[0]["messages"][0]["content"])
check("call_a: previous_postsがcall_Aのpayloadに入る", _sent["previous_posts"] == _pp_norm)
check("call_a: 出力のreusable_for_summaryは機械フィルタを通った文字列のリストになる（当日初出のBlast・旧形式の文字列は除外）",
      _out_r.ok and _out_r.data["reusable_for_summary"] == [_good["text"]], str(_out_r.data and _out_r.data["reusable_for_summary"]))
check("call_a: 除外した項目と理由がoutcome.reusable_droppedとto_dict()に残る",
      len(_out_r.reusable_dropped) == 2 and _out_r.to_dict()["reusable_dropped"] == _out_r.reusable_dropped
      and any("Blast" in d["text"] for d in _out_r.reusable_dropped), str(_out_r.reusable_dropped))
_c_r2 = _client_reusable([_good])
check("call_a: previous_postsを渡さない呼び出し（従来の呼び出し形式）でも動き、reusable_for_summaryは空になる（すべて除外）",
      generate_post.call_a(_c_r2, DAILY_DATA, _news_r, None).data["reusable_for_summary"] == [])
_payload_default, _, _ = generate_post._build_call_a_user_content(DAILY_DATA, _news_r, None)
check("_build_call_a_user_content: previous_postsを省略するとpayloadのprevious_postsは空配列",
      json.loads(_payload_default)["previous_posts"] == [])
# 採用済み材料（Blast相当がuse:trueで採用）を参照するreusableは、採用ラベルを見て除外される
_news_adopt = {"candidates": [{"tier": 1, "source": "FRB", "title": "Hana Bank issues bond", "summary": "x", "url": "https://e/1",
                               "published_at": "2026-10-02T01:00:00+09:00"}], "source_status": {}}
_out_adopt = generate_post.call_a(_client_reusable([{**_good, "candidate_ids": [1]}]), DAILY_DATA, _news_adopt, None, previous_posts=_pp_norm)
check("call_a: reusable項目がcandidate_idsで当日の採用済み候補を指す場合は除外される（decisionはコード導出の採用）",
      _out_adopt.ok and _out_adopt.data["reusable_for_summary"] == [] and "採用済み" in _out_adopt.reusable_dropped[0]["reason"],
      str(_out_adopt.reusable_dropped))

# run(): 前日以前の投稿（コミット済みdraft）をpreviousとして渡し、結果にprevious_posts_datesを残す
os.makedirs("outputs/2026-08-31", exist_ok=True)
Path("outputs/2026-08-31/daily_data.json").write_text(json.dumps(DAILY_DATA, ensure_ascii=False), encoding="utf-8")
for _day, _h in (("2026-08-30", "SECが規則案を公表しました。"), ("2026-08-29", "FRBが利上げを決定しました。")):
    os.makedirs(f"outputs/{_day}/draft", exist_ok=True)
    Path(f"outputs/{_day}/draft/post_bundle.json").write_text(json.dumps({"level": "L0", "sections": {
        "part1_headline": _h, "part1_points": "・項目です（Reuters、8月30日）。"}}, ensure_ascii=False), encoding="utf-8")
_res_prev = generate_post.run("2026-08-31", client=_make_run_client_tolerant(True, True))
check("run(): 前日以前の投稿本文（outputs/<日付>/draft/post_bundle.json）をcall_Aへ渡し、結果にprevious_posts_datesを残す",
      _res_prev["previous_posts_dates"] == ["2026-08-30", "2026-08-29"], str(_res_prev.get("previous_posts_dates")))
check("run(): call_aの結果にreusable_droppedが含まれる（STATUS用）", "reusable_dropped" in _res_prev["call_a"])

# プロンプト（R1）
_A = generate_post.SYSTEM_A
check("R1: WRITES_Aのreusable_for_summaryは「前日以前の投稿本文（previous_posts）で扱った材料のうち、新しい動きがないものだけ」と定義し、"
      "当日の候補・tier4・当日初出の材料は書かないと明記している（v1.92・オーナー指示）",
      "前日以前の投稿本文（入力の\n  previous_posts）で既に扱った材料のうち、当日になっても新しい動きがない" in _A
      and "次は書かない: 当日の候補（採用・不採用を問わず）、tier4、当日初出の材料。" in _A)
check("R1: 出力形式は {text, carried_from, candidate_ids} 形式で、形式外・前日以前の本文と対応しない項目は機械的に除外される旨を明記している",
      '{ "text": "...", "carried_from": "YYYY-MM-DD", "candidate_ids": [] }' in _A
      and "システムが機械的に除外する" in _A)
check("R1: 採用（use:true）した材料はすべて主要なポイントへ載せる／載せない材料はuse:false／ヘッドラインの繰り返しにしない（オーナー指示）",
      "採用（use:true）した材料はすべて part1_headline・part1_points に載せる" in _A
      and "載せない材料は use:false にする" in _A and "ヘッドラインの繰り返しにしない" in _A)
check("R1: tier4はreusable_for_summaryを含め本文・総括のどこにも書かない（情報源規律の抜け道を残さない）。旧指示（継続監視の対象としてreusableに記す）は残っていない",
      "reusable_for_summaryにも書かない" in _A
      and "継続監視の対象として reusable_for_summary に記す" not in _A
      and "audit_ledgerではなくreusable_for_summaryに記す" not in _A
      and "tier 4等の継続監視材料があれば記す" not in _A)
check("R1: 前日以前の投稿本文（previous_posts）で既に扱った材料に新しい動きがなければ、本文には書かずreusable_for_summaryに記す（news_candidates_yesterdayは本番で常に空だったため比較対象を置き換え）",
      "入力の previous_posts（前日以前の投稿本文" in _A and "news_candidates_yesterday に同一の" not in _A)
_B = generate_post.CALL_B_INSTRUCTIONS
check("CALL_B指示: reusable_for_summaryは前日以前の投稿で扱った継続材料（システムが検証済み・空配列が通常）。空配列の日は前編に無い材料を総括に書かない",
      "前日以前の投稿で扱った継続材料。システムが検証済みで、" in _B and "空配列の日は、前編に" in _B
      and "無い材料への言及を総括に書かない" in _B and "（継続監視材料。part2_summary" not in _B)

# STATUS表示
_gen_rs = json.loads(json.dumps(_g_gen))
_gen_rs["call_a"]["reusable_dropped"] = [{"text": "イーサリアムのレイヤー2「Blast」が撤退を発表したと報じられています", "reason": "対応する語が見つからない"}]
_gen_rs["call_a"]["data"]["reusable_for_summary"] = ["Hana Bankのデジタル債券は継続監視（CoinDesk、10月1日）"]
_gen_rs["previous_posts_dates"] = ["2026-10-01", "2026-09-30"]
_st_rs = compose_post.render_generation_status(_gen_rs, DAILY_DATA)
check("STATUS: reusable_for_summaryの保持・除外が記録される（件数・渡した前日以前の投稿の日付・除外理由）",
      "reusable_for_summary（前日以前の投稿で扱った継続材料のみ。v1.92）: 保持1件／除外1件（call_Aへ渡した前日以前の投稿: 2026-10-01・2026-09-30）" in _st_rs
      and "  - 保持: 「Hana Bankのデジタル債券は継続監視" in _st_rs and "  - 除外: 「イーサリアムのレイヤー2「Blast」" in _st_rs
      and "— 対応する語が見つからない" in _st_rs, _st_rs[:900])
_gen_old = json.loads(json.dumps(_g_gen))
check("STATUS: 旧形式のgen（reusable_droppedも前日以前の投稿の日付も無い）でも例外にならず、「記録なし」と表示する",
      "保持" in compose_post.render_generation_status(_gen_old, DAILY_DATA)
      and "前日以前の投稿: 記録なし" in compose_post.render_generation_status(_gen_old, DAILY_DATA))
_gen_fail = json.loads(json.dumps(_g_gen)); _gen_fail["call_a"]["ok"] = False
check("STATUS: call_Aが失敗した日はreusable_for_summaryの行を出さない",
      "reusable_for_summary（前日以前" not in compose_post.render_generation_status(_gen_fail, DAILY_DATA))

# 実データ（本番にコミット済みの過去の投稿・読み取りのみ）: 過去のreusable_for_summaryの項目（当日の材料が98%）に
# 前日以前の投稿との対応確認を当てはめると、ほぼすべて除外される
_tot_items = _kept_items = 0
for _bp in sorted((REPO / "outputs").glob("2026-*/draft/post_bundle.json")):
    _bb = json.loads(_bp.read_text(encoding="utf-8"))
    _items = _bb.get("reusable_for_summary") or []
    if not _items:
        continue
    _pps = generate_post._load_previous_posts(_bp.parent.parent.name, outputs_root=REPO / "outputs")
    for _it in _items:
        _tot_items += 1
        if any(_norm([{"text": _it, "carried_from": p["date"], "candidate_ids": []}], _pps)[0] for p in _pps):
            _kept_items += 1
check("実データ: 過去のreusable_for_summary（当日の材料が大半）に機械フィルタを当てはめると、保持されるのは2割未満（試算で50件中4件）",
      _tot_items >= 48 and _kept_items / _tot_items < 0.2, f"{_kept_items}/{_tot_items}")

print("=== v1.93（オーナー承認）: 指標日の見出しの規則（プロンプト）・候補への目印（scheduled_event_match）・指標日の見出しのWARN ===")
_SE_JOBS = [{"title": "Non-Farm Employment Change", "country": "USD", "impact": "High"},
            {"title": "Unemployment Rate", "country": "USD", "impact": "High"},
            {"title": "Average Hourly Earnings m/m", "country": "USD", "impact": "High"},
            {"title": "BOJ Press Conference", "country": "JPY", "impact": "High"},
            {"title": "CPI m/m", "country": "USD", "impact": "Medium"}]
_fam_jobs = indicator_events.high_us_event_families(_SE_JOBS)
check("indicator_events: 重要度High・米国（USD）の指標だけを指標ファミリーにまとめる（他国・Medium・形式不正は対象外）",
      [f["family"]["key"] for f in _fam_jobs] == ["jobs"] and len(_fam_jobs[0]["events"]) == 3
      and indicator_events.high_us_event_families(None) == [] and indicator_events.high_us_event_families("x") == []
      and indicator_events.high_us_event_families([{"title": 1}, "a", None]) == []
      and [f["family"]["key"] for f in indicator_events.high_us_event_families(
          [{"title": "Core PCE Price Index m/m", "country": "USD", "impact": "High"},
           {"title": "Final GDP q/q", "country": "USD", "impact": "High"},
           {"title": "FOMC Statement", "country": "USD", "impact": "High"},
           {"title": "Federal Funds Rate", "country": "USD", "impact": "High"},
           {"title": "ISM Manufacturing PMI", "country": "USD", "impact": "High"}])] == ["pce", "gdp", "fomc", "ism"])
check("indicator_events: 候補のtitle（英語）が指標に対応するときだけ目印の文字列を返す（雇用統計・PCE等の実際の過去日の候補）",
      indicator_events.match_label("US job growth undershoots expectations in September, but labor market remains stable", _fam_jobs)
      == "雇用統計（Non-Farm Employment Change／Unemployment Rate／Average Hourly Earnings m/m）"
      and indicator_events.match_label("Bitcoin briefly hits $87K as weak US jobs data sends bond yields lower", _fam_jobs) != ""
      and indicator_events.match_label("FRB approves Fleur Capital application", _fam_jobs) == ""
      and indicator_events.match_label(None, _fam_jobs) == "" and indicator_events.match_label("jobs", []) == "")
check("indicator_events: 見出し（日本語）が指標に触れているかを判定する",
      indicator_events.headline_mentions("米国の9月の雇用統計が予想を下回りました。", _fam_jobs[0]["family"])
      and not indicator_events.headline_mentions("FRBがFleur Capitalの申請承認を発表しました。", _fam_jobs[0]["family"])
      and not indicator_events.headline_mentions(None, _fam_jobs[0]["family"]))
_cands = [{"candidate_id": 1, "tier": 2, "source": "Reuters", "title": "US job growth undershoots expectations"},
          {"candidate_id": 2, "tier": 1, "source": "FRB", "title": "Federal Reserve Board approves application by Fleur"},
          {"candidate_id": 3, "tier": 3, "source": "CoinDesk", "title": "Weak US jobs data sends Bitcoin lower"},
          {"candidate_id": 4, "tier": 4, "source": "Google News", "title": "US jobs report preview"}]
_fl = generate_post._flag_scheduled_event_matches(_cands, _SE_JOBS)
check("scheduled_event_match: 指標日は、対応しうるtier1〜3の候補にだけ目印が付く（無関係な候補・tier4には付かない）。元の候補は変更しない",
      _fl[0].get("scheduled_event_match", "").startswith("雇用統計（") and "scheduled_event_match" not in _fl[1]
      and _fl[2].get("scheduled_event_match", "").startswith("雇用統計（") and "scheduled_event_match" not in _fl[3]
      and all("scheduled_event_match" not in c for c in _cands), str(_fl))
check("scheduled_event_match: 指標日でない日（Highの米指標が無い・scheduled_eventsが無い）は何も付けない",
      generate_post._flag_scheduled_event_matches(_cands, []) == _cands
      and generate_post._flag_scheduled_event_matches(_cands, None) == _cands
      and generate_post._flag_scheduled_event_matches(_cands, [{"title": "CPI m/m", "country": "USD", "impact": "Low"}]) == _cands)
_dd_ind = json.loads(json.dumps(DAILY_DATA)); _dd_ind["scheduled_events"] = _SE_JOBS
_news_ind = {"candidates": [{"tier": 2, "source": "Reuters", "title": "US job growth undershoots expectations", "summary": "x",
                             "url": "https://e/1", "published_at": "2026-10-02T01:00:00+09:00"},
                            {"tier": 1, "source": "FRB", "title": "Fed approves Fleur", "summary": "y", "url": "https://e/2",
                             "published_at": "2026-10-02T02:00:00+09:00"}], "source_status": {}}
_uc_ind, _, _id_ind = generate_post._build_call_a_user_content(_dd_ind, _news_ind, None)
_pl_ind = json.loads(_uc_ind)["news_candidates_today"]
check("call_Aのpayload: 指標日は対応候補にscheduled_event_matchが付く。台帳復元に使う候補（id_to_candidate）は目印で変わらない",
      sum(1 for c in _pl_ind if c.get("scheduled_event_match")) == 1
      and all("scheduled_event_match" not in c for c in _id_ind.values()), str(_pl_ind))

# 指標日の見出しのWARN
_led_jobs = [{"source": "Reuters", "title": "US job growth undershoots expectations in September", "decision": "採用", "reason": "x", "verified_by": "", "url": "", "published_at": ""},
             {"source": "FRB", "title": "Federal Reserve Board approves application by Fleur", "decision": "採用", "reason": "x", "verified_by": "", "url": "", "published_at": ""}]


def _ind_warn(headline, points, ledger=_led_jobs, se=_SE_JOBS):
    au = verify_post.Audit()
    verify_post.check_indicator_headline_warn(au, {"part1_headline": headline, "part1_points": points}, ledger, se)
    return au


_au_i = _ind_warn("FRBがFleur Capitalの申請の承認を発表しました。", "・FRBは承認を発表しました。\n・米国の9月の雇用統計は予想を下回りました。")
check("指標日の見出しのWARN: 指標に対応する採用済みの材料があるのに見出しがその指標に触れていない日は警告（10/2型）。FAILにはならない",
      len(_au_i.warnings) == 1 and _au_i.warnings[0]["id"] == "W_indicator_headline" and _au_i.warnings[0]["family"] == "jobs"
      and "雇用統計に触れていません" in _au_i.warnings[0]["detail"] and "指標日（雇用統計: " in _au_i.warnings[0]["detail"]
      and "US job growth undershoots" in _au_i.warnings[0]["detail"] and _au_i.failed == 0, str(_au_i.warnings))
check("指標日の見出しのWARN: 警告に「主要なポイントの1番目が指標に触れているか」を添える（例外（2）に従った日かをオーナーが目視で判断できる）",
      "主要なポイントの1番目は触れていません" in _au_i.warnings[0]["detail"] and _au_i.warnings[0]["points_first_mentions"] is False
      and "目視で確認してください" in _au_i.warnings[0]["detail"])
_au_exc = _ind_warn("SECが暗号資産の規則案を公表しました。", "・米国の9月の雇用統計は予想を下回りました。\n・FRBは承認を発表しました。")
check("指標日の見出しのWARN: 例外（2）の形（見出しは制度材料・指標は主要なポイントの1番目）でも警告は出る（目視用）が、「1番目は触れています」と示す",
      len(_au_exc.warnings) == 1 and "主要なポイントの1番目は触れています" in _au_exc.warnings[0]["detail"]
      and _au_exc.warnings[0]["points_first_mentions"] is True)
check("指標日の見出しのWARN: 見出しが指標に触れていれば警告なし",
      _ind_warn("米国の9月の雇用統計が市場予想を下回りました。", "・x").warnings == [])
check("指標日の見出しのWARN: 採用されていない（不採用）対応候補・対応候補が無い日・指標日でない日・定型文の見出しは警告なし",
      _ind_warn("FRBが承認を発表しました。", "・x", ledger=[{**_led_jobs[0], "decision": "不採用"}, _led_jobs[1]]).warnings == []
      and _ind_warn("FRBが承認を発表しました。", "・x", ledger=[_led_jobs[1]]).warnings == []
      and _ind_warn("FRBが承認を発表しました。", "・x", se=[]).warnings == []
      and _ind_warn("FRBが承認を発表しました。", "・x", se=None).warnings == []
      and _ind_warn(generate_post.FIXED_HEADLINE, "・x").warnings == []
      and _ind_warn("", "・x").warnings == [] and _ind_warn("FRBが承認を発表しました。", "・x", ledger=None).warnings == [])
check("指標日の見出しのWARN: 独立2ソース採用（decision=採用（独立2ソース））も対応材料として数える／指標が複数なら指標ごとに1件",
      len(_ind_warn("FRBが発表しました。", "・x", ledger=[{**_led_jobs[0], "decision": "採用（独立2ソース）"}]).warnings) == 1
      and len(_ind_warn("FRBが発表しました。", "・x",
                        ledger=[{**_led_jobs[0], "title": "US PCE inflation rises; payrolls too", "decision": "採用"}],
                        se=_SE_JOBS + [{"title": "Core PCE Price Index m/m", "country": "USD", "impact": "High"}]).warnings) == 2)
check("指標日の見出しのWARN: 警告の種類は登録簿に登録済みで、種類別件数・警告ブロックに「指標日の見出し」として出る",
      "W_indicator_headline" in dict(verify_post.WARNING_KINDS)
      and verify_post.warning_kind_label("W_indicator_headline") == "指標日の見出し"
      and "指標日の見出し1" in verify_post.format_warning_counts(_au_i.warnings)
      and "⚠ [指標日の見出し] 指標日（雇用統計" in repair_post.render_warning_block(
          {"warnings": _au_i.warnings, "final_failing_checks": [], "final_failing_check_details": []}))
check("run_all: 指標日の見出しの警告は、他の監査項目の結果（failed）を変えない（FAILにしない）",
      verify_post.run_all(json.loads(json.dumps(_b_dir)), _dd_ind).failed == verify_post.run_all(json.loads(json.dumps(_b_dir)), DAILY_DATA).failed)
# 実データ: 本番にコミット済みの過去の投稿で、警告が出る日（読み取りのみ）
_ind_days = {}
for _bp in sorted((REPO / "outputs").glob("2026-*/draft/post_bundle.json")):
    _day = _bp.parent.parent.name
    _bb = json.loads(_bp.read_text(encoding="utf-8"))
    _ddp = _bp.parent.parent / "daily_data.json"
    if not _ddp.exists():
        continue
    _dd_real = json.loads(_ddp.read_text(encoding="utf-8"))
    _au_real = verify_post.Audit()
    verify_post.check_indicator_headline_warn(_au_real, _bb["sections"], _bb.get("audit_ledger"), _dd_real.get("scheduled_events"))
    _ind_days[_day] = [w["family"] for w in _au_real.warnings]
check("実データ: 指標日（9/1 ISM・9/4 雇用統計・9/10 PPI・9/30 PCE/GDP・10/2 雇用統計）のうち、警告が出るのは10/2（雇用統計）だけ",
      _ind_days.get("2026-10-02") == ["jobs"]
      and all(not _ind_days.get(d) for d in ("2026-09-01", "2026-09-04", "2026-09-10", "2026-09-30")), str(_ind_days))

# プロンプト（規則(1)(2)(3)）
_A93 = generate_post.SYSTEM_A
check("v1.93のプロンプト: ①の中での主題の選び方の規則(1)（指標日は対応材料が採用済みなら原則としてそれを見出しの主にする）が入っている（A/Bラベル・tierの違いでは決めない）",
      "### ①の中での主題の選び方（v1.93・オーナー指示）" in _A93
      and "A/B/Cの分類やtierの違い（tier1かtier2か）では決めない" in _A93
      and "重要度High・米国（USD）の" in _A93 and "原則としてその材料をpart1_headlineの主とする" in _A93)
check("v1.93のプロンプト: 規則(2)例外（暗号通貨に直接関わる大型の制度材料が公式発表で確認できる日は、それを見出しにし指標は主要なポイントの1番目）が入っている",
      "SEC・CFTC等の規則案・最終規則・\n    登録承認、ETFの承認など" in _A93 and "公式発表（tier1）で確認できる日" in _A93
      and "(1)の指標の材料はpart1_pointsの1番目に置く" in _A93)
check("v1.93のプロンプト: 規則(3)（暗号通貨と関係の薄い個別の申請承認・意見募集期間の延長など手続き的な発表は見出しにしない）が入っている",
      "個別の申請の承認、意見募集期間の延長" in _A93 and "part1_headlineの主題にしない" in _A93)
check("v1.93のプロンプト: scheduled_event_matchは機械的な目印であり事実・採否の根拠ではない旨をSCHEDULED_EVENTS_GUIDANCEが明記し、SYSTEM_Aに含まれる",
      "`scheduled_event_match`" in generate_post.SCHEDULED_EVENTS_GUIDANCE
      and "事実の根拠でも採否の根拠でもありません" in generate_post.SCHEDULED_EVENTS_GUIDANCE
      and generate_post.SCHEDULED_EVENTS_GUIDANCE in _A93)

print("=== v1.94（オーナー承認）: 市場のフローの書式のWARN（統合運用基準§3.3） ===")
_OK1 = ("【出来事・ニュース】米国の9月の雇用統計が市場予想を下回ったとReutersが報じました → 【地政学・マクロの変化】利上げ観測の後退が意識された可能性があります → "
        "【中間市場指標・市場心理】債券利回りの低下が確認されたとされます → 【暗号通貨価格】BTC・ETHは同時期に下落しましたが、因果は未確認です。 #BTC #ETH")
_OK2 = "【出来事・ニュース】G7が備蓄放出に合意しました（Reuters、10月2日。公式発表は未確認） → 【暗号通貨価格】BTC・ETHは小幅な動きにとどまり、因果は未確認です。"
_fv = verify_post.find_flow_format_violations
check("フロー書式: §3.3どおりの1本（4段階・矢印3本・1文・末尾に限定表現・タグは末尾）は違反なし",
      _fv("・" + _OK1) == [] and _fv(_OK1) == [])
check("フロー書式: 複数連鎖は①②から連番で、①②で始まる行（「・」なし）が違反なし。全角括弧内の句点は文数に数えない",
      _fv("①" + _OK1 + "\n②" + _OK2) == [])
check("フロー書式: 材料が無い日の定型文1件のみ・空・None・空行だけは対象外",
      _fv(generate_post.FIXED_FLOW) == [] and _fv("・" + generate_post.FIXED_FLOW) == [] and _fv("") == []
      and _fv(None) == [] and _fv("\n \n") == [])
_prose = ("・FRBの手続きに関する発表が相次ぎました。暗号通貨への直接の言及は確認できません。BTC・ETHは24時間比でいずれも下落となりました。 #BTC #ETH")
_vp = _fv(_prose)
check("フロー書式: 10/2型（ラベルも矢印も無い散文・3文）は、ラベル欠落・矢印なし・1文でない・先頭が違う等で違反になる",
      len(_vp) == 1 and {"no_event_label", "no_price_label", "not_start_event", "no_arrows", "sentences"} <= set(_vp[0]["reasons"])
      and _vp[0]["chain_no"] == 1, str(_vp))
def _reasons(text): return set(c for v in _fv(text) for c in v["reasons"])
check("フロー書式: 【暗号通貨価格】が無い／【出来事・ニュース】が無い／先頭が違う",
      "no_price_label" in _reasons("【出来事・ニュース】aが起きました → 【地政学・マクロの変化】bの可能性があります。")
      and {"no_event_label", "not_start_event"} <= _reasons("【地政学・マクロの変化】bが意識された可能性 → 【暗号通貨価格】cで因果は未確認です。"))
check("フロー書式: 段階の順序違反・同じ段階の重複・矢印の直後がラベルでない・矢印の不足",
      "label_order" in _reasons("【出来事・ニュース】a → 【暗号通貨価格】c → 【地政学・マクロの変化】bの可能性があります。")
      and "label_dup" in _reasons("【出来事・ニュース】a → 【出来事・ニュース】b → 【暗号通貨価格】cで因果は未確認です。")
      and "arrow_label_mismatch" in _reasons("【出来事・ニュース】a → 好感された可能性 → 【暗号通貨価格】cで因果は未確認です。")
      and "arrows" in _reasons("【出来事・ニュース】a 【地政学・マクロの変化】b → 【暗号通貨価格】cで因果は未確認です。"))
check("フロー書式: 文数（句点が2つ・句点が無い）はNG。全角括弧内の句点は数えない",
      "sentences" in _reasons("【出来事・ニュース】a → 【暗号通貨価格】cでした。因果は未確認です。")
      and "sentences" in _reasons("【出来事・ニュース】a → 【暗号通貨価格】cで因果は未確認です")
      and "sentences" not in _reasons(_OK2))
check("フロー書式: ハッシュタグは連鎖の末尾（句点の後）だけ。途中・句点の前はNG",
      "tag_in_body" in _reasons("【出来事・ニュース】a #BTC → 【暗号通貨価格】cで因果は未確認です。")
      and "tag_not_after_period" in _reasons("【出来事・ニュース】a → 【暗号通貨価格】cで因果は未確認です #BTC")
      and not (_reasons("・" + _OK1) & {"tag_in_body", "tag_not_after_period"}))
_ok_a = "【出来事・ニュース】a → 【暗号通貨価格】cで因果は未確認です。"
check("フロー書式: ①②③の付け方（複数なら①から連番・1本なら付けない）と最大3本",
      "numbering" in _reasons("・" + _ok_a + "\n・" + _ok_a) and "numbering" in _reasons("①" + _ok_a)
      and "numbering" in _reasons("②" + _ok_a + "\n①" + _ok_a)
      and _reasons("①" + _ok_a + "\n②" + _ok_a + "\n③" + _ok_a) == set()
      and "too_many_chains" in _reasons("\n".join(("①②③④"[i] if i < 3 else "・") + _ok_a for i in range(4))))
check("フロー書式: 末尾（句点の直前45字以内）に限定表現が無い連鎖は違反（語幹で判定。「とみられます」「意識された可能性」等は許容）",
      "no_limit_at_end" in _reasons("【出来事・ニュース】a → 【暗号通貨価格】BTCが上昇しました。")
      and "no_limit_at_end" not in _reasons("【出来事・ニュース】a → 【暗号通貨価格】BTCが上昇したとみられます。")
      and "no_limit_at_end" not in _reasons("【出来事・ニュース】a → 【暗号通貨価格】BTCが上昇し、断定はできません。"))
_au_f = verify_post.Audit()
verify_post.check_flow_format_warn(_au_f, {"part2_flow": "①" + _OK1 + "\n②" + "【出来事・ニュース】a → 【暗号通貨価格】cでした。因果は未確認です。"})
check("フロー書式のWARN: 違反のある連鎖ごとに1件（何本目か・理由・連鎖を含む）。FAILにしない",
      len(_au_f.warnings) == 1 and _au_f.warnings[0]["id"] == "W_flow_format" and _au_f.warnings[0]["chain_no"] == 2
      and "市場のフローの2本目が書式（統合運用基準§3.3）から外れています" in _au_f.warnings[0]["detail"]
      and "1文でない" in _au_f.warnings[0]["detail"] and _au_f.failed == 0, str(_au_f.warnings))
check("フロー書式のWARN: 種類は登録簿に登録済みで、STATUSの種類別件数・警告ブロックに「フロー書式」として出る",
      verify_post.warning_kind_label("W_flow_format") == "フロー書式"
      and _wk(flow=1).endswith("フロー書式1") and "フロー書式1" in verify_post.format_warning_counts(_au_f.warnings)
      and "⚠ [フロー書式] 市場のフローの2本目" in repair_post.render_warning_block(
          {"warnings": _au_f.warnings, "final_failing_checks": [], "final_failing_check_details": []}))
_hf = json.loads(json.dumps(_b_dir)); _hf["sections"]["part2_flow"] = _prose
check("run_all: 書式の警告は他の監査項目の結果（failed）を変えない（FAILにしない）。散文のフローでも警告になる",
      any(w["id"] == "W_flow_format" for w in verify_post.run_all(_hf, DAILY_DATA).warnings)
      and verify_post.run_all(_hf, DAILY_DATA).failed == verify_post.run_all(json.loads(json.dumps(_b_dir)), DAILY_DATA).failed)
# 実データ（本番にコミット済みの投稿・読み取りのみ）
_ff = {}
for _bp in sorted((REPO / "outputs").glob("2026-*/draft/post_bundle.json")):
    _bb = json.loads(_bp.read_text(encoding="utf-8"))
    _ff[_bp.parent.parent.name] = _fv(_bb["sections"].get("part2_flow"))
check("実データ: 書式どおりだった本番9/30は警告なし・L1の定型文の10/1は対象外・書式外だった10/2は2連鎖とも警告",
      _ff["2026-09-30"] == [] and _ff["2026-10-01"] == [] and [v["chain_no"] for v in _ff["2026-10-02"]] == [1, 2]
      and all("no_event_label" in v["reasons"] and "sentences" in v["reasons"] for v in _ff["2026-10-02"]), str(_ff["2026-10-02"]))

print()
print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
if FAIL:
    print("FAILED CASES:")
    for f in FAIL:
        print(" -", f)
    sys.exit(1)
print("ALL OK")
