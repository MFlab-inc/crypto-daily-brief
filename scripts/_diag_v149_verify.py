"""診断用一時スクリプト（v1.49実データ検証・オーナー指示）。

8/28にC18が「マーカー['を受けて']と価格変動語['上昇']が同一文に存在
（限定表現なし）」でFAILした事象（他12項目はPASS・level=L0）への対処
（RULES_CAUSALへコミット拒否の帰結を明記・notable_move時の注意を追記）
の効果を実測する。オーナー指定の3点を確認する。
1) C18がPASSすること
2) 値動きの記述が残っていること（限定表現を付けた形で）
3) 他のゲートに影響がないこと

news_candidates.json は daily.yml のコミット対象外のため、8/28当日の
実候補セットは復元できない。かわりに collect_news.collect_news() を
対象日2026-08-28で今このジョブ上で再実行する。

コミット済みの outputs/2026-08-28/daily_data.json をそのまま使う
（BTC・ETHともnotable_move: true。このジョブのローカルディスク上でのみ
参照・書き込みはしない）。実際の generate_post.call_a()・call_b()・
compose_post.compose()・verify_post.run_all()（実API呼び出し）を実行する。

注記: LLM出力は実行ごとに変動しうるため、本検証の「C18 PASS」は
単一サンプルの確認であり、常にPASSすることを保証するものではない。
RULES_CAUSALは v1.20/v1.22時点で既にC18とほぼ同一の語彙・限定表現指示を
含んでおり、8/28の事象はプロンプト指示が皆無だったのではなく、既存の
指示があってもなおLLMが遵守しなかったケースである。したがって本対処
（帰結の明記強化）が遵守率をどこまで押し上げるかは1回の実行では
確認できず、実運用のゲート（C18）が最終的な安全網であることに変わりは
ない。

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

print(f"=== intraday_range（notable_move確認） ===")
for sym, v in daily_data.get("intraday_range", {}).items():
    print(f"  {sym}: notable_move={v.get('notable_move')} inconsistent={v.get('inconsistent')}")
print()

print("=== collect_news.collect_news() を対象日2026-08-28で再実行（実RSS・実tier1本文取得） ===")
news = collect_news.collect_news(TARGET)
candidates = news["candidates"]
tier1 = [c for c in candidates if c.get("tier") == 1]
tier3 = [c for c in candidates if c.get("tier") == 3]
print(f"取得候補数: tier1={len(tier1)}件 tier3={len(tier3)}件")
print()

client = anthropic.Anthropic()
print("=== 呼び出しAを実行（実API・RULES_CAUSAL強化後） ===")
a = generate_post.call_a(client, daily_data, news, None)
print(f"call_A: ok={a.ok} attempts={a.attempts} error={a.error}")
if a.ok:
    print(f"input_tokens={a.usage['input_tokens']} output_tokens={a.usage['output_tokens']}")
print(f"attempt_errors={a.attempt_errors}")

if not a.ok:
    print("call_A失敗。以降の検証をスキップします。")
    sys.exit(0)

print()
print("=== 呼び出しBを実行（実API・RULES_CAUSAL強化後） ===")
b = generate_post.call_b(client, daily_data, a.data)
print(f"call_B: ok={b.ok} attempts={b.attempts} error={b.error}")
print(f"attempt_errors={b.attempt_errors}")

selected, _ = generate_post._select_candidates_for_call_a(candidates)

bundle = compose_post.compose(daily_data, {
    "level": "L0" if (a.ok and b.ok) else "L1",
    "call_a": a.to_dict(),
    "call_b": b.to_dict(),
    "news_source_status": news.get("source_status", {}),
    "news_candidate_count": len(selected),
    "total_usage": {"input_tokens": 0, "output_tokens": 0},
})

print()
print("=== LLM生成セクションの実文言（値動き記述が残っているか目視確認用） ===")
for key in ("headline_for_image", "part1_headline", "part1_points", "part2_flow", "part2_summary"):
    print(f"--- {key} ---")
    print(bundle.get(key))
    print()

print("=== verify_post.run_all() 監査結果 ===")
au = verify_post.run_all(bundle, daily_data)
for c in au.checks:
    print(f"{c['id']} {c['result']} - {(c.get('detail') or '')[:300]}")
print(f"failed={au.failed}")
