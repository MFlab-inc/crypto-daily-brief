"""診断用一時スクリプト（8/31のC23 FAIL原因調査・本日分の状況確認の一環）。

2026-08-31の実行でC23のみFAILした（他13項目PASS、level=L0）。
detail: 総括に本文未確認の固有名詞候補（['Base', 'DeFi']）。

実失敗回（daily.yml run_id=33447040302、target_date=2026-08-31）が
GitHub Actionsへ残したデバッグ用アーティファクト（post-draft-2026-08-31、
artifact_id=9778439008）をGitHub REST API経由で直接ダウンロードし、
実際のpart1_points・part2_summary（総括）・reusable_for_summaryを確認する。
「Base」は8/26の実データでC24用allowlistへ既に追加済みの語彙だが、
C23は独立したallowlistを持つため（オーナー指示で意図的に分離）、
C23側にも同様の追加が必要か、あるいは今回は別の文脈での真の指摘かを
判別する。

LLMは呼ばない。コミットは一切行わない。調査後、本スクリプトと
ワークフローは削除する。
"""
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

ARTIFACT_ID = "9778439008"
OWNER = "MFlab-inc"
REPO = "crypto-daily-brief"
TOKEN = os.environ["GH_TOKEN"]

zip_path = Path("/tmp/post-draft-2026-08-31.zip")
extract_dir = Path("/tmp/post-draft-2026-08-31")

url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/artifacts/{ARTIFACT_ID}/zip"
print(f"アーティファクトをダウンロード中: {url}")
result = subprocess.run(
    ["curl", "-sSL", "-w", "\nHTTP_STATUS:%{http_code}\n",
     "-H", f"Authorization: token {TOKEN}",
     "-H", "Accept: application/vnd.github+json",
     "-o", str(zip_path), url],
    capture_output=True, text=True,
)
print(result.stdout)
if result.returncode != 0:
    print(f"curl失敗: returncode={result.returncode} stderr={result.stderr}")
    sys.exit(1)

print(f"ダウンロード完了: {zip_path} ({zip_path.stat().st_size} bytes)")

with zipfile.ZipFile(zip_path) as zf:
    print("=== zip内ファイル一覧 ===")
    for name in zf.namelist():
        print(f"  {name}")
    zf.extractall(extract_dir)

bundle_path = extract_dir / "draft" / "post_bundle.json"
if not bundle_path.exists():
    print(f"post_bundle.jsonが見つかりません: {bundle_path}")
    sys.exit(1)

bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
sections = bundle.get("sections", {})

print("\n=== part1_points（全文） ===")
print(sections.get("part1_points"))

print("\n=== part2_summary（総括・全文） ===")
print(sections.get("part2_summary"))

print("\n=== part2_flow（市場のフロー・全文・参考） ===")
print(sections.get("part2_flow"))

print("\n=== reusable_for_summary ===")
print(json.dumps(bundle.get("reusable_for_summary"), ensure_ascii=False, indent=2))

print("\n=== audit_ledger（tier3・全件） ===")
audit_ledger = bundle.get("audit_ledger") or []
for e in audit_ledger:
    if "Base" in str(e.get("title", "")) or "DeFi" in str(e.get("title", "")) or \
       "base" in str(e.get("url", "")).lower() or "defi" in str(e.get("url", "")).lower():
        print(f"  [候補] source={e.get('source')} decision={e.get('decision')}")
        print(f"    title={e.get('title')!r}")
        print(f"    reason={e.get('reason')!r}")

print(f"\naudit_ledger総件数: {len(audit_ledger)}")
