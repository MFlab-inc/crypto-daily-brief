"""診断用一時スクリプト（v1.47実データ検証・オーナー指示）。

8/27にcall_Aが3試行とも出力トークン上限（8,000）で切断した事象
（入力58,905・出力24,000）への対応（tier1本文上限2000→1500字＋
切り詰めマーカー、不採用reasonの全角60字上限）の効果を実測する。

news_candidates.json は daily.yml のコミット対象外のため、8/27当日の
実候補セットは復元できない。かわりに collect_news.collect_news() を
対象日2026-08-27で今このジョブ上で再実行し（実RSS取得・実tier1本文
取得——新しい1500字上限がすでに効いた状態で取得される）、現在
取得可能な範囲でできるだけ実データに近い候補集合を再構成する。
RSSフィードの保持期間により、8/27当時と完全に同一の候補集合には
ならない可能性がある点に留意（本文中に明記する）。

コミット済みの outputs/2026-08-27/daily_data.json をそのまま使い
（このジョブのローカルディスク上でのみ参照・書き込みはしない）、
実際の generate_post.call_a()（実API呼び出し）を実行する。
調査後、本スクリプトとワークフローは削除する。
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import generate_post  # noqa: E402

TARGET = "2026-08-27"
daily_data = json.loads(Path(f"outputs/{TARGET}/daily_data.json").read_text(encoding="utf-8"))

print(f"=== ARTICLE_BODY_CHAR_LIMIT（新）= {collect_news.ARTICLE_BODY_CHAR_LIMIT} ===")
print()

print("=== collect_news.collect_news() を対象日2026-08-27で再実行（実RSS・実tier1本文取得） ===")
news = collect_news.collect_news(TARGET)
candidates = news["candidates"]
tier1 = [c for c in candidates if c.get("tier") == 1]
tier3 = [c for c in candidates if c.get("tier") == 3]
print(f"取得候補数: tier1={len(tier1)}件 tier3={len(tier3)}件 (8/27実データ時点はtier1=11件・tier3=44件中19選定+4救済)")
print()

print("=== tier1候補ごとのsummary（本文補強済み）長さ ===")
total_tier1_chars = 0
truncated_count = 0
for c in tier1:
    s = c.get("summary", "")
    total_tier1_chars += len(s)
    is_truncated = s.endswith(collect_news.ARTICLE_BODY_TRUNCATION_MARKER)
    if is_truncated:
        truncated_count += 1
    print(f"  [{c.get('source')}] {len(s)}字 truncated={is_truncated} : {c.get('title', '')[:60]}")
print(f"tier1 summary合計文字数: {total_tier1_chars}字 / うち{truncated_count}件が新1500字上限で切り詰め")
print(f"（旧2000字上限だった場合の理論上限差: 切り詰められた{truncated_count}件×最大500字 = "
      f"最大{truncated_count * 500}字の削減）")

print()
print("=== 呼び出しAを実行（実API・新コード＝本文1500字上限+不採用reason60字上限が有効） ===")
client = anthropic.Anthropic()
news_yesterday = None
prev_path = Path(f"outputs/2026-08-26/news_candidates.json")
if prev_path.exists():
    news_yesterday = json.loads(prev_path.read_text(encoding="utf-8"))

a = generate_post.call_a(client, daily_data, news, news_yesterday)
print(f"call_A: ok={a.ok} attempts={a.attempts} error={a.error}")
print(f"input_tokens={a.usage['input_tokens']} output_tokens={a.usage['output_tokens']}")
print(f"（8/27実際の失敗時: input=58905 output=24000（3試行とも上限切断・成功なし））")
ts = a.truncation_stats
print(f"tier3_total={ts.get('tier3_total')} tier3_selected={ts.get('tier3_selected')} "
      f"tier3_pairs_rescued={ts.get('tier3_pairs_rescued')}")

if a.ok:
    ledger = a.data.get("audit_ledger", [])
    print()
    print(f"=== audit_ledger（{len(ledger)}件）の不採用reason長チェック（全角60字上限の遵守確認） ===")
    over_limit = []
    for e in ledger:
        if e.get("decision") == "不採用":
            reason = e.get("reason", "")
            # 簡易全角換算: ASCII1字=0.5、それ以外=1として概算
            width = sum(0.5 if ord(ch) < 128 else 1.0 for ch in reason)
            if width > 60:
                over_limit.append((width, reason))
    print(f"不採用エントリ数: {sum(1 for e in ledger if e.get('decision') == '不採用')}件")
    print(f"全角60字超過: {len(over_limit)}件")
    for w, r in over_limit[:5]:
        print(f"  [約{w:.0f}字] {r}")
    print()
    print("=== part1_headline ===")
    print(a.data.get("part1_headline"))
    print("=== part1_points ===")
    print(a.data.get("part1_points"))
else:
    print(f"call_A失敗の生エラー: {a.error}")
