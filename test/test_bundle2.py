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
from datetime import date as _date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRATCH = Path(tempfile.mkdtemp(prefix="bundle2_test_"))
sys.path.insert(0, str(REPO / "scripts"))
os.chdir(SCRATCH)

import generate_post  # noqa: E402
import compose_post  # noqa: E402
import verify_post  # noqa: E402
import collect_news  # noqa: E402

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


print("=== generate_post._call_json ===")

# 1) 成功（1回目でJSON妥当）・toolsパラメータを一切渡さないことも確認（v1.15）
c = FakeClient(lambda kw, n: json_response(CALL_A_DATA))
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
    return json_response(CALL_A_DATA)
c = FakeClient(flaky_json)
out = generate_post.call_a(c, DAILY_DATA, {"candidates": []}, None)
check("callA JSON不正→リトライ成功", out.ok and out.attempts == 2, str(out.error))

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
    body = json.dumps(CALL_A_DATA, ensure_ascii=False)
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
    return json_response(CALL_A_DATA)
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

print("=== generate_post.py: tier 3プロンプトの確認（v1.20） ===")
check("NEWS_SELECTIONにtier 3の「補完・裏取り」記述がある",
      "tier 3" in generate_post.NEWS_SELECTION and "補完・裏取り" in generate_post.NEWS_SELECTION)
check("NEWS_SELECTIONにtier 3単独を主根拠にしない旨の記述がある",
      "tier 3の候補のみを根拠に" in generate_post.NEWS_SELECTION)
check("WRITES_Aがtier 1・3・4すべてを記録対象としている",
      "tier 1・3・4のすべて" in generate_post.WRITES_A)

print("=== generate_post.py: 独立2ソース規定の確認（v1.28・統合運用基準の既定を実装へ反映） ===")
check("NEWS_SELECTIONに独立2ソース規定の3条件が記述されている",
      all(s in generate_post.NEWS_SELECTION for s in (
          "独立2ソース規定", "2つ以上の独立したtier3媒体", "意見・予想・分析ではなく",
          "媒体名を複数列挙")))
check("独立2ソース規定はヘッドラインへの昇格を認めない",
      "【ヘッドライン】への昇格は引き続きtier1の裏付けを必要とする" in generate_post.NEWS_SELECTION)
check("独立2ソース規定採用時のdecision値がOUTPUT_FORMAT_Aの例に含まれる",
      "採用（独立2ソース）" in generate_post.OUTPUT_FORMAT_A
      and "採用（独立2ソース）" in generate_post.NEWS_SELECTION)
check("NO_CANDIDATES_FALLBACKが独立2ソース規定該当時にpart1_pointsの定型文を使わない旨を記述",
      "独立2ソース規定" in generate_post.NO_CANDIDATES_FALLBACK
      and "part1_pointsの定型文フォールバックを使わず" in generate_post.NO_CANDIDATES_FALLBACK)

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

print("=== generate_post.py: ヘッドラインの判定手順（v1.30・オーナー指示） ===")
check("NEWS_SELECTIONにヘッドラインの判定手順が明示的な分岐として記述されている",
      all(s in generate_post.NEWS_SELECTION for s in (
          "ヘッドラインの判定手順", "tier1の裏付けがある採用材料",
          "その材料に基づく実文言のヘッドラインを書く")))
check("ヘッドラインの判定手順は独立2ソース材料単独では昇格しない旨を明記",
      "独立2ソース材料は【主要なポイント】には掲載できるが、【ヘッドライン】の"
      in generate_post.NEWS_SELECTION
      and "根拠にはできない" in generate_post.NEWS_SELECTION)
check("WRITES_Aのheadline_for_imageもヘッドラインの判定手順に従う旨を記述",
      "ヘッドラインの判定手順" in generate_post.WRITES_A
      and generate_post.WRITES_A.count("ヘッドラインの判定手順") >= 2)

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
check("NO_CANDIDATES_FALLBACKに直接因果未確認のみを理由にした不採用を禁じる文言がある",
      "「暗号通貨価格への直接因果が未確認」であること" in generate_post.NO_CANDIDATES_FALLBACK
      and "のみを理由に不採用としてはならない" in generate_post.NO_CANDIDATES_FALLBACK)
check("WRITES_Aのpart1_pointsがB分類材料に因果未確認の限定表現を含める旨を参照している",
      "重要性判定と因果表現の分離" in generate_post.WRITES_A
      and "暗号通貨価格への直接因果は未確認" in generate_post.WRITES_A)

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
_uc, _ = generate_post._build_call_a_user_content(DAILY_DATA, _news_today_elig, None)
_uc_parsed = json.loads(_uc)
check("_build_call_a_user_content: news_candidates_todayの各項目にeligibilityが付与される",
      all("eligibility" in c for c in _uc_parsed["news_candidates_today"]))
check("NEWS_SELECTIONがeligibilityフィールドの存在と、それに従う旨を候補に明記している",
      "eligibility" in generate_post.NEWS_SELECTION
      and "判定に従うこと" in generate_post.NEWS_SELECTION)

print("=== generate_post.py: tier3候補数上限の確認（v1.21） ===")
_tier1_fixed = [{"tier": 1, "source": "SEC", "published_at": "Mon, 17 Aug 2026 10:00:00 GMT"} for _ in range(3)]
_tier3_15 = [{"tier": 3, "source": "CoinDesk", "title": f"item{i}",
              "published_at": f"Mon, 17 Aug 2026 {i:02d}:00:00 GMT"} for i in range(15)]
_selected, _stats = generate_post._select_candidates_for_call_a(_tier1_fixed + _tier3_15)
check("tier1は全件（上限なし）で選定される",
      sum(1 for c in _selected if c.get("tier") == 1) == 3, str(_stats))
check(f"tier3は上限{generate_post.TIER3_CANDIDATE_LIMIT}件に絞られる",
      sum(1 for c in _selected if c.get("tier") == 3) == generate_post.TIER3_CANDIDATE_LIMIT, str(_stats))
check("tier3は公開日時の新しい順で選定される（最新のitem14が先頭）",
      [c["title"] for c in _selected if c.get("tier") == 3][0] == "item14",
      [c["title"] for c in _selected if c.get("tier") == 3])
check("truncation_statsが正しく報告される（15件中10件選定・5件除外）",
      _stats == {"tier3_total": 15, "tier3_selected": 10, "tier3_dropped": 5}, str(_stats))

_selected_few, _stats_few = generate_post._select_candidates_for_call_a(_tier1_fixed + _tier3_15[:5])
check("tier3が上限未満なら全件選定され除外0件",
      _stats_few == {"tier3_total": 5, "tier3_selected": 5, "tier3_dropped": 0}, str(_stats_few))

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
      "tier3候補 15件中 10件を選定" in status_text and "5件を件数上限により除外" in status_text,
      status_text)

_gen_not_truncated = json.loads(json.dumps(_gen_truncated))
_gen_not_truncated["call_a"]["truncation_stats"] = _stats_few
_gen_not_truncated["call_a"]["data"] = CALL_A_DATA
status_text2 = compose_post.render_generation_status(_gen_not_truncated)
check("GENERATION_STATUS.md: tier3除外が無ければ目視確認行を表示しない",
      "件数上限により除外" not in status_text2, status_text2)

print("=== generate_post.run(): news_candidate_countは渡した件数基準（v1.21） ===")
os.makedirs("outputs/2026-08-21", exist_ok=True)
Path("outputs/2026-08-21/daily_data.json").write_text(
    json.dumps({**DAILY_DATA, "target_date_jst": "2026-08-21"}, ensure_ascii=False), encoding="utf-8")
_news_many = {"collected_at": "2026-08-21T09:00:00+09:00", "target_date_jst": "2026-08-21",
              "source_status": {}, "candidates": _tier1_fixed + _tier3_15}
Path("outputs/2026-08-21/news_candidates.json").write_text(json.dumps(_news_many, ensure_ascii=False), encoding="utf-8")


def _make_run_client_tolerant(a_ok, b_ok):
    def fn(kw, n):
        is_call_a = kw.get("system") == generate_post.SYSTEM_A
        if is_call_a:
            return json_response(CALL_A_DATA) if a_ok else FakeResponse([FakeTextBlock("bad")])
        return json_response(CALL_B_DATA) if b_ok else FakeResponse([FakeTextBlock("bad")])
    return FakeClient(fn)


_c = _make_run_client_tolerant(True, True)
_result21 = generate_post.run("2026-08-21", client=_c)
# 生の取得総数は 3(tier1) + 15(tier3) = 18件だが、実際に渡すのは 3 + 10(上限) = 13件。
check("run(): news_candidate_countは取得総数(18)ではなく渡した件数(13)を反映する",
      _result21["news_candidate_count"] == 13, str(_result21["news_candidate_count"]))
check("run(): call_a.truncation_statsにtier3の除外情報が記録される",
      _result21["call_a"]["truncation_stats"] == {"tier3_total": 15, "tier3_selected": 10, "tier3_dropped": 5},
      str(_result21["call_a"]["truncation_stats"]))

print("=== generate_post.run() レベル判定 ===")
os.makedirs("outputs/2026-08-17", exist_ok=True)
Path("outputs/2026-08-17/daily_data.json").write_text(json.dumps(DAILY_DATA, ensure_ascii=False), encoding="utf-8")


def make_run_client(a_ok, b_ok):
    def fn(kw, n):
        is_call_a = kw.get("system") == generate_post.SYSTEM_A
        if is_call_a:
            return json_response(CALL_A_DATA) if a_ok else FakeResponse([FakeTextBlock("bad")])
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

# 実文言ヘッドライン＋tier1採用なし（独立2ソースのみ）はFAIL
# （実データ8/21で実際に発生した形：ヘッドラインがtier3単独材料を根拠にしていた）
_, c22 = _c21([
    {"source": "Cointelegraph", "url": "https://example.com/i1", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
    {"source": "CoinDesk", "url": "https://example.com/i2", "title": "...", "published_at": "2026-08-17",
     "verified_by": "v", "decision": "採用（独立2ソース）", "reason": "2媒体一致"},
], headline="BTCが上昇し、A社のライセンス取得報道も material となった一日。")
check("C22: tier1採用が無いヘッドラインはFAIL（既知の限界：簡易版のため対応関係は見ない）",
      c22["result"] == "FAIL", str(c22))

print("=== collect_news.py（RSS方式・CryptoPanic撤去後） ===")

RSS_TODAY_ONLY = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Today item (GMT same-day)</title><link>https://example.gov/a</link><pubDate>Mon, 17 Aug 2026 10:00:00 GMT</pubDate></item>
<item><title>Yesterday item</title><link>https://example.gov/b</link><pubDate>Sun, 16 Aug 2026 10:00:00 GMT</pubDate></item>
<item><title>JST boundary item (UTC prev-day, JST today 00:30)</title><link>https://example.gov/c</link><pubDate>Sun, 16 Aug 2026 15:30:00 GMT</pubDate></item>
</channel></rss>"""

RSS_WITH_SUMMARY = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Item with summary</title><link>https://example.gov/d</link><pubDate>Mon, 17 Aug 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;Some &lt;b&gt;detail&lt;/b&gt; text.&lt;/p&gt;</description></item>
</channel></rss>"""


class _FakeRssResp:
    def __init__(self, status_code, content: bytes):
        self.status_code = status_code
        self.content = content


def _patch_requests_get(fn):
    orig = collect_news.requests.get
    collect_news.requests.get = fn
    return orig


# 1) 正常フィード: 対象日フィルタが機能する（JST変換後の日付で比較する境界ケース込み）
orig_get = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_TODAY_ONLY.encode("utf-8")))
status, cands, detail = collect_news.fetch_rss("https://example.gov/feed.rss")
collect_news.requests.get = orig_get
check("fetch_rss: 正常時はok・3件取得", status == "ok" and len(cands) == 3, f"{status} {len(cands)}")

orig_get2 = _patch_requests_get(lambda url, **kw: _FakeRssResp(200, RSS_TODAY_ONLY.encode("utf-8")))
st, kept = collect_news._collect_from_feed("TESTGOV", "https://example.gov/feed.rss",
                                            _date(2026, 8, 17), tier=1, kind="official")
collect_news.requests.get = orig_get2
check("_collect_from_feed: 対象日(JST)の2件のみ残る（UTC境界含む）",
      st["status"] == "ok" and st["raw_count"] == 3 and st["kept_count"] == 2 and len(kept) == 2,
      f"{st} kept={kept}")
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
                                              _date(2026, 8, 17), tier=1, kind="official")
collect_news.requests.get = orig_get4
check("_collect_from_feed: candidateにsummaryが含まれる（呼び出しAの根拠として渡る）",
      len(kept2) == 1 and kept2[0]["summary"] == "Some detail text.", str(kept2))

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

print("=== post_draft.yml: フェイルクローズ・冪等性ガードの確認（v1.20） ===")
post_draft_yml = (REPO / ".github" / "workflows" / "post_draft.yml").read_text(encoding="utf-8")
check("post_draft.yml: continue-on-errorが除去されている（フェイルクローズ化）",
      "continue-on-error" not in post_draft_yml)
check("post_draft.yml: force_redispatch入力がある", "force_redispatch" in post_draft_yml)
check("post_draft.yml: 冪等性ガードのステップがある",
      "冪等性ガード" in post_draft_yml and "steps.guard.outputs.skip" in post_draft_yml)

print()
print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
if FAIL:
    print("FAILED CASES:")
    for f in FAIL:
        print(" -", f)
    sys.exit(1)
print("ALL OK")
