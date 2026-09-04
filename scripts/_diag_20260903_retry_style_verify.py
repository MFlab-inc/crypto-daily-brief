"""診断用一時スクリプト（v1.64・オーナー指示の2点をまとめて9/3データで実LLM検証）。

【1】call_Aリトライへの失敗フィードバック追加後、9/3相当データで
    ・call_Aが1〜2回試行で成功するか
    ・トークン消費が平常水準（入力19,000前後）に近づくか
    ・採用された材料が減っていないか（3件の主要なポイントが維持されるか）
【2】呼び出しAへのです・ます調明示指示後、9/3相当データで
    ・part1_headline・part1_pointsが敬体になるか

【実データでの再構成方法】9/3の実audit_ledger（post_bundle.json・
committed済み）から、全40件のsource・url・title・published_atを
改変なしで抽出し、config/news_sources.jsonのtierマッピングで
tierを機械的に復元した（Reutersのみ個別にtier=2を付与。urlレスの
config登録のため）。抽出順序はcommitted済みaudit_ledgerの配列順そのもの
であり、これは実際の生成時のcandidate_id割当順と一致することを
reasonフィールド中の相互参照（例: id3=FRB Waller発言をid12,18,19,20の
Reuters記事が裏付け、id32・id40がStandard Chartered記事の相互参照）
から確認済み。summaryは永続化されていないためtitleで代用する
（検証目的の近似であることを明記）。

【重要な限界】9/3の1・2試行目の失敗（候補ID[31,39]のペア不成立）は、
LLMの非決定的なサンプリングに起因する。今回の再実行で同一の組み合わせ
（id31=Cointelegraph「Kraken/SoFi提携」・id39=CoinDesk「SoFi/Kraken提携」
——同一事実だが見出しの字面が大きく異なりtitleトークン重複率が低い、
本質的にthreshold付近の際どいケース）を再現できる保証はない。再現した
場合は【1】の3指標を直接比較でき、再現しなかった場合はトークン消費・
採用件数のみ評価し、リトライ機構自体の効果は別途正直に限界として報告する。

daily_data.jsonは9/3の実コミット済みファイルをそのまま使う。本スクリプトは
ANTHROPIC_API_KEYを使い実際にLLMを呼び出す（call_A・call_B）。生成結果は
コミットしない。調査後、本スクリプトとデータファイル・ワークフローは削除する。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

TARGET_DATE = "2026-09-03"
OUT_DIR = Path(f"outputs/{TARGET_DATE}")
DATA_FILE = Path(__file__).parent / "_diag_20260903_data.json"

candidates = json.loads(DATA_FILE.read_text(encoding="utf-8"))
print(f"候補復元: {len(candidates)}件（tier1={sum(1 for c in candidates if c['tier']==1)}・"
      f"tier2={sum(1 for c in candidates if c['tier']==2)}・"
      f"tier3={sum(1 for c in candidates if c['tier']==3)}件）")

OUT_DIR.mkdir(parents=True, exist_ok=True)
(OUT_DIR / "news_candidates.json").write_text(json.dumps({
    "collected_at": "2026-09-04T00:00:00+09:00",
    "target_date_jst": TARGET_DATE,
    "source_status": {},
    "candidates": candidates,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK: {OUT_DIR / 'news_candidates.json'} を一時生成（コミットしない）")

print("\n=== generate_post.run()を実LLMで実行 ===")
client = anthropic.Anthropic()
result = generate_post.run(TARGET_DATE, client=client)

a = result["call_a"]
print(f"call_A: ok={a['ok']} attempts={a['attempts']} error={a['error']}")
print(f"attempt_errors={a['attempt_errors']}")
print(f"level={result['level']}")
print(f"news_candidate_count（選定後・Call Aへ渡した件数）={result['news_candidate_count']}")

if not a["ok"]:
    print("ERROR: call_Aが失敗した。中断する。")
    sys.exit(1)

data = a["data"]
in_tok = a["usage"]["input_tokens"]
out_tok = a["usage"]["output_tokens"]

print("\n=== 【1】判定: リトライ試行回数・トークン消費 ===")
print(f"attempts={a['attempts']}（9/3実運用時は3）")
print(f"call_A input_tokens={in_tok}（平常水準の目安: 19,000前後。9/3実運用時はin=73,509）")
print(f"call_A output_tokens={out_tok}（9/3実運用時はout=15,081）")
reproduced_same_failure = any("候補ID: [31, 39]" in e or "[31, 39]" in e for e in a["attempt_errors"])
print(f"9/3と同一の候補ID[31,39]ペア不成立が再現したか: {reproduced_same_failure}")
if a["attempt_errors"]:
    print("今回のattempt_errors全文:")
    for i, e in enumerate(a["attempt_errors"], 1):
        print(f"  {i}試行目: {e}")

audit_ledger = data.get("audit_ledger", [])
adopted = [e for e in audit_ledger if e.get("decision") in ("採用", "採用（独立2ソース）")]
print(f"\n採用された材料（decision=採用系）: {len(adopted)}件")
for e in adopted:
    print(f"  - [{e.get('decision')}] {e.get('source')}: {e.get('title')[:60]}")
print(f"part1_points（改行区切り）:\n{data.get('part1_points')}")
_points_count = len([ln for ln in str(data.get("part1_points", "")).split("\n") if ln.strip()])
print(f"part1_pointsの箇条書き数: {_points_count}（9/3実運用時は3）")

print("\n=== 【2】判定: です・ます調になっているか ===")
headline = str(data.get("part1_headline", ""))
points = str(data.get("part1_points", ""))
print(f"part1_headline: {headline!r}")
print(f"part1_points: {points!r}")


def _style_check(text: str) -> list[str]:
    import re
    hits = []
    for s in re.split(r"[。\n]", text):
        s = s.strip()
        if not s:
            continue
        core = re.sub(r"[（(][^（）()]*[）)]\s*$", "", s.rstrip("。")).rstrip()
        if not core:
            continue
        if not re.search(r"(です|ます|ました|ません|でした|でしょう|ください)[」』〕）]*$", core):
            hits.append(s)
    return hits


headline_hits = _style_check(headline)
points_hits = _style_check(points)
print(f"\npart1_headline: です・ます以外の文={len(headline_hits)}件: {headline_hits}")
print(f"part1_points: です・ます以外の文={len(points_hits)}件: {points_hits}")

print("\n=== 総括 ===")
print(f"1a. call_A試行回数: {a['attempts']}回（9/3実運用時: 3回）")
print(f"1b. トークン消費: in={in_tok} out={out_tok}（9/3実運用時: in=73,509 out=15,081）")
print(f"1c. 採用材料数: {len(adopted)}件・part1_points箇条書き数: {_points_count}件（9/3実運用時: 3件）")
print(f"2. 文体: headline違反={len(headline_hits)}件・points違反={len(points_hits)}件"
      f"（0件ならです・ます調で統一・9/3実運用時はheadline 3件/points 8件が違反だった）")
