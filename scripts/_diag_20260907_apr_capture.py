"""診断用一時スクリプト（v1.68・APR画面ローディング検知強化のライブ検証）。

実際のダッシュボード（https://ethusdc-apr.netlify.app/）に対し、
scripts/capture_apr.py の capture() を直接呼び出して以下を確認する。
・実DOMに対して_judge_incomplete()が正しく動作するか（例外なく完走するか）
・撮影が成功した場合、6プール分のTODAY・N/A0件を実際に満たしているか
・apr_capture_status.json が意図せず生成されていないか（正常時）
・出力画像のサイズが妥当か（クロップ後、極端に小さい/壊れていないか）

このスクリプトは outputs/ 以下には書き込まず、/tmp 配下にのみ出力する
（コミットしない）。検証後、本スクリプトとワークフローは削除する。
"""
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import capture_apr  # noqa: E402

OUT = "/tmp/_diag_apr_screenshot.jpg"
STATUS_PATH = Path(OUT).with_name("apr_capture_status.json")
STATUS_PATH.unlink(missing_ok=True)

print(f"MAX_RETRY={capture_apr.MAX_RETRY} "
      f"WAIT_AFTER_REFRESH_SCHEDULE={capture_apr.WAIT_AFTER_REFRESH_SCHEDULE} "
      f"EXPECTED_POOL_COUNT={capture_apr.EXPECTED_POOL_COUNT}")

tmp = str(Path(OUT).with_suffix(".full.png"))
ok, detail = capture_apr.capture(tmp)
print(f"\n=== capture() 結果 ===")
print(f"ok={ok}")
print(f"detail={detail!r}")

if ok:
    capture_apr.crop_apr_cards(tmp, OUT)
    Path(tmp).unlink(missing_ok=True)
    size = Path(OUT).stat().st_size
    from PIL import Image
    img = Image.open(OUT)
    print(f"出力画像: {OUT} ({size} bytes, {img.size[0]}x{img.size[1]}px)")
    print(f"apr_capture_status.json が生成されていないこと: {not STATUS_PATH.exists()}")
else:
    capture_apr._write_incomplete_status(OUT, detail)
    print(f"未完了マーカー内容:")
    print(STATUS_PATH.read_text(encoding="utf-8"))
    print("（今回はライブサイトが実際に読み込み未完了だった可能性——"
          "detailを確認し、DefiLlama/GeckoTerminal側の一時的な遅延か、"
          "判定ロジック側の問題かを切り分けてください）")

print("\n=== 総括 ===")
print(f"capture()が例外なく完走: OK")
print(f"最終結果: {'成功（画像あり）' if ok else '未完了（画像なし・マーカー記録）'}")
