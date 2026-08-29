"""診断用一時スクリプト（v1.51実データ検証・オーナー指示）。

Google News RSSのsite:演算子修正とtier4候補数上限（TIER4_CANDIDATE_LIMIT）の
効果を実測する。
1) Google News RSSが実際に0件でなくなったか
2) tier4候補数上限が実データでも正しく機能するか
3) 呼び出しA〜監査までの一連の流れに悪影響が無いか

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
tier4 = by_tier.get(4, [])
print(f"\ntier4（Google News）実測: {len(tier4)}件")
for c in tier4[:10]:
    print(f"  - [{c.get('published_at')}] {c.get('title')} (source={c.get('source')})")
print()

print("=== _select_candidates_for_call_a() の選定結果確認 ===")
selected, stats = generate_post._select_candidates_for_call_a(candidates)
print(f"stats={json.dumps(stats, ensure_ascii=False)}")
selected_tier4 = [c for c in selected if c.get("tier") == 4]
print(f"選定後のtier4候補数: {len(selected_tier4)}件"
      f"（TIER4_CANDIDATE_LIMIT={generate_post.TIER4_CANDIDATE_LIMIT}）")
if len(tier4) > generate_post.TIER4_CANDIDATE_LIMIT:
    print(f"→ tier4が上限を超過した実データケース。上限{generate_post.TIER4_CANDIDATE_LIMIT}件に"
          f"絞られていることを確認: {'OK' if len(selected_tier4) == generate_post.TIER4_CANDIDATE_LIMIT else 'NG'}")
else:
    print("→ 今回の実データではtier4が上限に達しなかった（全件選定されるはず）")
    print(f"   全件選定されているか: {'OK' if len(selected_tier4) == len(tier4) else 'NG'}")

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

bundle = compose_post.compose(daily_data, {
    "level": "L0" if (a.ok and b.ok) else "L1",
    "call_a": a.to_dict(),
    "call_b": b.to_dict(),
    "news_source_status": news.get("source_status", {}),
    "news_candidate_count": len(selected),
    "total_usage": {"input_tokens": 0, "output_tokens": 0},
})

print()
print("=== GENERATION_STATUS.md（tier4除外行の確認用） ===")
gen_status = compose_post.render_generation_status({
    "level": "L0", "call_a": a.to_dict(), "call_b": b.to_dict(),
    "news_source_status": news.get("source_status", {}),
    "news_candidate_count": len(selected),
    "total_usage": {"input_tokens": a.usage["input_tokens"] + b.usage["input_tokens"],
                     "output_tokens": a.usage["output_tokens"] + b.usage["output_tokens"]},
}, daily_data)
for line in gen_status.splitlines():
    if "tier3候補" in line or "tier4候補" in line or "ペア救済" in line:
        print(f"  {line}")

print()
print("=== verify_post.run_all() 監査結果 ===")
au = verify_post.run_all(bundle, daily_data)
for c in au.checks:
    print(f"{c['id']} {c['result']} - {(c.get('detail') or '')[:200]}")
print(f"failed={au.failed}")
