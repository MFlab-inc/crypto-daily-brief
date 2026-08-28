"""診断用一時スクリプト（v1.48実データ検証・オーナー指示）。

8/27にcall_Aが3試行目でようやく成功した事象への構造対応
（audit_ledgerをcandidate_id方式へ再構成）の効果を実測する。
オーナー指定の4点を確認する。
1) 出力トークンがどこまで減るか
2) call_Aが1回試行で成功するか
3) C19・C21・C23が引き続きPASSするか
4) 不採用エントリのurl・titleが候補データと完全一致するか
   （LLMの転記ではなくコード側の補完であることの直接確認）

news_candidates.json は daily.yml のコミット対象外のため、8/27当日の
実候補セットは復元できない。かわりに collect_news.collect_news() を
対象日2026-08-27で今このジョブ上で再実行する（v1.47検証時にtier1=11件・
tier3=44件が実測値と完全一致することを確認済みの手法）。

コミット済みの outputs/2026-08-27/daily_data.json をそのまま使い
（このジョブのローカルディスク上でのみ参照・書き込みはしない）、
実際の generate_post.call_a()・compose_post.compose()・
verify_post.run_all()（実API呼び出し）を実行する。
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

TARGET = "2026-08-27"
daily_data = json.loads(Path(f"outputs/{TARGET}/daily_data.json").read_text(encoding="utf-8"))

print("=== collect_news.collect_news() を対象日2026-08-27で再実行（実RSS・実tier1本文取得） ===")
news = collect_news.collect_news(TARGET)
candidates = news["candidates"]
tier1 = [c for c in candidates if c.get("tier") == 1]
tier3 = [c for c in candidates if c.get("tier") == 3]
print(f"取得候補数: tier1={len(tier1)}件 tier3={len(tier3)}件 "
      f"(v1.47検証時点の再取得: tier1=11件・tier3=44件で実測と完全一致)")
print()

print("=== 呼び出しAを実行（実API・新コード＝audit_ledgerはcandidate_id方式） ===")
client = anthropic.Anthropic()
a = generate_post.call_a(client, daily_data, news, None)
print(f"call_A: ok={a.ok} attempts={a.attempts} error={a.error}")
print(f"input_tokens={a.usage['input_tokens']} output_tokens={a.usage['output_tokens']}")
print(f"（8/27実際の失敗時: input=58905 output=24000（3試行とも上限切断で失敗））")
print(f"（v1.47実測: input=37300 output=14658（2試行で成功））")
print(f"attempt_errors={a.attempt_errors}")

if not a.ok:
    print("call_A失敗。以降の検証をスキップします。")
    sys.exit(0)

ledger = a.data.get("audit_ledger", [])
print()
print(f"=== audit_ledger（{len(ledger)}件）のurl/titleが候補データと完全一致するか確認 ===")
id_to_candidate = {}
selected, _ = generate_post._select_candidates_for_call_a(candidates)
selected = generate_post._assign_candidate_ids(selected)
for c in selected:
    id_to_candidate[c["candidate_id"]] = c

# audit_ledgerには候補IDが残らない（reconstructで復元済みのため）。
# 復元後のurlが「候補一覧のいずれかのurlと完全一致するか」で検証する
# （どのcandidate_idに対応するかはreconstructの内部状態でしか分からない
# ため、ここでは「LLMが書ける余地のない値になっているか」を、候補一覧
# 全体のurlの集合に含まれるかで確認する）。
candidate_urls = {c.get("url") for c in selected}
candidate_titles = {c.get("title") for c in selected}
mismatched = [e for e in ledger if e.get("url") not in candidate_urls or e.get("title") not in candidate_titles]
print(f"audit_ledger全{len(ledger)}件のうち、url・titleが候補一覧のいずれとも一致しないエントリ: {len(mismatched)}件")
for e in mismatched[:5]:
    print(f"  不一致: url={e.get('url')!r} title={e.get('title')!r}")

print()
print("=== 不採用エントリのverified_by（空文字であるべき）確認 ===")
rejected = [e for e in ledger if e.get("decision") == "不採用"]
rejected_with_verified_by = [e for e in rejected if e.get("verified_by")]
print(f"不採用エントリ数: {len(rejected)}件 / うちverified_byが空でないもの: {len(rejected_with_verified_by)}件")

bundle = compose_post.compose(daily_data, {
    "level": "L0", "call_a": a.to_dict(),
    "call_b": generate_post.call_b(client, daily_data, a.data).to_dict(),
    "news_source_status": news.get("source_status", {}),
    "news_candidate_count": len(selected),
    "total_usage": {"input_tokens": 0, "output_tokens": 0},
})

print()
print("=== verify_post.run_all() 監査結果 ===")
au = verify_post.run_all(bundle, daily_data)
for c in au.checks:
    print(f"{c['id']} {c['result']} - {(c.get('detail') or '')[:200]}")
print(f"failed={au.failed}")
