"""診断用一時スクリプト（8/30 C22 FAILの原因調査・オーナー指示）。

2026-08-30の実行でC22のみFAILした（tier1裏付け・独立2ソース・
notable_moveのいずれも不成立）。オーナーはCronosのネットワーク停止を
CoinDeskとCointelegraph両方が報じていたはずと確認済みで、独立2ソース
として採用されなかった原因を求めている。

【方針転換】当初はcollect_news.pyを本ジョブ上で再実行してtier3候補を
直接確認する方針だったが、CoinDesk/CointelegraphのRSSは高頻度更新の
ローリングウィンドウであり、1日以上経過すると対象日時点の記事が
既に入れ替わってしまうことが実行結果から判明した（Cronos関連記事が
1件も残っていなかった）。そのため、実際の失敗回（run_id=33339632874）
がGitHub Actions上へ残したデバッグ用アーティファクト
（post-draft-2026-08-30, artifact_id=9740143390）をGitHub REST API経由で
このジョブ上から直接ダウンロードし、当時のnews_candidates由来の
audit_ledger（draft/post_generation.json）を直接確認する方式に切り替える
（このジョブはGitHub Actionsランナー上で動くため、セッションのサンド
ボックスとは異なりAzure Blob Storageへの実アクセスに制限が無い）。

LLMは呼ばない（無料・決定論的）。generate_post.pyのペア検出ロジック
（_tokenize_title/_overlap_coefficient/_find_independent_pairs）を
実際のcandidate_id・titleにそのまま適用する。

調査後、本スクリプトとワークフローは削除する。
"""
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, "scripts")
import generate_post  # noqa: E402

ARTIFACT_ID = "9740143390"
OWNER = "MFlab-inc"
REPO = "crypto-daily-brief"
TOKEN = os.environ["GH_TOKEN"]

zip_path = Path("/tmp/post-draft-2026-08-30.zip")
extract_dir = Path("/tmp/post-draft-2026-08-30")

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

gen_path = extract_dir / "draft" / "post_generation.json"
if not gen_path.exists():
    print(f"post_generation.jsonが見つかりません: {gen_path}")
    print("extract_dir配下:")
    for p in extract_dir.rglob("*"):
        print(f"  {p}")
    sys.exit(1)

gen = json.loads(gen_path.read_text(encoding="utf-8"))
audit_ledger = gen.get("call_a", {}).get("data", {}).get("audit_ledger", [])
print(f"\naudit_ledger件数: {len(audit_ledger)}")

# 注意: _reconstruct_audit_ledger()が書き出す最終エントリは
# _AUDIT_LEDGER_STATIC_FIELDS=(source, url, title, published_at) +
# verified_by/decision/reason のみで、candidate_id・tier・use・
# pairs_with_candidate_id は含まれない（generate_post.py参照）。
# tier3（CoinDesk・Cointelegraph）はsource名で識別する。
TIER3_SOURCES = {"CoinDesk", "Cointelegraph"}
print("\n=== tier3エントリ全件（CoinDesk・Cointelegraph、source名で識別） ===")
tier3_entries = [e for e in audit_ledger if e.get("source") in TIER3_SOURCES]
for e in tier3_entries:
    print(f"  source={e.get('source')} decision={e.get('decision')}")
    print(f"    title={e.get('title')!r}")
    print(f"    url={e.get('url')}")
    print(f"    reason={e.get('reason')!r}")

print("\n=== Cronos関連候補の特定（タイトル/urlに'cronos'を含むもの） ===")
cronos_entries = [e for e in tier3_entries
                   if "cronos" in str(e.get("title", "")).lower()
                   or "cronos" in str(e.get("url", "")).lower()]
for e in cronos_entries:
    print(f"  source={e.get('source')} decision={e.get('decision')}")
    print(f"    title={e.get('title')!r}")
    print(f"    reason={e.get('reason')!r}")

if len(cronos_entries) >= 2:
    print("\n=== Cronos候補間のoverlap係数（実タイトル・実アルゴリズム） ===")
    for i in range(len(cronos_entries)):
        for j in range(i + 1, len(cronos_entries)):
            a, b = cronos_entries[i], cronos_entries[j]
            a_tok = generate_post._tokenize_title(a.get("title", ""))
            b_tok = generate_post._tokenize_title(b.get("title", ""))
            sim = generate_post._overlap_coefficient(a_tok, b_tok)
            same_source = a.get("source") == b.get("source")
            print(f"  [{a.get('source')}] vs [{b.get('source')}] "
                  f"(同一source={same_source}): overlap={sim:.4f}")
            print(f"    A({a.get('source')}) title={a.get('title')!r}")
            print(f"    A tokens({len(a_tok)}): {sorted(a_tok)}")
            print(f"    B({b.get('source')}) title={b.get('title')!r}")
            print(f"    B tokens({len(b_tok)}): {sorted(b_tok)}")
            print(f"    共通({len(a_tok & b_tok)}): {sorted(a_tok & b_tok)}")
            print(f"    0.4で合格: {sim >= 0.4} / 0.3で合格: {sim >= 0.3}")
else:
    print(f"\nCronos関連候補が{len(cronos_entries)}件のみ検出（2件必要）。"
          "タイトルに'cronos'が含まれない表記の可能性あり。上記tier3全件の目視確認結果を参照。")

print("\n=== part1_points（実際にpart1_pointsへ採用された内容） ===")
print(gen.get("call_a", {}).get("data", {}).get("part1_points"))

print("\n=== part1_headline ===")
print(gen.get("call_a", {}).get("data", {}).get("part1_headline"))
