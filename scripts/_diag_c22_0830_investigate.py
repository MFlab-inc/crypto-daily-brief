"""診断用一時スクリプト（8/30 C22 FAILの原因調査・オーナー指示）。

2026-08-30の実行でC22のみFAILした（tier1裏付け・独立2ソース・
notable_moveのいずれも不成立）。オーナーはCronosのネットワーク停止を
CoinDeskとCointelegraph両方が報じていたはずと確認済みで、独立2ソース
として採用されなかった原因を求めている。

本スクリプトはLLMを一切呼ばない（無料・決定論的）。collect_news.py
（実RSS取得）とgenerate_post.pyのペア検出ロジック
（_tokenize_title/_overlap_coefficient/_find_independent_pairs/
_select_candidates_for_call_a）をそのまま使い、以下を確認する。

1. tier3候補（CoinDesk・Cointelegraph）の全タイトルを列挙する
   （tier3候補数上限15件で切られていないかも確認できる——
   実際の対象日tier3候補数がログで4+4=8件と判明済みのため
   上限には触れていないはずだが、実タイトルで直接確認する）。
2. Cronos関連と思われる候補を特定し、実際のタイトル同士の
   overlap係数を計算する。
3. 閾値0.4・0.3それぞれで_find_independent_pairs()がペアを
   検出するかを確認する。
4. _select_candidates_for_call_a()の出力（実際にcall_Aへ渡る
   候補集合）にCronos関連候補が含まれるかも確認する。

調査後、本スクリプトとワークフローは削除する。
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402
import generate_post  # noqa: E402

TARGET = "2026-08-30"

news = collect_news.collect_news(TARGET)
candidates = news.get("candidates", [])
print(f"取得候補総数: {len(candidates)}")

by_tier = {}
for c in candidates:
    by_tier.setdefault(c.get("tier"), []).append(c)
for tier in sorted(by_tier):
    print(f"tier{tier}: {len(by_tier[tier])}件")

print("\n=== tier3候補（CoinDesk・Cointelegraph）全タイトル ===")
tier3 = by_tier.get(3, [])
for c in tier3:
    print(f"  [{c.get('source')}] {c.get('title')!r}")

print("\n=== Cronos関連候補の特定（タイトルに'cronos'を含むもの、大小文字無視） ===")
cronos_candidates = [c for c in tier3 if "cronos" in str(c.get("title", "")).lower()]
for c in cronos_candidates:
    print(f"  candidate_id候補: source={c.get('source')} tier={c.get('tier')} "
          f"published_at={c.get('published_at')}\n    title={c.get('title')!r}")

if len(cronos_candidates) >= 2:
    print("\n=== Cronos候補間のoverlap係数（実タイトル・実アルゴリズム） ===")
    for i in range(len(cronos_candidates)):
        for j in range(i + 1, len(cronos_candidates)):
            a, b = cronos_candidates[i], cronos_candidates[j]
            a_tok = generate_post._tokenize_title(a.get("title", ""))
            b_tok = generate_post._tokenize_title(b.get("title", ""))
            sim = generate_post._overlap_coefficient(a_tok, b_tok)
            same_source = a.get("source") == b.get("source")
            print(f"  [{a.get('source')}] vs [{b.get('source')}] "
                  f"(同一source={same_source}): overlap={sim:.4f}")
            print(f"    A tokens({len(a_tok)}): {sorted(a_tok)}")
            print(f"    B tokens({len(b_tok)}): {sorted(b_tok)}")
            print(f"    共通({len(a_tok & b_tok)}): {sorted(a_tok & b_tok)}")
            print(f"    0.4で合格: {sim >= 0.4} / 0.3で合格: {sim >= 0.3}")
else:
    print(f"\nCronos関連候補が{len(cronos_candidates)}件のみ検出（2件必要）。"
          "タイトルに'cronos'が含まれない表記の可能性あり。全tier3タイトルを目視確認してください。")

print("\n=== _find_independent_pairs()の実際の出力（新しい順ソート・貪欲法） ===")


def _sort_key(c):
    return collect_news.parse_pubdate_jst(c.get("published_at", "")) or datetime.min.replace(
        tzinfo=collect_news.JST)


tier3_sorted = sorted(tier3, key=_sort_key, reverse=True)
for threshold in (0.4, 0.3):
    pairs = generate_post._find_independent_pairs(tier3_sorted, threshold)
    print(f"\nthreshold={threshold}: {len(pairs)}組検出")
    for a, b in pairs:
        print(f"  [{a.get('source')}] {a.get('title')!r}")
        print(f"  [{b.get('source')}] {b.get('title')!r}")

print("\n=== _select_candidates_for_call_a()（実際にcall_Aへ渡る候補集合） ===")
for threshold in (0.4, 0.3):
    selected, stats = generate_post._select_candidates_for_call_a(candidates, threshold)
    cronos_in_selected = [c for c in selected if "cronos" in str(c.get("title", "")).lower()]
    print(f"threshold={threshold}: 選定{len(selected)}件（stats={stats}）"
          f" / うちCronos関連{len(cronos_in_selected)}件")
