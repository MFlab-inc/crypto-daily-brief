"""診断用一時スクリプト（対策2・オーナー指示）。

オーナーの日中高値・安値取得案について、実装前に報告するようオーナーから
明示的に指示された調査。CoinMarketCap APIの実キー（Basicプラン・現行の
CMC_API_KEY）で、OHLCV系エンドポイントに実際にアクセスできるか・
Basicプランで利用可能か・レスポンスにhigh/lowフィールドが含まれるかを
実測する。調査後は削除する（診断専用・恒久コードではない）。
"""
import json
import os
import sys

import requests

API_KEY = os.environ.get("CMC_API_KEY", "")
BASE = "https://pro-api.coinmarketcap.com"
HEADERS = {"X-CMC_PRO_API_KEY": API_KEY, "Accepts": "application/json"}


def call(label: str, url: str, params: dict) -> None:
    print(f"=== {label} ===")
    print(f"GET {url} params={params}")
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
        print(f"HTTP status: {resp.status_code}")
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            print(f"レスポンス本文（JSON以外）: {resp.text[:500]}")
            return
        status = body.get("status", {})
        print(f"status: {json.dumps(status, ensure_ascii=False)}")
        data = body.get("data")
        if data is None:
            print("data: null")
        else:
            # 大きすぎる場合に備え先頭のみ
            s = json.dumps(data, ensure_ascii=False, indent=2)
            print(f"data（先頭1500字）: {s[:1500]}")
    except requests.RequestException as e:
        print(f"リクエスト例外: {e}")
    print()


if not API_KEY:
    print("ERROR: CMC_API_KEY が未設定です。")
    sys.exit(1)

print(f"CMC_API_KEY: 設定あり (length={len(API_KEY)})")
print()

# 1) 現行使用中のquotes/latestにhigh/lowが無いことを再確認（aux指定含む）
call(
    "quotes/latest（現行使用中・aux指定でhigh/lowの有無を確認）",
    f"{BASE}/v1/cryptocurrency/quotes/latest",
    {"symbol": "BTC", "convert": "USD",
     "aux": "num_market_pairs,cmc_rank,date_added,tags,platform,max_supply,"
            "circulating_supply,total_supply,is_active,is_fiat"},
)

# 2) active-day（当日・確定前）OHLCV。ドキュメント上はGrowthプラン以上とされる。
call(
    "ohlcv/latest（当日OHLCV・Growthプラン以上との情報あり）",
    f"{BASE}/v1/cryptocurrency/ohlcv/latest",
    {"symbol": "BTC", "convert": "USD"},
)

# 3) historical daily OHLCV（当日分・Startupプラン以上との情報あり）
call(
    "ohlcv/historical（日次OHLCV・当日分・Startupプラン以上との情報あり）",
    f"{BASE}/v2/cryptocurrency/ohlcv/historical",
    {"symbol": "BTC", "convert": "USD", "time_period": "daily", "count": 1},
)

# 4) 参考: 現在のプラン情報を確認できるエンドポイント（存在すれば）
call(
    "key/info（現行プランの上限・利用実績を確認）",
    f"{BASE}/v1/key/info",
    {},
)
