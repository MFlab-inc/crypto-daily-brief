"""診断用一時スクリプト（フォローアップ・日銀本文取得の実態確認とADP RSS検証）。

前回の診断で以下が判明した。
1. 日銀: 講演専用の別RSSは無い（/whatsnew/ページにはwhatsnew.xmlのみ・
   候補URL3件はすべて404）。一方、9/2の実コミット済みaudit_ledgerでは
   高田審議委員の講演自体は日本銀行tier1のwhatsnew.xml経由で候補に
   含まれていた（不採用理由="C: 審議委員の講演で、summaryが空欄のため
   内容を確認できない"）——つまり「講演カテゴリのRSSが無い」ことが
   原因ではなく、tier1候補の本文補強（fetch_article_body・v1.39）が
   このURLに対して機能しなかった可能性が高い。実際に同じ関数を通して
   確認する。
2. ADP: https://mediacenter.adp.com/press-releases?pagetemplate=rss
   というRSSリンクを発見した。実際に取得しRSSとして妥当か、
   ADP National Employment Reportに relevant な項目を含むかを確認する。

LLMは呼ばない。コミットは一切行わない。調査後、本スクリプトと
ワークフローは削除する。
"""
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402
import requests  # noqa: E402

print("########## 1. 日銀 whatsnew.xml の生XML内、9/2高田審議委員講演itemの実態確認 ##########")
resp = requests.get("https://www.boj.or.jp/rss/whatsnew.xml",
                     timeout=20, headers={"User-Agent": collect_news.USER_AGENT})
print(f"HTTP status: {resp.status_code}")
if resp.status_code == 200:
    root = ET.fromstring(resp.content)
    found = False
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if "高田" in title:
            found = True
            print(f"\n--- 該当item発見: {title!r} ---")
            for child in item:
                text = (child.text or "").strip()
                print(f"  <{child.tag}> text={text[:300]!r}")
    if not found:
        print("現在のwhatsnew.xmlには高田審議委員の講演item自体が既に無い"
              "（ローリングウィンドウで入れ替わった可能性・9/2実行時とは別）。")

print("\n\n########## 2. fetch_article_body()を実URLに対して実行 ##########")
real_url = "http://www.boj.or.jp/about/press/koen_2026/ko260902a.htm"
print(f"URL: {real_url}")
body = collect_news.fetch_article_body(real_url)
if body:
    print(f"抽出成功: {len(body)}字")
    print(f"先頭300字: {body[:300]!r}")
else:
    print("抽出失敗（Noneが返った）——<main>/<article>要素が見つからない、"
          "または抽出後200字以下、またはHTTP取得失敗のいずれか。")

print("\n--- 生HTML構造の確認（<main>/<article>タグの有無） ---")
resp2 = requests.get(real_url, timeout=20, headers={"User-Agent": collect_news.USER_AGENT})
print(f"HTTP status: {resp2.status_code}")
if resp2.status_code == 200:
    html = resp2.text
    print(f"取得バイト数: {len(resp2.content)}")
    print(f"<main タグを含むか: {'<main' in html.lower()}")
    print(f"<article タグを含むか: {'<article' in html.lower()}")

print("\n\n########## 3. ADP Media Center RSSフィードの実態確認 ##########")
adp_url = "https://mediacenter.adp.com/press-releases?pagetemplate=rss"
resp3 = requests.get(adp_url, timeout=20, headers={"User-Agent": collect_news.USER_AGENT})
print(f"URL: {adp_url}")
print(f"HTTP status: {resp3.status_code}")
print(f"Content-Type: {resp3.headers.get('Content-Type')}")
if resp3.status_code == 200:
    print(f"取得バイト数: {len(resp3.content)}")
    try:
        root3 = ET.fromstring(resp3.content)
        items = list(root3.iter("item"))
        print(f"item総数: {len(items)}")
        print("\n--- 先頭10件のタイトル・pubDate ---")
        for i, item in enumerate(items[:10]):
            title = (item.findtext("title") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            print(f"  [{i}] {title!r} ({pub})")
        print("\n--- 'Employment'または'National Employment Report'を含むタイトル ---")
        for item in items:
            title = (item.findtext("title") or "").strip()
            if "employment" in title.lower():
                print(f"  {title!r} ({(item.findtext('pubDate') or '').strip()})")
    except ET.ParseError as e:
        print(f"XML解析失敗: {e}")
        print(f"先頭500字: {resp3.text[:500]!r}")
