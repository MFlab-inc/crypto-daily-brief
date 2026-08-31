"""診断用一時スクリプト（8/30 C22 FAIL調査のフォローアップ・オーナー指示）。

CoinDesk・CointelegraphのRSSフィードに、取得件数を増やすパラメータ
（?limit=・?size=等）が存在するかを実測する。8/25の「選定で押し出された」
問題（ペア救済で部分対応済み）とは別に、8/30は「フェッチ段階で既に
取得できていない」問題であり、フェッチ件数そのものを増やせるかを確認する。

LLMは呼ばない（無料）。コミットは一切行わない。調査後、本スクリプトと
ワークフローは削除する。
"""
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

CANDIDATES = {
    "coindesk_base": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "coindesk_size100": "https://www.coindesk.com/arc/outboundfeeds/rss/?size=100",
    "coindesk_size50": "https://www.coindesk.com/arc/outboundfeeds/rss/?size=50",
    "coindesk_outputType": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml&size=100",
    "coindesk_limit100": "https://www.coindesk.com/arc/outboundfeeds/rss/?limit=100",
    "coindesk_count100": "https://www.coindesk.com/arc/outboundfeeds/rss/?count=100",
    "coindesk_page2": "https://www.coindesk.com/arc/outboundfeeds/rss/?page=2",
    "coindesk_from50": "https://www.coindesk.com/arc/outboundfeeds/rss/?from=0&size=100",
    "cointelegraph_base": "https://cointelegraph.com/rss",
    "cointelegraph_limit100": "https://cointelegraph.com/rss?limit=100",
    "cointelegraph_count100": "https://cointelegraph.com/rss?count=100",
    "cointelegraph_size100": "https://cointelegraph.com/rss?size=100",
    "cointelegraph_num100": "https://cointelegraph.com/rss?num=100",
    "cointelegraph_page2": "https://cointelegraph.com/rss?page=2",
    "cointelegraph_posts_per_page": "https://cointelegraph.com/rss?posts_per_page=100",
}


def fetch(url: str) -> tuple[int | None, str | None, Exception | None]:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), None
    except Exception as e:  # noqa: BLE001
        return None, None, e


def analyze(label: str, url: str) -> None:
    status, body, err = fetch(url)
    if err is not None:
        print(f"{label}: ERROR {err!r}")
        return
    if status != 200:
        print(f"{label}: HTTP {status}")
        return
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        print(f"{label}: HTTP 200・XMLパース失敗 {e!r}（body先頭200字: {body[:200]!r}）")
        return
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    n = len(items)
    pubdates = []
    for it in items:
        pd = it.findtext("pubDate") or it.findtext("{http://www.w3.org/2005/Atom}published")
        if pd:
            parsed = collect_news.parse_pubdate_jst(pd)
            if parsed:
                pubdates.append(parsed)
    oldest = min(pubdates).isoformat() if pubdates else "N/A"
    newest = max(pubdates).isoformat() if pubdates else "N/A"
    print(f"{label}: HTTP 200・{n}件・oldest={oldest}・newest={newest}")


print("=== 各URLパターンの実測結果 ===")
for label, url in CANDIDATES.items():
    analyze(label, url)

print(f"\n=== 参考: RAW_ITEM_LIMIT（fetch_rss内部・日付フィルタ前の1フィードあたり上限）="
      f"{collect_news.RAW_ITEM_LIMIT} ===")
print("パラメータで取得件数を増やせても、この上限を超える分はfetch_rss()内で")
print("切り捨てられる（date filter以前の処理のため）。引き上げが必要なら")
print("あわせてRAW_ITEM_LIMITの変更もセットで検討する必要がある。")

print("\n=== 参考: 現行baseline（collect_news.collect_news()実行・パラメータなし）の実際の候補内訳 ===")
news = collect_news.collect_news(datetime.now(timezone.utc).astimezone(collect_news.JST).date().isoformat())
for name, status in news.get("source_status", {}).items():
    if name in ("CoinDesk", "Cointelegraph"):
        print(f"{name}: {status}")
tier3_today = [c for c in news.get("candidates", []) if c.get("tier") == 3]
print(f"tier3候補（対象日フィルタ後）合計: {len(tier3_today)}件")
