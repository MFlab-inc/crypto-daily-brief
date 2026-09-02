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
    "part2_flow": ["規制当局の発言 → 好感された可能性 → 主要銘柄の上昇が同時期に確認された（因果は未確認）。"],
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
        content = json.loads(kw["messages"][0]["content"])
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
    content = json.loads(kw["messages"][0]["content"])
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
check("callA: pair_overlap_threshold=0.6（overlap0.5のペア不成立）を明示指定するとMAX_ATTEMPTS回"
      "リトライ後に失敗する（config/pair_overlap.jsonで調整可能なことをend-to-endで確認）",
      not out_strict.ok and out_strict.attempts == generate_post.MAX_ATTEMPTS,
      f"ok={out_strict.ok} attempts={out_strict.attempts}")
check("callA: 閾値超過による失敗のattempt_errorsに「独立2ソースの相方が成立しない」が記録される"
      "（GENERATION_STATUS.mdへの記録経路の確認・オーナー指示の確認事項）",
      all("独立2ソースの相方が成立しない" in e for e in out_strict.attempt_errors),
      str(out_strict.attempt_errors))

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
      and "①〜④を参照" in generate_post.NEWS_SELECTION)
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

print("=== generate_post.py: part1_headline・part1_pointsの3軸決定（v1.44・オーナー指示） ===")
check("NO_CANDIDATES_FALLBACKに(i)tier1・tier2・(ii)独立2ソース・(iii)notable_moveの3軸が明記されている"
      "（v1.53フォローアップ・LLM自身のuse:true/pairs_with_candidate_id判断ベースへ改定・"
      "v1.59で(i)へtier2を追加）",
      "(i)   tier1またはtier2の候補でuse:trueと判断したものがあるか" in generate_post.NO_CANDIDATES_FALLBACK
      and "(ii)  tier3の候補で、独立2ソース規定に該当すると判断し" in generate_post.NO_CANDIDATES_FALLBACK
      and "(iii) 入力の intraday_range に notable_move: true の銘柄があるか"
      in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKに①〜④の優先順位すべてが記述されている",
      all(s in generate_post.NO_CANDIDATES_FALLBACK for s in (
          "① (i)あり", "② (i)なし・(ii)あり", "③ (i)なし・(ii)なし・(iii)あり",
          "④ (i)なし・(ii)なし・(iii)なし")))
check("NO_CANDIDATES_FALLBACKに定型文を使うのは3軸すべて「なし」の場合のみという明示がある",
      "定型文を使うのは、(i)(ii)(iii)のすべてが「なし」の場合に限る" in generate_post.NO_CANDIDATES_FALLBACK
      and "③と④を取り違えないこと" in generate_post.NO_CANDIDATES_FALLBACK
      and "定型文を使うのは④の場合のみである" in generate_post.NO_CANDIDATES_FALLBACK)
check("NO_CANDIDATES_FALLBACKの①〜④が、audit_ledgerのA/B/C（重要性判定）とは別分類である旨を明記（混同防止）",
      "とは別の分類である。混同しないこと" in generate_post.NO_CANDIDATES_FALLBACK)
check("②は独立2ソース材料単独でpart1_headlineの根拠になり、一次情報未確認の旨を明記する（v1.44新設）",
      "②（(i)なし・(ii)あり）の詳細" in generate_post.NO_CANDIDATES_FALLBACK
      and "独立2ソース材料の内容に基づき、part1_headlineに実文言を書く" in generate_post.NO_CANDIDATES_FALLBACK
      and "一次情報での確認ができていない旨を明記する" in generate_post.NO_CANDIDATES_FALLBACK)
check("③は定型文を使わず値動きを記述し、part1_pointsにニュース未確認を1項目明記する",
      "③（(i)なし・(ii)なし・(iii)あり）の詳細" in generate_post.NO_CANDIDATES_FALLBACK
      and "値動きの形状のみを" in generate_post.NO_CANDIDATES_FALLBACK
      and "「ニュース材料は確認できなかった」" in generate_post.NO_CANDIDATES_FALLBACK)
check("headline_for_imageの指示が④の場合のみに明示的に限定されている（③との混同防止）",
      "headline_for_image: ④の場合（tier1・tier2材料・独立2ソース材料・値動きの"
      in generate_post.NO_CANDIDATES_FALLBACK)

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
check("CALL_B_INSTRUCTIONSに総括で言及してよい範囲がpart1_points掲載済み・"
      "reusable_for_summaryの継続材料に限る旨が明記されている",
      "part1_points に掲載済みのもの" in generate_post.CALL_B_INSTRUCTIONS
      and "reusable_for_summary に渡された継続材料に限る" in generate_post.CALL_B_INSTRUCTIONS)
check("CALL_B_INSTRUCTIONSに本文で扱っていない新規の固有名詞を総括で持ち出さない旨が明記されている",
      "本文（part1_points）で扱っていない新規の固有名詞・" in generate_post.CALL_B_INSTRUCTIONS
      and "材料を総括で初めて持ち出さない" in generate_post.CALL_B_INSTRUCTIONS)
check("SYSTEM_BがCALL_B_INSTRUCTIONSの更新内容を含む",
      "です・ます調" in generate_post.SYSTEM_B)

print("=== generate_post.py: part2_flowの材料をpart1_points採用済みに限定（v1.56・オーナー指示） ===")

check("CALL_B_INSTRUCTIONSにpart2_flowの材料をpart1_points掲載済みに限る旨が明記されている",
      "ここで扱う材料は、呼び出しAのpart1_pointsに既に掲載されている材料に" in generate_post.CALL_B_INSTRUCTIONS)
check("CALL_B_INSTRUCTIONSにreusable_for_summaryをpart2_flowで使わない旨が明記されている"
      "（reusable_for_summaryはpart2_summaryの1行言及にのみ使う）",
      "や、part1_pointsに書かれていない新規の材料をpart2_flowで" in generate_post.CALL_B_INSTRUCTIONS
      and "持ち出さない（v1.56・オーナー指示）" in generate_post.CALL_B_INSTRUCTIONS)

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
generate_post._derive_decisions = lambda entries, id_map, threshold: {1: "", 2: "採用"}
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
check("L0: 見出し4件が前編に順序どおり", all(h in b["part1_md"] for h in verify_post.REQUIRED_HEADINGS_PART1))
check("L0: ヘッドラインは実文言", b["sections"]["part1_headline"] == CALL_A_DATA["part1_headline"])
check("L0: audit_ledger引き継ぎ", b["audit_ledger"] == CALL_A_DATA["audit_ledger"])

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

print("=== verify_post: C22 notable_move由来ヘッドラインの扱い（v1.42・オーナー指示） ===")

_au_c22a = verify_post.Audit()
verify_post.check_c22(_au_c22a, "BTCは一時上昇したのち上げ幅を縮小した。", [], {},
                       {"BTC": {"notable_move": True}})
check("check_c22: tier1採用は無くてもnotable_move:trueがあればSKIP（値動きは情報源階層の対象外）",
      _au_c22a.checks[0]["result"] == "SKIP", str(_au_c22a.checks[0]))

_au_c22b = verify_post.Audit()
verify_post.check_c22(_au_c22b, "BTCは一時上昇したのち上げ幅を縮小した。", [], {},
                       {"BTC": {"notable_move": False}, "ETH": {"notable_move": False}})
check("check_c22: notable_moveキーはあってもすべてFalseならFAIL（trueが無い）",
      _au_c22b.checks[0]["result"] == "FAIL", str(_au_c22b.checks[0]))

_au_c22c = verify_post.Audit()
verify_post.check_c22(_au_c22c, "BTCは一時上昇したのち上げ幅を縮小した。", [], {}, None)
check("check_c22: intraday_range自体が無い（従来のdaily_data.json）場合もFAIL（回帰確認）",
      _au_c22c.checks[0]["result"] == "FAIL", str(_au_c22c.checks[0]))

_au_c22d = verify_post.Audit()
verify_post.check_c22(
    _au_c22d, "BTCが上昇し、FRBの発表も重なった一日となった。",
    [{"source": "FRB", "url": "https://example.com/h", "title": "...", "published_at": "2026-08-17",
      "verified_by": "v", "decision": "採用", "reason": "一次情報"}],
    {"FRB": 1}, {"BTC": {"notable_move": True}})
check("check_c22: tier1採用がある場合はnotable_moveの有無に関わらずPASS（tier1が優先）",
      _au_c22d.checks[0]["result"] == "PASS", str(_au_c22d.checks[0]))

# run_all()経由でもintraday_rangeが正しく伝播することを確認
# （audit_ledgerに独立2ソース採用を含めない・純粋にnotable_moveのみの経路を見る）
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
_b_notable["sections"]["part1_headline"] = "BTCは一時上昇したのち上げ幅を縮小した。"
au_notable = verify_post.run_all(_b_notable, _dd_notable)
c22_notable = next(x for x in au_notable.checks if x["id"] == "C22_headline_tier1_basis")
check("run_all(): daily_data.intraday_rangeがcheck_c22へ正しく伝播しSKIPになる",
      c22_notable["result"] == "SKIP", str(c22_notable))

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

print("=== generate_post.py: notable_moveのプロンプト指示（v1.41フォローアップ・オーナー承認） ===")
check("SYSTEM_AにINTRADAY_MOVE_GUIDANCE（オーナー指定の文言）が含まれる",
      "その24時間の値動きは記述に値する材料である" in generate_post.SYSTEM_A
      and "あなたは数値を書かないこと" in generate_post.SYSTEM_A
      and "値動きの" in generate_post.SYSTEM_A and "形状のみを記述する" in generate_post.SYSTEM_A)

print()
print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
if FAIL:
    print("FAILED CASES:")
    for f in FAIL:
        print(" -", f)
    sys.exit(1)
print("ALL OK")
