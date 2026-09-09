#!/usr/bin/env python3
"""調査専用の使い捨て診断スクリプト（非コミット運用・確認後にgit rmする）。
実装変更は一切行わない。9/8対象日でLiquid Network続報（3,400 BTC返還・
CoinDesk報道）が本番の選定ロジックでどう扱われたか、および代替案として
検討中の「公開時刻の近接によるペア救済」を適用した場合にどうなるかを
実データで確認する。outputs/には書き込まない。
"""
import json
import sys
from datetime import date, timedelta

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402
import generate_post as gp  # noqa: E402

KEYWORDS = ["liquid", "whitehat", "white hat", "3,400", "3400", "270m", "$270"]

SOURCES = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Cointelegraph": "https://cointelegraph.com/rss",
}

target = date(2026, 9, 8)
window_start, window_end = collect_news.collection_window_ny(target)
print(f"9/8のNY17:00基準ウィンドウ: {window_start} 〜 {window_end}")

all_raw = []
tier3_candidates = []
for name, url in SOURCES.items():
    status, items, detail = collect_news.fetch_rss(url)
    print(f"\n{name}: status={status} 取得件数={len(items)}")
    if status != "ok":
        continue
    for it in items:
        all_raw.append({**it, "source": name})

    filt_status, cands = collect_news._collect_from_feed(
        name, url, window_start, window_end, tier=3, kind="rss")
    print(f"  9/8ウィンドウ内: {filt_status}")
    tier3_candidates.extend(cands)

print(f"\n生データ内のLiquid関連キーワード一致（ウィンドウ無視・全件走査）:")
for it in all_raw:
    text = f"{it['title']} {it.get('summary', '')}".lower()
    if any(k in text for k in KEYWORDS):
        print(f"  [{it['source']}] {it['title']!r} published_at={it['published_at']!r}")

print(f"\n9/8ウィンドウ内tier3候補数（救済前）: {len(tier3_candidates)}")

# 実際の本番選定ロジックをそのまま使う
threshold = gp.load_pair_overlap_threshold()
print(f"現在のPAIR_OVERLAP_THRESHOLD: {threshold}")


def pub_dt(c):
    return collect_news.parse_pubdate_jst(c.get("published_at", "")) or None


tier3_sorted = sorted(
    [c for c in tier3_candidates if pub_dt(c) is not None],
    key=pub_dt, reverse=True)
print(f"\n=== 9/8 tier3候補（新しい順、全{len(tier3_sorted)}件） ===")
for i, c in enumerate(tier3_sorted, start=1):
    mark = " <-- Liquid関連" if any(
        k in f"{c['title']} {c.get('summary', '')}".lower() for k in KEYWORDS) else ""
    in_top = "TOP15" if i <= gp.TIER3_CANDIDATE_LIMIT else "圏外"
    print(f"  #{i} [{in_top}] [{c['source']}] {c['title'][:70]}{mark}")

# 本番と同じ選定関数（tier3のみ抽出して疑似実行）
selected, stats = gp._select_candidates_for_call_a(tier3_candidates, threshold)
print(f"\n=== 本番選定ロジック適用結果 ===")
print(f"stats: {stats}")
liquid_selected = [c for c in selected if any(
    k in f"{c['title']} {c.get('summary', '')}".lower() for k in KEYWORDS)]
print(f"Liquid関連が選定されたか: {bool(liquid_selected)}")
for c in liquid_selected:
    print(f"  選定: [{c['source']}] {c['title']}")

# 時刻近接によるペア救済（検討中の代替案）を模擬適用
print(f"\n=== 代替案: 公開時刻の近接によるペア救済を模擬適用 ===")
for delta_min in (60, 120, 180, 360):
    top_n = tier3_sorted[:gp.TIER3_CANDIDATE_LIMIT]
    top_ids = {id(c) for c in top_n}
    rescued = []
    for i, a in enumerate(tier3_sorted):
        if id(a) in top_ids:
            continue
        a_dt = pub_dt(a)
        for b in tier3_sorted:
            if b is a or b.get("source") == a.get("source"):
                continue
            b_dt = pub_dt(b)
            gap = abs((a_dt - b_dt).total_seconds()) / 60
            if gap <= delta_min:
                rescued.append(a)
                break
    liquid_rescued = [c for c in rescued if any(
        k in f"{c['title']} {c.get('summary', '')}".lower() for k in KEYWORDS)]
    print(f"Δt<={delta_min}分: 救済対象{len(rescued)}件中、Liquid関連救済="
          f"{bool(liquid_rescued)}（救済総数が多い場合は誤検知過多の参考値）")
