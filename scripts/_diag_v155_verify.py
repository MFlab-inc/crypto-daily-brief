"""診断用一時スクリプト（v1.55・C19空欄自動補完の実データ検証・オーナー指示）。

8/28データでcall_A〜監査を複数回独立実行し、以下を確認する。
1) C19が常にPASSすること（decision/reasonが空でも自動補完されるため）。
2) reason空欄の事象が実際に再現した場合、自動補完件数が
   GENERATION_STATUS.mdへ正しく記録されること。
3) 事象が再現しなかった場合でも、従来どおり正常動作すること
   （auto_filled=0で何も余計な記録が出ないこと）。

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
client = anthropic.Anthropic()

N_RUNS = 3
any_auto_filled = False

for run_no in range(1, N_RUNS + 1):
    print(f"\n=== Run {run_no}/{N_RUNS} ===")
    news = collect_news.collect_news(TARGET)
    a = generate_post.call_a(client, daily_data, news, None)
    print(f"call_A: ok={a.ok} attempts={a.attempts} error={a.error}")
    print(f"audit_ledger_auto_filled_count={a.audit_ledger_auto_filled_count}")
    if a.attempt_errors:
        print(f"attempt_errors（{len(a.attempt_errors)}件）:")
        for i, err in enumerate(a.attempt_errors, 1):
            print(f"  {i}: {err[:200]}")

    if not a.ok:
        print("call_A失敗。このrunの以降の検証をスキップします。")
        continue
    if a.audit_ledger_auto_filled_count > 0:
        any_auto_filled = True

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

    status_text = compose_post.render_generation_status(gen, daily_data)
    if "audit_ledger自動補完" in status_text:
        print("--- GENERATION_STATUS.md該当箇所 ---")
        for line in status_text.splitlines():
            if "audit_ledger自動補完" in line:
                print(f"  {line}")

    au = verify_post.run_all(bundle, daily_data)
    c19 = next(c for c in au.checks if c["id"] == "C19_audit_ledger")
    print(f"C19_audit_ledger: {c19['result']} - {(c19.get('detail') or '')[:200]}")
    print(f"failed={au.failed}")
    if au.failed:
        print("FAILしたcheck一覧:")
        for c in au.checks:
            if c["result"] == "FAIL":
                print(f"  {c['id']}: {(c.get('detail') or '')[:200]}")

print()
print("=== まとめ ===")
print(f"{N_RUNS}回中、reason空欄の事象が再現した回数: "
      f"{'あり（上記参照）' if any_auto_filled else 'なし（0件のまま正常動作）'}")
