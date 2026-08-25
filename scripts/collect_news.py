#!/usr/bin/env python3
"""collect_news.py — 公式発表RSS＋（任意）Google Newsによるニュース候補収集
（v0.4方針転換・§10 第2弾-4）。

方針転換の経緯（オーナー指示・DESIGN_CHANGES.md v1.11参照）：
Reutersは2020年に公開RSSを廃止済み、CryptoPanicもエンドポイント不明のまま
HTTP 404が実測された。優先度1（規制当局・政府・企業・取引所の公式発表）の
RSSが最も確実かつ一次情報として価値が高いと判断し、CryptoPanic連携は撤去した。

`config/news_sources.json` に列挙されたRSSを1件ずつ独立して取得する
（fetch_cmc の3エンドポイント分離と同じ思想 — 1件の失敗が他を巻き添えにしない）。

【v1.38: 材料収集ウィンドウをJST暦日からNY 17:00基準へ変更（オーナー指示）】
取得した各項目は、対象日のAmerica/New_York 17:00で終わる24時間
（`collection_window_ny()`参照）に公開されたものだけを候補として残す。
市場の1日はJST暦日ではなくNY 17:00区切りであり、米国当局・政府機関の
発表は現地日中（＝JST未明）が大半のため、旧来のJST暦日基準では
構造的にほぼ全ての米国発材料が翌日のJST暦日へ流れていた
（DESIGN_CHANGES.md v1.38参照。対象日ラベルの決定＝実行時JSTの前日、
は統合運用基準§1のとおり変更していない——変更したのは材料収集の
範囲のみ）。1件も候補が無い日があっても正常（停止しない）。

v1.20: 優先度2（Reuters・Bloomberg）は公開RSSが無いため正式に断念し
（DESIGN_CHANGES.md v1.19の独立レビュー指摘・v1.20参照）、優先度3として
CoinDesk・Cointelegraph（英語・日本語版）を追加した。tierはnews_sources.json
側の各エントリで指定し（既定1）、tier 3は「補完・裏取り」用途に限り、
単独では事実の主根拠にしない（呼び出しA側のプロンプトで指示）。

優先度4の候補発見層として Google News RSS（Reuters記事の発見のみ）も
任意で使う。見出しとURLのみを候補として渡し、記事本文を根拠にしない
（v1.15: 呼び出しAはweb_searchを使わず、本スクリプトが渡すsummary
〈RSSのdescription由来〉のみを根拠に選別・執筆する。tier 4はsummaryが
無い/薄いため、単独では事実の根拠にできない設計になっている）。
到達性が不安定でも本スクリプトは失敗しない。
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import requests

JST = timezone(timedelta(hours=9))
# v1.38（オーナー指示）: 材料収集ウィンドウの基準タイムゾーン。市場の1日の
# 区切りであるNY 17:00を、夏時間・冬時間を自動判定するzoneinfoで扱う
# （固定オフセットのdatetime.timezoneでは自前でDST判定が必要になり誤りやすい）。
NY_TZ = ZoneInfo("America/New_York")
REQUEST_TIMEOUT_SEC = 15
RAW_ITEM_LIMIT = 50  # 1フィードあたりの取得上限（日付フィルタ前）。暴走防止のガード値。
SUMMARY_MAX_LEN = 500  # 1候補あたりのsummary長の上限（プロンプト肥大化防止・v1.15）。
SOURCES_CONFIG_PATH = Path(__file__).parent.parent / "config" / "news_sources.json"
GOOGLE_NEWS_NAME = "Google News (Reuters検索)"
GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com"
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# 一般的なブラウザのUser-Agent文字列（v1.13）。BLSがHTTP 403を返した際、
# 独自UA（旧: "crypto-daily-brief/1.0 (+https://github.com/...)"）が
# bot対策で拒否されている可能性を疑い変更した。変更後も403が続く場合は
# それ以上UAを変えて追跡せず、取得不能として記録するにとどめる
# （DESIGN_CHANGES.md参照）。
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")


def _now_jst_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _load_sources() -> list[dict[str, Any]]:
    if not SOURCES_CONFIG_PATH.exists():
        return []
    try:
        data = json.loads(SOURCES_CONFIG_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    sources = data.get("sources", [])
    return [s for s in sources if isinstance(s, dict) and s.get("name") and s.get("url")]


def parse_pubdate_jst(raw: str) -> datetime | None:
    """RSSのpubDate（RFC 822想定）をJST awareなdatetimeへ変換する。
    解釈できない・空の場合、およびタイムゾーン情報を持たない場合はNone
    （呼び出し側で収集ウィンドウ・対象日フィルタから除外する）。
    公開関数（v1.21よりgenerate_post.pyがtier3候補の新しい順ソートで再利用。
    v1.38より_collect_from_feed()の収集ウィンドウ判定にも使う——表示上は
    JSTへ変換するが、tz-aware datetimeとしての瞬時は変わらないため、
    NY基準のウィンドウ（collection_window_ny()）との比較にもそのまま使える）。

    v1.38（オーナー指示）: タイムゾーン情報が無いpubDateは、以前は
    「RFC822の慣例としてUTC扱い」としていたが、実際のタイムゾーンが
    不明である以上、それを推測で補うと窓の内外を誤って判定しうる。
    フェイルクローズ（不明なものは除外）へ変更し、解析失敗と同様にNoneを
    返す。
    """
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None or dt.tzinfo is None:
        return None
    return dt.astimezone(JST)


def collection_window_ny(target: "date") -> tuple[datetime, datetime]:
    """対象日の材料収集ウィンドウを返す（v1.38・オーナー指示）。

    (window_start, window_end) はいずれもtz-aware。半開区間
    [window_start, window_end) として扱う（window_end自体は含まない）。
    window_end = 対象日のAmerica/New_York 17:00（ローカル時刻）。
    window_start = window_end の1日前（同じくローカル17:00）。
    【境界の扱い・オーナー指示で明示】NY 17:00ちょうどのpubDateは
    「翌日側」の候補として扱う（当日側には含めない）。タイムゾーン情報を
    持たないpubDateは`parse_pubdate_jst()`がNoneを返しフェイルクローズ
    （窓の内外を問わず除外）される——詳細は同関数のdocstring参照。

    datetimeの引き算はtimedeltaぶんの暦日を進めたうえで同じtzinfo
    （ZoneInfo）を再付与するため、window_start・window_endのそれぞれが
    「その暦日のNY 17:00」として夏時間・冬時間を自動的に正しく解決する
    （例: 冬時間はUTC-5、夏時間はUTC-4）。時刻をハードコードしていない。

    【注意・Pythonのdatetime減算の落とし穴】本関数が返す2つのdatetimeは
    同一のtzinfoオブジェクト（NY_TZ）を共有しているため、呼び出し側で
    `window_end - window_start` のように両者を直接引き算すると、Pythonは
    「tzinfoが同一なら実時刻への正規化をせず素の日時フィールドのまま
    引き算する」という仕様上、DST切替を跨ぐ日（3月・11月の切替日）でも
    常に24時間ちょうどを返してしまう（実際には23時間・25時間になり得る）。
    真の経過時間が必要な場合は両者を`.astimezone(timezone.utc)`してから
    引き算すること。本モジュールの実際のフィルタ処理
    （`_collect_from_feed`のwindow_start <= pub_dt < window_end）は
    pub_dt側がJST固定オフセット（NY_TZとは別のtzinfoオブジェクト）である
    ため、この落とし穴の影響を受けない（実測で確認済み。DESIGN_CHANGES.md
    v1.38参照）。
    """
    window_end = datetime(target.year, target.month, target.day, 17, 0, tzinfo=NY_TZ)
    window_start = window_end - timedelta(days=1)
    return window_start, window_end


def _clean_summary(raw: str) -> str:
    """<description>由来の要約からHTMLタグを除去し、空白を正規化して長さを
    上限で切り詰める（呼び出しAのプロンプトへそのまま埋め込むため）。
    """
    text = _HTML_TAG_RE.sub("", raw or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > SUMMARY_MAX_LEN:
        text = text[:SUMMARY_MAX_LEN] + "…"
    return text


def fetch_rss(url: str, timeout: int = REQUEST_TIMEOUT_SEC) -> tuple[str, list[dict[str, str]], str]:
    """1フィードを取得しRSS 2.0の<item>一覧へ変換する。

    戻り値: (status: "ok"|"failed", items, detail)。ネットワーク障害・非200・
    XML不正のいずれでも例外を送出せず"failed"を返す — 1フィードの不調が
    他のフィード・パイプライン全体を巻き添えにしないため（§4.1の要件と同じ思想）。
    """
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        if resp.status_code != 200:
            return "failed", [], f"HTTP {resp.status_code}"
        root = ET.fromstring(resp.content)
        items = []
        for item in list(root.iter("item"))[:RAW_ITEM_LIMIT]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            summary = _clean_summary(item.findtext("description") or "")
            if title or link:
                items.append({"title": title, "url": link, "published_at": pub_date, "summary": summary})
        return "ok", items, ""
    except requests.RequestException as e:
        return "failed", [], f"{type(e).__name__}: {e}"
    except ET.ParseError as e:
        return "failed", [], f"XML解析失敗: {e}"


def _collect_from_feed(name: str, url: str, window_start: datetime, window_end: datetime,
                        *, tier: int, kind: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    status, items, detail = fetch_rss(url)
    if status != "ok":
        print(f"WARN: {name} 取得失敗: {detail} (url={url})", file=sys.stderr)
        return {"status": "failed", "detail": detail}, []

    candidates = []
    for it in items:
        # v1.38: JST暦日の一致判定ではなく、NY 17:00基準ウィンドウへの
        # 瞬時（instant）比較。aware datetime同士の比較はPythonが内部で
        # 実際の時刻差として正しく評価するため、pub_dt側の表示タイムゾーン
        # （JST）とwindow側（NY）が異なっていても問題ない。
        pub_dt = parse_pubdate_jst(it["published_at"])
        if pub_dt is None or not (window_start <= pub_dt < window_end):
            continue
        candidates.append({
            "title": it["title"],
            "url": it["url"],
            "source": name,
            "published_at": it["published_at"],
            "summary": it.get("summary", ""),
            "kind": kind,
            "tier": tier,
        })
    print(f"OK: {name} {len(items)}件取得・対象日{len(candidates)}件（url={url}）")
    return {"status": "ok", "raw_count": len(items), "kept_count": len(candidates)}, candidates


_TIER_KIND = {1: "official", 3: "supplementary"}


def collect_news(target_date: str) -> dict[str, Any]:
    target = date.fromisoformat(target_date)
    window_start, window_end = collection_window_ny(target)
    source_status: dict[str, Any] = {}
    all_candidates: list[dict[str, Any]] = []

    for src in _load_sources():
        # v1.20: tierはnews_sources.json側で指定（既定1）。tier 3（CoinDesk等の
        # 暗号通貨特化メディア）を優先度2の欠落（Reuters/Bloombergとも公開RSS
        # 廃止済み・DESIGN_CHANGES.md v1.19参照）を補う「補完・裏取り」として追加。
        tier = src.get("tier", 1)
        kind = _TIER_KIND.get(tier, "official")
        st, cands = _collect_from_feed(src["name"], src["url"], window_start, window_end, tier=tier, kind=kind)
        source_status[src["name"]] = st
        all_candidates.extend(cands)

    # 優先度4: Google News RSS（候補発見のみ・任意）。失敗しても縮退。
    g_st, g_cands = _collect_from_feed(GOOGLE_NEWS_NAME, GOOGLE_NEWS_URL, window_start, window_end,
                                        tier=4, kind="candidate_discovery")
    source_status[GOOGLE_NEWS_NAME] = g_st
    all_candidates.extend(g_cands)

    return {
        "collected_at": _now_jst_iso(),
        "target_date_jst": target_date,
        "source_status": source_status,
        "candidates": all_candidates,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: collect_news.py <対象日 YYYY-MM-DD>", file=sys.stderr)
        return 1
    target_date = sys.argv[1]

    result = collect_news(target_date)

    out_dir = Path(f"outputs/{target_date}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "news_candidates.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    ok_sources = [n for n, s in result["source_status"].items() if s.get("status") == "ok"]
    failed_sources = [n for n, s in result["source_status"].items() if s.get("status") != "ok"]
    print(f"OK: {out_path}（候補{len(result['candidates'])}件／情報源 成功:{ok_sources} 失敗:{failed_sources}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
