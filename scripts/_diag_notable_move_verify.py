"""診断用一時スクリプト（v1.41フォローアップ実データ検証・オーナー指示）。

8/25データで本文への反映を検証する。
1) 前編【主要指標】にBTC・ETHの日中レンジ行が出ること
2) BNBの行が出ないこと
3) notable_move が BTC で true になること
4) C16b（散文中の数値転記）が引き続きPASSすること

既にコミット済みの outputs/2026-08-25/daily_data.json を読み込み、
intraday_range を注入したうえで実際のcompose_post.compose()・
generate_post.run()（実API呼び出し）・verify_post.run_all()を実行する。
このジョブのローカルディスク上でのみdaily_data.jsonを上書きし、
コミットはしない（調査用途のみ）。調査後、本スクリプトとワークフローは
削除する。
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "scripts")
import anthropic  # noqa: E402
import collect_news  # noqa: E402
import compose_post  # noqa: E402
import fetch_data  # noqa: E402
import generate_post  # noqa: E402
import verify_post  # noqa: E402

TARGET = "2026-08-25"
daily_data_path = Path(f"outputs/{TARGET}/daily_data.json")
daily_data = json.loads(daily_data_path.read_text(encoding="utf-8"))

target_date_obj = date.fromisoformat(TARGET)
window_start, window_end = collect_news.collection_window_ny(target_date_obj)


def close_price_for(sym: str):
    for a in daily_data.get("assets", []):
        if a.get("asset") == sym:
            try:
                return float(str(a["usd"]).replace("$", "").replace(",", ""))
            except (KeyError, ValueError):
                return None
    return None


threshold = fetch_data.load_notable_move_threshold()
print(f"notable_move_threshold = {threshold}")
print()

intraday_range = {}
for sym, (cb_product, bs_pair, representative) in fetch_data.INTRADAY_SYMBOLS.items():
    r = fetch_data.fetch_intraday_range(sym, cb_product, bs_pair, window_start, window_end)
    entry = {"high": r["high"], "low": r["low"], "source": r["source"],
              "retrieved_at": r["retrieved_at"], "representative": representative}
    if representative:
        close = close_price_for(sym)
        nm = fetch_data.compute_notable_move(r["high_raw"], close, threshold)
        print(f"{sym}: high_raw={r['high_raw']} close(既存daily_data.jsonの#{sym})={close} "
              f"乖離率={(r['high_raw'] - close) / close * 100 if r['high_raw'] and close else 'N/A'}% "
              f"notable_move={nm}")
        if nm is not None:
            entry["notable_move"] = nm
    intraday_range[sym] = entry

print()
print("=== 注入するintraday_range ===")
print(json.dumps(intraday_range, ensure_ascii=False, indent=2))

daily_data["intraday_range"] = intraday_range
daily_data_path.write_text(json.dumps(daily_data, ensure_ascii=False, indent=2), encoding="utf-8")

print()
print("=== 呼び出しA・Bを実行（実API・intraday_range注入後のdaily_data.jsonを使用） ===")
client = anthropic.Anthropic()
gen = generate_post.run(TARGET, client=client)
bundle = compose_post.compose(daily_data, gen)

print(f"call_A: ok={gen['call_a']['ok']} attempts={gen['call_a']['attempts']}")
print(f"call_B: ok={gen['call_b']['ok']} attempts={gen['call_b']['attempts']}")
print()
print("=== sections.part1_numeric（前編【主要指標】） ===")
print(bundle["sections"]["part1_numeric"])
print()
print("=== sections.part1_headline（呼び出しAの出力） ===")
print(bundle["sections"]["part1_headline"])
print()
print("=== sections.part1_points（呼び出しAの出力） ===")
print(bundle["sections"]["part1_points"])

print()
print("=== verify_post.run_all() 監査結果 ===")
au = verify_post.run_all(bundle, daily_data)
for c in au.checks:
    print(f"{c['id']} {c['result']} - {(c.get('detail') or '')[:200]}")
print(f"failed={au.failed}")
