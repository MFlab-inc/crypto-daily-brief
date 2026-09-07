#!/usr/bin/env python3
"""v1.69検証用の使い捨て診断スクリプト（非コミット運用・確認後にgit rmする）。
capture_apr.py の新フロー（撮影→検査→リトライ）を実ダッシュボードに対して
2パターンで検証する。outputs/ には一切書き込まない。

パターンA（通常タイミング）: 現行の待機秒数のまま実行し、通常運用で
リグレッションが無いこと（正常に完了・画像が残ること）を確認する。

パターンB（意図的短縮）: WAIT_INITIAL/WAIT_AFTER_REFRESH_SCHEDULE/WAIT_BETWEEN
を1秒に縮め、未完了状態を意図的に作り出す。判定が発火してリトライが実際に
回ること、最終的に完了しなければ画像なし+apr_capture_status.json生成という
フェイルクローズが機能することを確認する。
"""
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import capture_apr  # noqa: E402


def run_mode(mode: str, shrink: bool) -> None:
    workdir = Path(f"/tmp/diag_v169_{mode}")
    workdir.mkdir(parents=True, exist_ok=True)
    tmp = str(workdir / "candidate.full.png")
    out = str(workdir / "apr_screenshot.jpg")

    if shrink:
        capture_apr.WAIT_INITIAL = 1
        capture_apr.WAIT_AFTER_REFRESH_SCHEDULE = (1, 1, 1)
        capture_apr.WAIT_BETWEEN = 1

    print(f"\n===== パターン[{mode}] shrink={shrink} =====")
    print(f"WAIT_INITIAL={capture_apr.WAIT_INITIAL} "
          f"WAIT_AFTER_REFRESH_SCHEDULE={capture_apr.WAIT_AFTER_REFRESH_SCHEDULE} "
          f"WAIT_BETWEEN={capture_apr.WAIT_BETWEEN}")

    ok, detail = capture_apr.capture(tmp)
    print(f"capture() 戻り値: ok={ok} detail={detail!r}")

    # __main__ ブロックと同じ後処理をここで再現する（capture_apr.py自体は未変更で確認）
    if not ok:
        Path(tmp).unlink(missing_ok=True)
        capture_apr._write_incomplete_status(out, detail)
        print("→ 画像なしで終了（フェイルクローズ・正常終了想定）")
    else:
        capture_apr.crop_apr_cards(tmp, out)
        Path(tmp).unlink(missing_ok=True)
        print(f"→ 完了: {out}")

    status_path = Path(out).with_name("apr_capture_status.json")
    print(f"[確認] {out} 存在: {Path(out).exists()}")
    print(f"[確認] {status_path} 存在: {status_path.exists()}")
    if status_path.exists():
        print(f"[確認] status内容: {status_path.read_text(encoding='utf-8')}")


def run_mode_zero(mode: str) -> None:
    """B(1秒)でも実サイトが速すぎて未完了を作れなかったため、0秒まで縮めて
    Refreshクリック直後（ネットワーク往復を待たず）に撮影・検査する。"""
    workdir = Path(f"/tmp/diag_v169_{mode}")
    workdir.mkdir(parents=True, exist_ok=True)
    tmp = str(workdir / "candidate.full.png")
    out = str(workdir / "apr_screenshot.jpg")

    capture_apr.WAIT_INITIAL = 0
    capture_apr.WAIT_AFTER_REFRESH_SCHEDULE = (0, 0, 0)
    capture_apr.WAIT_BETWEEN = 0

    print(f"\n===== パターン[{mode}] 待機ゼロ =====")
    ok, detail = capture_apr.capture(tmp)
    print(f"capture() 戻り値: ok={ok} detail={detail!r}")

    if not ok:
        Path(tmp).unlink(missing_ok=True)
        capture_apr._write_incomplete_status(out, detail)
        print("→ 画像なしで終了（フェイルクローズ・正常終了想定）")
    else:
        capture_apr.crop_apr_cards(tmp, out)
        Path(tmp).unlink(missing_ok=True)
        print(f"→ 完了: {out}")

    status_path = Path(out).with_name("apr_capture_status.json")
    print(f"[確認] {out} 存在: {Path(out).exists()}")
    print(f"[確認] {status_path} 存在: {status_path.exists()}")
    if status_path.exists():
        print(f"[確認] status内容: {status_path.read_text(encoding='utf-8')}")


if __name__ == "__main__":
    run_mode("A_normal", shrink=False)
    run_mode("B_forced_short", shrink=True)
    run_mode_zero("C_zero_wait")
