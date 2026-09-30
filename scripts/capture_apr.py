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

v1.69（オーナー指示・9/6対象日で同一症状が疑われた件の対処）: 実際には
9/6対象日の自動実行はv1.68適用前のコミットで動いており（v1.68の反映が
実行後だった）、v1.68のロジック自体はまだ本番で一度も実行されていな
かったことが調査で判明した。ただし調査の過程でv1.68の実装には別の構造
的リスクが見つかった——判定（`body = page.inner_text("body")`）と撮影
（`page.screenshot()`）が別呼び出しに分かれており、両者の間に分岐と
print呼び出しが挟まる。この間隔自体は実測上ごく短いが、「判定に通った
画面」と「実際に撮影した画面」が理論上別物になり得る余地を残していた。
オーナー指示によりこれを解消する: 撮影を先に行い、撮影直後（間に待機・
分岐を挟まない）のDOMを検査対象にする。これにより検査対象は常に
「実際に撮影した画面」そのものになる。判定・撮影の呼び出し順が入れ替わる
だけで、検知条件（`_judge_incomplete()`）自体は変更しない。

v1.83（オーナー承認・2026-09-30。9/29対象日にAPR画像が欠落した件への対処）:
9/29は3回の試行がすべて「N/A 0・GeckoTerminal取得失敗 0・ローディング False・
TODAY 0/6」で終わった。ダッシュボードは、DefiLlama Yields APIの一覧取得が成功
すれば（該当プールが0件でも）Baseの合成カード2枚を必ず描画するため、TODAY 0件は
「一覧取得そのものが失敗しエラー表示になった」ことを示す（ダッシュボードのコード
から推定）。ただし従来の実装は件数しか記録せず、失敗の具体的な種類（HTTPエラー・
ネットワーク遮断・応答の異常等）を特定できなかった。次の2点を追加する。
  対策1（失敗時の診断）: 未完了と判定した試行ごとに、画面の文字（先頭500字）・
      エラー表示・コンソールエラー・ページ内例外・yields.llama.fi／
      api.geckoterminal.comの応答状態（HTTPステータスと一部ヘッダー）・要求失敗を
      ログへ出す。失敗した試行の画像と診断JSONは、リポジトリにコミットされない
      apr_diagnostics/<対象日>/ へ保存し、GitHub Actionsのアーティファクトにだけ
      含める（outputs/には置かない。⑤コミットが outputs/ をgit addするため）。
      診断は補助であり、診断側の失敗で撮影を妨げない。
  対策2（追加試行）: 標準の3試行がすべて未完了の場合、約60秒空けてページを再読み込み
      してから追加で2試行する（再読み込みで画面の状態も初期化する）。上流APIの
      一時的な障害・レート制限が数十秒〜数分続く場合に備える。失敗した日だけ実行
      時間が延びる（最大でおよそ+3分）。追加試行を含めても未完了なら従来どおり
      画像なしで正常終了し（フェイルクローズ方針(b)は不変）、attempts に実際の
      試行回数を記録する。

使い方: python capture_apr.py <出力jpgパス>
"""
from __future__ import annotations

import json
import os
import re
import shutil
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
# v1.83（オーナー承認）: 標準の3試行がすべて未完了のとき、約60秒空けてページを
# 再読み込みしてから追加で試行する回数・待機秒数。
EXTRA_ATTEMPTS = 2
EXTRA_COOLDOWN = 60
# v1.83: 診断（失敗時の原因調査用の記録）。DIAG_HOSTSはダッシュボードが依存する外部API。
# 失敗画像・診断JSONの保存先はリポジトリ直下（outputs/の外。⑤コミットの対象外）。
DIAG_DIR_ROOT = "apr_diagnostics"
DIAG_HOSTS = ("yields.llama.fi", "api.geckoterminal.com")
DIAG_BODY_CHARS = 500
DIAG_MAX_EVENTS = 60
DIAG_HEADERS = ("server", "cf-mitigated", "cf-ray", "retry-after", "content-type", "content-length")
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


class _Diagnostics:
    """v1.83（オーナー承認）: 失敗時の原因調査用の記録。

    ブラウザのイベント（コンソール・ページ内例外・yields.llama.fi等の応答・要求失敗）
    を試行番号つきで貯め、未完了と判定した試行のスナップショット（画面の文字・
    エラー表示・関連イベント）をログへ出す。診断は補助であり、どの処理も例外を
    外へ出さない（診断の失敗で撮影を妨げない）。attempt 0 は最初のページ読み込み
    （初回の自動取得）、1以降は各試行。
    """

    def __init__(self, diag_dir: "Path | None" = None):
        self.diag_dir = Path(diag_dir) if diag_dir else None
        self.attempt = 0
        self.t0 = time.monotonic()
        self.events: list[dict] = []
        self.snapshots: list[dict] = []

    def start_attempt(self, n: int) -> None:
        self.attempt = n
        self.t0 = time.monotonic()

    def _add(self, **kw) -> None:
        if len(self.events) < DIAG_MAX_EVENTS:
            self.events.append({"attempt": self.attempt, "t": round(time.monotonic() - self.t0, 1), **kw})

    def attach(self, page) -> None:
        for name, handler in (("console", self._on_console), ("pageerror", self._on_pageerror),
                              ("response", self._on_response), ("requestfailed", self._on_requestfailed)):
            try:
                page.on(name, handler)
            except Exception as e:  # noqa: BLE001
                print(f"  （診断: {name}リスナーを登録できません: {type(e).__name__}: {e}）")

    def _on_console(self, msg) -> None:
        try:
            if getattr(msg, "type", "") in ("error", "warning"):
                self._add(kind="console", level=msg.type, text=str(msg.text)[:300])
        except Exception:  # noqa: BLE001
            pass

    def _on_pageerror(self, err) -> None:
        try:
            self._add(kind="pageerror", text=str(err)[:300])
        except Exception:  # noqa: BLE001
            pass

    def _on_response(self, resp) -> None:
        try:
            url = str(resp.url)
            if not any(h in url for h in DIAG_HOSTS):
                return
            headers = {}
            try:
                raw = resp.headers or {}
                headers = {k: str(raw[k])[:80] for k in DIAG_HEADERS if k in raw}
            except Exception:  # noqa: BLE001
                pass
            self._add(kind="response", url=url.split("?")[0][:200], status=resp.status, headers=headers)
        except Exception:  # noqa: BLE001
            pass

    def _on_requestfailed(self, req) -> None:
        try:
            failure = req.failure
            if isinstance(failure, dict):
                failure = failure.get("errorText")
            self._add(kind="requestfailed", url=str(req.url).split("?")[0][:200], failure=str(failure)[:200])
        except Exception:  # noqa: BLE001
            pass

    def note(self, text: str) -> None:
        self._add(kind="note", text=text[:300])

    def _attempt_events(self, n: int) -> list[dict]:
        # 試行1には最初のページ読み込み（attempt 0）の初回取得も含める
        wanted = {n, 0} if n == 1 else {n}
        return [e for e in self.events if e["attempt"] in wanted]

    def snapshot(self, n: int, body: str, judge_detail: str) -> dict:
        collapsed = re.sub(r"\s+", " ", body or "").strip()
        banner = re.search(r"Error:[^\n]*(?:\n[^\n]*)?", body or "")
        evs = self._attempt_events(n)
        yields = [e for e in evs if e.get("kind") in ("response", "requestfailed") and "yields.llama.fi" in e.get("url", "")]
        return {
            "attempt": n,
            "judge": judge_detail,
            "body_head": collapsed[:DIAG_BODY_CHARS],
            "error_banner": banner.group(0).replace("\n", " ")[:300] if banner else None,
            "yields_llama_fi": yields,
            "events": evs,
        }

    @staticmethod
    def format_lines(snap: dict) -> list[str]:
        n = snap["attempt"]
        lines = [f"  診断[試行{n}] 画面の文字(先頭{DIAG_BODY_CHARS}字): {snap['body_head'] or '（空）'}"]
        lines.append(f"  診断[試行{n}] エラー表示: {snap['error_banner'] or 'なし（Error:の表示は見つからない）'}")
        y = snap["yields_llama_fi"]
        if y:
            parts = []
            for e in y:
                if e["kind"] == "response":
                    hdr = ",".join(f"{k}={v}" for k, v in (e.get("headers") or {}).items())
                    parts.append(f"HTTP {e['status']}（{e['t']}秒{', ' + hdr if hdr else ''}）")
                else:
                    parts.append(f"要求失敗 {e['failure']}（{e['t']}秒）")
            lines.append(f"  診断[試行{n}] yields.llama.fi の応答: " + " / ".join(parts))
        else:
            lines.append(f"  診断[試行{n}] yields.llama.fi の応答: 応答・失敗イベントなし（要求が発行されていない・保留中・イベント取得不可のいずれか）")
        others = [e for e in snap["events"] if e.get("kind") in ("response", "requestfailed") and "yields.llama.fi" not in e.get("url", "")]
        if others:
            lines.append(f"  診断[試行{n}] その他の外部要求: " + " / ".join(
                (f"{e['url']} → HTTP {e['status']}" if e["kind"] == "response" else f"{e['url']} → 失敗 {e['failure']}") for e in others))
        errs = [e for e in snap["events"] if e.get("kind") in ("console", "pageerror")]
        if errs:
            lines.append(f"  診断[試行{n}] コンソール・ページ内エラー: " + " / ".join(
                f"[{e.get('level') or e['kind']}] {e['text']}" for e in errs[:8]))
        return lines

    def record_failure(self, n: int, body: str, judge_detail: str, screenshot_path: "str | None") -> None:
        """未完了と判定した試行の診断をログへ出し、失敗画像・診断JSONを保存する。"""
        try:
            snap = self.snapshot(n, body, judge_detail)
            self.snapshots.append(snap)
            for line in self.format_lines(snap):
                print(line)
            if self.diag_dir is not None:
                self.diag_dir.mkdir(parents=True, exist_ok=True)
                if screenshot_path and Path(screenshot_path).exists():
                    shutil.copy(screenshot_path, self.diag_dir / f"apr_failed_attempt{n}.png")
                (self.diag_dir / "apr_diagnostics.json").write_text(
                    json.dumps({"url": URL, "snapshots": self.snapshots}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"  （診断の記録に失敗しました。撮影は続行します: {type(e).__name__}: {e}）")


def _click_refresh(page) -> None:
    try:
        page.locator("xpath=//button[contains(text(),'Refresh')]").click(timeout=5_000)
    except Exception as e:  # noqa: BLE001
        print(f"  Refreshボタンが見つかりません: {e}")


def capture(full_path: str, diag_dir: "str | Path | None" = None) -> tuple[bool, str, int]:
    """成功時 (True, "", 試行回数) を返す。最大試行後も未完了の場合は
    (False, 判定内訳, 試行回数) を返し、呼び出し元はスクリーンショットを保存しない
    （v1.68・オーナー指示）。

    v1.83: 標準の3試行（Refresh後の待機 8→12→16秒）がすべて未完了なら、約60秒空けて
    ページを再読み込みしてから追加で2試行する。未完了の試行ごとに診断をログへ出し、
    失敗画像・診断JSONはdiag_dir（リポジトリ管理外。アーティファクト専用）へ保存する。
    """
    from playwright.sync_api import sync_playwright

    diag = _Diagnostics(diag_dir)
    total_attempts = MAX_RETRY + EXTRA_ATTEMPTS
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT)
        diag.attach(page)
        diag.start_attempt(0)
        page.goto(URL, wait_until="load", timeout=60_000)
        time.sleep(WAIT_INITIAL)

        last_detail = ""
        for attempt in range(1, total_attempts + 1):
            extra = attempt > MAX_RETRY
            try:
                if extra:
                    print(f"[追加試行 {attempt - MAX_RETRY}/{EXTRA_ATTEMPTS}] {EXTRA_COOLDOWN}秒空けてページを再読み込み...")
                    time.sleep(EXTRA_COOLDOWN)
                    # 診断の経過秒は再読み込みの時点から数える（空けた待機を含めない）
                    diag.start_attempt(attempt)
                    page.goto(URL, wait_until="load", timeout=60_000)
                    time.sleep(WAIT_INITIAL)
                else:
                    diag.start_attempt(attempt)
                    print(f"[試行 {attempt}/{MAX_RETRY}] Refreshクリック...")
                _click_refresh(page)
                wait_s = WAIT_AFTER_REFRESH_SCHEDULE[min(attempt - 1, len(WAIT_AFTER_REFRESH_SCHEDULE) - 1)]
                print(f"  {wait_s}秒待機（GeckoTerminal/DefiLlamaロード待ち）...")
                time.sleep(wait_s)

                # v1.69（オーナー承認）: 先に撮影し、撮影直後（間に待機・分岐を
                # 挟まない）のDOMを検査対象にする。「判定に通った画面」ではなく
                # 「実際に撮影した画面」を検査するため、撮影→検査の順に固定する。
                page.screenshot(path=full_path)
                # v1.2 承認2: HTMLソースではなく描画済みテキストを判定対象にする。
                # ソースには JS のリテラル（noteEl.textContent = '⚠ GeckoTerminal取得失敗'）が
                # 常に含まれ、正常時も必ず誤検知して3回空振りしていた。
                body = page.inner_text("body")
            except Exception as e:  # noqa: BLE001
                # 追加試行中の例外（再読み込みの失敗・ブラウザ側の不調）は、標準試行の
                # 未完了を「画像なしの正常終了」で確定させる方針(b)を崩さないよう、
                # 失敗した試行として扱う（標準試行中の例外は従来どおり呼び出し元へ）。
                if not extra:
                    raise
                last_detail = f"追加試行{attempt - MAX_RETRY}で例外: {type(e).__name__}: {e}"[:300]
                print(f"  ✗ {last_detail}")
                diag.note(last_detail)
                continue
            incomplete, last_detail = _judge_incomplete(body)
            if not incomplete:
                print("  ✓ 撮影画像の完了を確認。" if attempt == 1 else f"  ✓ 撮影画像の完了を確認（{attempt}回目の試行で成功）。")
                browser.close()
                return True, "", attempt
            print(f"  ✗ 撮影画像が未完了（{last_detail}）。" + ("再試行..." if attempt < total_attempts else ""))
            diag.record_failure(attempt, body, last_detail, full_path)
            if attempt < MAX_RETRY:
                time.sleep(WAIT_BETWEEN)

        print(f"警告: {total_attempts}回試行（標準{MAX_RETRY}＋追加{EXTRA_ATTEMPTS}）後も未完了（{last_detail}）。撮影を見送ります。")
        browser.close()
        return False, last_detail, total_attempts


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


def _write_incomplete_status(out_path: str, detail: str, attempts: int = MAX_RETRY) -> None:
    """v1.68: 最大試行後も未完了だった旨をverify_data.py（C25）向けに記録する。
    v1.83: attemptsは追加試行を含む実際の試行回数（標準MAX_RETRY回＋追加）。"""
    status_path = Path(out_path).with_name("apr_capture_status.json")
    status_path.write_text(json.dumps({
        "status": "incomplete",
        "attempts": attempts,
        "standard_attempts": MAX_RETRY,
        "extra_attempts": max(0, attempts - MAX_RETRY),
        "detail": detail,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"記録: {status_path}")


def _diag_dir_for(out_path: str) -> Path:
    """診断（失敗画像・診断JSON）の保存先。outputs/の外（リポジトリ直下のapr_diagnostics/
    <対象日>/）。⑤コミットは outputs/ だけをgit addするため、ここはコミットされず、
    フェーズ1のアーティファクトにだけ含まれる。環境変数APR_DIAG_DIRで上書きできる。"""
    root = os.environ.get("APR_DIAG_DIR") or DIAG_DIR_ROOT
    return Path(root) / Path(out_path).resolve().parent.name


def main(argv: "list[str] | None" = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = argv[0] if argv else "apr_screenshot.jpg"
    tmp = str(Path(out).with_suffix(".full.png"))
    diag_dir = _diag_dir_for(out)
    ok, detail, attempts = capture(tmp, diag_dir)
    if not ok:
        Path(tmp).unlink(missing_ok=True)
        _write_incomplete_status(out, detail, attempts)
        # v1.68（オーナー承認・方針(b)）: 画像なしで正常終了する。数値データ・
        # インフォグラフィックとは無関係な補助画像1点の欠落でフェーズ1全体を
        # フェイルクローズさせない。
        print(f"診断（失敗画像・診断JSON）: {diag_dir}（アーティファクトにのみ含まれ、コミットされない）")
        print("APR画面の読み込みが完了しなかったため、画像なしで終了します（フェイルクローズではなく正常終了）。")
        return 0
    crop_apr_cards(tmp, out)
    Path(tmp).unlink(missing_ok=True)
    print(f"✓ 完了: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
