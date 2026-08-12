#!/usr/bin/env python3
"""fetch_data.py — 日次データ取得 → daily_data.json 生成（LLM不使用）

統合運用基準 §1/§9 準拠:
- 対象日 = 実行時 Asia/Tokyo の前日。日付・曜日はプログラムで算出。
- 取得不能値は推測せず「未確認」。
- 変化率ラベルは「24時間比」(レンダラー側見出し)。数値は ±N.NN% 形式。

取得元（全て実ログ・実装から確認済みの正本）:
- CoinMarketCap  /v1/cryptocurrency/quotes/latest?symbol=BTC,ETH,BNB&convert=USD
                 /v1/global-metrics/quotes/latest
                 /v3/fear-and-greed/latest        (Alternative.me は使用禁止)
- GeckoTerminal  Base 2プール (DefiLlamaはBase Uniswap V3の追跡を停止)
- DefiLlama      api.llama.fi/v2/chains, /v2/historicalChainTvl/Base,
                 /overview/dexs/base, stablecoins.llama.fi/stablecoins
- ExchangeRate-API open.er-api.com/v6/latest/USD
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

JST = timezone(timedelta(hours=9))
UA = {"User-Agent": "crypto-daily-brief/1.0"}
TIMEOUT = 20
UNCONFIRMED = "未確認"

# GeckoTerminal fallback pool addresses — eth_usdc_apr.html より (BaseScan検証済 2026-07)
GECKO_POOLS = {
    "0.05": "0xd0b53d9277642d899df5c87a3966a349a798f224",
    "0.3": "0x6c561b446416e1a00e8e93e221854d6ea4171372",
}
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


def get_json(url: str, headers: dict | None = None, params: dict | None = None):
    r = requests.get(url, headers={**UA, **(headers or {})}, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


# ---------- formatting helpers (実サンプル 8/9・8/10 準拠) ----------

def fmt_usd_int(v: float) -> str:
    return f"${round(v):,}"


def fmt_jpy_man(usd: float, fx: float) -> str:
    man = usd * fx / 1e4
    if man >= 100:
        return f"約{man:,.1f}万円"
    if man >= 10:
        return f"約{man:.1f}万円"
    return f"約{man:.2f}万円"


def fmt_change(v: float) -> str:
    return f"{v:+.2f}%"


def fmt_cap_usd(v: float) -> str:      # $2.185兆
    return f"${v / 1e12:.3f}兆"


def fmt_cap_jpy(v_usd: float, fx: float) -> str:  # ¥345.0兆
    return f"¥{v_usd * fx / 1e12:.1f}兆"


def fmt_vol_usd(v: float) -> str:      # $528.2億
    return f"${v / 1e8:.1f}億"


def fmt_vol_jpy(v_usd: float, fx: float) -> str:  # ¥8.34兆 / ¥469億
    yen = v_usd * fx
    if yen >= 1e12:
        return f"¥{yen / 1e12:.2f}兆"
    return f"¥{yen / 1e8:,.0f}億"


def fmt_tvl_usd(v: float) -> str:      # $46.20億
    return f"${v / 1e8:.2f}億"


def fmt_dex_usd(v: float) -> str:      # $2.971億
    return f"${v / 1e8:.3f}億"


def fmt_m(v: float) -> str:            # $10.19M
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    return f"${v / 1e6:.2f}M"


# ---------- fetchers（各関数は失敗時 None を返し、呼び出し側で「未確認」化） ----------

def fetch_cmc(api_key: str) -> dict:
    """CMCの3エンドポイントを個別に取得する（v1.2 承認3）。

    以前は1関数で3本を直列に呼んでいたため、1本の失敗（例: プラン外や一時的な
    エラー）が価格・時価総額まで巻き添えにして全項目「未確認」になっていた。
    区画ごとに try/except し、取れた区画だけを返す。取れなかった区画はキーを
    作らず、呼び出し側で「未確認」に落とす（推測で埋めない方針は不変）。
    """
    h = {"X-CMC_PRO_API_KEY": api_key}
    base = "https://pro-api.coinmarketcap.com"
    out: dict = {}

    try:
        q = get_json(f"{base}/v1/cryptocurrency/quotes/latest", h,
                     {"symbol": "BTC,ETH,BNB", "convert": "USD"})["data"]
        for sym in ("BTC", "ETH", "BNB"):
            u = q[sym]["quote"]["USD"]
            out[sym] = {"price": float(u["price"]), "chg": float(u["percent_change_24h"])}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] cmc quotes/latest: {e}", file=sys.stderr)

    try:
        g = get_json(f"{base}/v1/global-metrics/quotes/latest", h)["data"]
        out["global"] = {
            "mcap": float(g["quote"]["USD"]["total_market_cap"]),
            "vol": float(g["quote"]["USD"]["total_volume_24h"]),
            "btc_d": float(g["btc_dominance"]),
            "eth_d": float(g["eth_dominance"]),
        }
    except Exception as e:  # noqa: BLE001
        print(f"[warn] cmc global-metrics: {e}", file=sys.stderr)

    try:
        # 取得元は変更しない（Alternative.me は使用禁止 — 統合運用基準）。
        fg = get_json(f"{base}/v3/fear-and-greed/latest", h)["data"]
        out["fg"] = {"value": int(fg["value"]), "label": str(fg["value_classification"])}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] cmc fear-and-greed: {e}", file=sys.stderr)

    return out


def fetch_fx() -> float | None:
    j = get_json("https://open.er-api.com/v6/latest/USD")
    if j.get("result") != "success":
        return None
    return float(j["rates"]["JPY"])


def fetch_gecko_pool(addr: str, fee_pct: float) -> dict | None:
    j = get_json(f"https://api.geckoterminal.com/api/v2/networks/base/pools/{addr}")
    a = j["data"]["attributes"]
    vol = float(a["volume_usd"]["h24"])
    tvl = float(a["reserve_in_usd"])
    apr = vol * (fee_pct / 100) / tvl * 365 * 100  # eth_usdc_apr.html で検証済みの算式
    return {"apr": apr, "tvl": tvl, "vol": vol}


def fetch_base_tvl() -> float | None:
    for c in get_json("https://api.llama.fi/v2/chains"):
        if str(c.get("name", "")).lower() == "base":
            return float(c["tvl"])
    return None


def fetch_base_tvl_change() -> float | None:
    hist = get_json("https://api.llama.fi/v2/historicalChainTvl/Base")
    if len(hist) < 2:
        return None
    prev, last = hist[-2]["tvl"], hist[-1]["tvl"]
    return (last - prev) / prev * 100 if prev else None


def fetch_base_dex_volume() -> float | None:
    j = get_json("https://api.llama.fi/overview/dexs/base",
                 params={"excludeTotalDataChart": "true",
                         "excludeTotalDataChartBreakdown": "true"})
    if isinstance(j.get("total24h"), (int, float)):
        return float(j["total24h"])
    protos = j.get("protocols") or []
    vals = [p.get("total24h") for p in protos if isinstance(p.get("total24h"), (int, float))]
    return float(sum(vals)) if vals else None


def fetch_usdc_dominance_base() -> float | None:
    """Base上ステーブルコイン総流通量を分母にした #USDC 比率（基準 §3.2）。"""
    j = get_json("https://stablecoins.llama.fi/stablecoins",
                 params={"includePrices": "false"})
    total = usdc = 0.0
    for a in j.get("peggedAssets", []):
        cur = (a.get("chainCirculating", {}).get("Base", {})
               .get("current", {}) or {})
        v = cur.get("peggedUSD")
        if isinstance(v, (int, float)):
            total += v
            if a.get("symbol") == "USDC":
                usdc += v
    if total <= 0:
        return None
    return usdc / total * 100


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001 — 取得失敗は「未確認」へ落とす設計
        print(f"[warn] {fn.__name__}: {e}", file=sys.stderr)
        return None


# ---------- main ----------

def main() -> int:
    api_key = os.environ.get("CMC_API_KEY", "")
    now = datetime.now(JST)
    run_id = now.strftime("%Y%m%dT%H%M%S_JST")
    target = (now - timedelta(days=1)).date()
    weekday = WEEKDAYS_JP[target.weekday()]

    out_dir = Path(os.environ.get("OUT_DIR", f"outputs/{target.isoformat()}"))
    out_dir.mkdir(parents=True, exist_ok=True)

    t_start = datetime.now(JST)
    cmc = safe(fetch_cmc, api_key) if api_key else None
    fx = safe(fetch_fx)
    g005 = safe(fetch_gecko_pool, GECKO_POOLS["0.05"], 0.05)
    g03 = safe(fetch_gecko_pool, GECKO_POOLS["0.3"], 0.3)
    b_tvl = safe(fetch_base_tvl)
    b_chg = safe(fetch_base_tvl_change)
    b_dex = safe(fetch_base_dex_volume)
    usdc_d = safe(fetch_usdc_dominance_base)
    t_end = datetime.now(JST)

    # v1.2 承認3: cmc は区画ごとに欠損しうるため、区画単位で参照する。
    quotes = cmc or {}
    g = quotes.get("global")
    fg = quotes.get("fg")

    def asset(sym: str, label: str) -> dict:
        d = quotes.get(sym)
        if d and fx:
            direction = "up" if d["chg"] > 0 else "down" if d["chg"] < 0 else "neutral"
            return {"asset": label, "usd": fmt_usd_int(d["price"]),
                    "jpy": fmt_jpy_man(d["price"], fx),
                    "change_24h": fmt_change(d["chg"]), "direction": direction}
        return {"asset": label, "usd": UNCONFIRMED, "jpy": "",
                "change_24h": UNCONFIRMED, "direction": "neutral"}

    eth = quotes.get("ETH")
    eth_dir = "neutral"
    if eth:
        eth_dir = "up" if eth["chg"] > 0 else "down" if eth["chg"] < 0 else "neutral"
    lp_msg = {  # 統合運用基準 §4 の決定的ルール（LLM不使用）
        "up": "#ETHが上昇中。#USDC偏り・上限側レンジ外・反落耐性を確認",
        "down": "#ETHが下落中。#ETH偏り・下限側レンジ外・下落耐性を確認",
        "neutral": "#ETHの方向を確認し、#USDC偏り・レンジ外・価格変動耐性を確認",
    }[eth_dir]

    def pool(name: str, g: dict | None) -> dict:
        if g:
            return {"name": name, "apr": f"{g['apr']:.2f}%",
                    "tvl": fmt_m(g["tvl"]), "volume_24h": fmt_m(g["vol"])}
        return {"name": name, "apr": UNCONFIRMED, "tvl": UNCONFIRMED,
                "volume_24h": UNCONFIRMED}

    start_s = t_start.strftime("%Y-%m-%d %H:%M")
    end_s = t_end.strftime("%H:%M")
    retrieved_at = (f"{start_s} JST" if start_s.endswith(end_s)
                    else f"{start_s}–{end_s} JST")

    sources = ["CoinMarketCap API" if cmc else None,
               "GeckoTerminal" if (g005 or g03) else None,
               "DefiLlama" if (b_tvl or b_dex or usdc_d is not None) else None,
               "ExchangeRate-API" if fx else None]
    data = {
        "target_date_jst": target.isoformat(),
        "weekday_jp": weekday,
        "date_title": f"{target.year}年{target.month}月{target.day}日（{weekday}）暗号通貨・DEX市場概況",
        "summary": os.environ.get(
            "SUBTITLE_OVERRIDE",
            "（シャドー運用中：ヘッドラインはフェーズ2で生成）"),
        # 画像内の通貨表記は # を付けない（v1.1 B-3）。X投稿本文の # 付与は維持。
        "assets": [asset("BTC", "BTC"), asset("ETH", "ETH"), asset("BNB", "BNB")],
        "market": {
            "fear_greed": (fg if fg else {"value": 0, "label": UNCONFIRMED}),
            "market_cap": fmt_cap_usd(g["mcap"]) if g else UNCONFIRMED,
            # 丸括弧はレンダラー側で付与する。ここで括ると二重括弧になる（v1.1 A-1）。
            "market_cap_jpy": fmt_cap_jpy(g["mcap"], fx) if g and fx else "",
            "volume_24h": fmt_vol_usd(g["vol"]) if g else UNCONFIRMED,
            "volume_24h_jpy": fmt_vol_jpy(g["vol"], fx) if g and fx else "",
            "btc_dominance": f"{g['btc_d']:.2f}%" if g else UNCONFIRMED,
            "eth_dominance": f"{g['eth_d']:.2f}%" if g else UNCONFIRMED,
        },
        "base": {
            "tvl": fmt_tvl_usd(b_tvl) if b_tvl else UNCONFIRMED,
            "tvl_jpy": fmt_vol_jpy(b_tvl, fx) if b_tvl and fx else "",
            "tvl_change": fmt_change(b_chg) if b_chg is not None else UNCONFIRMED,
            "tvl_direction": ("up" if b_chg > 0 else "down" if b_chg < 0 else "neutral")
                             if b_chg is not None else "neutral",
            "dex_volume": fmt_dex_usd(b_dex) if b_dex else UNCONFIRMED,
            "dex_volume_jpy": fmt_vol_jpy(b_dex, fx) if b_dex and fx else "",
            "usdc_dominance": f"{usdc_d:.1f}%" if usdc_d is not None else UNCONFIRMED,
        },
        "lp": {"pools": [pool("Base 0.05%プール", g005), pool("Base 0.3%プール", g03)],
               "check_message": lp_msg},
        "footer": {
            # 開始と終了が同分なら範囲表記にせず単一時刻で表す（v1.1 A-3）。
            "retrieved_at": retrieved_at,
            "usd_jpy": f"¥{fx:.2f}" if fx else UNCONFIRMED,
            "sources": " / ".join(s for s in sources if s) or UNCONFIRMED,
        },
    }

    (out_dir / "daily_data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    raw = {"run_id": run_id, "fetched_at": now.isoformat(),
           "cmc": cmc, "fx": fx, "gecko_005": g005, "gecko_03": g03,
           "base_tvl": b_tvl, "base_tvl_chg": b_chg, "base_dex": b_dex,
           "usdc_dominance": usdc_d}
    (out_dir / "raw_data.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "run_context.env").write_text(
        f"run_id={run_id}\ntarget_date_jst={target.isoformat()}\n"
        f"target_date_compact={target.strftime('%Y%m%d')}\nweekday_jp={weekday}\n"
        f"started_at={now.isoformat()}\n", encoding="utf-8")
    print(f"OK: {out_dir}/daily_data.json (run_id={run_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
