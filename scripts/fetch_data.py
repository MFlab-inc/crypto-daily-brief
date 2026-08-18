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
- bitFlyer       api.bitflyer.com/v1/ticker?product_code=ETH_JPY（v1.4・後編用）
- Coincheck      coincheck.com/api/ticker?pair=eth_jpy（v1.4・後編用）

domestic セクション（v1.4）は X投稿後編【主要指標（詳細）】用のデータであり、
図版には描画しない。片方でも取得不能なら合計は「算出不能」とし、
BTC/JPY・推定値・前日値による代替は行わない（統合運用基準 §3.2）。

v1.5（改善①案B・改善②）: base.dex_volume_eth_usdc は資産ベースを揃えた
同種比較用（Base ETH/USDCプール0.05%+0.3%の出来高合計、追加API不要）。
チェーン全体の base.dex_volume は従来どおり参考値として残す。
lp.pools[].change_vs_prev は前日 daily_data.json との算術的な変化率
（APR・24時間出来高・TVL）。原因の解釈・推測は行わない。
どちらも図版には描画しない。
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


def _as_float(v) -> float | None:
    """数値/数値文字列を float へ。それ以外は None（Coincheck は文字列で返す版がある）。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fetch_bitflyer_eth_volume() -> dict | None:
    """bitFlyer ETH/JPY 24時間出来高（ETH建て・ローリング24h・認証不要 — v1.4）。

    フォールバック3段（オーナー承認済み）:
      ① 公式API /v1/ticker?product_code=ETH_JPY の volume
      ② TokenInsight — ペア別(ETH/JPY)出来高のエンドポイント・レスポンス構造が
         公開ドキュメントで確認できなかったためスキップする。確認できたのは
         取引所全体の出来高（/api/v1/history/exchanges/{id} の spot/derivatives/total）
         のみで、全ペア合算は分母が異なり ETH/JPY の代替にならない（基準 §3.2）。
         TI_API_KEY はワークフローから渡済み。構造確認後にここへ実装を追加する。
      ③ 取得不能（呼び出し側で「取得不能」表記へ落とす）
    """
    try:
        j = get_json("https://api.bitflyer.com/v1/ticker",
                     params={"product_code": "ETH_JPY"})
        v = _as_float(j.get("volume"))
        if v is not None:
            return {"volume_eth": v, "source": "bitFlyer公式API",
                    "field": "volume (rolling 24h)",
                    "retrieved_at": datetime.now(JST).isoformat()}
        print(f"[warn] bitflyer ticker: volume欠落/形式不正 keys={sorted(j)}",
              file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] bitflyer ticker: {e}", file=sys.stderr)
    if os.environ.get("TI_API_KEY"):
        print("[warn] bitflyer fallback(2) TokenInsight: ペア別ETH/JPY出来高の"
              "エンドポイント未確認のためスキップ → 取得不能へ", file=sys.stderr)
    return None


def _parse_prev_apr(s: str) -> float | None:
    """前日 daily_data.json の pool.apr（例 "12.26%"）を float へ（v1.5）。"""
    if not s or s == UNCONFIRMED:
        return None
    try:
        return float(str(s).rstrip("%"))
    except ValueError:
        return None


def _parse_prev_fmt_m(s: str) -> float | None:
    """前日 daily_data.json の pool.tvl / volume_24h（fmt_m形式）を float(USD) へ（v1.5）。"""
    if not s or s == UNCONFIRMED:
        return None
    t = str(s).replace("$", "").replace(",", "")
    try:
        if t.endswith("B"):
            return float(t[:-1]) * 1e9
        if t.endswith("M"):
            return float(t[:-1]) * 1e6
        return float(t)
    except ValueError:
        return None


def load_prev_pools(target) -> dict | None:
    """前日 outputs/{前日}/daily_data.json の lp.pools を name をキーに読み込む（v1.5）。

    ファイルが無い/壊れている場合は None（呼び出し側で「前日データなし」に落とす）。
    """
    prev_path = Path(f"outputs/{(target - timedelta(days=1)).isoformat()}/daily_data.json")
    if not prev_path.exists():
        return None
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        pools = prev.get("lp", {}).get("pools", [])
        return {p.get("name"): p for p in pools if isinstance(p, dict) and p.get("name")}
    except Exception as e:  # noqa: BLE001
        print(f"[warn] load_prev_pools: {e}", file=sys.stderr)
        return None


def fetch_coincheck_eth_volume() -> dict | None:
    """Coincheck ETH/JPY 24時間出来高（ETH建て・認証不要 — v1.4）。"""
    try:
        j = get_json("https://coincheck.com/api/ticker", params={"pair": "eth_jpy"})
        v = _as_float(j.get("volume"))
        if v is not None:
            return {"volume_eth": v, "source": "Coincheck公式API",
                    "field": "volume (24h)",
                    "retrieved_at": datetime.now(JST).isoformat()}
        print(f"[warn] coincheck ticker: volume欠落/形式不正 keys={sorted(j)}",
              file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] coincheck ticker: {e}", file=sys.stderr)
    return None


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
    bf_dom = fetch_bitflyer_eth_volume()   # 失敗時 None（内部でフォールバック処理）
    cc_dom = fetch_coincheck_eth_volume()
    dom_t = datetime.now(JST)
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

    # ---------- 同種比較用: Base ETH/USDCプール出来高合計（v1.5 改善①案B） ----------
    # チェーン全体のDEX合算（b_dex）は資産ベースが揃わない。取得済みの2プール分
    # （0.05%+0.3%）を合算するだけで、追加APIは使わない。片方でも欠けたら
    # 部分合算にはせず未確認（推測しない方針は不変）。チェーン全体値は参考として残す。
    if g005 and g03:
        dex_eth_usdc_vol = g005["vol"] + g03["vol"]
        dex_eth_usdc_s = fmt_m(dex_eth_usdc_vol)
        dex_eth_usdc_jpy_s = fmt_vol_jpy(dex_eth_usdc_vol, fx) if fx else ""
    else:
        dex_eth_usdc_s = UNCONFIRMED
        dex_eth_usdc_jpy_s = ""

    # ---------- APR変化の要因分解（v1.5 改善②）。算術的分解のみ、解釈・推測はしない ----------
    NO_PREV_DATA = "比較不可（前日データなし）"
    NO_PREV_VALUE = "比較不可（前日値未確認）"
    NO_CURR_VALUE = "比較不可（当日値未確認）"
    prev_pools = load_prev_pools(target)

    def change_field(curr: float | None, prev: float | None) -> str:
        if curr is None:
            return NO_CURR_VALUE
        if prev is None or prev == 0:
            return NO_PREV_VALUE
        return fmt_change((curr - prev) / prev * 100)

    def pool_changes(pool_name: str, g: dict | None) -> dict:
        if prev_pools is None:
            return {"apr_change": NO_PREV_DATA, "volume_24h_change": NO_PREV_DATA,
                    "tvl_change": NO_PREV_DATA}
        prev = prev_pools.get(pool_name)
        prev_apr = _parse_prev_apr(prev.get("apr", "")) if prev else None
        prev_tvl = _parse_prev_fmt_m(prev.get("tvl", "")) if prev else None
        prev_vol = _parse_prev_fmt_m(prev.get("volume_24h", "")) if prev else None
        curr_apr = g["apr"] if g else None
        curr_tvl = g["tvl"] if g else None
        curr_vol = g["vol"] if g else None
        return {
            "apr_change": change_field(curr_apr, prev_apr),
            "volume_24h_change": change_field(curr_vol, prev_vol),
            "tvl_change": change_field(curr_tvl, prev_tvl),
        }

    pools_built = [pool("Base 0.05%プール", g005), pool("Base 0.3%プール", g03)]
    # ループ変数名は既存の CMC グローバル指標 `g`（quotes.get("global")）と
    # 衝突させない（関数スコープのため上書きしてしまう — v1.5 実装時に検出・修正）。
    for pd, pool_g in zip(pools_built, (g005, g03)):
        pd["change_vs_prev"] = pool_changes(pd["name"], pool_g)

    # ---------- 国内2社（v1.4） ----------
    # 片方でも取得不能なら合計は「算出不能」。BTC/JPY・推定値・前日値で代替しない。
    def fmt_eth(v: float) -> str:
        return f"{v:,.2f} ETH"

    def fmt_domestic_usd(v: float) -> str:
        # $2M未満は実額表示。fmt_m（$0.01M=1万ドル刻み）では表示丸めだけで
        # C11 の ±0.5% を超え、出来高激減日に正データでフェイルクローズしてしまう
        # （v1.4 レビューで実証）。通常域（$5M以上）は fmt_m で見本の表記に揃える。
        if v < 2e6:
            return f"${round(v):,}"
        return fmt_m(v)

    eth_px = (quotes.get("ETH") or {}).get("price")
    if bf_dom and cc_dom:
        combined = bf_dom["volume_eth"] + cc_dom["volume_eth"]
        combined_eth_s = fmt_eth(combined)
        combined_usd_s = (fmt_domestic_usd(combined * eth_px) if eth_px
                          else "算出不能（ETH価格が未確認のため）")
    else:
        miss = "・".join(n for n, v in (("bitFlyer", bf_dom),
                                        ("Coincheck", cc_dom)) if not v)
        combined_eth_s = f"算出不能（{miss}が取得不能のため）"
        combined_usd_s = combined_eth_s
    domestic = {
        "bitflyer_eth_24h": fmt_eth(bf_dom["volume_eth"]) if bf_dom else "取得不能",
        "coincheck_eth_24h": fmt_eth(cc_dom["volume_eth"]) if cc_dom else "取得不能",
        "combined_eth": combined_eth_s,
        "combined_usd": combined_usd_s,
        "retrieved_at": f"{dom_t.strftime('%Y-%m-%d %H:%M')} JST",
    }

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
            # v1.5 改善①案B: 資産ベースを揃えた同種比較用（参考: 上のdex_volumeはチェーン全体）
            "dex_volume_eth_usdc": dex_eth_usdc_s,
            "dex_volume_eth_usdc_jpy": dex_eth_usdc_jpy_s,
            "usdc_dominance": f"{usdc_d:.1f}%" if usdc_d is not None else UNCONFIRMED,
        },
        "lp": {"pools": pools_built,
               "check_message": lp_msg},
        # v1.4: X投稿後編【主要指標（詳細）】用。図版には描画しない。
        "domestic": domestic,
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
           "usdc_dominance": usdc_d,
           # v1.4: 取得フィールド・取得時刻(JST ISO)を含む個別記録（基準 §3.2 の
           # 「取得フィールド・時間窓」を後編で記載するための正本）
           "bitflyer": bf_dom, "coincheck": cc_dom}
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
