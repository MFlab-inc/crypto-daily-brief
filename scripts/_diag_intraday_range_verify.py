"""診断用一時スクリプト（v1.41実データ検証・オーナー指示）。

8/25データで日中高値・安値の実装を検証する。
1) NY 17:00区切りの窓（8/25 06:00 JST〜8/26 06:00 JSTになるか）
2) BTCのhighが$81,255前後になるか（Coinbase・Bitstamp両方を独立に取得し比較）
3) ETH・BNBも取得できるか
4) レート制限関連ヘッダーの確認
調査後は削除する（診断専用・恒久コードではない）。
"""
import json
import sys
from datetime import date, timezone as _tz

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402
import fetch_data  # noqa: E402
import requests  # noqa: E402

TARGET = date(2026, 8, 25)
window_start, window_end = collect_news.collection_window_ny(TARGET)

print("=== NY 17:00区切りの窓 ===")
print(f"window_start (NY): {window_start.isoformat()}")
print(f"window_end   (NY): {window_end.isoformat()}")
print(f"window_start (JST): {window_start.astimezone(collect_news.JST).isoformat()}")
print(f"window_end   (JST): {window_end.astimezone(collect_news.JST).isoformat()}")
print()


def fetch_source_independently(url: str, params: dict, parse_fn, label: str):
    try:
        raw = fetch_data.get_json(url, params=params)
        candles = parse_fn(raw)
        rng = fetch_data._range_from_candles(candles, window_start, window_end)
        in_window = sum(1 for c in candles if window_start.timestamp() <= c["time"] < window_end.timestamp())
        print(f"{label}: 取得件数={len(candles)} 窓内件数={in_window}")
        print(f"{label}: high/low(生値) = {rng}")
        if rng:
            print(f"{label}: high/low(整形) = {fetch_data.fmt_usd_int(rng[0])} / {fetch_data.fmt_usd_int(rng[1])}")
        return rng
    except Exception as e:  # noqa: BLE001
        print(f"{label}: 例外 {e}")
        return None


for sym, (cb_product, bs_pair, representative) in fetch_data.INTRADAY_SYMBOLS.items():
    print(f"########## {sym}（representative={representative}） ##########")

    cb_rng = fetch_source_independently(
        f"https://api.exchange.coinbase.com/products/{cb_product}/candles",
        {"granularity": 3600,
         "start": window_start.astimezone(_tz.utc).isoformat(),
         "end": window_end.astimezone(_tz.utc).isoformat()},
        fetch_data._parse_coinbase_candles, "Coinbase単独")

    bs_rng = fetch_source_independently(
        f"https://www.bitstamp.net/api/v2/ohlc/{bs_pair}/",
        {"step": 3600, "limit": 200,
         "start": int(window_start.timestamp()), "end": int(window_end.timestamp())},
        fetch_data._parse_bitstamp_candles, "Bitstamp単独")

    if cb_rng and bs_rng:
        print(f"取引所間の差: high差={abs(cb_rng[0] - bs_rng[0]):.2f} low差={abs(cb_rng[1] - bs_rng[1]):.2f}")

    result = fetch_data.fetch_intraday_range(sym, cb_product, bs_pair, window_start, window_end)
    print(f"fetch_intraday_range()の返り値（実装が実際に使う値）: {json.dumps(result, ensure_ascii=False)}")
    print()

print("=== レート制限関連ヘッダーの確認（Coinbase BTC-USD candlesへ直接アクセス） ===")
resp = requests.get("https://api.exchange.coinbase.com/products/BTC-USD/candles",
                     params={"granularity": 3600}, timeout=20)
print(f"status: {resp.status_code}")
for k, v in resp.headers.items():
    if "rate" in k.lower() or k.lower().startswith("cb-"):
        print(f"  {k}: {v}")
print()

print("=== レート制限関連ヘッダーの確認（Bitstamp BTC/USD OHLCへ直接アクセス） ===")
resp2 = requests.get("https://www.bitstamp.net/api/v2/ohlc/btcusd/",
                      params={"step": 3600, "limit": 26}, timeout=20)
print(f"status: {resp2.status_code}")
for k, v in resp2.headers.items():
    if "rate" in k.lower():
        print(f"  {k}: {v}")
