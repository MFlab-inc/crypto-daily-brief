"""診断用一時スクリプト（v1.56・part2_flow材料制限プロンプト修正の実データ検証・
オーナー指示：「実装後、8/29のデータ（土曜）で再実行し、C24がpart2_flowの
ETF・Polygonの記述を検出してFAILすること」を確認する）。

2026-08-29（実インシデント発生日・土曜）データでcall_A〜監査を複数回独立
実行し、プロンプト修正（part2_flowをpart1_points採用済み材料に限定）が
実際にreusable_for_summary由来材料（ETF資金流出・Polygon脆弱性）の
part2_flowへの混入を防ぐかどうかを観察する。

プロンプト修正が完全に効けば、C24は「候補なし」または「候補はあるが
part1_pointsに存在」でPASSし続けるはず（=漏れが再現しない）。もし
プロンプト修正をすり抜けて漏れが再現した場合は、C24がFAILすることで
機械的に検出される（バックストップとして機能）。どちらの結果であれ、
ありのまま報告する。

対象日が土曜であるため、part2_flowにETF言及が生じた場合は
ETF_WEEKEND_GUIDANCE（金額非表示・「直近営業日までの確定値」明記）の
遵守状況もあわせて観察する（生じない場合は対象外・SKIP扱いで報告）。

news_candidates.json は daily.yml のコミット対象外のため、実測は
collect_news.collect_news() を今このジョブ上で実行して行う。
コミット済みの outputs/2026-08-29/daily_data.json をそのまま使う
（このジョブのローカルディスク上でのみ参照・書き込みはしない）。

調査後、本スクリプトとワークフローは削除する。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import compose_post  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

TARGET = "2026-08-29"
daily_data = json.loads(Path(f"outputs/{TARGET}/daily_data.json").read_text(encoding="utf-8"))
print(f"target_date_jst={TARGET} weekday_jp={daily_data.get('weekday_jp')}")
client = anthropic.Anthropic()

N_RUNS = 3
# 実インシデント（2026-08-29実データ）でpart2_flowに漏れていた材料語
LEAK_MARKERS = ["Polygon", "ポリゴン", "ETF"]

pair_overlap_threshold = generate_post.load_pair_overlap_threshold()
print(f"pair_overlap_threshold={pair_overlap_threshold}")

summary_rows = []

for run_no in range(1, N_RUNS + 1):
    print(f"\n=== Run {run_no}/{N_RUNS} ===")
    news = collect_news.collect_news(TARGET)
    a = generate_post.call_a(client, daily_data, news, None, pair_overlap_threshold)
    print(f"call_A: ok={a.ok} attempts={a.attempts} error={a.error}")
    if not a.ok:
        print("call_A失敗。このrunの以降の検証をスキップします。")
        summary_rows.append((run_no, "call_A失敗", None, None))
        continue

    b = generate_post.call_b(client, daily_data, a.data)
    print(f"call_B: ok={b.ok} attempts={b.attempts}")
    if not b.ok:
        print("call_B失敗。このrunの以降の検証をスキップします。")
        summary_rows.append((run_no, "call_B失敗", None, None))
        continue

    selected, _stats = generate_post._select_candidates_for_call_a(
        news.get("candidates", []), pair_overlap_threshold)
    gen = {
        "level": "L0",
        "call_a": a.to_dict(),
        "call_b": b.to_dict(),
        "news_source_status": news.get("source_status", {}),
        "news_candidate_count": len(selected),
        "total_usage": {"input_tokens": 0, "output_tokens": 0},
    }
    bundle = compose_post.compose(daily_data, gen)
    sections = bundle.get("sections", {})
    part1_headline = sections.get("part1_headline", "")
    part1_points = sections.get("part1_points", "")
    part2_flow = sections.get("part2_flow", "")

    print(f"part1_headline: {part1_headline[:150]}")
    print(f"--- part2_flow（全文） ---\n{part2_flow}")

    leaked = [m for m in LEAK_MARKERS if m in part2_flow]
    print(f"LEAK_MARKERSのpart2_flow内出現: {leaked if leaked else 'なし'}")

    etf_note = "対象外（ETF言及なし）"
    if "ETF" in part2_flow:
        has_amount = bool(re.search(r"[\d,]+\s*(億|万|百万)?\s*(ドル|円|USD|\$)", part2_flow))
        has_confirmed_phrase = ("直近営業日" in part2_flow) and ("確定値" in part2_flow)
        etf_note = (f"ETF言及あり: 金額らしき記載={'あり(規定違反の可能性)' if has_amount else 'なし'} / "
                    f"「直近営業日までの確定値」明記={'あり' if has_confirmed_phrase else 'なし'}")
        print(f"ETF_WEEKEND_GUIDANCE遵守状況: {etf_note}")

    au = verify_post.run_all(bundle, daily_data)
    c24 = next((c for c in au.checks if c["id"] == "C24_flow_no_unadopted_material"), None)
    c24_result = c24["result"] if c24 else "N/A"
    print(f"C24_flow_no_unadopted_material: {c24_result} - {(c24.get('detail') or '')[:250] if c24 else ''}")
    print(f"overall failed={au.failed}")
    if au.failed:
        print("FAILしたcheck一覧:")
        for c in au.checks:
            if c["result"] == "FAIL":
                print(f"  {c['id']}: {(c.get('detail') or '')[:200]}")

    summary_rows.append((run_no, c24_result, leaked, etf_note))

print()
print("=== まとめ（3回分） ===")
for run_no, c24_result, leaked, etf_note in summary_rows:
    print(f"Run{run_no}: C24={c24_result} leak_markers={leaked} etf={etf_note}")

reproduced = [r for r in summary_rows if r[2]]
print()
if reproduced:
    print(f"プロンプト修正後もLEAK_MARKERSがpart2_flowに再出現した回数: {len(reproduced)}/{N_RUNS}")
    print("→ プロンプト修正だけでは完全には防げていない。C24が実際にFAILとして"
          "捕捉できているかを上記のC24結果で確認すること。")
else:
    print(f"プロンプト修正後、{N_RUNS}回ともLEAK_MARKERS（Polygon/ETF等）は"
          "part2_flowに再出現しなかった。")
    print("→ この場合、C24のFAIL再現は今回は直接観察できない"
          "（C24自体の検出力は既にコミット済み実データへの直接テストで確認済み）。")
