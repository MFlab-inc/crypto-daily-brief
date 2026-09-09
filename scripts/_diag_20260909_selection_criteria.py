#!/usr/bin/env python3
"""調査専用の使い捨て診断スクリプト（非コミット運用・確認後にgit rmする）。
実装変更は一切行わない。tier3選定基準の見直し案3つ（①同一媒体内の掲載順・
②金額表現の規模・③公開時刻の近接によるペア検出）を検証する。
outputs/には書き込まない。

9/7の実データ（news_candidates.jsonは非コミットのため復元不可）の代わりに、
本日時点のCoinDesk・Cointelegraphの実フィードを使い、①掲載順がpubDate順と
一致するか、②金額表現の抽出可否・カバレッジ、③時刻近接ペアの誤検知率、を
確認する。9/7のLiquid Network関連3件（実測済み・前回調査で確認）の
タイムスタンプは既知の事実として埋め込み、時刻近接ルールを適用した場合の
挙動を分析する。
"""
import json
import re
import sys
from datetime import date

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402
import generate_post as gp  # noqa: E402

SOURCES = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
}

AMOUNT_RE = re.compile(
    r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|billion|trillion|m|b|k|mln|bn)?\b", re.IGNORECASE)

_MULT = {
    "": 1, "k": 1_000,
    "m": 1_000_000, "million": 1_000_000, "mln": 1_000_000,
    "b": 1_000_000_000, "billion": 1_000_000_000, "bn": 1_000_000_000,
    "trillion": 1_000_000_000_000,
}


def extract_max_amount_usd(text: str) -> float | None:
    best = None
    for num, unit in AMOUNT_RE.findall(text or ""):
        try:
            val = float(num.replace(",", "")) * _MULT.get(unit.lower(), 1)
        except ValueError:
            continue
        if best is None or val > best:
            best = val
    return best


print("===== ①RSSフィード順とpubDate順の一致確認 =====")
raw_items = {}
for name, url in SOURCES.items():
    status, items, detail = collect_news.fetch_rss(url)
    raw_items[name] = items
    print(f"\n{name}: status={status} 件数={len(items)}")
    if status != "ok":
        continue
    dts = [collect_news.parse_pubdate_jst(it["published_at"]) for it in items]
    dts = [d for d in dts if d is not None]
    is_sorted_desc = all(dts[i] >= dts[i + 1] for i in range(len(dts) - 1))
    print(f"  フィード順=pubDate降順と完全一致: {is_sorted_desc}")
    if not is_sorted_desc:
        for i in range(len(dts) - 1):
            if dts[i] < dts[i + 1]:
                print(f"  逆転箇所: item[{i}]={dts[i]} < item[{i+1}]={dts[i+1]}")

print("\n===== ②金額表現の抽出可否・カバレッジ（tier3=CoinDesk+Cointelegraph） =====")
all_tier3 = []
for name, items in raw_items.items():
    for it in items:
        all_tier3.append({**it, "source": name})
with_amount = 0
for it in all_tier3:
    amt = extract_max_amount_usd(f"{it['title']} {it.get('summary', '')}")
    if amt is not None:
        with_amount += 1
        if amt >= 50_000_000:
            print(f"  [{it['source']}] ${amt:,.0f}  {it['title'][:90]}")
print(f"金額表現ありの記事: {with_amount}/{len(all_tier3)} 件"
      f"（{with_amount/len(all_tier3)*100:.0f}%）")

print("\n===== ③公開時刻の近接ペア検出・誤検知率（CoinDesk×Cointelegraph、本日データ） =====")
cd_items = raw_items.get("CoinDesk", [])
ct_items = raw_items.get("Cointelegraph", [])
for delta_min in (30, 60, 120, 180, 360):
    pairs = []
    for a in cd_items:
        ta = collect_news.parse_pubdate_jst(a["published_at"])
        if ta is None:
            continue
        for b in ct_items:
            tb = collect_news.parse_pubdate_jst(b["published_at"])
            if tb is None:
                continue
            gap = abs((ta - tb).total_seconds()) / 60
            if gap <= delta_min:
                pairs.append((gap, a["title"], b["title"]))
    print(f"\nΔt <= {delta_min}分: {len(pairs)}組")
    for gap, ta, tb in sorted(pairs)[:8]:
        print(f"  差{gap:.0f}分 | CD: {ta[:60]} | CT: {tb[:60]}")

print("\n===== 9/7 Liquid Network関連（既知の実測値）に時刻近接ルールを適用した場合 =====")
known = [
    ("CoinDesk", "Bitcoin network used by exchanges hit by $320 million exploit...", "2026-09-07T03:43:12+00:00"),
    ("Cointelegraph", "'White hats' take 4000 BTC from Liquid...(Hodler's Digest)", "2026-09-07T00:05:02+00:00"),
    ("Cointelegraph", "Bitcoin sidechain Liquid pauses after purported 'white hats'...", "2026-09-07T05:40:05+00:00"),
]
from datetime import datetime
times = [(s, t, datetime.fromisoformat(ts)) for s, t, ts in known]
for i in range(len(times)):
    for j in range(i + 1, len(times)):
        s1, t1, d1 = times[i]
        s2, t2, d2 = times[j]
        gap_min = abs((d1 - d2).total_seconds()) / 60
        cross_source = s1 != s2
        print(f"  {s1} <-> {s2} (異なる媒体={cross_source}): 差{gap_min:.0f}分")
