"""診断用一時スクリプト（C21構造的解消・raw LLM出力の直接調査・オーナー指示ではなく
自主的な深掘り。前回診断でcall_Aが8/28データで2回とも3回リトライ後FAILEDとなった
原因を特定するため）。

_call_json()のpost_process（_reconstruct_audit_ledger・decision導出）を経由せず、
呼び出しAの生JSON応答をそのまま出力する。tier3のuse:trueエントリについて、
pairs_with_candidate_idの有無・妥当性確認の各条件（相手の実在・tier3・use:true・
source違い・overlap係数）の判定結果を個別に表示し、どの条件で失敗しているかを
特定する。

調査後、本スクリプトとワークフローは削除する。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import generate_post  # noqa: E402

TARGET = "2026-08-28"
daily_data = json.loads(Path(f"outputs/{TARGET}/daily_data.json").read_text(encoding="utf-8"))
news = collect_news.collect_news(TARGET)

pair_overlap_threshold = generate_post.load_pair_overlap_threshold()
user_content, truncation_stats, id_to_candidate = generate_post._build_call_a_user_content(
    daily_data, news, None, pair_overlap_threshold)

print(f"threshold={pair_overlap_threshold}")
print(f"渡した候補数={len(id_to_candidate)}（tier内訳: "
      f"tier1={sum(1 for c in id_to_candidate.values() if c.get('tier') == 1)}, "
      f"tier3={sum(1 for c in id_to_candidate.values() if c.get('tier') == 3)}, "
      f"tier4={sum(1 for c in id_to_candidate.values() if c.get('tier') not in (1, 3))})")
print()

client = anthropic.Anthropic()
response = client.messages.create(
    model=generate_post.MODEL,
    max_tokens=generate_post.CALL_A_MAX_TOKENS,
    system=generate_post.SYSTEM_A,
    messages=[{"role": "user", "content": user_content}],
    thinking={"type": "disabled"},
)
usage = generate_post._extract_usage(response)
print(f"input_tokens={usage['input_tokens']} output_tokens={usage['output_tokens']}")
text = generate_post._strip_code_fence(generate_post._extract_text(response))
data = json.loads(text)
llm_ledger = data.get("audit_ledger", [])
print(f"LLM生audit_ledger件数={len(llm_ledger)}")
print()

print("=== tier3のuse:trueエントリの詳細 ===")
use_by_id = {e.get("candidate_id"): bool(e.get("use")) for e in llm_ledger if isinstance(e, dict)}
for e in llm_ledger:
    if not isinstance(e, dict):
        continue
    cid = e.get("candidate_id")
    cand = id_to_candidate.get(cid)
    if not cand or cand.get("tier") != 3 or not e.get("use"):
        continue
    claim = e.get("pairs_with_candidate_id")
    print(f"[id={cid}] source={cand.get('source')!r} title={cand.get('title', '')[:70]!r}")
    print(f"    reason={e.get('reason', '')!r}")
    print(f"    pairs_with_candidate_id={claim!r}")
    if claim is None:
        print("    -> 判定: 相方の申告なし（pairs_with_candidate_id未設定）")
    else:
        target = id_to_candidate.get(claim)
        if target is None:
            print(f"    -> 判定: NG（相手candidate_id={claim}が存在しない）")
        else:
            checks = []
            checks.append(("相手が実在", True))
            checks.append(("相手がtier3", target.get("tier") == 3))
            checks.append(("相手もuse:true", use_by_id.get(claim, False)))
            checks.append(("sourceが異なる", target.get("source") != cand.get("source")))
            sim = generate_post._overlap_coefficient(
                generate_post._tokenize_title(cand.get("title", "")),
                generate_post._tokenize_title(target.get("title", "")))
            checks.append((f"overlap({sim:.2f})>=閾値({pair_overlap_threshold})", sim >= pair_overlap_threshold))
            ok = all(c[1] for c in checks)
            print(f"    相手候補: source={target.get('source')!r} title={target.get('title', '')[:70]!r}")
            print(f"    -> 判定: {'OK' if ok else 'NG'} " + " / ".join(f"{name}={v}" for name, v in checks))
    print()

print("=== 参考: 機械的ペア検出（_find_independent_pairs）が見つけた実在ペア（閾値内） ===")
tier3_candidates = [c for c in id_to_candidate.values() if c.get("tier") == 3]

def pub_dt(c):
    return collect_news.parse_pubdate_jst(c.get("published_at", "")) or datetime.min.replace(
        tzinfo=collect_news.JST)
tier3_sorted = sorted(tier3_candidates, key=pub_dt, reverse=True)
mech_pairs = generate_post._find_independent_pairs(tier3_sorted, pair_overlap_threshold)
id_by_obj = {id(c): cid for cid, c in id_to_candidate.items()}
for a, b in mech_pairs:
    aid, bid = id_by_obj.get(id(a)), id_by_obj.get(id(b))
    a_use = use_by_id.get(aid, False)
    b_use = use_by_id.get(bid, False)
    print(f"  [id={aid} use={a_use}] {a['source']}: {a['title'][:60]!r}")
    print(f"  [id={bid} use={b_use}] {b['source']}: {b['title'][:60]!r}")
    print(f"    -> 両方use:trueか: {a_use and b_use}")
    print()
