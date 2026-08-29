"""診断用一時スクリプト（C21構造的解消の実データ検証・オーナー指示）。

1) overlap閾値0.4 vs 0.3の比較（8/24・8/26・8/28の実tier3候補で
   _find_independent_pairs()を実行し、閾値でペア判定がどう変わるか報告）。
   ペア救済（pre-selection）とpairs_with_candidate_id妥当性確認
   （post-selection）は同じoverlap係数ロジックを共用するため、この比較で
   両方の挙動を代表できる。
2) 8/28データで call_A〜監査を2回独立実行し、C21が2回ともPASSすること
   （サンプリングゆらぎに対する頑健性）を確認する。
3) リトライが発生した場合、attempt_errorsに記録されること
   （GENERATION_STATUS.mdへの記録経路の確認）。
4) decisionがコード導出になったことでoutput_tokensが減るかを、
   v1.53検証時点の実測値（8/28・input=23,773 output=3,761）と比較する。

news_candidates.json は daily.yml のコミット対象外のため、実測は
collect_news.collect_news() を今このジョブ上で実行して行う。
コミット済みの outputs/2026-08-28/daily_data.json をそのまま使う
（このジョブのローカルディスク上でのみ参照・書き込みはしない）。

調査後、本スクリプトとワークフローは削除する。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import compose_post  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

print("=== [1] overlap閾値0.4 vs 0.3の比較（8/24・8/26・8/28の実tier3候補） ===")
for target in ("2026-08-24", "2026-08-26", "2026-08-28"):
    news = collect_news.collect_news(target)
    tier3 = [c for c in news["candidates"] if c.get("tier") == 3]

    def pub_dt(c):
        return collect_news.parse_pubdate_jst(c.get("published_at", "")) or datetime.min.replace(
            tzinfo=collect_news.JST)
    tier3_sorted = sorted(tier3, key=pub_dt, reverse=True)

    pairs_04 = generate_post._find_independent_pairs(tier3_sorted, 0.4)
    pairs_03 = generate_post._find_independent_pairs(tier3_sorted, 0.3)
    print(f"\n--- {target}: tier3候補{len(tier3)}件 ---")
    print(f"  閾値0.4: {len(pairs_04)}組")
    for a, b in pairs_04:
        sim = generate_post._overlap_coefficient(
            generate_post._tokenize_title(a.get("title", "")), generate_post._tokenize_title(b.get("title", "")))
        print(f"    [{sim:.2f}] {a['source']}: {a['title'][:60]!r} <-> {b['source']}: {b['title'][:60]!r}")
    print(f"  閾値0.3: {len(pairs_03)}組")
    for a, b in pairs_03:
        sim = generate_post._overlap_coefficient(
            generate_post._tokenize_title(a.get("title", "")), generate_post._tokenize_title(b.get("title", "")))
        print(f"    [{sim:.2f}] {a['source']}: {a['title'][:60]!r} <-> {b['source']}: {b['title'][:60]!r}")
    only_03 = len(pairs_03) - len(pairs_04)
    print(f"  差分: 0.3のみで追加検出されるペア {only_03}組"
          f"（0.4のペアが0.3で失われることはない——閾値を下げるほど条件は緩くなる）")

print()
print("=== [2][3][4] 8/28データでcall_A〜監査を2回独立実行（実API使用） ===")
TARGET = "2026-08-28"
daily_data = json.loads(Path(f"outputs/{TARGET}/daily_data.json").read_text(encoding="utf-8"))
client = anthropic.Anthropic()

for run_no in (1, 2):
    print(f"\n--- Run {run_no} ---")
    news = collect_news.collect_news(TARGET)
    a = generate_post.call_a(client, daily_data, news, None)
    print(f"call_A: ok={a.ok} attempts={a.attempts} error={a.error}")
    if a.ok:
        print(f"input_tokens={a.usage['input_tokens']} output_tokens={a.usage['output_tokens']}")
    if a.attempt_errors:
        print(f"attempt_errors（{len(a.attempt_errors)}件・リトライが発生した証跡）:")
        for i, err in enumerate(a.attempt_errors, 1):
            print(f"  {i}: {err[:200]}")
    else:
        print("attempt_errors: なし（1回目で成功）")

    if not a.ok:
        print("call_A失敗。このrunの以降の検証をスキップします。")
        continue

    b = generate_post.call_b(client, daily_data, a.data)
    print(f"call_B: ok={b.ok} attempts={b.attempts}")

    selected, stats = generate_post._select_candidates_for_call_a(news["candidates"])
    gen = {
        "level": "L0" if (a.ok and b.ok) else "L1",
        "call_a": a.to_dict(),
        "call_b": b.to_dict(),
        "news_source_status": news.get("source_status", {}),
        "news_candidate_count": len(selected),
        "total_usage": {"input_tokens": 0, "output_tokens": 0},
    }
    bundle = compose_post.compose(daily_data, gen)

    # [3] GENERATION_STATUS.mdへのリトライ記録経路を確認（実際にcompose_post.pyの
    # レンダリング関数を通す。post_draft.ymlが書き出す実ファイルと同じ経路。
    # render_generation_status()はcompose()と同じ「gen」形状を受け取る＝
    # bundleではない点に注意）。
    status_text = compose_post.render_generation_status(gen, daily_data)
    if a.attempt_errors:
        print(f"GENERATION_STATUS.mdへのリトライ記録: attempt_errorsが{len(a.attempt_errors)}件あり、"
              f"レンダリング結果にcall_Aの試行関連記述が{'含まれる' if '試行' in status_text else '含まれない'}")
        print("--- GENERATION_STATUS.md該当箇所 ---")
        for line in status_text.splitlines():
            if "call_A" in line or "試行" in line:
                print(f"  {line}")

    au = verify_post.run_all(bundle, daily_data)
    print("verify_post.run_all()結果:")
    for c in au.checks:
        print(f"  {c['id']} {c['result']} - {(c.get('detail') or '')[:200]}")
    print(f"  failed={au.failed}")

print()
print("=== v1.53検証時点（本修正前）の実測値との比較用参考値 ===")
print("v1.53検証2回目（commit 7186924・8/28）: call_A input_tokens=23773 output_tokens=3761")
