"""診断用一時スクリプト（日銀・審議委員講演／ADP雇用統計のRSS調査・オーナー指示）。

9/2の実運用で以下の材料を取りこぼした（オーナー報告・記録のみで
急ぎではない）。
・日銀・高田創審議委員の講演（9/2、札幌）
・日本の長期金利上昇・日経平均下落（NHK）
・米ADP民間雇用統計（ADP公式・Reuters）

このうち日銀は、現在tier1として`https://www.boj.or.jp/rss/whatsnew.xml`
（全般の新着情報）のみを情報源としており、審議委員講演カテゴリ専用の
RSSがあるかを調査する（FRBのspeeches.xml追加＝v1.52と同じ考え方）。
ADPは民間統計機関で、BLSがHTTP 403で取れない現状の代替候補として
公開RSSの有無を調査する。

このサンドボックスからはboj.or.jp・adpemploymentreport.com等への
直接アクセスがネットワークプロキシで遮断されているため、GitHub Actions
ランナー（ネットワーク制限なし）上で調査する。LLMは呼ばない。
コミットは一切行わない。調査後、本スクリプトとワークフローは削除する。
"""
import sys

import requests

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


def fetch(url: str, label: str, max_chars: int = 4000) -> str:
    print(f"\n=== {label} ===")
    print(f"URL: {url}")
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
        print(f"HTTP status: {resp.status_code}")
        if resp.status_code != 200:
            return ""
        text = resp.text
        print(f"取得バイト数: {len(resp.content)}")
        return text
    except requests.RequestException as e:
        print(f"取得失敗: {type(e).__name__}: {e}")
        return ""


print("########## 1. 日銀RSS一覧ページの調査 ##########")
boj_rss_page = fetch("https://www.boj.or.jp/rss.htm", "日銀RSS配信案内ページ")
if boj_rss_page:
    print("\n--- ページ内の.xml/.rdfへのリンク（候補URL抽出） ---")
    import re
    links = re.findall(r'href="([^"]*\.(?:xml|rdf)[^"]*)"', boj_rss_page)
    for link in sorted(set(links)):
        print(f"  {link}")
    print("\n--- 'こうえん'/'講演'/'記者会見' を含む周辺テキスト（該当箇所の前後100字） ---")
    for kw in ("講演", "記者会見"):
        for m in re.finditer(kw, boj_rss_page):
            start = max(0, m.start() - 100)
            end = min(len(boj_rss_page), m.end() + 100)
            snippet = re.sub(r"\s+", " ", boj_rss_page[start:end])
            print(f"  [{kw}] ...{snippet}...")

print("\n\n########## 2. 日銀「ニュース一覧」ページのカテゴリ別RSS確認 ##########")
boj_whatsnew = fetch("https://www.boj.or.jp/whatsnew/", "日銀ニュース一覧ページ")
if boj_whatsnew:
    import re
    links2 = re.findall(r'href="([^"]*\.(?:xml|rdf)[^"]*)"', boj_whatsnew)
    for link in sorted(set(links2)):
        print(f"  {link}")

# 既知の日銀RSS命名パターンの候補を直接試す（rss.htmで見つからない場合の保険）。
print("\n\n########## 3. 日銀RSS候補URLの直接確認 ##########")
CANDIDATE_BOJ_URLS = [
    "https://www.boj.or.jp/rss/koen.xml",
    "https://www.boj.or.jp/rss/whatsnew_koen.xml",
    "https://www.boj.or.jp/rss/mopo.xml",
    "https://www.boj.or.jp/mopo/r_menu_koen/index.htm",
]
for url in CANDIDATE_BOJ_URLS:
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        print(f"  {url} -> HTTP {resp.status_code} ({len(resp.content)} bytes)")
    except requests.RequestException as e:
        print(f"  {url} -> 取得失敗: {type(e).__name__}: {e}")

print("\n\n########## 4. ADP関連ページのRSS/Atomリンク確認 ##########")
for url, label in [
    ("https://adpemploymentreport.com/", "ADP National Employment Report公式サイト"),
    ("https://mediacenter.adp.com/", "ADP Media Center（プレスリリース）"),
    ("https://www.adp.com/spark/rss.aspx", "ADP SPARK Blog RSS（参考・雇用統計とは別物の可能性）"),
]:
    html = fetch(url, label)
    if html:
        import re
        rss_links = re.findall(
            r'<link[^>]*type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', html, re.IGNORECASE)
        print(f"  <link type=rss/atom>タグ: {rss_links or 'なし'}")
        rss_hrefs = re.findall(r'href="([^"]*rss[^"]*)"', html, re.IGNORECASE)
        print(f"  'rss'を含むhref: {sorted(set(rss_hrefs)) or 'なし'}")

print("\n\n########## 5. PRNewswire issuer別フィードの確認（ADP用） ##########")
# PRNewswireは組織別RSSを提供している場合がある（例: /rss/news-releases-list.rss は全体、
# 組織固有のURLがあるかを確認する）。
for url in [
    "https://www.prnewswire.com/rss/consumer-technology-latest-news/consumer-technology-latest-news-list.rss",
    "https://www.prnewswire.com/news/automatic-data-processing%2C-inc-/",
]:
    fetch(url, f"PRNewswire候補: {url}", max_chars=500)
