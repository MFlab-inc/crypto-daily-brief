"""診断用一時スクリプト（v1.53実データ検証・オーナー指示）。

経済カレンダー（scheduled_events）機能を実データで検証する。
1) 対象日2026-08-28で、ウォーシュ講演・PCE等が実際にHighインパクトとして
   取得されるか（8/28再現・sparsity確認）
2) Highインパクトの件数（オーナー指定のsparsity確認——少なすぎるようなら
   Mediumも含める方向で報告）
3) call_A〜監査までの一連の流れに影響が無いか
4) 生成された本文にscheduled_eventsの内容が、対応するRSS候補の裏付けなく
   直接書かれていないか（目視確認・機械監査は未実装のため人力で確認）

news_candidates.json は daily.yml のコミット対象外のため、実測は
collect_news.collect_news() を今このジョブ上で実行して行う。
コミット済みの outputs/2026-08-28/daily_data.json をそのまま使う
（このジョブのローカルディスク上でのみ参照・書き込みはしない）。

調査後、本スクリプトとワークフローは削除する。
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import compose_post  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

TARGET = "2026-08-28"
daily_data = json.loads(Path(f"outputs/{TARGET}/daily_data.json").read_text(encoding="utf-8"))

print(f"=== fetch_economic_calendar() を対象日{TARGET}で実行（実JSON取得） ===")
window_start, window_end = collect_news.collection_window_ny(date.fromisoformat(TARGET))
scheduled_events = collect_news.fetch_economic_calendar(window_start, window_end)
print(f"\nHighインパクトイベント件数: {len(scheduled_events)}件")
for e in scheduled_events:
    print(f"  - [{e['time_jst']}] {e['country']} {e['title']}")
daily_data["scheduled_events"] = scheduled_events
print()

print(f"=== collect_news.collect_news() を対象日{TARGET}で実行（実RSS取得） ===")
news = collect_news.collect_news(TARGET)
print()

print("=== 呼び出しA〜監査の一連の流れ確認（実API使用） ===")
client = anthropic.Anthropic()
a = generate_post.call_a(client, daily_data, news, None)
print(f"call_A: ok={a.ok} attempts={a.attempts} error={a.error}")
if a.ok:
    print(f"input_tokens={a.usage['input_tokens']} output_tokens={a.usage['output_tokens']}")
print(f"attempt_errors={a.attempt_errors}")

if not a.ok:
    print("call_A失敗。以降の検証をスキップします。")
    sys.exit(0)

b = generate_post.call_b(client, daily_data, a.data)
print(f"call_B: ok={b.ok} attempts={b.attempts} error={b.error}")

selected, stats = generate_post._select_candidates_for_call_a(news["candidates"])
bundle = compose_post.compose(daily_data, {
    "level": "L0" if (a.ok and b.ok) else "L1",
    "call_a": a.to_dict(),
    "call_b": b.to_dict(),
    "news_source_status": news.get("source_status", {}),
    "news_candidate_count": len(selected),
    "total_usage": {"input_tokens": 0, "output_tokens": 0},
})

print()
print("=== 生成された本文全文（scheduled_eventsの直接引用が無いか目視確認用） ===")
sections = bundle.get("sections", {})
for key in ("part1_headline", "part1_points", "part2_flow", "part2_summary"):
    print(f"--- {key} ---")
    print(sections.get(key, ""))
    print()

print("=== scheduled_eventsのタイトルが本文に直接（対応候補なしで）出現していないか簡易チェック ===")
full_text = "\n".join(sections.get(k, "") for k in ("part1_headline", "part1_points", "part2_flow", "part2_summary"))
for e in scheduled_events:
    # 完全一致でのタイトル出現のみを機械的にチェックする（簡易・厳密な保証ではない）。
    if e["title"] in full_text:
        print(f"  注意: scheduled_eventsのタイトルが本文に完全一致で出現: {e['title']!r}"
              f"（対応するRSS候補の裏付けがあるか目視確認が必要）")
    else:
        print(f"  OK: {e['title']!r} は本文に完全一致では出現しない（言い換えられているか未使用）")

print()
print("=== verify_post.run_all() 監査結果 ===")
au = verify_post.run_all(bundle, daily_data)
for c in au.checks:
    print(f"{c['id']} {c['result']} - {(c.get('detail') or '')[:200]}")
print(f"failed={au.failed}")
