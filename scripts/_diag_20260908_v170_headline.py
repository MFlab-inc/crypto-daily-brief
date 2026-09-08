#!/usr/bin/env python3
"""v1.70検証用の使い捨て診断スクリプト（非コミット運用・確認後にgit rmする）。
2つのシナリオでcall_a()を実際のAPIへ発火し、以下を確認する。
  シナリオ1: 独立2ソース（tier3×2）で固有名詞の関与が不明確なケース
    （Coldcard事例の再現）。期待: ヘッドラインに日付冒頭・但し書き・
    問題を暗示する形での製品名を含めない。主要銘柄言及時は#付き。
    但し書きはpart1_pointsへ。
  シナリオ2: tier1（SEC）で固有名詞の関与が明確なケース（過剰抑制の
    誤検知が無いことの確認）。期待: 企業名（LumenFi）が普通に書かれる。
outputs/ には一切書き込まない（標準出力のみ）。
"""
import json
import sys

sys.path.insert(0, "scripts")
import generate_post  # noqa: E402
import anthropic  # noqa: E402

DAILY_DATA = {
    "target_date_jst": "2026-09-07",
    "weekday_jp": "月",
    "date_title": "2026年9月7日（月）暗号通貨・DEX市場概況",
    "summary": "",
    "assets": [
        {"asset": "BTC", "usd": "$79,052", "jpy": "約1,234.6万円", "change_24h": "-1.12%", "direction": "down"},
        {"asset": "ETH", "usd": "$2,483", "jpy": "約38.8万円", "change_24h": "-0.87%", "direction": "down"},
        {"asset": "BNB", "usd": "$738", "jpy": "約11.5万円", "change_24h": "-1.53%", "direction": "down"},
    ],
    "intraday_range": {
        "BTC": {"high": "$80,564", "low": "$78,666", "source": "coinbase", "representative": True,
                "inconsistent": False, "notable_move": False},
        "ETH": {"high": "$2,536", "low": "$2,466", "source": "coinbase", "representative": True,
                "inconsistent": False, "notable_move": False},
        "BNB": {"high": "$756", "low": "$733", "source": "coinbase", "representative": False, "inconsistent": False},
    },
    "scheduled_events": [],
    "market": {"fear_greed": {"value": 73, "label": "Greed"}, "market_cap": "$2.687兆",
               "market_cap_jpy": "¥419.7兆", "volume_24h": "$752.1億", "volume_24h_jpy": "¥11.75兆",
               "btc_dominance": "59.07%", "eth_dominance": "11.27%"},
}

SCENARIO_1_CANDIDATES = [
    {
        "title": "Stolen funds tied to hardware wallet brand resurface after quiet period, analysis finds",
        "summary": ("Blockchain analytics firm ChainTrace says a portion of previously stolen bitcoin, "
                    "some of which had been moved into wallets associated with a popular hardware wallet "
                    "brand called 'VaultKey', was transferred again in a new wave of transactions. "
                    "The firm did not say how the funds came to be associated with VaultKey-labeled "
                    "addresses, and VaultKey has not commented."),
        "published_at": "2026-09-07T10:00:00Z", "source": "CryptoWire", "tier": 3,
    },
    {
        "title": "Portion of old bitcoin theft proceeds moves again, tied to hardware wallet addresses",
        "summary": ("According to blockchain analytics firm ChainTrace, roughly 40% of a historical "
                    "bitcoin theft has been moved in a new wave, with the funds passing through addresses "
                    "associated with the VaultKey hardware wallet brand. It remains unclear whether "
                    "VaultKey's security was involved in the original theft."),
        "published_at": "2026-09-07T11:30:00Z", "source": "BlockDaily", "tier": 3,
    },
]

SCENARIO_2_CANDIDATES = [
    {
        "title": "SEC charges crypto lending platform LumenFi with securities fraud",
        "summary": ("The U.S. Securities and Exchange Commission announced charges against crypto "
                    "lending platform LumenFi and its founder, alleging the company misappropriated "
                    "customer funds and made false statements to investors. The SEC's complaint states "
                    "LumenFi diverted over $50 million in customer deposits for unauthorized uses."),
        "published_at": "2026-09-07T09:00:00Z", "source": "SEC", "tier": 1,
    },
]


def run_scenario(name: str, candidates: list[dict]) -> None:
    print(f"\n===== {name} =====")
    client = anthropic.Anthropic()
    news_today = {"candidates": candidates, "source_status": {}}
    outcome = generate_post.call_a(client, DAILY_DATA, news_today, None)
    print(f"ok={outcome.ok} attempts={outcome.attempts}")
    if not outcome.ok:
        print(f"エラー: {outcome.error}")
        return
    data = outcome.data
    print("headline_for_image:", data.get("headline_for_image"))
    print("part1_headline:", data.get("part1_headline"))
    print("part1_points:")
    for p in data.get("part1_points", []):
        print("  -", p)
    print("audit_ledger:")
    for e in data.get("audit_ledger", []):
        print(" ", json.dumps(e, ensure_ascii=False))


if __name__ == "__main__":
    run_scenario("シナリオ1: 独立2ソース・固有名詞の関与が不明確（Coldcard事例再現）", SCENARIO_1_CANDIDATES)
    run_scenario("シナリオ2: tier1・固有名詞の関与が明確（過剰抑制の誤検知確認）", SCENARIO_2_CANDIDATES)
