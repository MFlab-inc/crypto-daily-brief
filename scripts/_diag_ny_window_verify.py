#!/usr/bin/env python3
"""_diag_ny_window_verify.py — 一時的な調査用スクリプト。

v1.38（材料収集ウィンドウをJST暦日からNY 17:00基準へ変更）の効果を
実データで検証する（オーナー指示）。

・2026-08-18: SEC規則案（2026-76 SEC Proposes New Regulation Crypto Assets、
  pubDate Aug 18 13:15:48 -0400・v1.24で判明済み）が対象日候補に入るか。
  旧JST暦日基準ではJST換算がAug19 02:15になり翌日扱いで除外されていた。
・2026-08-24: Coinbaseのトークン化株式Base稼働に関する材料が対象日候補に
  入るか（Base公式RSSは情報源に無いため、CoinDesk/Cointelegraph等の
  tier3による報道を対象に確認する）。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import collect_news  # noqa: E402


def _dump_matches(target: str, keywords: list[str], *, sources: set[str] | None = None) -> None:
    print(f"===== 対象日: {target} =====")
    news = collect_news.collect_news(target)
    cands = news.get("candidates", [])
    print(f"候補総数: {len(cands)}件")
    matches = []
    for c in cands:
        if sources is not None and c.get("source") not in sources:
            continue
        blob = (c.get("title", "") + " " + c.get("summary", "")).lower()
        if any(kw.lower() in blob for kw in keywords):
            matches.append(c)
    print(f"キーワード一致候補: {len(matches)}件")
    for c in matches:
        print(f"  - source={c.get('source')!r} tier={c.get('tier')!r} published_at={c.get('published_at')!r}")
        print(f"    title={c.get('title')!r}")
        print(f"    summary={c.get('summary', '')[:200]!r}")
    print()


def main() -> None:
    _dump_matches("2026-08-18", ["Crypto Assets", "2026-76", "Regulation"], sources={"SEC"})
    _dump_matches("2026-08-24", ["tokenized", "Base", "Coinbase"])


if __name__ == "__main__":
    main()
