#!/usr/bin/env python3
"""調査専用の使い捨て診断スクリプト（非コミット運用・確認後にgit rmする）。
実装変更は一切行わない。9/7のLiquid Network（Blockstreamのビットコイン
サイドチェーン）流出事案の取りこぼしを調査するため、CoinDesk・
Cointelegraphの実RSSフィードを取得し、該当記事の有無・pubDate・
9/7のNY 17:00基準ウィンドウとの関係を確認する。outputs/には書き込まない。
"""
import json
import sys
from datetime import date

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402

KEYWORDS = ["liquid", "blockstream", "320 million", "$320", "sidechain", "4,000 btc", "4000 btc"]

SOURCES = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
}


def matches(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return any(k in text for k in KEYWORDS)


target = date(2026, 9, 7)
window_start, window_end = collect_news.collection_window_ny(target)
print(f"9/7のNY17:00基準ウィンドウ: {window_start} 〜 {window_end}")
print(f"RAW_ITEM_LIMIT = {collect_news.RAW_ITEM_LIMIT}")
print()

for name, url in SOURCES.items():
    print(f"===== {name} ({url}) =====")
    status, items, detail = collect_news.fetch_rss(url)
    print(f"status={status} detail={detail!r} 取得件数={len(items)}")
    if not items:
        continue
    pub_dates = [it.get("published_at", "") for it in items if it.get("published_at")]
    print(f"先頭item pubDate: {items[0].get('published_at')!r}")
    print(f"末尾item pubDate: {items[-1].get('published_at')!r}")

    found = [it for it in items if matches(it)]
    print(f"キーワード一致件数: {len(found)}")
    for it in found:
        print(json.dumps({
            "title": it.get("title"), "published_at": it.get("published_at"),
            "url": it.get("url"), "summary": (it.get("summary") or "")[:300],
        }, ensure_ascii=False, indent=2))

    # 9/7ウィンドウでのフィルタ結果（本番と同じ関数を使用。ただし取得タイミングは
    # 本番の9/7実行時刻とは異なるため参考値）。
    filt_status, cands = collect_news._collect_from_feed(
        name, url, window_start, window_end, tier=3, kind="rss")
    print(f"9/7ウィンドウでの{name}候補数（本スクリプト実行時点・参考値）: {filt_status}")
    for c in cands:
        if matches(c):
            print("  [ウィンドウ内一致]", json.dumps(c, ensure_ascii=False))
    print()
