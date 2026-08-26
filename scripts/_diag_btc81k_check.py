"""診断用一時スクリプト（v1.39フォローアップ）。

オーナー指摘: 8/25にBTCが一時$81,000台（5/15以来約3か月ぶり高値）を
つけた事実報道が、tier3候補プールのどこに位置し、LIMIT=15で候補集合に
入ったか・CoinDesk側の同一事実報道が存在し候補に入ったかを確認する。

collect_news.collect_news() を実行して2026-08-25の生のtier3候補
（件数上限適用前）を取得し、
1. 全tier3候補を公開日時の新しい順に並べ、LIMIT=15の内外を明示
2. $81,000関連キーワードでの全文検索（title+summary）
を出力する。調査後は削除する（診断専用・恒久コードではない）。
"""
import re
import sys
from datetime import date

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402
import generate_post  # noqa: E402

TARGET = date(2026, 8, 25)

print("=== collect_news.collect_news(2026-08-25) を実行 ===")
result = collect_news.collect_news(TARGET)
candidates = result["candidates"]
tier3 = [c for c in candidates if c.get("tier") == 3]
print(f"tier3候補総数: {len(tier3)}")
print()

print("=== tier3候補: 公開日時の新しい順（LIMIT=15の内外を明示） ===")


from datetime import datetime  # noqa: E402
tier3_sorted = sorted(
    tier3,
    key=lambda c: collect_news.parse_pubdate_jst(c.get("published_at", "")) or datetime.min.replace(tzinfo=collect_news.JST),
    reverse=True,
)

LIMIT = generate_post.TIER3_CANDIDATE_LIMIT
print(f"TIER3_CANDIDATE_LIMIT = {LIMIT}")
for i, c in enumerate(tier3_sorted, 1):
    marker = "IN" if i <= LIMIT else "OUT"
    print(f"{i:2d}. [{marker}] [{c.get('source')}] {c.get('published_at')}")
    print(f"     {c.get('title')}")
print()

print("=== キーワード検索: 81,000 / 81k / three-month / 3-month / since may / highest since ===")
pattern = re.compile(r"81,?000|81k|three.?month|since may|3-month|highest since|81,2|\\$81", re.IGNORECASE)
hits = []
for c in tier3:
    text = (c.get("title", "") or "") + " " + (c.get("summary", "") or "")
    if pattern.search(text):
        hits.append(c)

if not hits:
    print("キーワード一致する候補は tier3 に見つかりませんでした。")
else:
    for c in hits:
        rank = tier3_sorted.index(c) + 1
        print(f"[{c.get('source')}] rank={rank} (LIMIT={LIMIT}内={'Yes' if rank <= LIMIT else 'No'})")
        print(f"  title: {c.get('title')}")
        print(f"  pubDate: {c.get('published_at')}")
        print(f"  url: {c.get('url')}")
        print(f"  summary: {(c.get('summary') or '')[:500]}")
        print()

print("=== Cointelegraph『Bitcoin slips from $80K...』の実summaryを直接確認 ===")
for c in tier3:
    if c.get("source") == "Cointelegraph" and "slips from $80" in (c.get("title") or ""):
        rank = tier3_sorted.index(c) + 1
        print(f"rank={rank} (LIMIT={LIMIT}内={'Yes' if rank <= LIMIT else 'No'})")
        print(f"title: {c.get('title')}")
        print(f"pubDate: {c.get('published_at')}")
        print(f"url: {c.get('url')}")
        print(f"summary (全文): {c.get('summary')}")
