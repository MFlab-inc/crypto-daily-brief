#!/usr/bin/env python3
"""capture_apr.py — APRダッシュボード実画面撮影（統合運用基準 §6 準拠）

回収済み『暗号通貨市況レポート_APR画像_6カード_27秒待機撮影.py』の忠実移植。
Selenium+Firefox → Playwright+Firefox（GitHub Actions向け）。
待機・再試行・クロップ座標は原版と同一:
  初期読込3秒 / Refresh後8秒 / 最大3試行(+3秒) / 意図的待機 最大27秒
  crop: left=8, top=130, right=width-8, bottom=min(1050, height-10)
検出文字列: "N/A% TODAY" / "GeckoTerminal取得失敗"

使い方: python capture_apr.py <出力jpgパス>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PIL import Image

URL = "https://ethusdc-apr.netlify.app/"
MAX_RETRY = 3
WAIT_INITIAL = 3
WAIT_AFTER_REFRESH = 8   # 原版コメント: 0.5秒では不足
WAIT_BETWEEN = 3
VIEWPORT = {"width": 1500, "height": 1280}


def capture(full_path: str) -> bool:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(URL, wait_until="load", timeout=60_000)
        time.sleep(WAIT_INITIAL)

        for attempt in range(1, MAX_RETRY + 1):
            print(f"[試行 {attempt}/{MAX_RETRY}] Refreshクリック...")
            try:
                page.locator("xpath=//button[contains(text(),'Refresh')]").click(timeout=5_000)
            except Exception as e:  # noqa: BLE001
                print(f"  Refreshボタンが見つかりません: {e}")
            print(f"  {WAIT_AFTER_REFRESH}秒待機（GeckoTerminalロード待ち）...")
            time.sleep(WAIT_AFTER_REFRESH)

            src = page.content()
            na = src.count("N/A% TODAY")
            err = src.count("GeckoTerminal取得失敗")
            if na == 0 and err == 0:
                print("  ✓ N/A表示なし。撮影します。")
                page.screenshot(path=full_path)
                browser.close()
                return True
            print(f"  ✗ N/A検出（N/A: {na}, エラー: {err}）。再試行...")
            if attempt < MAX_RETRY:
                time.sleep(WAIT_BETWEEN)

        print(f"警告: {MAX_RETRY}回試行後もN/A残存。現状を撮影・保存します。")
        page.screenshot(path=full_path)
        browser.close()
        return True


def crop_apr_cards(screenshot_path: str, output_path: str) -> None:
    img = Image.open(screenshot_path)
    width, height = img.size
    print(f"元画像サイズ: {width}x{height}px")
    box = (8, 130, width - 8, min(1050, height - 10))
    cropped = img.crop(box)
    if cropped.mode == "RGBA":
        cropped = cropped.convert("RGB")
    cropped.save(output_path, "JPEG", quality=95)
    print(f"保存完了: {output_path} ({cropped.size[0]}x{cropped.size[1]}px)")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "apr_screenshot.jpg"
    tmp = str(Path(out).with_suffix(".full.png"))
    if not capture(tmp):
        print("ERROR: 撮影に失敗しました。")
        sys.exit(1)
    crop_apr_cards(tmp, out)
    Path(tmp).unlink(missing_ok=True)
    print(f"✓ 完了: {out}")
