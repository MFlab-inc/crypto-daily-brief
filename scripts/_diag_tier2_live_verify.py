"""診断用一時スクリプト（tier2/Reuters実装のライブ検証・オーナー指示）。

オーナーの5点チェックリストを実データ・実LLM呼び出しで検証する。
1. 9/1のイラン・原油の記事が tier2 として採用されるか
2. part1_headline がその材料に基づく実文言になるか
3. C21・C22 が正しく判定するか
4. トークン消費と上限8,000に対する余裕
5. 8/26・8/28で誤検知や退行がないか

【5番目について・事前確認済み】outputs/2026-08-26/draft/post_bundle.json
の実データ（ローカル・ネットワーク不要）を直接確認したところ、audit_ledger
に"Google News (Reuters検索)"のsourceを持つ候補は1件も無かった——
つまりtier2への昇格ロジックが作用する対象が元々存在せず、この日の
生成結果はtier2実装の有無に関わらず不変（退行の可能性が無い）。
8/28はdraft自体が生成されていない日（監査FAILによりコミット未到達）
のため、そもそも比較対象が存在しない（既知の限界）。したがって本
スクリプトは1〜4に絞って実LLM検証を行う。

【1〜4の検証方法・重要な制約】outputs/{date}/news_candidates.json
（collect_news.pyの生出力・summary本文を含む）はリポジトリへコミット
されない一時ファイルであり、9/1当日のものはもう存在しない。実際に
コミットされているのは post_bundle.json の audit_ledger のみで、
source・url・title・published_atは保持されているが、LLMの判断根拠と
なったsummary本文は保持されていない。

そのため本スクリプトは、9/1の実audit_ledgerから実タイトル・実URL・
実source・実published_atを抽出し（全件、改変なし）、以下の方針で
news_candidates_today相当のデータを再構成する。
- tier1・tier3候補: 実データそのまま。summaryは永続化されていないため
  タイトルで代用する（検証目的の近似であることを明記）。
- tier2候補（Reutersのイラン・原油記事）: 実タイトル・実URL・実
  published_atをそのまま使い、実際のcollect_news._collect_from_feed()
  の実装（<source>要素の解析によるtier4→tier2昇格ロジック含む）に
  実際に通してtier2候補を生成する——手動でtier=2を代入するのではなく、
  実コードパスを検証する。summaryはオーナー報告済みの実数値
  （Brent +4.60%・WTI +5.20%・米イラン交戦再開）に基づき構成する。

daily_data.jsonは9/1の実コミット済みファイルをそのまま使う。

本スクリプトはANTHROPIC_API_KEYを使い実際にLLMを呼び出す（call_A・
call_B）。生成結果はコミットしない（outputs/2026-09-01/news_candidates.json
はこのジョブのランナー上にのみ一時的に書き込まれ、後続のコミット
ステップは存在しない）。調査後、本スクリプトとワークフローは削除する。
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

TARGET_DATE = "2026-09-01"
OUT_DIR = Path(f"outputs/{TARGET_DATE}")

# 9/1の実audit_ledgerから抽出した実データ（全件・改変なし。source/title/
# url/published_atはpost_bundle.jsonの実コミット済みデータと完全一致）。
REAL_TIER1_TIER3_ITEMS = [
    {"source": "SEC", "title": "SEC Announces Agenda and Panelists for Roundtable on Preparations for 24-Hour Trading",
     "url": "https://www.sec.gov/newsroom/press-releases/2026-83-sec-announces-agenda-panelists-roundtable-preparations-24-hour-trading",
     "published_at": "Tue, 01 Sep 2026 15:17:39 -0400"},
    {"source": "SEC", "title": "SEC Charges San Francisco Bay Area Private Fund Executives with Multimillion Dollar Ponzi-Like Scheme",
     "url": "https://www.sec.gov/newsroom/press-releases/2026-82-sec-charges-san-francisco-bay-area-private-fund-executives-multimillion-dollar-ponzi-scheme",
     "published_at": "Tue, 01 Sep 2026 13:52:32 -0400"},
    {"source": "SEC", "title": "SEC Proposes to Modernize Rules for Registered Transfer Agents",
     "url": "https://www.sec.gov/newsroom/press-releases/2026-81-sec-proposes-modernize-rules-registered-transfer-agents",
     "published_at": "Tue, 01 Sep 2026 10:57:00 -0400"},
    {"source": "FRB（speeches）", "title": "Barr, Unlocking Opportunities for Workers and Entrepreneurs with a Criminal Record",
     "url": "https://www.federalreserve.gov/newsevents/speech/barr20260901a.htm",
     "published_at": "Tue, 1 Sep 2026 13:05:00 GMT"},
    {"source": "OCC", "title": "OCC Releases CRA Performance Evaluations for 23 National Banks and Federal Savings Associations",
     "url": "https://www.occ.gov/news-issuances/news-releases/2026/nr-occ-2026-74.html",
     "published_at": "1 Sep 2026 10:00:00 -0400"},
    {"source": "日本銀行", "title": "金融安定理事会によるG20財務大臣・中央銀行総裁へのレターの公表について",
     "url": "http://www.boj.or.jp/intl_finance/meeting/group/gro260901a.htm",
     "published_at": "Tue, 01 Sep 2026 17:00:00 +0900"},
    {"source": "日本銀行", "title": "債券市場サーベイ（2026年8月調査）",
     "url": "http://www.boj.or.jp/paym/bond/bond_list/bond2608.pdf",
     "published_at": "Tue, 01 Sep 2026 16:00:00 +0900"},
    {"source": "日本銀行", "title": "日銀当座預金増減要因と金融調節（8月実績）",
     "url": "http://www.boj.or.jp/statistics/boj/fm/juqf/juqf08.xlsx",
     "published_at": "Tue, 01 Sep 2026 13:00:00 +0900"},
    {"source": "USTR", "title": "Media Credentialing Opens for the G20 Trade Ministerial in Milwaukee, Wisconsin",
     "url": "https://ustr.gov/about/policy-offices/press-office/press-releases/2026/august/media-credentialing-opens-g20-trade-ministerial-milwaukee-wisconsin",
     "published_at": "Tue, 01 Sep 2026 17:25:46 +0000"},
    {"source": "ホワイトハウス", "title": "Fact Sheet: President Donald J. Trump Announces Historic Oil Agreement to Secure American Energy Dominance and Drive Venezuela’s Economic Recovery",
     "url": "https://www.whitehouse.gov/fact-sheets/2026/08/fact-sheet-president-donald-j-trump-announces-historic-oil-agreement-to-secure-american-energy-dominance-and-drive-venezuelas-economic-recovery/",
     "published_at": "Mon, 31 Aug 2026 23:55:33 +0000"},
    {"source": "Cointelegraph", "title": "Binance expands TradFi push with options on 1,000 US stocks, ETFs",
     "url": "https://cointelegraph.com/news/binance-adds-options-on-1000-us-stocks-and-etfs-in-tradfi-expansion",
     "published_at": "Tue, 01 Sep 2026 20:42:29 +0000"},
    {"source": "Cointelegraph", "title": "UK crime agency froze $13.5M amid probe into Premier League crypto sponsor",
     "url": "https://cointelegraph.com/news/uk-crime-agency-froze-premier-league-crypto-partner-sorare",
     "published_at": "Tue, 01 Sep 2026 20:14:12 +0000"},
    {"source": "Cointelegraph", "title": "Here’s what happened in crypto today",
     "url": "https://cointelegraph.com/news/what-happened-in-crypto-today",
     "published_at": "Tue, 01 Sep 2026 20:00:17 +0000"},
    {"source": "Cointelegraph", "title": "SEC proposes broad update to decades-old transfer agent rules with blockchain nod",
     "url": "https://cointelegraph.com/news/sec-proposes-transfer-agent-overhaul-as-securities-move-onchain",
     "published_at": "Tue, 01 Sep 2026 17:52:51 +0000"},
    {"source": "Cointelegraph", "title": "Kalshi issues first lifetime ban for Republican politician over insider bets",
     "url": "https://cointelegraph.com/news/kalshi-bans-politicians-insider-trading-bets-manipulation",
     "published_at": "Tue, 01 Sep 2026 17:39:48 +0000"},
    {"source": "Cointelegraph", "title": "BofA, Citi, Goldman Sachs among 21 institutions planning stablecoin launch",
     "url": "https://cointelegraph.com/news/21-financial-institutions-g7-stablecoin-venture",
     "published_at": "Tue, 01 Sep 2026 16:39:12 +0000"},
    {"source": "Cointelegraph", "title": "Ethena launches USDe payments app, offers 6% rewards",
     "url": "https://cointelegraph.com/news/ethena-launches-usde-powered-money-app-across-48-countries",
     "published_at": "Tue, 01 Sep 2026 16:06:58 +0000"},
    {"source": "CoinDesk", "title": "Citi, Goldman, other global banks and asset managers team up on stablecoin venture",
     "url": "https://www.coindesk.com/business/2026/09/01/citi-goldman-other-global-banks-and-asset-managers-team-up-on-stablecoin-venture",
     "published_at": "Tue, 01 Sep 2026 15:36:27 +0000"},
    {"source": "Cointelegraph", "title": "Bitcoin stays flat as global bond bear market rages on, pushing JGB to high",
     "url": "https://cointelegraph.com/markets/bitcoin-remains-flat-as-global-bond-bear-market-rages-on",
     "published_at": "Tue, 01 Sep 2026 15:34:00 +0000"},
    {"source": "CoinDesk", "title": "Robinhood's new crypto network is printing cash, and it's sending Arbitrum's token soaring",
     "url": "https://www.coindesk.com/markets/2026/09/01/robinhood-s-new-crypto-network-is-printing-cash-and-it-s-sending-arbitrum-s-token-soaring",
     "published_at": "Tue, 01 Sep 2026 15:28:29 +0000"},
    {"source": "CoinDesk", "title": "Musk’s X hit by wave of unsolicited password reset emails",
     "url": "https://www.coindesk.com/tech/2026/09/01/musk-s-x-hit-by-wave-of-unsolicited-password-reset-emails",
     "published_at": "Tue, 01 Sep 2026 14:59:12 +0000"},
    {"source": "Cointelegraph", "title": "Fake Claude desktop app spreads crypto-stealing malware",
     "url": "https://cointelegraph.com/news/fake-claude-desktop-app-spreads-crypto-stealing-malware",
     "published_at": "Tue, 01 Sep 2026 14:00:00 +0000"},
    {"source": "CoinDesk", "title": "Firelight raises $8 million, expands beyond XRP as it aims to make DeFi less scary for fintechs",
     "url": "https://www.coindesk.com/business/2026/08/31/firelight-raises-usd8-million-expands-beyond-xrp-as-it-aims-to-make-defi-less-scary-for-fintechs",
     "published_at": "Tue, 01 Sep 2026 13:56:44 +0000"},
    {"source": "CoinDesk", "title": "Bitcoin enters ‘Rektember’ as rate-hike risk combines with seasonality to threaten rally",
     "url": "https://www.coindesk.com/markets/2026/09/01/bitcoin-enters-rektember-as-rate-hike-risks-threaten-its-august-rally",
     "published_at": "Tue, 01 Sep 2026 13:55:26 +0000"},
    {"source": "Cointelegraph", "title": "Does the Bitcoin rally mean we haven’t wasted our lives in crypto?",
     "url": "https://cointelegraph.com/magazine/does-bitcoins-rally-mean-we-havent-wasted-our-lives-in-crypto",
     "published_at": "Tue, 01 Sep 2026 13:30:00 +0000"},
    {"source": "CoinDesk", "title": "UK’s crime agency freezes Premier League $13.5 million account in crypto crime probe",
     "url": "https://www.coindesk.com/business/2026/09/01/uk-s-crime-agency-freezes-premier-league-usd13-5-million-account-in-crypto-crime-probe",
     "published_at": "Tue, 01 Sep 2026 12:37:10 +0000"},
    {"source": "Cointelegraph", "title": "London Stock Exchange partners with Kraken parent for tokenized UK stocks: FT",
     "url": "https://cointelegraph.com/news/london-stock-exchange-partners-kraken-for-tokenized-uk-stocks",
     "published_at": "Tue, 01 Sep 2026 10:56:41 +0000"},
    {"source": "CoinDesk", "title": "London Stock Exchange to work with Payward to bring biggest UK stocks onchain",
     "url": "https://www.coindesk.com/markets/2026/09/01/london-stock-exchange-to-work-with-payward-to-bring-biggest-uk-stocks-onchain",
     "published_at": "Tue, 01 Sep 2026 07:49:16 +0000"},
    {"source": "Cointelegraph", "title": "Trump Jr.-linked 1789 Capital leads Polymarket’s $1B raise: Report",
     "url": "https://cointelegraph.com/news/trump-jr-linked-fund-invest-300m-polymarket-1b-round",
     "published_at": "Tue, 01 Sep 2026 07:47:13 +0000"},
    {"source": "CoinDesk", "title": "Trump Jr's firm leads $1 billion Polymarket raise at $21 billion value: Report",
     "url": "https://www.coindesk.com/business/2026/09/01/trump-jr-s-firm-leads-usd1-billion-polymarket-raise-at-usd21-billion-value-report",
     "published_at": "Tue, 01 Sep 2026 04:19:54 +0000"},
]

# 実タイトル・実URL・実published_at（post_bundle.jsonの実コミット済みデータと一致）。
REAL_REUTERS_TITLE = "US launches new barrage of strikes on Iran around Strait of Hormuz - Reuters"
REAL_REUTERS_URL = ("https://news.google.com/rss/articles/CBMiygFBVV95cUxOYWVYQlZISm1jT2ZUaUZ4bDJ2ZE10ZEpaeXo5"
                     "MnBPQTJYS0ZJNDFjNmdBNGlPQjdyRTIxMVJWeDYzTlFEZi1wVm55eUJTUjkxSjB2WnVVU3NLaEtjTWlMTFFXZlZuTDYy"
                     "NzREc3hxWnpxRzdUV2MtRUdhei12TE9TQ0Rrc1hTMEN4alFnS1VFcVRzSEM1dmVxR2FYbzZXb1B2a254Y2FlVXlNMFBh"
                     "QVlFRTAyNzdoaE1FN2Q5dFF0LS1PZDR3bm1PS2JR?oc=5")
REAL_REUTERS_PUBLISHED_AT = "Tue, 01 Sep 2026 20:35:31 GMT"

print("=== 1. tier2候補の生成（実コードパス経由・<source>要素解析→tier4→tier2昇格） ===")
_fake_rss = f"""<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>{REAL_REUTERS_TITLE}</title>
<link>{REAL_REUTERS_URL}</link>
<pubDate>{REAL_REUTERS_PUBLISHED_AT}</pubDate>
<source url="https://www.reuters.com">Reuters</source></item>
</channel></rss>"""


class _FakeResp:
    def __init__(self, content: bytes):
        self.status_code = 200
        self.content = content


_orig_get = collect_news.requests.get
collect_news.requests.get = lambda url, **kw: _FakeResp(_fake_rss.encode("utf-8"))
_window_start, _window_end = collect_news.collection_window_ny(date(2026, 9, 1))
_status, _reuters_candidates = collect_news._collect_from_feed(
    collect_news.GOOGLE_NEWS_NAME, "https://news.google.com/fake", _window_start, _window_end,
    tier=4, kind="candidate_discovery")
collect_news.requests.get = _orig_get

print(f"取得結果: {_status}")
if not _reuters_candidates:
    print("ERROR: tier2候補の生成に失敗（収集ウィンドウ外に判定された可能性）。中断する。")
    sys.exit(1)
_reuters_cand = _reuters_candidates[0]
_reuters_cand["summary"] = (
    "Reuters報道（オーナー報告済みの実数値に基づく要約）: 米国がイラン国内の標的へ新たな空爆を実施し、"
    "ホルムズ海峡周辺での軍事衝突が再燃した。原油価格が急伸（Brent +4.60%・WTI +5.20%）。"
)
print(f"実体判定結果: source={_reuters_cand['source']!r} tier={_reuters_cand['tier']!r} kind={_reuters_cand['kind']!r}")
if _reuters_cand["source"] != "Reuters" or _reuters_cand["tier"] != 2:
    print("ERROR: tier2への昇格が機能していない。中断する。")
    sys.exit(1)

print("\n=== 2. news_candidates.json相当データの構成（実データ・タイトルをsummary代用） ===")
_tier_by_source = {s["name"]: s["tier"] for s in collect_news._load_sources()}
_filler_candidates = []
for it in REAL_TIER1_TIER3_ITEMS:
    tier = _tier_by_source.get(it["source"])
    if tier is None:
        print(f"WARN: source={it['source']!r} のtierが不明。スキップする。")
        continue
    _filler_candidates.append({
        "title": it["title"], "url": it["url"], "source": it["source"],
        "published_at": it["published_at"], "summary": it["title"],
        "kind": collect_news._TIER_KIND.get(tier, "official"), "tier": tier,
    })

all_candidates = _filler_candidates + [_reuters_cand]
print(f"候補総数: {len(all_candidates)}件（tier1={sum(1 for c in all_candidates if c['tier']==1)}・"
      f"tier2={sum(1 for c in all_candidates if c['tier']==2)}・"
      f"tier3={sum(1 for c in all_candidates if c['tier']==3)}件）")

OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "news_candidates.json").write_text(json.dumps({
    "collected_at": "2026-09-02T00:00:00+09:00",
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
print(f"level={result['level']}")
print(f"news_candidate_count（選定後・Call Aへ渡した件数）={result['news_candidate_count']}")
print(f"truncation_stats={a['truncation_stats']}")

if not a["ok"]:
    print("ERROR: call_Aが失敗した。中断する。")
    sys.exit(1)

data = a["data"]
audit_ledger = data.get("audit_ledger", [])
reuters_entries = [e for e in audit_ledger if e.get("source") == "Reuters"]

print("\n=== 判定1: Reuters記事がtier2として採用されるか ===")
if reuters_entries:
    for e in reuters_entries:
        print(json.dumps(e, ensure_ascii=False, indent=2))
else:
    print("ERROR: audit_ledgerにReuters（tier2）の記録が無い。")

print("\n=== 判定2: part1_headlineの実文言 ===")
print(f"part1_headline: {data.get('part1_headline')!r}")
print(f"headline_for_image: {data.get('headline_for_image')!r}")
print(f"part1_points: {json.dumps(data.get('part1_points'), ensure_ascii=False, indent=2)}")
_headline_reflects = any(
    kw in str(data.get("part1_headline", "")) for kw in ("イラン", "ホルムズ", "原油", "Iran", "Hormuz")
)
print(f"part1_headlineに材料関連キーワード（イラン/ホルムズ/原油等）が含まれるか: {_headline_reflects}")

print("\n=== 判定3: C21・C22の判定 ===")
tier_map = verify_post._load_source_tier_map()
au_c21 = verify_post.Audit()
verify_post.check_c21(au_c21, "L0", audit_ledger, result["news_candidate_count"], tier_map)
c21_result = au_c21.checks[0]
print(f"C21: {c21_result}")

au_c22 = verify_post.Audit()
verify_post.check_c22(au_c22, data.get("part1_headline"), audit_ledger, tier_map, None)
c22_result = au_c22.checks[0]
print(f"C22: {c22_result}")

print("\n=== 判定4: トークン消費と上限8,000に対する余裕 ===")
in_tok = a["usage"]["input_tokens"]
out_tok = a["usage"]["output_tokens"]
print(f"call_A input_tokens={in_tok} output_tokens={out_tok}")
print(f"CALL_A_MAX_TOKENS={generate_post.CALL_A_MAX_TOKENS}（output上限。今回のoutput消費率: "
      f"{out_tok / generate_post.CALL_A_MAX_TOKENS * 100:.1f}%）")

print("\n=== 総括 ===")
print(f"1. tier2採用: {'OK' if reuters_entries and reuters_entries[0].get('decision') == '採用' else 'NG'}")
print(f"2. part1_headline反映: {'OK' if _headline_reflects else '要目視確認（キーワード不一致）'}")
print(f"3a. C21: {c21_result['result']}")
print(f"3b. C22: {c22_result['result']}")
print(f"4. トークン余裕: output {out_tok}/{generate_post.CALL_A_MAX_TOKENS}"
      f"（{out_tok / generate_post.CALL_A_MAX_TOKENS * 100:.1f}%）")
