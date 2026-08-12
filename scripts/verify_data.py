#!/usr/bin/env python3
"""verify_data.py — 機械監査（統合運用基準 §8 / 納品前品質チェック ゲート1・2・4の機械化）

使い方:
  python verify_data.py outputs/2026-08-24/daily_data.json [--image outputs/.../infographic.png]

結果は同ディレクトリの final_audit_YYYYMMDD.json に {overall, failed, checks[]} で保存。
failed > 0 なら exit 1（フェイルクローズ: 自動納品契約 準拠）。
未確認値は不合格ではない（推測しないことが正）。不整合・禁止表記だけを FAIL とする。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
UNCONFIRMED = "未確認"
CHG_RE = re.compile(r"^[+-]\d+\.\d{2}%$")
WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]
UNIT = {"兆": 1e12, "億": 1e8, "万": 1e4}


def parse_money(s: str) -> float | None:
    """'$63,922' '約1,009.2万円' '¥345.0兆' '$10.19M' '86.7%' → float(USD/JPY/%生値)"""
    if not s or UNCONFIRMED in s:
        return None
    t = s.replace("（", "").replace("）", "").replace(",", "").replace("約", "")
    m = re.search(r"([\d.]+)\s*([兆億万MB]?)", t)
    if not m:
        return None
    v = float(m.group(1))
    u = m.group(2)
    if u in UNIT:
        v *= UNIT[u]
    elif u == "M":
        v *= 1e6
    elif u == "B":
        v *= 1e9
    return v


class Audit:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, cid: str, ok: bool | None, detail: str) -> None:
        result = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        self.checks.append({"id": cid, "result": result, "detail": detail})

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c["result"] == "FAIL")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--image", default=None)
    ap.add_argument("--skip-date-check", action="store_true",
                    help="対象日=実行前日 の照合を省略（過去日の再検証用）")
    a = ap.parse_args()

    jp = Path(a.json_path)
    d = json.loads(jp.read_text(encoding="utf-8"))
    au = Audit()
    blob = json.dumps(d, ensure_ascii=False)

    # C1 スキーマ必須キー
    need = ["target_date_jst", "weekday_jp", "date_title", "summary",
            "assets", "market", "base", "lp", "footer"]
    missing = [k for k in need if k not in d]
    au.add("C1_schema", not missing, f"missing={missing}" if missing else "全必須キーあり")

    # C2 日付・曜日の内部整合（§8: 日付・曜日）
    try:
        t = datetime.strptime(d["target_date_jst"], "%Y-%m-%d").date()
        wd_ok = d["weekday_jp"] == WEEKDAYS_JP[t.weekday()]
        title_ok = f"{t.year}年{t.month}月{t.day}日（{d['weekday_jp']}）" in d["date_title"]
        au.add("C2_date_internal", wd_ok and title_ok,
               f"weekday_ok={wd_ok} title_ok={title_ok}")
    except Exception as e:  # noqa: BLE001
        au.add("C2_date_internal", False, f"parse error: {e}")
        t = None

    # C3 対象日 = 実行時JSTの前日（§1）
    if a.skip_date_check or t is None:
        au.add("C3_date_is_yesterday", None, "skipped")
    else:
        exp = (datetime.now(JST) - timedelta(days=1)).date()
        au.add("C3_date_is_yesterday", t == exp, f"target={t} expected={exp}")

    # C4 24時間比の形式と direction 整合
    ok4, det4 = True, []
    for asset in d.get("assets", []):
        c = asset.get("change_24h", "")
        if c == UNCONFIRMED:
            if asset.get("direction") != "neutral":
                ok4, _ = False, det4.append(f"{asset.get('asset')}: 未確認なのに矢印あり")
            continue
        if not CHG_RE.match(c):
            ok4 = False
            det4.append(f"{asset.get('asset')}: 形式不正 {c!r}")
            continue
        want = "up" if c.startswith("+") and c != "+0.00%" else \
               "down" if c.startswith("-") and c != "-0.00%" else "neutral"
        if asset.get("direction") not in (want, "neutral") and want != "neutral":
            ok4 = False
            det4.append(f"{asset.get('asset')}: {c} なのに direction={asset.get('direction')}")
    au.add("C4_change_format", ok4, "; ".join(det4) or "±N.NN% 形式・矢印整合")

    # C5 禁止表記（基準 §1: 「暗号通貨」表記、「24時間比」ラベル統一）＋ 二重括弧（v1.1 A-2）
    banned = [w for w in ("仮想通貨", "前日比", "（（", "））") if w in blob]
    # 円換算はレンダラー側が丸括弧を付ける。JSON側で括ると画像が二重括弧になるため、
    # 実効的な回帰ガードとして該当4フィールドの先頭括弧も禁止する。
    prewrapped = [k for k, src in (("market_cap_jpy", d.get("market", {})),
                                   ("volume_24h_jpy", d.get("market", {})),
                                   ("tvl_jpy", d.get("base", {})),
                                   ("dex_volume_jpy", d.get("base", {})))
                  if str(src.get(k, "")).startswith("（")]
    au.add("C5_banned_terms", not banned and not prewrapped,
           f"found={banned} prewrapped={prewrapped}" if (banned or prewrapped)
           else "禁止語・二重括弧なし")

    # C6 円換算の再計算（±1.5%）: assets
    fx = parse_money(d.get("footer", {}).get("usd_jpy", ""))
    if not fx:
        au.add("C6_jpy_assets", None, "USD/JPY未確認のためスキップ")
    else:
        ok6, det6 = True, []
        for asset in d.get("assets", []):
            u, j = parse_money(asset.get("usd", "")), parse_money(asset.get("jpy", ""))
            if u and j:
                ratio = j / (u * fx)
                if abs(ratio - 1) > 0.015:
                    ok6 = False
                    det6.append(f"{asset.get('asset')}: ratio={ratio:.4f}")
        au.add("C6_jpy_assets", ok6, "; ".join(det6) or f"fx={fx} で整合")

    # C7 円換算の再計算: market / base
    if not fx:
        au.add("C7_jpy_macro", None, "USD/JPY未確認のためスキップ")
    else:
        ok7, det7 = True, []
        pairs = [("market_cap", "market_cap_jpy", d["market"]),
                 ("volume_24h", "volume_24h_jpy", d["market"]),
                 ("tvl", "tvl_jpy", d["base"]),
                 ("dex_volume", "dex_volume_jpy", d["base"])]
        for ku, kj, src in pairs:
            u, j = parse_money(src.get(ku, "")), parse_money(src.get(kj, ""))
            if u and j:
                ratio = j / (u * fx)
                if abs(ratio - 1) > 0.02:
                    ok7 = False
                    det7.append(f"{ku}: ratio={ratio:.4f}")
        au.add("C7_jpy_macro", ok7, "; ".join(det7) or "整合")

    # C8 参考APRの再計算（vol×fee÷TVL×365、±0.06pt）
    ok8, det8 = True, []
    for p in d.get("lp", {}).get("pools", []):
        apr = parse_money(p.get("apr", ""))
        tvl = parse_money(p.get("tvl", ""))
        vol = parse_money(p.get("volume_24h", ""))
        fee_m = re.search(r"(0\.05|0\.3)%", p.get("name", ""))
        if None in (apr, tvl, vol) or not fee_m or not tvl:
            continue
        calc = vol * (float(fee_m.group(1)) / 100) / tvl * 365 * 100
        if abs(calc - apr) > 0.06:
            ok8 = False
            det8.append(f"{p['name']}: 表示{apr:.2f} 再計算{calc:.2f}")
    au.add("C8_apr_recalc", ok8, "; ".join(det8) or "算式整合")

    # C9 Fear & Greed 値域
    fg = d.get("market", {}).get("fear_greed", {})
    v = fg.get("value")
    ok9 = isinstance(v, int) and 0 <= v <= 100
    au.add("C9_fg_range", ok9, f"value={v} label={fg.get('label')}")

    # C10 画像規格（2560×1440）
    if a.image:
        try:
            from PIL import Image
            with Image.open(a.image) as im:
                ok10 = im.size == (2560, 1440)
                au.add("C10_image_size", ok10, f"size={im.size}")
        except Exception as e:  # noqa: BLE001
            au.add("C10_image_size", False, f"open error: {e}")
    else:
        au.add("C10_image_size", None, "画像未指定")

    # ハッシュ台帳（納品時原本固定: 基準 §7）
    hashes = {jp.name: sha256(jp)}
    if a.image and Path(a.image).exists():
        hashes[Path(a.image).name] = sha256(Path(a.image))
    for extra in ("raw_data.json", "apr_screenshot.jpg"):
        ep = jp.parent / extra
        if ep.exists():
            hashes[extra] = sha256(ep)

    compact = (t.strftime("%Y%m%d") if t else "unknown")
    audit = {
        "overall": "PASS" if au.failed == 0 else "FAIL",
        "failed": au.failed,
        "checked_at_jst": datetime.now(JST).isoformat(),
        "checks": au.checks,
        "sha256": hashes,
    }
    out = jp.parent / f"final_audit_{compact}.json"
    out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if au.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
