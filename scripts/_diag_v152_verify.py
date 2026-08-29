"""診断用一時スクリプト（v1.52実データ検証・オーナー指示）。

FRB speeches.xml・testimony.xmlの追加が、実際に8/28のウォーシュFRB議長
ジャクソンホール講演（取りこぼしの発端）を捕捉するかを実測する。

news_candidates.json は daily.yml のコミット対象外のため、実測は
collect_news.collect_news() を今このジョブ上で実行して行う。
コミット済みの outputs/2026-08-28/daily_data.json をそのまま使う
（このジョブのローカルディスク上でのみ参照・書き込みはしない）。

調査後、本スクリプトとワークフローは削除する。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import compose_post  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

TARGET = "2026-08-28"
daily_data = json.loads(Path(f"outputs/{TARGET}/daily_data.json").read_text(encoding="utf-8"))

print(f"=== collect_news.collect_news() を対象日{TARGET}で実行（実RSS取得） ===")
news = collect_news.collect_news(TARGET)
candidates = news["candidates"]
by_tier = {}
for c in candidates:
    by_tier.setdefault(c.get("tier"), []).append(c)
for tier in sorted(by_tier, key=lambda x: (x is None, x)):
    print(f"  tier={tier}: {len(by_tier[tier])}件")
print()

print("=== FRB関連候補一覧（tier1） ===")
frb_candidates = [c for c in by_tier.get(1, []) if "FRB" in str(c.get("source", ""))]
for c in frb_candidates:
    print(f"  - source={c.get('source')} [{c.get('published_at')}] {c.get('title')}")
print()

print("=== ウォーシュ議長ジャクソンホール講演の捕捉確認 ===")
hits = [c for c in candidates
        if "warsh" in str(c.get("title", "")).lower() or "jackson" in str(c.get("title", "")).lower()]
if hits:
    print(f"*** {len(hits)}件ヒット ***")
    for h in hits:
        print(f"  source={h.get('source')} tier={h.get('tier')} [{h.get('published_at')}] {h.get('title')}")
        print(f"    url={h.get('url')}")
else:
    print("ヒットなし（news_sources.jsonのFRB speeches.xmlが対象日を過ぎて記事をローテートした可能性。"
          "実行時刻によっては再現しないことがある——DESIGN_CHANGES.mdに正直に記録する）")
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

selected, stats = generate_post._select_candidates_for_call_a(candidates)
bundle = compose_post.compose(daily_data, {
    "level": "L0" if (a.ok and b.ok) else "L1",
    "call_a": a.to_dict(),
    "call_b": b.to_dict(),
    "news_source_status": news.get("source_status", {}),
    "news_candidate_count": len(selected),
    "total_usage": {"input_tokens": 0, "output_tokens": 0},
})

print()
print("=== 生成された本文にウォーシュ講演への言及があるか（目視確認用） ===")
sections = bundle.get("sections", {})
for key in ("part1_headline", "part1_points", "part2_flow", "part2_summary"):
    text = sections.get(key, "")
    if "ウォーシュ" in text or "Warsh" in text or "ジャクソンホール" in text:
        print(f"  [{key}] 言及あり:")
        print(f"    {text}")
print()

print("=== verify_post.run_all() 監査結果 ===")
au = verify_post.run_all(bundle, daily_data)
for c in au.checks:
    print(f"{c['id']} {c['result']} - {(c.get('detail') or '')[:200]}")
print(f"failed={au.failed}")
