"""診断用一時スクリプト（対策2フォローアップ・オーナー指示）。

CMC有料プランへのアップグレードを見送り、無料・認証不要で日中高値・
安値（OHLCV）を取得できる代替手段を調査する。対象: CoinGecko（参考値
限定用途としての整合性検討）・Binance公開API・Coinbase Exchange公開
API・Kraken/Bitstamp（ボーナス調査）。BTC・ETH・BNBの3銘柄で到達性・
レスポンス構造・タイムスタンプ形式（NY 17:00区切りの自前集計が可能か）
・レート制限（ヘッダーで確認できる範囲）を実測する。調査後は削除する。
"""
import json
import sys

import requests

TIMEOUT = 20
UA = "crypto-daily-brief-diag/1.0"


def call(label: str, method_url_params) -> dict | None:
    print(f"=== {label} ===")
    url, params = method_url_params
    print(f"GET {url} params={params}")
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT, headers={"User-Agent": UA})
        print(f"HTTP status: {resp.status_code}")
        rl_headers = {k: v for k, v in resp.headers.items()
                      if "ratelimit" in k.lower() or "rate-limit" in k.lower()
                      or k.lower().startswith("x-mbx") or k.lower().startswith("cb-")
                      or k.lower() == "retry-after"}
        if rl_headers:
            print(f"レート制限関連ヘッダー: {json.dumps(rl_headers, ensure_ascii=False)}")
        if resp.status_code != 200:
            print(f"本文（先頭300字）: {resp.text[:300]}")
            print()
            return None
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            print(f"JSON以外の応答（先頭300字）: {resp.text[:300]}")
            print()
            return None
        s = json.dumps(body, ensure_ascii=False)
        print(f"レスポンス（先頭800字）: {s[:800]}")
        print()
        return body
    except requests.RequestException as e:
        print(f"リクエスト例外: {e}")
        print()
        return None


print("########## CoinGecko（無料API・APIキー無しの公開エンドポイント） ##########")
_CG_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin"}
for sym, cg_id in _CG_IDS.items():
    call(f"CoinGecko OHLC 24h（{sym}）",
         (f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc", {"vs_currency": "usd", "days": "1"}))

print("########## Binance 公開API（認証不要） ##########")
_BINANCE_SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT"}
for sym, pair in _BINANCE_SYMBOLS.items():
    call(f"Binance klines 1h×26本（{sym}）",
         ("https://api.binance.com/api/v3/klines",
          {"symbol": pair, "interval": "1h", "limit": 26}))

print("########## Coinbase Exchange 公開API（認証不要） ##########")
_COINBASE_PRODUCTS = {"BTC": "BTC-USD", "ETH": "ETH-USD", "BNB": "BNB-USD"}
for sym, product in _COINBASE_PRODUCTS.items():
    call(f"Coinbase Exchange candles 1h（{sym}・BNBは非上場の可能性あり）",
         (f"https://api.exchange.coinbase.com/products/{product}/candles",
          {"granularity": 3600}))

print("########## ボーナス調査: Kraken 公開API（認証不要） ##########")
_KRAKEN_PAIRS = {"BTC": "XBTUSD", "ETH": "ETHUSD", "BNB": "BNBUSD"}
for sym, pair in _KRAKEN_PAIRS.items():
    call(f"Kraken OHLC 1h（{sym}）",
         ("https://api.kraken.com/0/public/OHLC", {"pair": pair, "interval": 60}))

print("########## ボーナス調査: Bitstamp 公開API（認証不要・オーナー引用のBTC $81,255の出典） ##########")
_BITSTAMP_PAIRS = {"BTC": "btcusd", "ETH": "ethusd", "BNB": "bnbusd"}
for sym, pair in _BITSTAMP_PAIRS.items():
    call(f"Bitstamp OHLC 1h（{sym}）",
         (f"https://www.bitstamp.net/api/v2/ohlc/{pair}/", {"step": 3600, "limit": 26}))

sys.exit(0)
