"""診断用一時スクリプト（tier4/Reuters見直し調査・オーナー指示）。

9/1に「米イラン交戦再開による原油急騰」を取りこぼした件を受け、
オーナーから3案の検討を依頼された。
(a) Google News経由でも実体がReuters（url が reuters.com）のものは
    tier2として単独採用可能にする
(b) tier4のままだが独立2ソース判定でtier3と組めるようにする
(c) 現状維持・既知の限界として記録

【9/1実データで既に確認済み（本スクリプト実行前・ローカルの
outputs/2026-09-01/draft/post_bundle.jsonを直接読んで確認）】
audit_ledgerに「US launches new barrage of strikes on Iran around
Strait of Hormuz - Reuters」が実在し、source=Google News (Reuters検索)、
decision=不採用、reason="tier4のため候補発見専用として不採用"だった。
つまり材料はGoogle News経由で実際に取得できていたが、tier4という
分類のみを理由に機械的に不採用となっていた——オーナーの見立てどおり。

(a)の実装可否は「Google NewsのRSSアイテムから実体ソース（Reuters）を
安価に判定できるか」に懸かる。本スクリプトは、Google News RSS
（実際にcollect_news.pyが使っているURL）の生XMLを直接取得し、
<source>タグの有無・内容、<link>が直接URLかリダイレクトURLかを
実データで確認する（fetch_rss()は現在<source>を一切読んでいないため、
この情報が既に取れるかを確かめる必要がある）。

LLMは呼ばない。コミットは一切行わない。調査後、本スクリプトと
ワークフローは削除する。
"""
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, "scripts")
import collect_news  # noqa: E402
import requests  # noqa: E402

print(f"URL: {collect_news.GOOGLE_NEWS_URL}")

resp = requests.get(collect_news.GOOGLE_NEWS_URL, timeout=20,
                     headers={"User-Agent": collect_news.USER_AGENT})
print(f"HTTP status: {resp.status_code}")
print(f"取得バイト数: {len(resp.content)}")

root = ET.fromstring(resp.content)
items = list(root.iter("item"))
print(f"item総数: {len(items)}")

print("\n=== 先頭5件の生XML全要素（タグ名・属性・テキストをすべて表示） ===")
for i, item in enumerate(items[:5]):
    print(f"\n--- item[{i}] ---")
    for child in item:
        attrs = dict(child.attrib) if child.attrib else {}
        text = (child.text or "").strip()
        print(f"  <{child.tag}> attrs={attrs} text={text[:200]!r}")

print("\n=== <source>タグの有無・内容（全item） ===")
has_source_count = 0
non_reuters_sources = set()
for i, item in enumerate(items):
    source_el = item.find("source")
    if source_el is not None:
        has_source_count += 1
        src_text = (source_el.text or "").strip()
        src_url = source_el.attrib.get("url", "")
        if i < 15:
            print(f"  item[{i}]: source.text={src_text!r} source.url={src_url!r}")
        if "reuters" not in src_text.lower() and "reuters" not in src_url.lower():
            non_reuters_sources.add((src_text, src_url))
print(f"<source>タグを持つitem数: {has_source_count}/{len(items)}")
print(f"source.text/urlにreutersを含まないitem（site:reuters.com検索なのに"
      f"混入している場合を確認）: {non_reuters_sources or 'なし'}")

print("\n=== <link>の値のパターン確認（直接URLかGoogle Newsリダイレクトか） ===")
for i, item in enumerate(items[:10]):
    link = (item.findtext("link") or "").strip()
    is_google_redirect = "news.google.com" in link
    print(f"  item[{i}]: is_google_redirect={is_google_redirect} link={link[:150]!r}")

print("\n=== title末尾の \" - {発行元}\" パターン確認（参考・source代替シグナルになりうるか） ===")
for i, item in enumerate(items[:10]):
    title = (item.findtext("title") or "").strip()
    print(f"  item[{i}]: title={title!r}")

print("\n=== <guid>の値のパターン確認（参考） ===")
for i, item in enumerate(items[:5]):
    guid = item.find("guid")
    if guid is not None:
        print(f"  item[{i}]: guid.text={(guid.text or '')[:150]!r} attrib={dict(guid.attrib)}")
