"""診断用一時スクリプト（FRB speechesフィード調査・オーナー指示）。

8/28の最大材料（ウォーラーFRB議長のジャクソンホール講演。日本時間23時、
利上げに含みを持たせた内容）をパイプラインが取りこぼした事象への対応。
現行のtier1 FRBフィード（https://www.federalreserve.gov/feeds/press_all.xml）
は対象日1件のみ取得しており、講演そのものは含まれていなかったと見られる。

federalreserve.govにspeeches専用のRSSフィードが存在するか調査する。
このサンドボックス環境のegressプロキシはfederalreserve.govを遮断するため
（ローカルでcurl検証済み・CONNECT拒否）、GitHub Actionsランナー上で
実行する必要がある。

collect_news.fetch_rss()をそのまま使う（本番と同じRSS 2.0パース経路で
検証するため。feedparser等の新規依存は追加しない）。

調査後、本スクリプトとワークフローは削除する。
"""
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402

CANDIDATE_URLS = [
    "https://www.federalreserve.gov/feeds/speeches.xml",
    "https://www.federalreserve.gov/feeds/testimony.xml",
    "https://www.federalreserve.gov/feeds/press_monetary.xml",
    "https://www.federalreserve.gov/feeds/press_bcreg.xml",
    "https://www.federalreserve.gov/feeds/press_enforcement.xml",
    "https://www.federalreserve.gov/feeds/press_orders.xml",
    "https://www.federalreserve.gov/feeds/press_other.xml",
    "https://www.federalreserve.gov/feeds/testimony-speeches.xml",
]

print(f"実行時刻(UTC): {datetime.now(timezone.utc).isoformat()}")
print()

print("=== 候補URLをcollect_news.fetch_rss()で直接試行 ===")
for url in CANDIDATE_URLS:
    print(f"--- {url} ---")
    status, items, detail = collect_news.fetch_rss(url)
    print(f"  status={status} 件数={len(items)} detail={detail!r}")
    for it in items[:8]:
        print(f"    - [{it['published_at']}] {it['title']}")
    hits = [it for it in items
            if "jackson hole" in it["title"].lower() or "waller" in it["title"].lower()
            or "jackson hole" in it["summary"].lower() or "waller" in it["summary"].lower()]
    if hits:
        print(f"  *** Jackson Hole / Waller 関連ヒット: {len(hits)}件 ***")
        for h in hits:
            print(f"      [{h['published_at']}] {h['title']} (url={h['url']})")
    print()

print("=== feeds.htm（フィード一覧ページ）を取得し、実際のフィードURLを確認 ===")
try:
    resp = requests.get("https://www.federalreserve.gov/feeds.htm",
                         headers={"User-Agent": collect_news.USER_AGENT}, timeout=15)
    print(f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        import re
        hrefs = sorted(set(re.findall(r'href="([^"]*\.xml)"', resp.text)))
        print(f"見つかった.xmlリンク数: {len(hrefs)}")
        for h in hrefs:
            print(f"  {h}")
except Exception as e:
    print(f"接続失敗: {type(e).__name__}: {e}")
