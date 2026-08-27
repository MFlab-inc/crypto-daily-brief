"""診断用一時スクリプト（v1.44実データ検証・オーナー指示）。

8/26データを使い、v1.44の3件の修正を検証する。
1) 終値がレンジ外の銘柄（ETH）にinconsistent:trueを注入したとき、
   本文の日中レンジ行が省略されること（テンプレート側は単体テスト済み・
   ここではrun_all()経由でも副作用が無いことを確認する）
2) 独立2ソース材料のみ（tier1裏付けなし・notable_moveなし）の状況で、
   part1_headlineがその材料に基づく実文言になること（旧来は定型文の
   ままだった＝8/26実データで実際に発生した不具合そのもの）。ここでは
   実際にcommitされたaudit_ledgerに残るBankChain Alliance関連2記事
   （Cointelegraph・CoinDesk）のtitle/urlを使い、summaryのみ
   reasonフィールドの内容から妥当な範囲で再構成した候補を
   news_candidates_todayとして与える（実際のRSS取得summary本文は
   news_candidates.jsonがコミット対象外のため復元不能）。
3) C22がPASSになること（独立2ソース材料が根拠として認められる）。
4) C23が正しく動作すること（総括に本文未確認の固有名詞が無い健全な
   出力ならPASSになることを、この診断の呼び出しBの実出力で確認する）。

既にコミット済みの outputs/2026-08-26/daily_data.json を読み込み、
intraday_range.ETH.inconsistent を注入したうえで、実際の
generate_post.run()（実API呼び出し）・compose_post.compose()・
verify_post.run_all()を実行する。このジョブのローカルディスク上でのみ
daily_data.json・news_candidates.jsonを書き込み、コミットはしない。
調査後、本スクリプトとワークフローは削除する。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import compose_post  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

TARGET = "2026-08-26"
daily_data_path = Path(f"outputs/{TARGET}/daily_data.json")
daily_data = json.loads(daily_data_path.read_text(encoding="utf-8"))

print("=== 注入前のintraday_range（実データ・inconsistent未検出時点のもの） ===")
print(json.dumps(daily_data.get("intraday_range"), ensure_ascii=False, indent=2))

# 1) ETHの終値$2,492がレンジ$2,415〜$2,484の外（実データで観測済み）。
#    v1.44のcompute_inconsistent()相当の判定結果を注入する。
daily_data["intraday_range"]["ETH"]["inconsistent"] = True
daily_data_path.write_text(json.dumps(daily_data, ensure_ascii=False, indent=2), encoding="utf-8")

# 2) 独立2ソース材料のみのシナリオを再現する候補（実audit_ledgerのtitle/url
#    を使用。summaryはreasonフィールドの内容から妥当な範囲で再構成——
#    実際のRSS summary本文そのものではない点に留意）。
news_candidates = {
    "collected_at": "2026-08-27T10:00:00+09:00",
    "target_date_jst": TARGET,
    "source_status": {"Cointelegraph": {"status": "ok", "raw_count": 30, "kept_count": 1},
                       "CoinDesk": {"status": "ok", "raw_count": 25, "kept_count": 1}},
    "candidates": [
        {
            "title": "US state banking groups plan nationwide blockchain network for 2027",
            "url": "https://cointelegraph.com/news/us-banking-groups-nationwide-blockchain-network-2027",
            "source": "Cointelegraph",
            "published_at": "Wed, 26 Aug 2026 04:19:00 GMT",
            "summary": "US state banking associations are planning a nationwide blockchain "
                       "network called BankChain Alliance, targeting a 2027 launch to support "
                       "stablecoin and tokenized deposit infrastructure.",
            "kind": "media", "tier": 3,
        },
        {
            "title": "U.S. state banking associations plan to launch their own nationwide blockchain network",
            "url": "https://www.coindesk.com/policy/2026/08/25/u-s-state-banking-associations-plan-to-launch-their-own-nationwide-blockchain-network",
            "source": "CoinDesk",
            "published_at": "Tue, 25 Aug 2026 21:56:57 GMT",
            "summary": "State banking associations across the US are planning BankChain "
                       "Alliance, a nationwide blockchain network aimed at stablecoin and "
                       "tokenized deposit infrastructure, targeting a 2027 rollout.",
            "kind": "media", "tier": 3,
        },
    ],
}
news_path = Path(f"outputs/{TARGET}/news_candidates.json")
news_path.write_text(json.dumps(news_candidates, ensure_ascii=False, indent=2), encoding="utf-8")

print()
print("=== 呼び出しA・Bを実行（実API・独立2ソース材料のみ／tier1・notable_moveなし） ===")
client = anthropic.Anthropic()
gen = generate_post.run(TARGET, client=client)
bundle = compose_post.compose(daily_data, gen)

print(f"call_A: ok={gen['call_a']['ok']} attempts={gen['call_a']['attempts']}")
print(f"call_B: ok={gen['call_b']['ok']} attempts={gen['call_b']['attempts']}")
print()
print("=== sections.part1_headline（呼び出しAの出力） ===")
print(bundle["sections"]["part1_headline"])
print()
print("=== sections.part1_points（呼び出しAの出力） ===")
print(bundle["sections"]["part1_points"])
print()
print("=== headline_for_image ===")
print(bundle["headline_for_image"])
print()
print("=== audit_ledger ===")
print(json.dumps(bundle.get("audit_ledger"), ensure_ascii=False, indent=2))
print()
print("=== reusable_for_summary ===")
print(json.dumps(bundle.get("reusable_for_summary"), ensure_ascii=False, indent=2))
print()
print("=== sections.part2_summary（呼び出しBの出力・C23の対象） ===")
print(bundle["sections"]["part2_summary"])
print()
print("=== 前編【主要指標】（ETHの日中レンジ行が省略されることを確認） ===")
print(bundle["sections"]["part1_numeric"])

print()
print("=== verify_post.run_all() 監査結果 ===")
au = verify_post.run_all(bundle, daily_data)
for c in au.checks:
    print(f"{c['id']} {c['result']} - {(c.get('detail') or '')[:200]}")
print(f"failed={au.failed}")
