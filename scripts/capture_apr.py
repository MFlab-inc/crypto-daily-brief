#!/usr/bin/env python3
"""capture_apr.py — APRダッシュボード実画面撮影（統合運用基準 §6 準拠）

回収済み『暗号通貨市況レポート_APR画像_6カード_27秒待機撮影.py』の忠実移植。
Selenium+Firefox → Playwright+Firefox（GitHub Actions向け）。
クロップ座標は原版と同一。待機・再試行は原版どおり
「初期読込3秒 / Refresh後8秒 / 最大3試行(+3秒) / 意図的待機 最大27秒」
だったが、v1.68でRefresh後の待機を段階的に延ばす方式へ変更（後述）。
  crop: left=8, top=130, right=width-8, bottom=min(1050, height-10)
検出文字列: "N/A%" / "GeckoTerminal取得失敗"
  ※ 原版は "N/A% TODAY" だが、カードのDOMが
    <div class="apr-value">N/A<span>%</span></div><span class="apr-label">TODAY</span>
    と分かれており描画テキストが "N/A%\nTODAY"（間に改行）になるため、
    原版から一度も一致しなかった。検知の意図（TODAY値の欠落検出）は不変のまま
    "N/A%" へ短縮して修理（v1.3 承認）。

v1.68（オーナー指示・9/5実データでローディング中の画面がそのまま撮影された
事象への対処）: 既存のN/A検出は「値が空欄で描画された」状態のみを検知でき、
「グローバルなローディング表示のまま（プールカード自体が1件も描画されて
いない）」状態は検知対象外だった。以下の判定を追加する。
  (a) ダッシュボードJS（dashboard/eth_usdc_apr.html）のグローバル
      ローディング表示の実際の文言 "Fetching ETH/USDC pool data..." を
      そのまま検出対象にする。汎用的な "Loading" 一致は使わない——
      The Graph APIキーが未設定の場合、Base系2プールのスパークライン
      枠が "Loading chart..." のまま恒常的に残る設計であり（The Graph
      キー未設定時はfetchGraphHistory()がスパークライン枠に一切触れず
      早期returnする）、"Loading" の単純一致は正常時にも誤検知し続ける
      リスクがあるため。
  (b) 各プールカードに1回ずつ描画される "TODAY" ラベル（apr-labelクラス）
      の出現回数が想定件数（6件=3チェーン×2手数料）に満たない場合を
      未完了とみなす。"% TODAY" のような連続文字列では一致しない
      （前述のDOM分割と同じ理由）ため、"TODAY" 単独の出現回数で判定する。
既存のN/A検出とは OR 条件で扱い、いずれかに該当すればリトライする。

v1.68（オーナー承認・フェイルクローズ方針(b)）: 最大試行後も未完了の場合、
ローディング中の画像を撮影・コミットすることをやめ、apr_screenshot.jpg を
生成しない（画像なしで納品）。その旨を apr_capture_status.json に記録し、
verify_data.py（C25）がこれを拾って final_audit へ記録する。この欠落は
フェーズ1全体をフェイルクローズさせない（daily_data.json・infographicは
無関係に正常納品する）——数値データそのものの正確性の問題ではなく、
補助的なスクリーンショット1点が撮影できなかったという運用上の制約のため。

使い方: python capture_apr.py <出力jpgパス>
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PIL import Image

URL = "https://ethusdc-apr.netlify.app/"
MAX_RETRY = 3
WAIT_INITIAL = 3
# v1.68（オーナー承認）: DefiLlama Yields APIの応答が遅い日への耐性を上げる
# ため、Refresh後の待機を試行ごとに段階的に延ばす（8→12→16秒）。原版の
# 固定8秒から変更。
WAIT_AFTER_REFRESH_SCHEDULE = (8, 12, 16)
WAIT_BETWEEN = 3
# ETH/USDCプール想定表示件数（3チェーン=Ethereum/Base/Arbitrum × 2手数料=0.05%/0.3%）
EXPECTED_POOL_COUNT = 6
# v1.2 承認1: Selenium の set_window_size はブラウザ枠込みの外寸、Playwright の
# viewport は内寸。1280 のままだと原版より約80px下まで写り、§6が除外を求める
# 「レンジAPRシミュレーション」が入る。980 で原版のクロップ（1484×840相当）に一致。
VIEWPORT = {"width": 1500, "height": 980}


def _judge_incomplete(body: str) -> tuple[bool, str]:
    """描画済みテキストから撮影対象が未完了かどうかを判定する（v1.68）。
    戻り値は (未完了か, 判定内訳の文字列)。
    """
    na = body.count("N/A%")
    err = body.count("GeckoTerminal取得失敗")
    fetching = "Fetching ETH/USDC pool data" in body
    today_count = body.count("TODAY")
    incomplete = na > 0 or err > 0 or fetching or today_count < EXPECTED_POOL_COUNT
    detail = (f"N/A: {na}, GeckoTerminal取得失敗: {err}, "
              f"グローバルローディング表示: {fetching}, "
              f"TODAY件数: {today_count}/{EXPECTED_POOL_COUNT}")
    return incomplete, detail


def capture(full_path: str) -> tuple[bool, str]:
    """成功時 (True, "") を返す。最大試行後も未完了の場合は (False, 判定内訳) を
    返し、呼び出し元はスクリーンショットを保存しない（v1.68・オーナー指示）。
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(URL, wait_until="load", timeout=60_000)
        time.sleep(WAIT_INITIAL)

        last_detail = ""
        for attempt in range(1, MAX_RETRY + 1):
            print(f"[試行 {attempt}/{MAX_RETRY}] Refreshクリック...")
            try:
                page.locator("xpath=//button[contains(text(),'Refresh')]").click(timeout=5_000)
            except Exception as e:  # noqa: BLE001
                print(f"  Refreshボタンが見つかりません: {e}")
            wait_s = WAIT_AFTER_REFRESH_SCHEDULE[min(attempt - 1, len(WAIT_AFTER_REFRESH_SCHEDULE) - 1)]
            print(f"  {wait_s}秒待機（GeckoTerminal/DefiLlamaロード待ち）...")
            time.sleep(wait_s)

            # v1.2 承認2: HTMLソースではなく描画済みテキストを判定対象にする。
            # ソースには JS のリテラル（noteEl.textContent = '⚠ GeckoTerminal取得失敗'）が
            # 常に含まれ、正常時も必ず誤検知して3回空振りしていた。
            body = page.inner_text("body")
            incomplete, last_detail = _judge_incomplete(body)
            if not incomplete:
                print("  ✓ 完了を確認。撮影します。")
                page.screenshot(path=full_path)
                browser.close()
                return True, ""
            print(f"  ✗ 未完了検出（{last_detail}）。再試行...")
            if attempt < MAX_RETRY:
                time.sleep(WAIT_BETWEEN)

        print(f"警告: {MAX_RETRY}回試行後も未完了（{last_detail}）。撮影を見送ります。")
        browser.close()
        return False, last_detail


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


def _write_incomplete_status(out_path: str, detail: str) -> None:
    """v1.68: 最大試行後も未完了だった旨をverify_data.py（C25）向けに記録する。"""
    status_path = Path(out_path).with_name("apr_capture_status.json")
    status_path.write_text(json.dumps({
        "status": "incomplete",
        "attempts": MAX_RETRY,
        "detail": detail,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"記録: {status_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "apr_screenshot.jpg"
    tmp = str(Path(out).with_suffix(".full.png"))
    ok, detail = capture(tmp)
    if not ok:
        Path(tmp).unlink(missing_ok=True)
        _write_incomplete_status(out, detail)
        # v1.68（オーナー承認・方針(b)）: 画像なしで正常終了する。数値データ・
        # インフォグラフィックとは無関係な補助画像1点の欠落でフェーズ1全体を
        # フェイルクローズさせない。
        print("APR画面の読み込みが完了しなかったため、画像なしで終了します（フェイルクローズではなく正常終了）。")
        sys.exit(0)
    crop_apr_cards(tmp, out)
    Path(tmp).unlink(missing_ok=True)
    print(f"✓ 完了: {out}")
