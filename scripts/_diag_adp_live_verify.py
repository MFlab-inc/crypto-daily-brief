"""診断用一時スクリプト（ADP追加のライブ検証・オーナー指示）。

オーナーの3点チェックリストを実データ・実LLM呼び出しで検証する。
1. ADP雇用統計（8月分・3.8万人増）が候補として取得されるか
2. 企業広報が混在した場合、正しく不採用になるか
3. 候補数増加によるトークン消費への影響

【重要な制約・方法】9/2の実audit_ledger（already committed）から
実タイトル・実URL・実published_atを抽出し（41件・全件、改変なし）、
ADP以外の情報源はこれを使う（summaryは永続化されていないためタイトルで
代用・検証目的の近似）。

ADPは今回追加したばかりの情報源のため、実際のcollect_news._collect_from_feed()
（tier=1・本文補強含む）を対象日の実収集ウィンドウに対して実行し、
ウィンドウ内に実際に何件入るかを確認する（本番同様の窓フィルタ）。

あわせて、ADPフィードの生アイテム（ウィンドウ無視・現在取得できる
全件）も候補に加えて実LLMに渡し、企業広報（配当宣言・投資家向け
カンファレンス等）との混在時の判別能力を厳しめに検証する
（1日のウィンドウでは通常ADP由来候補は1件程度にしかならないため、
判別能力そのものを確認するにはこの上乗せが必要——実運用でこの規模の
ADP候補が同時に発生することは稀であり、トークン消費は上振れの
参考値として扱う）。

daily_data.jsonは9/2の実コミット済みファイルをそのまま使う。
LLMは呼ぶ（call_A・call_B）。生成結果はコミットしない。調査後、
本スクリプトとワークフローは削除する。
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

TARGET_DATE = "2026-09-02"
OUT_DIR = Path(f"outputs/{TARGET_DATE}")

# 9/2の実audit_ledgerから抽出した実データ（41件・全件・改変なし）。
REAL_ITEMS = [
    {"source": "CFTC", "tier": 1, "title": "CFTC Staff Issues No-Action Position on Large Trader Reporting for Direct Participants", "url": "https://www.cftc.gov/PressRoom/PressReleases/9293-26", "published_at": "Wed, 02 Sep 2026 17:27:34 +0000"},
    {"source": "CFTC", "tier": 1, "title": "CFTC Issues Final Rule to Modify Clearing Requirement for Canadian Dollar- and Mexican Peso-Denominated Interest Rate Swaps", "url": "https://www.cftc.gov/PressRoom/PressReleases/9292-26", "published_at": "Wed, 02 Sep 2026 16:04:52 +0000"},
    {"source": "日本銀行", "tier": 1, "title": "日本銀行が保有する国債の銘柄別残高", "url": "http://www.boj.or.jp/statistics/boj/other/mei/release/2026/mei260831.xlsx", "published_at": "Wed, 02 Sep 2026 17:00:00 +0900"},
    {"source": "日本銀行", "tier": 1, "title": "日本銀行が受入れている担保の残高（8月末）", "url": "http://www.boj.or.jp/statistics/boj/other/col/col2608.xlsx", "published_at": "Wed, 02 Sep 2026 17:00:00 +0900"},
    {"source": "日本銀行", "tier": 1, "title": "【挨拶】高田審議委員「わが国の経済・物価情勢と金融政策」（札幌）", "url": "http://www.boj.or.jp/about/press/koen_2026/ko260902a.htm", "published_at": "Wed, 02 Sep 2026 16:30:00 +0900"},
    {"source": "日本銀行", "tier": 1, "title": "営業毎旬報告（8月31日現在）", "url": "http://www.boj.or.jp/statistics/boj/other/acmai/release/2026/ac260831.htm", "published_at": "Wed, 02 Sep 2026 10:00:00 +0900"},
    {"source": "日本銀行", "tier": 1, "title": "マネタリーベース（8月）", "url": "http://www.boj.or.jp/statistics/boj/other/mb/mb.htm", "published_at": "Wed, 02 Sep 2026 08:50:00 +0900"},
    {"source": "ホワイトハウス", "tier": 1, "title": "Presidential Message on National Preparedness Month", "url": "https://www.whitehouse.gov/briefings-statements/2026/09/presidential-message-on-national-preparedness-month-6e71/", "published_at": "Wed, 02 Sep 2026 19:25:58 +0000"},
    {"source": "ホワイトハウス", "tier": 1, "title": "Presidential Message on National Childhood Cancer Awareness Month", "url": "https://www.whitehouse.gov/briefings-statements/2026/09/presidential-message-on-national-childhood-cancer-awareness-month/", "published_at": "Wed, 02 Sep 2026 15:59:31 +0000"},
    {"source": "ホワイトハウス", "tier": 1, "title": "Presidential Message on National Recovery Month", "url": "https://www.whitehouse.gov/briefings-statements/2026/09/presidential-message-on-national-recovery-month/", "published_at": "Wed, 02 Sep 2026 15:58:33 +0000"},
    {"source": "ホワイトハウス", "tier": 1, "title": "Ten Times Extreme Liberal Democrats in Congress Put Their Dangerous Agenda Ahead of the American People", "url": "https://www.whitehouse.gov/fact-sheets/2026/09/ten-times-extreme-liberal-democrats-in-congress-put-their-dangerous-agenda-ahead-of-the-american-people/", "published_at": "Wed, 02 Sep 2026 14:45:55 +0000"},
    {"source": "Reuters", "tier": 2, "title": "Fed survey shows economic activity edged up, prices rose moderately in recent weeks - Reuters", "url": "https://news.google.com/rss/articles/CBMiwgFBVV95cUxNeE9leGMyWlY3VGlFRnAzdGx2RHBDX05LbnlsSkU1TVF6enVtWU91cGpEY2NCdTMzMTZyX212OXdrMk83ZWRTNXhwemEtWGx4cjdhbWFTa0ozOVhnNGcteFMzdEJZUk5GT0FYYXBTX2lNeEZ1SnpyTXdTRzBDZkUxeDFmSVozOHJvbzRuU2VUQXRaTDJJOHRhd3BRandNSzkyMDc4NG5oMTYxaF9BbDV0MGN2bnl3T2FoUzZlTVZTWm84Zw?oc=5", "published_at": "Wed, 02 Sep 2026 19:53:01 GMT"},
    {"source": "Reuters", "tier": 2, "title": "Oil settles 1% higher, as US-Iran strikes threaten supplies - Reuters", "url": "https://news.google.com/rss/articles/CBMimwFBVV95cUxPLTRkVWlBVVJQeFBDbXB5UzFkd05qc05KVXhja1h2cC1aMUZxOTRGQTY4a0ZHeWpiSzl0UE50MjRTTjFVREhMUGJhd29Ka21tTTlISE9yd3pSSHFESEtVOTBzb2c0dEVFakx5eEJLamxsMUJxZ0NOSTBpNll2a2Z5eVBncmR6S3MtSW1ITE9hN01KbUljNlcwNlB3aw?oc=5", "published_at": "Wed, 02 Sep 2026 19:30:46 GMT"},
    {"source": "Reuters", "tier": 2, "title": "Dollar to hold gains, but stuck on sparse Fed rate guidance: Reuters poll - Reuters", "url": "https://news.google.com/rss/articles/CBMilAFBVV95cUxPYXlRdl9Td3JHLWRIX3R5U0ZSNm0yS0VVb09VcTdEWVpKM2Z1MUw2ai1nRGJwRnp0dWIwNDdMYlk2d3lnUzJBOE5aQnRzeU4tWHhQR3NuOTdzRklCYzJ2TGl1Q1dqMzRBVnlGbVJWNzN3Z3BHSTNnUU44bUprMnRtRW5taFZuVFlfWldxeEdFSDd0OFBQ?oc=5", "published_at": "Wed, 02 Sep 2026 18:52:32 GMT"},
    {"source": "Reuters", "tier": 2, "title": "EasyJet, Ithaca Energy to join FTSE 100 index - Reuters", "url": "https://news.google.com/rss/articles/CBMijwFBVV95cUxPbEF4WF8xaDdTcW5vdXB1UlVFYVlFU2FKa2VYSmVvNmZ5RDZ0Uk84WHM5NEVsWnFpUDV1OEhhVkxwVmFGcVpXVVA0YlpGWlB0R3VwRFRZWHBkdmhoc0wydHVTM24wTFgtbmg4ZGFRZXhNWlVnZkxhdnJHMTczWm9qdUg0WDNWc3dTMHFfSWFtMA?oc=5", "published_at": "Wed, 02 Sep 2026 17:46:23 GMT"},
    {"source": "Reuters", "tier": 2, "title": "Prediction market Kalshi to file for US crude oil 'perps', source says - Reuters", "url": "https://news.google.com/rss/articles/CBMisgFBVV95cUxOVHVHWUZFV2NwRnJRa3R6djZ0SE9RX3dENmp4OFZYaXh3OTRuYXdlUUl6MWgtX2Q3VmlxdFJSOWZrUW5MNFRoS1ZwME9UanA4dUpobUtJRlROZFhGLUprRGtvSVNnWF9wem9iZDFnRWJ4VnMtSXhqSGZpWVlNTFhETnd6ZWRFTVE3QW50QW42S0RQM2d1WnBxaHUxZE9zSGkyLUNIQXBRNTNTdWdnb1I5dl9R?oc=5", "published_at": "Wed, 02 Sep 2026 17:20:06 GMT"},
    {"source": "Reuters", "tier": 2, "title": "Bank of Canada holds key rate, says multiple hikes might be needed - Reuters", "url": "https://news.google.com/rss/articles/CBMiuAFBVV95cUxQdHFOOThCcFh0NUJwMnBRVmpuWi1wQ3pXU1c5ejZ6ci1MT3VJOEpsaEgyRURodEVsd2FKaGRQTjhWdUtLai1IZHQwaDQ5Z2JGbTg1b1pra2REcHNWdjg3U3I4TndveUMxemI2VVBiS1BfZ0FCakh2LTR3aHJzSXNrS0NaUlk0WTBDd1g3Q1NxTU04M015SE5feklvWVc0N3R2d3lOSEMyNnRyVDZNSVhkelJCTlNDLTA5?oc=5", "published_at": "Wed, 02 Sep 2026 16:43:35 GMT"},
    {"source": "Reuters", "tier": 2, "title": "European shares hit by rising bond yields, energy-driven inflation concerns - Reuters", "url": "https://news.google.com/rss/articles/CBMiyAFBVV95cUxPME1pdGN2bXZCdHkxUDdIazdHeHpCM0FrbVNIa2lHOVNOWnA5Ulk2UVpUdGhSWGJpNEE4ckFqeXFVZjhTV2FscDhPNG83RWRxMnVEZDF1TDNUT3ZuSnlYR05PbHVTWTlYUFhnNjhmM3hqR1dZcFJsV25FWmh4cXV1ZkN2RjNQMDcxeDJRMVVoRTE3dEJ4LXJubmdHQ1FjUkowbEFPQmc4SE9mYl9jY0hXeGZnNUJoSU1VU0RQVEN1VHdqeFE4WTc1WA?oc=5", "published_at": "Wed, 02 Sep 2026 16:39:46 GMT"},
    {"source": "Reuters", "tier": 2, "title": "Chevron expands Venezuela presence with $7 billion plan to double oil output in five years - Reuters", "url": "https://news.google.com/rss/articles/CBMiswFBVV95cUxPU0xfNHNSeU9ZOWlXYzMtTzV0MzRrOGtvZkV3MVl3T0pBV2NfamZZVHhDSmh1a0w1X0RrLUluaEFfYUxuRE9DRTg1VmkyMVY0b0JoVkdHMkhuY1hsSk9rZU12X0xJZG5IdDFaWFNnNjlWXzRnaFNlSldHSW96YmFUdW5FQ0M3RlJRcUQ0OGgwa3AxNDYxaXJ6Ukg5eWY5YTBQRzk4NW5GRFY3MjY2eE9Xc2ZnUQ?oc=5", "published_at": "Wed, 02 Sep 2026 16:28:36 GMT"},
    {"source": "Reuters", "tier": 2, "title": "Berkshire CEO Abel says AI to help power growth - Reuters", "url": "https://news.google.com/rss/articles/CBMirwFBVV95cUxOQUhNVlk0cFV2aWlLZS05RGdXb09LX2E3V01uSzBlc0tqY3R5S2NDblgyNk10QW05Z3FFSXBGVkhVTUJkSVU5TGxvZ0VqelU0eVdjV1gyWXBHWFZnMnQ5VW1sRnQyRXhkR1BYSlplWnF1OG4wYWFvWEJCQThFa2ljMFdvRFpVZk45eGFaNHdrSzZMVWNCSjNxcHVSNy1CdFZUNWxIWjBHSmFxXzhvZm1r?oc=5", "published_at": "Wed, 02 Sep 2026 16:26:23 GMT"},
    {"source": "Reuters", "tier": 2, "title": "India draws a bumper $136 billion in forex inflows, bolstering rupee defence - Reuters", "url": "https://news.google.com/rss/articles/CBMiqAFBVV95cUxQb05GRzZpQ2VFMXEyVTVCdzFLd2NtYVBqYUNldVo3WXhybzRZTXctUFEwSkxzWF9TcmE1d3hmM2JNMnkycndvLXJreW1XZkE1elp4QU5Sc25tbERmMVhaMktXUlNWQkQzMkF1VVl0YmFtQUo4c2hqZGhFX21HdFlmR3NsMVJwanZSaG12M3MxaUVvLUxyOGlzbE8tWjRQM0VVYjliWFR0ams?oc=5", "published_at": "Wed, 02 Sep 2026 16:23:48 GMT"},
    {"source": "Reuters", "tier": 2, "title": "London midcaps hit a nearly one-month low as gilt yields surge - Reuters", "url": "https://news.google.com/rss/articles/CBMioAFBVV95cUxOZ240Q0ItMU54WHVoWktIWk5aTl8yTEFsbmdTM3pZd2ZCUmhnU3dPa3AyUTVSREhHZENXQkdKc0tzVFplNTYyTF9acFJtNmhPX0lOQVFsMmg5bGZQdWVUaWZ2dVRfZklJTElhOVRvRlRKci1BWEJYVVhBSWZWTDVvMFBZVjhIUXJHenhlazJGZWxFRE1Oemc5aUFrNnd2Z1pv?oc=5", "published_at": "Wed, 02 Sep 2026 16:22:20 GMT"},
    {"source": "Reuters", "tier": 2, "title": "Rising Treasury yields could rattle US stocks as earnings season ends - Reuters", "url": "https://news.google.com/rss/articles/CBMivwFBVV95cUxQT0JPMlNBNHNJUVR2WWhfd0xOR3ZnWHAzampvY0tJRGFrN1NteWRFR28tekVYR0F1VW5GQ3I4M0FsR0dFalZzYUdERVlOSHJqOWRNNUFCVnFsaURzb0ZwWFZEZ3VHRTQ5czJaYkk2Ym9sOGROUEMxUHJzMzdFMnctMGZDbGRpUHdiOE1DSFI2VHhDNHdwWHlXTW13cG9FSUhOb0lrbEx5bXRaVzAyeVNsaGRYTWJYRnNqWjh1ZjFCcw?oc=5", "published_at": "Wed, 02 Sep 2026 15:55:25 GMT"},
    {"source": "Reuters", "tier": 2, "title": "Russia says no more hurdles in payments with India - Reuters", "url": "https://news.google.com/rss/articles/CBMiogFBVV95cUxNZ1V2Mm1heXhrd2l3akZMMEkzMDgyOEFFXzhzb1UtM0hjcGpsLXhjeHVwMVRyMFhpbnhzTVBoVTVyTW95Um1pQ0VlS0pQd0ZrakV0R2FJa3V1US1OWGNuVWhVcFExbHZKZlhIeXZkRGxSZVY3elU1RGZSUFZUVnJ4UHJhb1ZOZU1GaXdSTGFlbmJzcWdIc3Y0bmhlMXBJTHJZM0E?oc=5", "published_at": "Wed, 02 Sep 2026 15:39:43 GMT"},
    {"source": "Reuters", "tier": 2, "title": "US crude stocks fall on strong refining activity and exports, EIA says - Reuters", "url": "https://news.google.com/rss/articles/CBMivwFBVV95cUxPZ0trVFJRSV85d29RemYtTUdwT0lDaDhrT0RZSTA4a1I3U3BPbkhjZ2pNTi1WNW5pUWwxSWEzTjVZU09hXzd2aU1SLWtNMWl4QzlSOVBEZkUybWV3emZacnhlazBLQUVqcURGXzh4WTNUTW1DT3NxcF9zWVlqd3hqb3loTlBlVnhDbU55SWtNaXktNGdvcGN3UmE5OG9MMURPYjZyUTVWSWs0TVo3SGpKMGJvaG96ZXRSOTQ3SFZUcw?oc=5", "published_at": "Wed, 02 Sep 2026 15:38:15 GMT"},
    {"source": "Reuters", "tier": 2, "title": "UK bond yields hit fresh 19-year high, adding to pressure on Healey - Reuters", "url": "https://news.google.com/rss/articles/CBMitAFBVV95cUxQQlF1REpnZkFBOEQ5aWtMa2dFUExMOFRLMUxBQzgzeTdfYTByQ0dfbldMajJEVVloel9vb19MMEVkSHgtVTFaTGhhcjZRQURfOWREdkZoZGNtR2tvYmYzWkpIbTNzNGxQSGIwcDhsRnNubGhTN254TEMtek5Xdjhhbi03aDRWVG11RVQxbTNGVm80Ny1sRUVlRzFvVGlaNlVMWk1POEJxdkM5SjdGR3RoeG1lQ3M?oc=5", "published_at": "Wed, 02 Sep 2026 15:30:18 GMT"},
    {"source": "Cointelegraph", "tier": 3, "title": "Coinbase launches regulated crypto derivatives in Canada", "url": "https://cointelegraph.com/news/coinbase-launches-regulated-crypto-derivatives-in-canada", "published_at": "Wed, 02 Sep 2026 20:55:55 +0000"},
    {"source": "CoinDesk", "tier": 3, "title": "Kraken parent Payward delays IPO to second quarter of 2027 at earliest", "url": "https://www.coindesk.com/business/2026/09/02/kraken-parent-payward-pushes-ipo-back-to-mid-2027-at-earliest", "published_at": "Wed, 02 Sep 2026 20:08:34 +0000"},
    {"source": "Cointelegraph", "tier": 3, "title": "Here’s what happened in crypto today", "url": "https://cointelegraph.com/news/what-happened-in-crypto-today", "published_at": "Wed, 02 Sep 2026 19:11:15 +0000"},
    {"source": "Cointelegraph", "tier": 3, "title": "New Jersey officials petition US Supreme Court over prediction markets", "url": "https://cointelegraph.com/news/new-jersey-supreme-court-kalshi-prediction-markets-cftc", "published_at": "Wed, 02 Sep 2026 18:55:41 +0000"},
    {"source": "Cointelegraph", "tier": 3, "title": "Wyoming adds Chainlink reserve verification to state-issued stable token", "url": "https://cointelegraph.com/news/wyoming-chainlink-onchain-reserves-of-state-issued-stable-token", "published_at": "Wed, 02 Sep 2026 18:38:18 +0000"},
    {"source": "CoinDesk", "tier": 3, "title": "Crypto made new friends in U.S. primaries, but focus now shifts to general election", "url": "https://www.coindesk.com/news-analysis/2026/09/02/crypto-made-new-friends-in-u-s-primaries-but-focus-now-shifts-to-general-election", "published_at": "Wed, 02 Sep 2026 17:39:00 +0000"},
    {"source": "CoinDesk", "tier": 3, "title": "New Jersey becomes first state to ask Supreme Court to weigh in on prediction markets", "url": "https://www.coindesk.com/policy/2026/09/02/new-jersey-becomes-first-state-to-ask-supreme-court-to-weigh-in-on-prediction-markets", "published_at": "Wed, 02 Sep 2026 17:23:48 +0000"},
    {"source": "Cointelegraph", "tier": 3, "title": "Ondo urges SEC, CFTC to bring US stock perpetuals onshore", "url": "https://cointelegraph.com/news/ondo-urges-sec-cftc-bring-us-stock-perpetuals-onshore", "published_at": "Wed, 02 Sep 2026 16:39:22 +0000"},
    {"source": "Cointelegraph", "tier": 3, "title": "Bitcoin’s apparent demand turns negative as price struggles with $77K", "url": "https://cointelegraph.com/markets/bitcoins-apparent-demand-turns-negative-price-struggles-with-77k", "published_at": "Wed, 02 Sep 2026 16:35:56 +0000"},
    {"source": "Cointelegraph", "tier": 3, "title": "G20 members tout ‘clear pathways’ for digital asset innovation", "url": "https://cointelegraph.com/news/g20-members-clear-pathways-digital-asset-innovation", "published_at": "Wed, 02 Sep 2026 15:34:06 +0000"},
    {"source": "CoinDesk", "tier": 3, "title": "Crypto Long & Short: Crypto VCs are mistaking consensus for discipline", "url": "https://www.coindesk.com/coindesk-indices/2026/09/02/crypto-long-and-short-crypto-vcs-are-mistaking-consensus-for-discipline", "published_at": "Wed, 02 Sep 2026 15:15:02 +0000"},
    {"source": "Cointelegraph", "tier": 3, "title": "Sui DeFi protocol Full Sail to wind down after Switchboard incident", "url": "https://cointelegraph.com/news/full-sail-sui-wind-down-switchboard-incident", "published_at": "Wed, 02 Sep 2026 13:40:03 +0000"},
    {"source": "Cointelegraph", "tier": 3, "title": "BTC will hit $1M by 2030... but Arthur Hayes is buying ETH instead", "url": "https://cointelegraph.com/magazine/btc-will-hit-1m-by-2030-but-arthur-hayes-is-buying-eth-instead", "published_at": "Wed, 02 Sep 2026 13:30:00 +0000"},
    {"source": "CoinDesk", "tier": 3, "title": "CrowdStrike and federal authorities dismantle Russian malware that secretly stole crypto for 8 years", "url": "https://www.coindesk.com/tech/2026/09/02/crowdstrike-and-federal-authorities-dismantle-russian-malware-that-secretly-stole-crypto-for-8-years", "published_at": "Wed, 02 Sep 2026 13:14:47 +0000"},
    {"source": "Cointelegraph", "tier": 3, "title": "Hashkey joins DTCC working group as first Asian crypto service provider", "url": "https://cointelegraph.com/news/hashkey-dtcc-first-asian-crypto-service-provider", "published_at": "Wed, 02 Sep 2026 13:11:25 +0000"},
]

print(f"実データ再構成: {len(REAL_ITEMS)}件（9/2実audit_ledgerより・全件改変なし）")

print("\n=== 1. ADP実フィードを対象日の実収集ウィンドウに対して実行（本番同様） ===")
window_start, window_end = collect_news.collection_window_ny(date(2026, 9, 2))
adp_entry = next(s for s in collect_news._load_sources() if s["name"] == "ADP")
status_windowed, adp_windowed = collect_news._collect_from_feed(
    "ADP", adp_entry["url"], window_start, window_end, tier=1, kind="official")
print(f"取得結果: {status_windowed}")
print(f"ウィンドウ内候補数: {len(adp_windowed)}")
for c in adp_windowed:
    print(f"  title={c['title']!r}")
    print(f"  summary(先頭200字)={c['summary'][:200]!r}")

print("\n=== 2. ADP生フィード全件（ウィンドウ無視・判別能力の厳格検証用） ===")
status_raw, raw_items, detail_raw = collect_news.fetch_rss(adp_entry["url"])
print(f"取得結果: {status_raw}・{len(raw_items)}件")
adp_all_candidates = []
for it in raw_items:
    adp_all_candidates.append({
        "title": it["title"], "url": it["url"], "source": "ADP",
        "published_at": it["published_at"], "summary": it.get("summary", "") or it["title"],
        "kind": "official", "tier": 1,
    })
    print(f"  title={it['title']!r} pubDate={it['published_at']!r}")

print(f"\n候補統合: 実データ{len(REAL_ITEMS)}件 + ADP生フィード{len(adp_all_candidates)}件 "
      f"= 合計{len(REAL_ITEMS) + len(adp_all_candidates)}件")
all_candidates = [
    {"title": it["title"], "url": it["url"], "source": it["source"],
     "published_at": it["published_at"], "summary": it["title"],
     "kind": collect_news._TIER_KIND.get(it["tier"], "official"), "tier": it["tier"]}
    for it in REAL_ITEMS
] + adp_all_candidates

OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "news_candidates.json").write_text(json.dumps({
    "collected_at": "2026-09-03T12:00:00+09:00",
    "target_date_jst": TARGET_DATE,
    "source_status": {},
    "candidates": all_candidates,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK: {OUT_DIR / 'news_candidates.json'} を一時生成（コミットしない）")

print("\n=== 3. generate_post.run()を実LLMで実行 ===")
client = anthropic.Anthropic()
result = generate_post.run(TARGET_DATE, client=client)

a = result["call_a"]
print(f"call_A: ok={a['ok']} attempts={a['attempts']} error={a['error']}")
print(f"news_candidate_count（選定後）={result['news_candidate_count']}")
print(f"truncation_stats={a['truncation_stats']}")

if not a["ok"]:
    print("ERROR: call_Aが失敗した。中断する。")
    sys.exit(1)

data = a["data"]
audit_ledger = data.get("audit_ledger", [])
adp_entries = [e for e in audit_ledger if e.get("source") == "ADP"]

print("\n=== 判定1・2: ADP候補の採否一覧 ===")
for e in adp_entries:
    print(json.dumps(e, ensure_ascii=False, indent=2))

report_adopted = [e for e in adp_entries if "employment" in e.get("title", "").lower() and e.get("decision") != "不採用"]
report_entries = [e for e in adp_entries if "employment report" in e.get("title", "").lower()]
pr_entries = [e for e in adp_entries if "employment report" not in e.get("title", "").lower()]
pr_rejected = [e for e in pr_entries if e.get("decision") == "不採用"]

print(f"\nADP National Employment Report該当件数: {len(report_entries)}")
print(f"  うち採用（不採用以外）: {len(report_adopted)}")
print(f"企業広報等（Employment Report以外）該当件数: {len(pr_entries)}")
print(f"  うち正しく不採用: {len(pr_rejected)}/{len(pr_entries)}")

print("\n=== 判定3: トークン消費（今回はADP生フィード全10件を上乗せした厳格テストのため上振れ参考値） ===")
in_tok = a["usage"]["input_tokens"]
out_tok = a["usage"]["output_tokens"]
print(f"call_A input_tokens={in_tok} output_tokens={out_tok}")
print(f"CALL_A_MAX_TOKENS={generate_post.CALL_A_MAX_TOKENS}"
      f"（output消費率: {out_tok / generate_post.CALL_A_MAX_TOKENS * 100:.1f}%）")

print("\n=== 参考: C21・C22判定 ===")
tier_map = verify_post._load_source_tier_map()
au_c21 = verify_post.Audit()
verify_post.check_c21(au_c21, "L0", audit_ledger, result["news_candidate_count"], tier_map)
print(f"C21: {au_c21.checks[0]}")
au_c22 = verify_post.Audit()
verify_post.check_c22(au_c22, data.get("part1_headline"), audit_ledger, tier_map, None)
print(f"C22: {au_c22.checks[0]}")

print("\n=== 総括 ===")
print(f"1. ADP雇用統計が候補として取得され採用されたか: "
      f"{'OK' if report_adopted else ('候補には入ったが不採用' if report_entries else 'NG（候補に無い）')}")
print(f"2. 企業広報の正しい不採用: {len(pr_rejected)}/{len(pr_entries)}件"
      f"（{'OK' if pr_entries and len(pr_rejected) == len(pr_entries) else '要確認'}）")
print(f"3. トークン消費: output {out_tok}/{generate_post.CALL_A_MAX_TOKENS}"
      f"（{out_tok / generate_post.CALL_A_MAX_TOKENS * 100:.1f}%・ADP全10件上乗せの上振れ参考値）")
print(f"参考・本番同様のウィンドウ内ADP候補数: {len(adp_windowed)}件"
      f"（通常はこの件数のみが実際に混在する）")
