"""診断用一時スクリプト（tier2/Reuters実装・クエリ絞り込み効果調査・オーナー指示）。

(a)案承認に伴い、オーナーから追加で以下の実測を依頼された。
「クエリを絞りすぎて重要材料を落とすのが最悪」「絞り込みで9/1の記事が
落ちるなら、絞り込みは見送って上限15件のまま運用します」という明示の
判定ルールが示されているため、本スクリプトの結果でGOOGLE_NEWS_URLを
変更するかどうかを機械的に決める。

1. 現行クエリ（site:reuters.com のみ）と、金融・マクロキーワードのOR条件
   （オーナー指定の例示どおり）を加えた絞り込みクエリを実際に叩き、
   件数・内容の関連度を比較する（when:24hのローリングウィンドウなので
   「現在の効果」の直接比較になる・過去の再現ではない）。
2. 9/1のイラン・原油記事（"Strait of Hormuz"）が絞り込み後も取得できるかを
   確認する。when:24hは9/1時点の内容が既にロールオフしているため直接
   再現できない。固有フレーズでの存在確認（絞り込みなし・when:7d）→
   同条件に絞り込みキーワードを加えても同じ記事が見つかるか、という
   間接検証で代替する。

LLMは呼ばない。コミットは一切行わない。調査後、本スクリプトと
ワークフローは削除する。
"""
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402
import requests  # noqa: E402

# オーナー指定の例示そのまま（メッセージ本文より逐語）。
FINANCE_KEYWORDS = (
    'crypto OR bitcoin OR ethereum OR "federal reserve" OR inflation OR '
    'tariff OR oil OR "interest rate" OR SEC OR stablecoin'
)


def fetch(q: str, label: str) -> list[dict]:
    url = "https://news.google.com/rss/search"
    params = {"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    resp = requests.get(url, params=params, timeout=20,
                         headers={"User-Agent": collect_news.USER_AGENT})
    print(f"\n=== {label} ===")
    print(f"q={q!r}")
    print(f"実際のリクエストURL: {resp.url}")
    print(f"HTTP status: {resp.status_code}")
    if resp.status_code != 200:
        return []
    root = ET.fromstring(resp.content)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        items.append({"title": title, "pubDate": pub_date})
    print(f"item総数: {len(items)}")
    return items


print("########## 1. 現行クエリ vs 絞り込みクエリ（現在のwhen:24hでの直接比較） ##########")
baseline = fetch("when:24h site:reuters.com", "現行クエリ（絞り込みなし・本番と同一）")
narrowed = fetch(f"when:24h site:reuters.com ({FINANCE_KEYWORDS})", "絞り込みクエリ（オーナー案）")

if baseline:
    reduction = (1 - len(narrowed) / len(baseline)) * 100
    print(f"\n件数比較: 現行={len(baseline)}件 → 絞り込み後={len(narrowed)}件（削減率 {reduction:.0f}%）")

print("\n--- 現行クエリの先頭15件タイトル ---")
for i, it in enumerate(baseline[:15]):
    print(f"  [{i}] {it['title']}")

print("\n--- 絞り込みクエリの全タイトル ---")
for i, it in enumerate(narrowed):
    print(f"  [{i}] {it['title']}")

print("\n\n########## 2. 9/1のイラン・原油記事が絞り込み後も取得できるか（間接検証） ##########")
exist_check = fetch('when:7d site:reuters.com "Strait of Hormuz"',
                     "存在確認（絞り込みなし・固有フレーズ・7日）")
print("\n--- 存在確認結果 ---")
for it in exist_check:
    print(f"  title={it['title']!r} pubDate={it['pubDate']!r}")
found_baseline_style = any("hormuz" in it["title"].lower() for it in exist_check)
print(f"'Hormuz'を含むタイトルが存在確認クエリで見つかったか: {found_baseline_style}")

narrowed_check = fetch(f'when:7d site:reuters.com "Strait of Hormuz" ({FINANCE_KEYWORDS})',
                        "存在確認クエリ＋絞り込みキーワードを追加適用")
print("\n--- 絞り込み適用後の結果 ---")
for it in narrowed_check:
    print(f"  title={it['title']!r} pubDate={it['pubDate']!r}")
found_narrowed_style = any("hormuz" in it["title"].lower() for it in narrowed_check)
print(f"'Hormuz'を含むタイトルが絞り込み後も見つかったか: {found_narrowed_style}")

print("\n\n########## 判定（オーナー指示の明示ルールを適用） ##########")
if found_baseline_style and not found_narrowed_style:
    print("→ 絞り込みで9/1相当の記事が落ちる。オーナー指示によりクエリ絞り込みは見送り、"
          "現行クエリ＋tier2上限15件のまま運用する。")
elif found_baseline_style and found_narrowed_style:
    print("→ 絞り込み後も9/1相当の記事は取得できる。クエリ絞り込みの適用を検討可能"
          "（ただし①の削減率・関連度もあわせて判断）。")
else:
    print("→ 存在確認クエリ自体でHormuz記事が見つからず（Googleのインデックス変動・"
          "時間経過等の可能性）、絞り込みの影響を明確に判定できない。安全側に倒し、"
          "クエリ絞り込みは見送る。")
