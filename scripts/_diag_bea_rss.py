"""診断用一時スクリプト（BEA RSS到達性調査・オーナー指示item#4）。

bea.gov（米商務省経済分析局）のニュースリリースRSSフィードへの到達性を
実測する。ローカルサンドボックス環境ではapps.bea.gov/www.bea.govへの
egressがプロキシでブロックされ確認できなかったため、GH Actionsランナー
（本番と同じネットワーク環境）から実際に到達性・フィード構造を確認する。
調査後、本スクリプトとワークフローは削除する。
"""
import sys

import requests

UA = {"User-Agent": "crypto-daily-brief/1.0"}
CANDIDATES = [
    "https://apps.bea.gov/rss/rss.xml",
    "https://www.bea.gov/rss.xml",
]

for url in CANDIDATES:
    print(f"=== {url} ===")
    try:
        r = requests.get(url, headers=UA, timeout=20)
        print(f"HTTP {r.status_code}")
        print(f"Content-Type: {r.headers.get('Content-Type')}")
        print(f"Content-Length(実測): {len(r.content)} bytes")
        if r.status_code == 200:
            text = r.text
            print("--- 冒頭2000文字 ---")
            print(text[:2000])
            print("--- item/pubDate/title件数 ---")
            print(f"<item> count: {text.count('<item>')}")
            print(f"<pubDate> count: {text.count('<pubDate>')}")
            print("--- PCE/GDP/Personal Income関連タイトルを含むか ---")
            for kw in ("Personal Income", "PCE", "Gross Domestic Product", "GDP"):
                print(f"  '{kw}' in text: {kw in text}")
    except Exception as e:  # noqa: BLE001
        print(f"[error] {type(e).__name__}: {e}")
    print()

sys.exit(0)
