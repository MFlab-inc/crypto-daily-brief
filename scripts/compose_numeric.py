#!/usr/bin/env python3
"""compose_numeric.py — 前編【主要指標】・後編【主要指標（詳細）】のテンプレート差し込み
（v0.3 §6.1・§10 第1弾-3）。

LLM不使用。daily_data.json の値をそのまま差し込むだけで、独自の算出・言い換えは
行わない（C16「テンプレート差し込み分の数値がdaily_data.jsonと一致する」を
定義上つねに満たす）。取得不能でも行は省略せず、daily_data.json 側が持つ
「未確認」「算出不能（理由）」をそのまま反映する。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

UNCONFIRMED = "未確認"

_RETRIEVED_AT_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2}) (\d{2}:\d{2}(?:–\d{2}:\d{2})?) JST$")


def _paren(jpy: str) -> str:
    """（jpy）を返す。jpyが空文字なら空文字（v1.1 A-1と同じ: 空括弧を作らない）。"""
    return f"（{jpy}）" if jpy else ""


def _wareki_retrieved_at(s: str) -> str:
    """組版時のみ和暦風の日付表記へ変換する（v0.3修正3）。
    daily_data.json 側の footer.retrieved_at は変更しない（画像側フッターが
    同じ値をそのまま描画しているため）。単一時刻・範囲表記（v1.1 A-3）の
    どちらにも対応する。書式が一致しない場合（未確認等）はそのまま返す。
      "2026-08-18 07:50 JST"       -> "2026年8月18日07:50 JST"
      "2026-08-18 07:50–07:52 JST" -> "2026年8月18日07:50–07:52 JST"
    """
    m = _RETRIEVED_AT_RE.match(str(s))
    if not m:
        return s
    y, mo, d, time_part = m.groups()
    return f"{int(y)}年{int(mo)}月{int(d)}日{time_part} JST"


def _zenkaku_sources(s: str) -> str:
    """組版時のみ出典区切りを全角スラッシュへ統一する（v0.3修正2）。
    daily_data.json 側の footer.sources は変更しない（画像側フッターが
    半角" / "区切りのまま描画しているため）。前編の固定文言
    「CoinMarketCap API／ExchangeRate-API」と表記を揃える。
    """
    return str(s).replace(" / ", "／")


def _asset(daily_data: dict, symbol: str) -> dict:
    for a in daily_data.get("assets", []):
        if a.get("asset") == symbol:
            return a
    return {"usd": UNCONFIRMED, "jpy": "", "change_24h": UNCONFIRMED}


def compose_part0_target_date(daily_data: dict[str, Any]) -> str:
    """【対象日】。date_titleは図版見出し用の文言を含むため使わず、
    target_date_jst/weekday_jpから素の日付行を組む。
    """
    t = date.fromisoformat(daily_data["target_date_jst"])
    weekday = daily_data.get("weekday_jp", "")
    return f"{t.year}年{t.month}月{t.day}日（{weekday}）"


def compose_part1_numeric(daily_data: dict[str, Any]) -> str:
    m = daily_data.get("market", {})
    footer = daily_data.get("footer", {})
    btc, eth, bnb = (_asset(daily_data, s) for s in ("BTC", "ETH", "BNB"))

    fg = m.get("fear_greed", {})
    fg_label = fg.get("label", UNCONFIRMED)
    if fg_label == UNCONFIRMED:
        # value=0 は「未確認時のプレースホルダー」であり実際のFear&Greed値ではない
        # （fetch_data.py: fg else {"value": 0, "label": UNCONFIRMED}）。画像側は
        # ゲージ下の未確認ラベルと併記のため実害が薄いが、本文は数値単独で誤読され
        # やすいため「0」を出さず未確認のみ表示する。
        fg_line = f"・市場心理：Fear & Greed {UNCONFIRMED}（CoinMarketCap API）"
    else:
        fg_line = f"・市場心理：Fear & Greed {fg.get('value')}（{fg_label}、CoinMarketCap API）"

    lines = [
        "【主要指標】",
        f"・市場全体：時価総額 {m.get('market_cap', UNCONFIRMED)}{_paren(m.get('market_cap_jpy', ''))}"
        f"｜24時間取引高 {m.get('volume_24h', UNCONFIRMED)}{_paren(m.get('volume_24h_jpy', ''))}",
        f"・ #BTC：{btc.get('usd', UNCONFIRMED)}{_paren(btc.get('jpy', ''))}"
        f"｜24時間比 {btc.get('change_24h', UNCONFIRMED)}",
        f"・ #ETH：{eth.get('usd', UNCONFIRMED)}{_paren(eth.get('jpy', ''))}"
        f"｜24時間比 {eth.get('change_24h', UNCONFIRMED)}",
        f"・ #BNB：{bnb.get('usd', UNCONFIRMED)}{_paren(bnb.get('jpy', ''))}"
        f"｜24時間比 {bnb.get('change_24h', UNCONFIRMED)}",
        fg_line,
        f"・ドミナンス：BTC {m.get('btc_dominance', UNCONFIRMED)}｜ETH {m.get('eth_dominance', UNCONFIRMED)}",
        f"・出典・取得時刻：CoinMarketCap API／ExchangeRate-API、"
        f"{_wareki_retrieved_at(footer.get('retrieved_at', UNCONFIRMED))}、"
        f"USD/JPY {footer.get('usd_jpy', UNCONFIRMED)}",
    ]
    return "\n".join(lines)


def compose_part2_numeric(daily_data: dict[str, Any]) -> str:
    b = daily_data.get("base", {})
    dom = daily_data.get("domestic", {})
    footer = daily_data.get("footer", {})
    pools = daily_data.get("lp", {}).get("pools", [])
    p005 = pools[0] if len(pools) > 0 else {}
    p03 = pools[1] if len(pools) > 1 else {}

    lines = [
        "【主要指標（詳細）】",
        "・国内大手2社とBase上ETH/USDCの比較（24時間出来高・参考値）：",
        f"国内2社のETH/JPY現物 {dom.get('combined_usd', UNCONFIRMED)} "
        f"vs Base上ETH/USDC {b.get('dex_volume_eth_usdc', UNCONFIRMED)}｜"
        f"参考：Base上DEX全体 {b.get('dex_volume', UNCONFIRMED)}｜"
        "集計範囲・市場構造・取得時刻が異なるため、優劣や倍率の評価は行いません",
        f"・Baseチェーン：TVL {b.get('tvl', UNCONFIRMED)}{_paren(b.get('tvl_jpy', ''))}"
        f"｜24時間比 {b.get('tvl_change', UNCONFIRMED)}｜USDCドミナンス {b.get('usdc_dominance', UNCONFIRMED)}",
        f"・ ETH/USDC（Base）参考APR：0.05% {p005.get('apr', UNCONFIRMED)}"
        f"（TVL {p005.get('tvl', UNCONFIRMED)}／24h出来高 {p005.get('volume_24h', UNCONFIRMED)}）｜"
        f"0.3% {p03.get('apr', UNCONFIRMED)}"
        f"（TVL {p03.get('tvl', UNCONFIRMED)}／24h出来高 {p03.get('volume_24h', UNCONFIRMED)}）"
        "※24時間データの単純年率換算",
        f"・出典・取得時刻：{_zenkaku_sources(footer.get('sources', UNCONFIRMED))}、"
        f"{_wareki_retrieved_at(footer.get('retrieved_at', UNCONFIRMED))}",
    ]
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: compose_numeric.py <daily_data.json のパス>", file=sys.stderr)
        return 1
    d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print("【対象日】" + compose_part0_target_date(d))
    print()
    print(compose_part1_numeric(d))
    print()
    print(compose_part2_numeric(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
