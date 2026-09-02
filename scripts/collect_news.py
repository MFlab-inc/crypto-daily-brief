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

【v1.59: tier4のうち実体がReutersのものをtier2へ昇格（オーナー承認）】
9/1に「米イラン交戦再開による原油急騰」をGoogle News経由で取得済み
だったにもかかわらずtier4分類のみを理由に不採用となった事象を受け、
「取得経路（Google News）」と「情報源の信頼度（Reuters）」の混同を
解消する。統合運用基準§2はReutersを「優先度2（独立報道）」と位置づけて
おり、Google News経由でも実体がReutersと確認できた記事はtier2として
扱う（tier1と同様、単独で採用可能）。実体確認はGoogle News RSSの
<source url="https://www.reuters.com">Reuters</source>要素で行う——
<link>は全件がGoogle Newsのリダイレクトであり実URLのドメイン照合は
機能しないが、<source>要素は実データで100/100件が正しくReutersの実体を
示すことを確認済み（リダイレクトを辿る必要が無い。DESIGN_CHANGES.md
v1.58参照）。判定は`_is_reuters_source()`で行う。

あわせてGOOGLE_NEWS_URLのクエリへ金融・マクロキーワードのOR条件を追加した
（オーナー指示・実測で効果を確認済み）。site:reuters.comのみのクエリは
Reuters全体の一般ニュース（人事・地名変更等）が大半を占め、tier2の
候補プールが暗号資産・金融と無関係な記事で埋まる問題があったため。
絞り込み後も9/1のイラン・原油記事は取得できることを実測済み
（DESIGN_CHANGES.md v1.59参照）。
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
from datetime import date, datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
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
# v1.51（オーナー指示）: allinurl:演算子がGoogle News RSS側で機能しなくなり
# （when:24hの有無を問わず0件）、8/26以降「対象日0件」が継続していた。
# 実測でsite:演算子への置き換えとロケールパラメータ付与により復旧を確認
# （site:reuters.com＋hl/gl/ceidで50件・すべて実際のReuters記事）。
#
# v1.59（オーナー指示・実測のうえ適用）: site:reuters.comのみでは
# Reuters全体の一般ニュース（人事・地名変更・スポーツ等）が上位を占め、
# tier2候補プールが暗号資産・金融と無関係な記事で埋まることを実測で確認
# （9/1相当の実データで先頭15件中10件超が無関係）。金融・マクロキーワード
# のOR条件を追加。診断の結果、(1) 絞り込み後も9/1のイラン・原油記事
# （"Strait of Hormuz"関連）は取得できることを実測で確認、
# (2) 絞り込み後の候補は金利・インフレ・原油・stablecoin等
# 金融関連が明確に多数を占めることを確認——「絞り込みで重要材料を
# 落とすなら見送る」というオーナーの判定基準を満たしたため適用する
# （DESIGN_CHANGES.md v1.59参照）。キーワード一覧はオーナー指定。
# なお、Google News RSSは1クエリあたり最大100件で頭打ちになるため
# （絞り込み前後で件数自体は変化しなかった・実測済み）、件数上限としての
# 効果は無い——効果は内容の関連度向上であり、件数削減ではない。
GOOGLE_NEWS_QUERY_KEYWORDS = (
    'crypto OR bitcoin OR ethereum OR "federal reserve" OR inflation OR '
    'tariff OR oil OR "interest rate" OR SEC OR stablecoin'
)
GOOGLE_NEWS_URL = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
    "q": f"when:24h site:reuters.com ({GOOGLE_NEWS_QUERY_KEYWORDS})",
    "hl": "en-US", "gl": "US", "ceid": "US:en",
})
_HTML_TAG_RE = re.compile(r"<[^>]+>")
# 一般的なブラウザのUser-Agent文字列（v1.13）。BLSがHTTP 403を返した際、
# 独自UA（旧: "crypto-daily-brief/1.0 (+https://github.com/...)"）が
# bot対策で拒否されている可能性を疑い変更した。変更後も403が続く場合は
# それ以上UAを変えて追跡せず、取得不能として記録するにとどめる
# （DESIGN_CHANGES.md参照）。
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# v1.39（オーナー指示）: tier1候補はsummaryが空/薄い場合が多く（政府機関RSSは
# タイトルとリンクのみという構成が多い）、波及経路は説明できても本文に書ける
# 実質的な内容が無いまま不採用になる事象が実データで確認された。tier1候補
# （日次0〜7件程度・取得コストは小さい）に限り、リンク先の<main>/<article>
# 本文を取得して要約を補う。
# v1.47（オーナー指示）: 8/27実データでcall_A入力トークンが前日の3倍
# （18,699→58,905）に膨らみ3試行とも出力上限で切断される事象が発生。
# tier1候補が11件（通常より多い）だった日で、本文取得量が入力膨張の
# 一因と推測されたため2000→1500へ引き下げ。切り詰めた場合はモデルが
# 「本文の全量」と誤認しないよう末尾に明示のマーカーを付す。
ARTICLE_BODY_CHAR_LIMIT = 1500
ARTICLE_BODY_TRUNCATION_MARKER = "…（以下略）"
ARTICLE_FETCH_TIMEOUT_SEC = 20
_MAIN_ARTICLE_MIN_CHARS = 200
_BODY_SKIP_TAGS = {"script", "style", "nav", "header", "footer"}
_BODY_MAIN_TAGS = {"main", "article"}


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

    v1.59（オーナー承認）: 各itemの<source>要素（text・url属性）も
    source_name・source_urlとして返す。多くのフィードには存在しないが
    （空文字になるだけで害はない）、Google Newsのような集約フィードでは
    元の発行元（実体）を示す——tier4のうちReutersの実体判定に使う
    （`_is_reuters_source()`参照）。
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
            source_el = item.find("source")
            source_name = (source_el.text or "").strip() if source_el is not None else ""
            source_url = source_el.attrib.get("url", "") if source_el is not None else ""
            if title or link:
                items.append({
                    "title": title, "url": link, "published_at": pub_date, "summary": summary,
                    "source_name": source_name, "source_url": source_url,
                })
        return "ok", items, ""
    except requests.RequestException as e:
        return "failed", [], f"{type(e).__name__}: {e}"
    except ET.ParseError as e:
        return "failed", [], f"XML解析失敗: {e}"


class _MainArticleExtractor(HTMLParser):
    """<main>/<article>要素直下のテキストのみを抽出する（v1.39）。

    <script>/<style>/<nav>/<header>/<footer>の内側は無視する。regexによる
    タグ検出は入れ子構造で正しく対応できないため、標準ライブラリの
    html.parser.HTMLParserでDOMを正しく辿る（新規の重い依存を追加しない）。
    <main>/<article>が無いページ（実測でFRBが該当。DESIGN_CHANGES.md
    v1.39参照）ではtextが空のままになる——呼び出し側はこの場合、
    ナビゲーション文言等が中心のページ全体へフォールバックせず、
    元のRSS summaryをそのまま使う（無内容なsummaryより、無関係な文言を
    本文と誤認させるほうが有害と判断したため）。
    """

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._main_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _BODY_SKIP_TAGS:
            self._skip_depth += 1
        if tag in _BODY_MAIN_TAGS:
            self._main_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _BODY_SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in _BODY_MAIN_TAGS and self._main_depth > 0:
            self._main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0 or self._main_depth <= 0:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    @property
    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._chunks)).strip()


def fetch_article_body(url: str, timeout: int = ARTICLE_FETCH_TIMEOUT_SEC) -> str | None:
    """tier1候補のリンク先本文を取得する（v1.39・オーナー指示）。

    <main>/<article>要素が見つかり、かつ抽出後の文字数が
    _MAIN_ARTICLE_MIN_CHARSを超える場合のみ本文を返す（先頭
    ARTICLE_BODY_CHAR_LIMIT字で切り詰める）。見つからない・取得失敗・
    文字数不足のいずれの場合もNoneを返す——呼び出し側はNoneの場合、
    元のRSS summaryをそのまま使う（フェイルクローズ不要。あくまで
    summaryの補強であり、本関数の失敗が候補自体を落とすことはない）。

    v1.47（オーナー指示）: 切り詰めが発生した場合、文の途中で切れても
    構わないが、末尾にARTICLE_BODY_TRUNCATION_MARKERを付し、モデルが
    「これが本文の全量」と誤認しないようにする。
    """
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        if resp.status_code != 200:
            return None
        parser = _MainArticleExtractor()
        parser.feed(resp.text)
        text = parser.text
        if len(text) <= _MAIN_ARTICLE_MIN_CHARS:
            return None
        if len(text) > ARTICLE_BODY_CHAR_LIMIT:
            return text[:ARTICLE_BODY_CHAR_LIMIT] + ARTICLE_BODY_TRUNCATION_MARKER
        return text
    except requests.RequestException:
        return None
    except Exception:  # noqa: BLE001 — summaryの補強に過ぎず、本文取得の
        # 不調で候補収集全体を巻き添えにしない（fetch_rss・§4.1と同じ思想）。
        return None


def _is_reuters_source(item: dict[str, str]) -> bool:
    """Google News経由の記事の実体がReutersかを、RSSの<source>要素で判定する
    （v1.59・オーナー承認）。<source url="https://www.reuters.com">Reuters
    </source>という構造を実データで確認済み（取得100件中100件・
    site:reuters.com検索にもかかわらずReuters以外の<source>の混入は0件。
    DESIGN_CHANGES.md v1.58参照）。<link>はGoogle Newsのリダイレクトの
    ためドメイン照合はできないが、本関数はリダイレクトを辿らずに判定できる。
    """
    name = item.get("source_name", "").lower()
    src_url = item.get("source_url", "").lower()
    return "reuters" in name or "reuters.com" in src_url


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
        summary = it.get("summary", "")
        if tier == 1 and it["url"]:
            # v1.39（オーナー指示）: tier1候補のみリンク先本文で補強する
            # （日次0〜7件程度・取得コストは小さい）。<main>/<article>が
            # 見つからない場合はNoneが返り、元のRSS summaryをそのまま使う。
            body = fetch_article_body(it["url"])
            if body:
                summary = body

        cand_source, cand_tier, cand_kind = name, tier, kind
        # v1.59（オーナー承認）: tier4（Google News・候補発見専用）のうち
        # 実体がReutersと確認できたものはtier2（統合運用基準§2の優先度2・
        # 独立報道）へ昇格し、単独採用を可能にする。取得経路（Google News）
        # と情報源の信頼度（Reuters）を混同しないための措置（DESIGN_CHANGES.md
        # v1.58・v1.59参照）。
        if tier == 4 and _is_reuters_source(it):
            cand_source, cand_tier, cand_kind = "Reuters", 2, _TIER_KIND[2]

        candidates.append({
            "title": it["title"],
            "url": it["url"],
            "source": cand_source,
            "published_at": it["published_at"],
            "summary": summary,
            "kind": cand_kind,
            "tier": cand_tier,
        })
    print(f"OK: {name} {len(items)}件取得・対象日{len(candidates)}件（url={url}）")
    return {"status": "ok", "raw_count": len(items), "kept_count": len(candidates)}, candidates


# v1.53（オーナー指示）: 経済カレンダー（CPI・PCE・FOMC・雇用統計・要人講演等）
# の予定を取得する。8/22カナダ関税・8/26 PCE・8/28ジャクソンホール講演など
# 「その日最大の材料」を繰り返し取りこぼした事象への対応——CPI・PCE・FOMC
# 等の予定日は事前に確定しており報道を待つ必要がない。scheduled_events自体は
# 呼び出しAへ「この材料を探すべき」というヒントとして渡すのみで、本文の
# 直接の根拠にはしない（対応するRSS候補が無ければ何も書かない。プロンプト
# 側の指示で担保する）。
#
# データソースはnfs.faireconomy.media（Forex Factoryの経済カレンダーを
# JSON形式で配信する非公式だが広く使われているエンドポイント）。
# MFlab-inc/EA-Risk-Monitorのscripts/lib/calendar.js（リアルタイムFX
# リスク監視向け・48時間先読み）を参考にしたが、用途が異なるため
# 以下を変更した（オーナー承認）：
# ・thisweekフィードのみ使用する。nextweekは本システムが前日分のみを
#   扱う（48時間先読みの必要が無い）ため不要と判断——実測でnextweekは
#   HTTP 404だったこともこの判断の裏付けとなった。
# ・country=="All"（Jackson Hole Symposiumのような通貨非依存イベント）を
#   除外しない。元実装はFXペア向けの通貨フィルタで除外していたが、
#   暗号市場のマクロ心理を扱う本用途では拾う対象とする。
# ・impact=="High"のみを対象とする（Medium以下はヒントとしてノイズに
#   なりやすいというオーナー判断）。
# ・イベント種別分類（EVENT_RULES的なregex分類）は移植しない——LLMへの
#   ヒントとして渡すだけで自動判定には使わないため不要。
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CAL_CURRENCIES = {"USD", "JPY", "EUR", "GBP", "AUD", "CAD", "CHF", "CNY", "NZD", "All"}


def fetch_economic_calendar(window_start: datetime, window_end: datetime) -> list[dict[str, Any]]:
    """対象日の収集ウィンドウ（collection_window_ny()と同じ半開区間
    [window_start, window_end)）に該当する高インパクト経済イベントを返す。

    取得・解析に失敗した場合（非200・JSON不正等）は空リストを返す
    （collect_news.pyの他の取得関数と同じフェイルオープンの思想——
    経済カレンダーは本文生成の必須要素ではなく、あくまでヒントであるため
    失敗を理由にパイプライン全体を止めない）。
    """
    try:
        resp = requests.get(FF_CALENDAR_URL, timeout=REQUEST_TIMEOUT_SEC,
                             headers={"User-Agent": USER_AGENT})
        if resp.status_code != 200:
            print(f"WARN: 経済カレンダー取得失敗: HTTP {resp.status_code} (url={FF_CALENDAR_URL})",
                  file=sys.stderr)
            return []
        raw_events = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"WARN: 経済カレンダー取得失敗: {type(e).__name__}: {e} (url={FF_CALENDAR_URL})",
              file=sys.stderr)
        return []

    events = []
    for e in raw_events:
        if not isinstance(e, dict) or e.get("impact") != "High" or e.get("country") not in CAL_CURRENCIES:
            continue
        try:
            event_dt = datetime.fromisoformat(str(e.get("date", "")))
        except ValueError:
            continue
        if event_dt.tzinfo is None or not (window_start <= event_dt < window_end):
            continue
        events.append({
            "title": e.get("title", ""),
            "country": e.get("country", ""),
            "impact": e.get("impact", ""),
            "time_jst": event_dt.astimezone(JST).isoformat(),
        })
    events.sort(key=lambda ev: ev["time_jst"])
    print(f"OK: 経済カレンダー {len(raw_events)}件取得・対象日High{len(events)}件（url={FF_CALENDAR_URL}）")
    return events


_TIER_KIND = {1: "official", 2: "independent_report", 3: "supplementary"}


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
