"""診断用一時スクリプト（経済カレンダー取得可否調査・オーナー指示）。

MFlab-inc/EA-Risk-Monitor の scripts/lib/calendar.js が使う
Forex Factory 経済カレンダーJSONフィード（nfs.faireconomy.media）の
到達性・データ形状・過去日カバレッジを確認する。このサンドボックス
環境のegressプロキシは多くの外部サイトを遮断するため、GitHub Actions
ランナー上で実行する必要がある。

確認項目:
1. thisweek/nextweekフィードの到達性・件数
2. 8/28（ジャクソンホール講演当日）・8/26（PCE発表日）の該当イベントが
   含まれているか（週境界をまたいだ過去日がthisweekフィードに残るか）
3. レスポンスの実フィールド形状（date/country/impact/title等）

調査後、本スクリプトとワークフローは削除する。
"""
import json
from datetime import datetime, timezone

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
URLS = {
    "thisweek": "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "nextweek": "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
    "lastweek（calendar.jsは使っていないが週境界カバレッジ確認のため試行）":
        "https://nfs.faireconomy.media/ff_calendar_lastweek.json",
}

print(f"実行時刻(UTC): {datetime.now(timezone.utc).isoformat()}")
print()

all_events = []
for label, url in URLS.items():
    print(f"--- {label}: {url} ---")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"  接続失敗: {type(e).__name__}: {e}")
        continue
    print(f"  HTTP {resp.status_code} (content-length={len(resp.content)})")
    if resp.status_code != 200:
        print(f"  body先頭200字: {resp.text[:200]!r}")
        continue
    try:
        data = resp.json()
    except Exception as e:
        print(f"  JSON解析失敗: {e}")
        continue
    print(f"  件数={len(data)}")
    if data:
        print(f"  1件目の生フィールド: {json.dumps(data[0], ensure_ascii=False)}")
        all_events.extend(data)
    print()

print("=== 実測フィールドのimpact値の種類（想定: High/Medium/Low/Holiday等） ===")
impacts = sorted(set(e.get("impact") for e in all_events))
print(impacts)
print()

print("=== 実測フィールドのcountry値の種類 ===")
countries = sorted(set(e.get("country") for e in all_events))
print(countries)
print()

print("=== 8/28（JST）ジャクソンホール講演・8/26（JST）PCE発表が含まれるか ===")
for e in all_events:
    date_str = str(e.get("date", ""))
    title = str(e.get("title", ""))
    if ("2026-08-2" in date_str) and (
        "jackson" in title.lower() or "pce" in title.lower()
        or "personal consumption" in title.lower() or "waller" in title.lower()
        or "warsh" in title.lower()
    ):
        print(f"  HIT: {json.dumps(e, ensure_ascii=False)}")

print()
print("=== 8/26〜8/29の全イベント一覧（USD/JPYのみ・日付範囲確認用） ===")
for e in sorted(all_events, key=lambda x: str(x.get("date", ""))):
    date_str = str(e.get("date", ""))
    if date_str.startswith("2026-08-2") and e.get("country") in ("USD", "JPY"):
        print(f"  [{date_str}] {e.get('country')} impact={e.get('impact')} {e.get('title')}")
