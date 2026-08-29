"""診断用一時スクリプト（Google News RSS 0件問題調査・オーナー指示）。

8/26以降、Google News RSS（GOOGLE_NEWS_URL）が「対象日0件／取得0件」を
継続している。このサンドボックス環境のegressプロキシはnews.google.comを
遮断するため（ローカルでcurl検証済み・CONNECT拒否）、GitHub Actions
ランナー上で実行する必要がある。

現行クエリと複数のバリエーションを試行し、原因を切り分ける
（クエリ構文の問題か、Google News RSS自体の仕様変更・地域制限かを
判別する）。

調査後、本スクリプトとワークフローは削除する。
"""
import sys

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402

CANDIDATES = [
    ("現行クエリ（そのまま）", collect_news.GOOGLE_NEWS_URL),
    ("when:24hを外す", "https://news.google.com/rss/search?q=allinurl:reuters.com"),
    ("hl/gl/ceidを付与（現行クエリ+標準ロケールパラメータ）",
     "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&hl=en-US&gl=US&ceid=US:en"),
    ("hl/gl/ceidのみ・allinurl無し（Google News RSS自体が生きているかの基本確認）",
     "https://news.google.com/rss/search?q=bitcoin&hl=en-US&gl=US&ceid=US:en"),
    ("allinurl構文を site: へ変更", "https://news.google.com/rss/search?q=when:24h+site:reuters.com&hl=en-US&gl=US&ceid=US:en"),
]

for label, url in CANDIDATES:
    print(f"--- {label} ---")
    print(f"    url={url}")
    status, items, detail = collect_news.fetch_rss(url)
    print(f"    status={status} 件数={len(items)} detail={detail!r}")
    for it in items[:5]:
        print(f"      - [{it['published_at']}] {it['title']}")
    print()
