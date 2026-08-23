#!/usr/bin/env python3
"""_diag_raw_feed_contents.py — 一時的な調査用スクリプト。

新規4情報源（米財務省・USTR・ホワイトハウス2本）について、対象日フィルタを
かけない生の取得結果（全件のtitle・pubDate）を出力する。対カナダ関税措置
（8/22）が、日付が合わずに除外されているだけなのか、それともこれらの
フィードに一次情報として一度も現れていないのかを切り分ける。

調査完了後は削除する（本リポジトリに残す想定のスクリプトではない）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import collect_news  # noqa: E402

TARGET_NAMES = {"米財務省", "USTR", "ホワイトハウス", "ホワイトハウス（大統領令等）"}


def main() -> None:
    for src in collect_news._load_sources():
        if src["name"] not in TARGET_NAMES:
            continue
        print(f"===== {src['name']} ({src['url']}) =====")
        status, items, detail = collect_news.fetch_rss(src["url"])
        print(f"status={status} detail={detail}")
        if status != "ok":
            print()
            continue
        print(f"取得件数: {len(items)}")
        for it in items:
            print(f"  - pubDate={it['published_at']!r}")
            print(f"    title={it['title']!r}")
        print()


if __name__ == "__main__":
    main()
