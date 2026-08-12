#!/usr/bin/env python3
"""Render the approved fixed crypto/DEX daily infographic.

Usage:
  python3 fixed_infographic_renderer.py daily_data.json output.png

The renderer fixes the approved layout, palette, panel sequence and decoration.
Only verified values supplied in daily_data.json may change.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

W, H = 2560, 1440
NAVY = "#07275A"
WHITE = "#FFFFFF"
PALE_BLUE = "#E2F0FF"
LINE = "#203C6E"
GRAY = "#6E7888"
LIGHT_GRAY = "#D5DCE7"
GREEN = "#008D44"
RED = "#CB3333"
ORANGE = "#F7931A"
GOLD = "#F3BA2F"

FONT_CANDIDATES = {
    "regular": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "bold": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES["bold" if bold else "regular"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
         fill: str = NAVY, bold: bool = False, anchor: str = "la") -> None:
    draw.text(xy, value, font=font(size, bold), fill=fill, anchor=anchor)


def fitted_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, max_width: int,
                size: int, fill: str = NAVY, bold: bool = False, anchor: str = "la",
                min_size: int = 18) -> int:
    """Draw text at the largest size that remains inside a fixed horizontal area."""
    for current_size in range(size, min_size - 1, -1):
        active_font = font(current_size, bold)
        bbox = draw.textbbox((0, 0), value, font=active_font, anchor=anchor)
        if bbox[2] - bbox[0] <= max_width:
            draw.text(xy, value, font=active_font, fill=fill, anchor=anchor)
            return current_size
    draw.text(xy, value, font=font(min_size, bold), fill=fill, anchor=anchor)
    return min_size


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int,
            fill: str = WHITE, outline: str | None = LINE, width: int = 4) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def line(draw: ImageDraw.ImageDraw, a: tuple[int, int], b: tuple[int, int],
         fill: str = LINE, width: int = 3) -> None:
    draw.line((a, b), fill=fill, width=width)


def panel_header(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], n: str, label: str) -> None:
    x1, y1, x2, _ = box
    draw.rounded_rectangle((x1, y1, x1 + 112, y1 + 82), radius=17, fill=NAVY)
    draw.polygon([(x1 + 105, y1), (x1 + 155, y1), (x1 + 100, y1 + 82), (x1 + 55, y1 + 82)], fill=WHITE)
    text(draw, (x1 + 52, y1 + 40), n, 58, WHITE, True, "mm")
    text(draw, (x1 + 185, y1 + 40), label, 42, NAVY, True, "lm")
    line(draw, (x1 + 28, y1 + 82), (x2 - 28, y1 + 82), NAVY, 4)


def draw_asset_symbol(draw: ImageDraw.ImageDraw, cx: int, cy: int, asset: str) -> None:
    if asset == "#BTC":
        draw.ellipse((cx - 53, cy - 53, cx + 53, cy + 53), fill=ORANGE)
        # Use a stable geometric mark rather than a font-dependent Bitcoin symbol.
        text(draw, (cx, cy), "B", 66, WHITE, True, "mm")
        line(draw, (cx - 17, cy - 36), (cx - 17, cy + 36), WHITE, 4)
        line(draw, (cx - 7, cy - 36), (cx - 7, cy + 36), WHITE, 4)
    elif asset == "#ETH":
        draw.ellipse((cx - 53, cy - 53, cx + 53, cy + 53), fill="#F4F5F7", outline=LIGHT_GRAY, width=2)
        draw.polygon([(cx, cy - 43), (cx - 30, cy), (cx, cy + 5), (cx + 30, cy)], fill="#4B4E55")
        draw.polygon([(cx, cy + 13), (cx - 30, cy + 4), (cx, cy + 43), (cx + 30, cy + 4)], fill="#16181C")
    elif asset == "#BNB":
        draw.ellipse((cx - 53, cy - 53, cx + 53, cy + 53), fill=GOLD)
        for dx, dy in [(0, -22), (-22, 0), (22, 0), (0, 22)]:
            draw.polygon([(cx + dx, cy + dy - 13), (cx + dx + 13, cy + dy),
                          (cx + dx, cy + dy + 13), (cx + dx - 13, cy + dy)], outline=WHITE, width=5)
        draw.polygon([(cx, cy - 10), (cx + 10, cy), (cx, cy + 10), (cx - 10, cy)], fill=WHITE)
    else:
        raise ValueError(f"Unsupported asset logo: {asset}")


def direction(draw: ImageDraw.ImageDraw, x: int, y: int, pct: str, direction_value: str,
              show_label: bool = True) -> None:
    if direction_value == "up":
        color, prefix = GREEN, "▲ "
    elif direction_value == "down":
        color, prefix = RED, "▼ "
    elif direction_value == "neutral":
        # 未確認時は矢印を描かず、方向を断定しない。
        color, prefix = GRAY, ""
    else:
        raise ValueError(f"Unsupported direction: {direction_value}")
    label = "24時間比 " if show_label else ""
    fitted_text(draw, (x, y), f"{prefix}{label}{pct}", 345, 36, color, True, "ra", 24)


def draw_gauge(draw: ImageDraw.ImageDraw, cx: int, cy: int, value: int, label: str) -> None:
    colors = ["#DD2525", "#F47516", "#FAB20A", "#A3BF0D", "#008D44"]
    bbox = (cx - 190, cy - 190, cx + 190, cy + 190)
    for i, color in enumerate(colors):
        start = 180 + i * 36
        draw.arc(bbox, start=start, end=start + 38, fill=color, width=36)
    angle = math.radians(180 + max(0, min(100, value)) * 1.8)
    ex = cx + int(math.cos(angle) * 132)
    ey = cy + int(math.sin(angle) * 132)
    draw.line((cx, cy, ex, ey), fill=NAVY, width=15)
    draw.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), fill=NAVY)
    text(draw, (cx, cy + 93), f"{value} / 100", 57, NAVY, True, "mm")
    text(draw, (cx, cy + 158), label, 42, NAVY, True, "mm")


def stat_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, kind: str) -> None:
    """Draw compact data icons with Pillow primitives to avoid font fallback errors."""
    draw.ellipse((cx - 46, cy - 46, cx + 46, cy + 46), fill=NAVY)
    if kind == "cap":
        draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=WHITE, width=3)
        draw.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), outline=WHITE, width=3)
        draw.line((cx - 27, cy, cx + 27, cy), fill=WHITE, width=3)
    elif kind in {"volume", "dex"}:
        for offset, height in [(-19, 16), (-4, 30), (11, 22)]:
            draw.rectangle((cx + offset, cy + 13 - height, cx + offset + 9, cy + 13), fill=WHITE)
    elif kind == "btc_dom":
        draw.ellipse((cx - 23, cy - 23, cx + 23, cy + 23), outline=WHITE, width=3)
        draw.pieslice((cx - 22, cy - 22, cx + 22, cy + 22), start=270, end=360, fill=WHITE)
        draw.line((cx, cy, cx, cy - 22), fill=NAVY, width=2)
        draw.line((cx, cy, cx + 22, cy), fill=NAVY, width=2)
    elif kind == "eth_dom":
        draw.ellipse((cx - 23, cy - 23, cx + 23, cy + 23), outline=WHITE, width=3)
        draw.pieslice((cx - 22, cy - 22, cx + 22, cy + 22), start=0, end=180, fill=WHITE)
        draw.line((cx - 22, cy, cx + 22, cy), fill=NAVY, width=2)
    elif kind == "base":
        draw.rectangle((cx - 21, cy - 21, cx + 21, cy + 21), outline=WHITE, width=3)
        draw.line((cx - 21, cy - 21, cx + 21, cy + 21), fill=WHITE, width=3)
        draw.line((cx - 21, cy + 21, cx + 21, cy - 21), fill=WHITE, width=3)
    elif kind == "usdc":
        draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), outline=WHITE, width=3)
        text(draw, (cx, cy), "$", 33, WHITE, True, "mm")
    else:
        raise ValueError(f"Unsupported stat icon: {kind}")


def draw_header(draw: ImageDraw.ImageDraw, data: dict[str, Any]) -> None:
    draw.rectangle((0, 0, W, 180), fill=WHITE)
    draw.rectangle((0, 0, W, 24), fill=NAVY)
    draw.polygon([(0, 24), (180, 24), (105, 180), (0, 180)], fill=NAVY)
    draw.polygon([(62, 24), (95, 24), (20, 180), (0, 180)], fill=WHITE)
    draw.polygon([(W, 24), (W - 180, 24), (W - 105, 180), (W, 180)], fill=NAVY)
    draw.polygon([(W - 62, 24), (W - 95, 24), (W - 20, 180), (W, 180)], fill=WHITE)
    fitted_text(draw, (W // 2, 75), data["date_title"], 2080, 70, NAVY, True, "mm", 48)
    fitted_text(draw, (W // 2, 143), data["summary"], 2050, 44, NAVY, True, "mm", 28)


def draw_assets(draw: ImageDraw.ImageDraw, data: dict[str, Any], box: tuple[int, int, int, int]) -> None:
    panel_header(draw, box, "1", "主要暗号通貨の価格")
    x1, y1, x2, _ = box
    # 円換算と変化率の列を分離し、「24時間比」は列見出しとして一度だけ表示する。
    text(draw, (x1 + 700, y1 + 108), "日本円換算", 22, NAVY, True, "lm")
    text(draw, (x2 - 28, y1 + 108), "24時間比", 22, NAVY, True, "ra")
    y_positions = [y1 + 158, y1 + 290, y1 + 422]
    for i, item in enumerate(data["assets"]):
        y = y_positions[i]
        if i:
            line(draw, (x1 + 30, y - 65), (x2 - 30, y - 65), LIGHT_GRAY, 2)
        draw_asset_symbol(draw, x1 + 80, y, item["asset"])
        text(draw, (x1 + 180, y), item["asset"], 48, NAVY, True, "lm")
        text(draw, (x1 + 395, y), item["usd"], 54, NAVY, True, "lm")
        text(draw, (x1 + 700, y), f"（{item['jpy']}）", 28, NAVY, False, "lm")
        direction(draw, x2 - 28, y, item["change_24h"], item["direction"], show_label=False)


def draw_market(draw: ImageDraw.ImageDraw, data: dict[str, Any], box: tuple[int, int, int, int]) -> None:
    panel_header(draw, box, "2", "市場概況")
    x1, y1, x2, _ = box
    gauge = data["market"]["fear_greed"]
    # 見出しと半円ゲージが重ならないよう、見出しを上方へ配置して余白を確保する。
    text(draw, (x1 + 285, y1 + 112), "Fear & Greed", 34, NAVY, True, "mm")
    draw_gauge(draw, x1 + 285, y1 + 330, int(gauge["value"]), gauge["label"])
    line(draw, (x1 + 500, y1 + 100), (x1 + 500, y1 + 500), LINE, 3)
    stats = [
        ("cap", "時価総額", data["market"]["market_cap"], data["market"]["market_cap_jpy"]),
        ("volume", "24時間取引高", data["market"]["volume_24h"], data["market"]["volume_24h_jpy"]),
        ("btc_dom", "#BTCドミナンス", data["market"]["btc_dominance"], ""),
        ("eth_dom", "#ETHドミナンス", data["market"]["eth_dominance"], ""),
    ]
    # 各指標を「ラベル＋数値」の1行へ統合し、区切り線との干渉を防ぐ。
    stat_y_positions = [y1 + 145 + i * 100 for i in range(len(stats))]
    stat_text_width = x2 - (x1 + 700) - 28
    for i, (kind, label, main, sub) in enumerate(stats):
        y = stat_y_positions[i]
        if i:
            line(draw, (x1 + 530, y - 50), (x2 - 28, y - 50), LIGHT_GRAY, 2)
        stat_icon(draw, x1 + 600, y, kind)
        detail = f"{label}  {main}" + (f"（{sub}）" if sub else "")
        fitted_text(draw, (x1 + 700, y), detail, stat_text_width, 32, NAVY, True, "lm", 20)


def draw_base(draw: ImageDraw.ImageDraw, data: dict[str, Any], box: tuple[int, int, int, int]) -> None:
    panel_header(draw, box, "3", "Baseチェーンの状況")
    x1, y1, x2, _ = box
    items = [
        ("base", "Base TVL", data["base"]["tvl"], data["base"]["tvl_jpy"], data["base"].get("tvl_change", ""), data["base"].get("tvl_direction", "neutral")),
        ("dex", "Base 24h DEX出来高", data["base"]["dex_volume"], data["base"]["dex_volume_jpy"], "", "neutral"),
        ("usdc", "#USDCドミナンス", data["base"]["usdc_dominance"], "", "", "neutral"),
    ]
    for i, (kind, label, main, sub, change, direction_value) in enumerate(items):
        y = y1 + 142 + i * 112
        if i:
            line(draw, (x1 + 30, y - 56), (x2 - 30, y - 56), LIGHT_GRAY, 2)
        stat_icon(draw, x1 + 80, y, kind)
        text(draw, (x1 + 165, y), label, 37, NAVY, True, "lm")
        text(draw, (x1 + 560, y), main, 51, NAVY, True, "lm")
        if sub:
            text(draw, (x1 + 770, y), f"（{sub}）", 25, NAVY, False, "lm")
        if change:
            # 列見出しに「24時間比」を1回だけ記載し、行内では変化率数値のみを表示する。
            text(draw, (x2 - 80, y - 35), "24時間比", 22, NAVY, True, "mm")
            direction(draw, x2 - 30, y + 17, change, direction_value, show_label=False)


def draw_pool_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    draw.ellipse((cx - 78, cy - 78, cx + 78, cy + 78), fill=NAVY)
    draw.arc((cx - 36, cy - 46, cx + 36, cy + 45), start=150, end=390, fill=WHITE, width=8)
    draw.arc((cx - 23, cy - 26, cx + 23, cy + 28), start=150, end=390, fill=WHITE, width=5)


def draw_lp(draw: ImageDraw.ImageDraw, data: dict[str, Any], box: tuple[int, int, int, int]) -> None:
    panel_header(draw, box, "4", "#ETH/#USDC LP確認")
    x1, y1, x2, _ = box
    draw_pool_icon(draw, x1 + 160, y1 + 235)
    text(draw, (x1 + 160, y1 + 346), "#ETH/#USDC", 35, NAVY, True, "mm")
    text(draw, (x1 + 160, y1 + 389), "Base 流動性プール", 28, NAVY, True, "mm")
    line(draw, (x1 + 330, y1 + 105), (x1 + 330, y1 + 375), LINE, 3)
    pool_boxes = [(x1 + 360, y1 + 98, x2 - 28, y1 + 225), (x1 + 360, y1 + 245, x2 - 28, y1 + 372)]
    for box2, pool in zip(pool_boxes, data["lp"]["pools"]):
        rounded(draw, box2, 14, fill=PALE_BLUE, outline=None, width=0)
        ax1, ay1, ax2, ay2 = box2
        # 各行をボックスの上下余白内で中央揃えにし、内容が枠外へ出ないよう幅を制限する。
        top_line_y = ay1 + 38
        bottom_line_y = ay1 + 89
        fitted_text(draw, (ax1 + 28, top_line_y), pool["name"], 300, 32, NAVY, True, "lm", 24)
        fitted_text(draw, (ax2 - 25, top_line_y), f"APR {pool['apr']}（参考値）", 410, 30, NAVY, True, "rm", 22)
        fitted_text(draw, (ax1 + 28, bottom_line_y), f"TVL {pool['tvl']}", 275, 29, NAVY, True, "lm", 22)
        fitted_text(draw, (ax2 - 25, bottom_line_y), f"24h Volume {pool['volume_24h']}", 410, 29, NAVY, True, "rm", 22)
    fitted_text(draw, (x2 - 28, y1 + 391), "※ APRは公開画面・実運用レンジを確認", 520, 20, NAVY, False, "ra", 18)


def draw_bottom(draw: ImageDraw.ImageDraw, data: dict[str, Any]) -> None:
    draw.rounded_rectangle((60, 1185, W - 60, 1325), radius=15, fill=NAVY)
    sx, sy = 150, 1255
    draw.polygon([(sx, sy - 48), (sx + 40, sy - 28), (sx + 35, sy + 25), (sx, sy + 56), (sx - 35, sy + 25), (sx - 40, sy - 28)], outline=WHITE, width=7)
    text(draw, (sx, sy + 3), "✓", 54, WHITE, True, "mm")
    # LP確認帯は投資判断時の見落としを避けるため、従来45pxから60pxへ拡大する。
    fitted_text(draw, (W // 2, 1255), data["lp"]["check_message"], 1840, 60, WHITE, True, "mm", 48)
    x, y = W - 145, 1280
    for i, height in enumerate([23, 50, 85]):
        draw.rectangle((x + i * 28, y - height, x + i * 28 + 18, y), fill=WHITE)
    draw.line((x - 12, y - 4, x + 95, y - 105), fill=WHITE, width=8)
    draw.polygon([(x + 95, y - 105), (x + 65, y - 102), (x + 93, y - 76)], fill=WHITE)


def draw_footer(draw: ImageDraw.ImageDraw, data: dict[str, Any]) -> None:
    fitted_text(
        draw, (W // 2, 1380),
        f"データ取得：{data['footer']['retrieved_at']}  ｜  USD/JPY {data['footer']['usd_jpy']}  ｜  ソース：{data['footer']['sources']}",
        2200, 28, NAVY, False, "mm", 18,
    )


def expected_direction(change_24h: Any) -> str:
    """24時間比の表示値と矢印の整合を判定する。未確認・ゼロは矢印なし。"""
    value = str(change_24h).strip()
    if value.startswith("+"):
        return "up"
    if value.startswith("-"):
        return "down"
    return "neutral"


def validate_data(data: dict[str, Any]) -> None:
    expected_assets = ["#BTC", "#ETH", "#BNB"]
    assets = data.get("assets")
    if not isinstance(assets, list) or [item.get("asset") for item in assets] != expected_assets:
        raise ValueError("assets must contain #BTC, #ETH and #BNB in that exact order")

    target_date_jst = data.get("target_date_jst")
    weekday_jp = data.get("weekday_jp")
    if not isinstance(target_date_jst, str) or not isinstance(weekday_jp, str):
        raise ValueError("target_date_jst and weekday_jp are required")
    try:
        target_date = datetime.strptime(target_date_jst, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("target_date_jst must use YYYY-MM-DD") from exc
    expected_weekday_jp = ["月", "火", "水", "木", "金", "土", "日"][target_date.weekday()]
    if weekday_jp != expected_weekday_jp:
        raise ValueError(f"weekday_jp mismatch: {target_date_jst} is {expected_weekday_jp}曜日")
    expected_date_label = f"{target_date.year}年{target_date.month}月{target_date.day}日（{weekday_jp}）"
    if expected_date_label not in str(data.get("date_title", "")):
        raise ValueError("date_title must contain target_date_jst and weekday_jp")

    if len(data.get("lp", {}).get("pools", [])) != 2:
        raise ValueError("lp.pools must contain exactly two Base pool records")
    for item in assets:
        direction_value = item.get("direction")
        if direction_value not in {"up", "down", "neutral"}:
            raise ValueError("assets[].direction must be up, down or neutral")
        if direction_value != expected_direction(item.get("change_24h", "")):
            raise ValueError(
                f"{item.get('asset')} direction must match change_24h; "
                "unverified or zero values require neutral"
            )
    if data.get("base", {}).get("tvl_direction", "neutral") not in {"up", "down", "neutral"}:
        raise ValueError("base.tvl_direction must be up, down or neutral")


def render(data: dict[str, Any]) -> Image.Image:
    validate_data(data)
    image = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(image)
    draw_header(draw, data)
    boxes = [(60, 195, 1260, 715), (1280, 195, 2500, 715), (60, 740, 1260, 1160), (1280, 740, 2500, 1160)]
    for box in boxes:
        rounded(draw, box, 18, WHITE, LINE, 4)
    draw_assets(draw, data, boxes[0])
    draw_market(draw, data, boxes[1])
    draw_base(draw, data, boxes[2])
    draw_lp(draw, data, boxes[3])
    draw_bottom(draw, data)
    draw_footer(draw, data)
    return image


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: fixed_infographic_renderer.py daily_data.json output.png")
    source, output = map(Path, sys.argv[1:])
    data = json.loads(source.read_text(encoding="utf-8"))
    render(data).save(output, quality=95)
    print(output)


if __name__ == "__main__":
    main()
