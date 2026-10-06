#!/usr/bin/env python3
"""generate_post.py — 呼び出しA・B（LLM生成）と縮退レベル判定（v0.3 §5・§10 第2弾-5・v1.15改定）。

呼び出しA（ヘッドライン・主要なポイント）と呼び出しB（フロー・総括）を分離し、
片方の失敗が全体を巻き添えにしない（§2.2・§5.3）。各呼び出しは最大
MAX_ATTEMPTS回まで試行し、それでも失敗した呼び出しは compose_post.py 側の
縮退ラダー（§7）へ「失敗」として渡す。

【v1.15: 呼び出しAからweb_searchを撤去（オーナー指示）】
v1.11〜v1.13でweb_search必須化を試みたが、RSS候補が乏しい日に呼び出しAが
検索を繰り返し（最大56回・v1.11）、上限（max_uses）を設けても（v1.13）
3試行とも空応答のまま失敗する事象が2回連続で実測された（DESIGN_CHANGES.md
v1.12・v1.14）。オーナー判断により、パラメータ調整ではなく呼び出し構造自体の
問題と結論し、呼び出しAからツールを完全に撤去した。collect_news.py が
取得したRSS候補（title・summary・published_at・source・tier）をユーザー
メッセージへテキストとして埋め込み、その中から選別・執筆させる方式へ変更。
呼び出しBと同一の「ツール無しの通常メッセージ呼び出し」構造になり、Bが
安定して1回で成功し続けている実績（3回のdispatchで3回とも1回目に成功）が
Aにもそのまま当てはまる見込み。

縮退レベルの判定について（台本にない状態の扱い・要確認として報告する）:
  台本§7の表は L0=両成功／L1=Aのみ失敗／L2=両失敗 の3値のみを定義しており、
  「Aは成功・Bのみ失敗」という状態が明記されていない。本実装では
  level = 失敗した呼び出し数（0→L0, 1→L1, 2→L2）として一般化し、
  「Bのみ失敗」もL1として扱う（Aの成果＝headline_for_image/part1系は活かし、
  Bの2セクションのみ§7.1の定型文に落とす）。L3はdaily_data.json欠損・
  C1〜C11監査FAILの判定であり、本モジュールの呼び出し前提条件として
  compose_post.py側で判定する（本モジュールはdaily_data.jsonの存在を前提とする）。

CLI（単独実行・検証用。実際の合成は compose_post.py が run() を直接呼ぶ):
  ANTHROPIC_API_KEY=... python scripts/generate_post.py <対象日 YYYY-MM-DD>
  → outputs/{対象日}/draft/post_generation.json に生の呼び出し結果を書き出す。
"""
from __future__ import annotations

import copy
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import anthropic

import collect_news
import indicator_events

MODEL = "claude-sonnet-5"
# v1.21: 4000→8000へ再引き上げ。v1.20でtier3（CoinDesk・Cointelegraph）を
# 追加した結果、候補急増日（実測30件）でaudit_ledgerの全候補記録が
# 4000トークンに収まらずJSON途中で打ち切られる事象が実測された
# （DESIGN_CHANGES.md v1.21参照）。候補数上限（TIER3_CANDIDATE_LIMIT）と
# 併用し、上限を設けてもなお安全余裕を持たせるための引き上げ。
CALL_A_MAX_TOKENS = 8000
CALL_B_MAX_TOKENS = 2000
MAX_ATTEMPTS = 3  # 初回+リトライ2回（§5.3「リトライ: 各2回まで」）
RETRY_DELAYS_SEC = (2, 4)
# v1.21: tier3（CoinDesk・Cointelegraph等）は候補が多い日に急増しうる
# （実測: 1日で28件）。tier1（公式発表）は全件を渡すが、tier3は公開日時の
# 新しい順で上位この件数までに絞って呼び出しAへ渡す（DESIGN_CHANGES.md
# v1.21参照。オーナー指示）。
# v1.39（オーナー指示）: 10→15へ引き上げ。上限10が独立2ソース規定を満たす
# ペアの片方を切り捨てる事象が実データで確認された（8/25・44件中34件を
# 除外し、ペアの一方が11位で漏れた実例）。上限20案は実測でcall_A出力が
# 上限8000の88%（7075トークン）に達し、tier3候補急増日（実測44件）を
# 踏まえると再度の途中切断リスクに近づくため見送り、11で足りた実測に
# 安全マージンを加えた15とした（DESIGN_CHANGES.md v1.39参照）。
TIER3_CANDIDATE_LIMIT = 15

# v1.59（オーナー承認）: tier2（Reuters・Google News経由で実体確認済み）の
# 選定上限。統合運用基準ではReutersが優先度2でtier3（優先度3）より上位
# であり件数を下回らせる理由がないため、tier3と同格の15とする（オーナー
# 指定）。tier1（無制限）とは異なり上限を設ける——Reuters検索クエリは
# site:reuters.comのみで金融・暗号資産に絞られておらず、実データで
# 上位に人事・地名変更等の無関係な一般ニュースが多数含まれることを
# 確認済み（DESIGN_CHANGES.md v1.58参照）。tier1同様の無制限扱いは
# 無関係記事の混入によるトークン消費・選定ノイズの増大を招く。
TIER2_CANDIDATE_LIMIT = 15

# v1.39フォローアップ（オーナー承認）: 「公開日時の新しい順で上位N件」という
# 選定方式は、収集ウィンドウ序盤に出た記事を窓終盤の記事群に押しやる構造的な
# 時間帯バイアスを持つ（実データ: 8/25のBTC $80,000到達＝3か月ぶり高値を
# 報じたCoinDesk記事2本が、公開時刻が早いという理由だけで44件中24位・43位
# となりLIMIT=15後も候補集合から漏れていた）。件数上限の引き上げでは
# 解決しないため、独立2媒体が同一事実を報じているペアは、順位に関わらず
# 両方を候補集合へ残す（ペア救済）。救済はTIER3_CANDIDATE_LIMIT件の
# 上限外で加算する（当初オーナー案の「上限を超えても両方残す」を反映）。
PAIR_OVERLAP_THRESHOLD_DEFAULT = 0.4  # タイトルのトークン重なり係数（overlap coefficient）の
# 閾値のデフォルト値。8/24のCoinbase/Baseトークン化株式ペア（既知の独立2ソース
# 成功例）で0.45と実測し較正した値（DESIGN_CHANGES.md v1.39参照。較正基盤は
# 1件のみで薄い）。v1.53フォローアップ（オーナー指示）: ペア救済（pre-selection）
# と独立2ソース自己申告の妥当性確認（post-selection）の両方で共用し、
# config/pair_overlap.json（load_pair_overlap_threshold()）で調整可能にした。
# ファイル欠損・不正時のフェイルクローズ値としてこの定数を維持する。
PAIR_OVERLAP_CONFIG_PATH = Path(__file__).parent.parent / "config" / "pair_overlap.json"
PAIR_RESCUE_MAX_PAIRS = 5  # ペア救済は最大5組（最大10件）まで。無制限だと
# トークン予算を超えるリスクがあるため上限を設ける（オーナー指示）。

# v1.51（オーナー指示）: tier4（Google News・候補発見専用）は、
# GOOGLE_NEWS_URLのクエリ演算子修正（allinurl:→site:）まで実測が常に
# 0件だったため無制限で渡していたが、修正後は実データで50件
# （RAW_ITEM_LIMIT上限）に達することを確認した。tier3と同じ構造の
# 予算超過リスクを避けるため、公開日時の新しい順で上位この件数までに
# 絞る（オーナー指定の目安「上位10件まで」）。
TIER4_CANDIDATE_LIMIT = 10

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def load_pair_overlap_threshold() -> float:
    """タイトルのトークン重なり係数の閾値をconfig/pair_overlap.jsonから読む
    （v1.53フォローアップ・オーナー指示）。ペア救済（pre-selection）と
    独立2ソース自己申告pairs_with_candidate_idの妥当性確認（post-selection）
    の両方で共用する。ファイル欠損・不正時はデフォルト値
    （PAIR_OVERLAP_THRESHOLD_DEFAULT）にフェイルクローズする
    （他のconfig読み込み関数・fetch_data.load_notable_move_thresholdと
    同じ方針）。
    """
    if not PAIR_OVERLAP_CONFIG_PATH.exists():
        return PAIR_OVERLAP_THRESHOLD_DEFAULT
    try:
        data = json.loads(PAIR_OVERLAP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return PAIR_OVERLAP_THRESHOLD_DEFAULT
    v = data.get("pair_overlap_threshold")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else PAIR_OVERLAP_THRESHOLD_DEFAULT


def _tokenize_title(title: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(title).lower()))


def _overlap_coefficient(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _find_independent_pairs(tier3_sorted: list[dict],
                             threshold: float = PAIR_OVERLAP_THRESHOLD_DEFAULT) -> list[tuple[dict, dict]]:
    """独立2媒体が同一事実を報じているとみられるペアを検出する（v1.39
    フォローアップ）。タイトルのトークン重なり係数がthreshold以上、
    かつsourceが異なる組み合わせをペアとみなす。1記事が複数ペアへ
    重複計上されないよう、ペアが確定した記事は以降の走査から除外する
    （貪欲法）。tier3_sortedは公開日時の新しい順を前提とし、より新しい
    記事同士の組み合わせが優先的にペア判定される。
    """
    pairs: list[tuple[dict, dict]] = []
    used: set[int] = set()
    n = len(tier3_sorted)
    for i in range(n):
        a = tier3_sorted[i]
        if id(a) in used:
            continue
        a_tokens = _tokenize_title(a.get("title", ""))
        for j in range(i + 1, n):
            b = tier3_sorted[j]
            if id(b) in used or a.get("source") == b.get("source"):
                continue
            sim = _overlap_coefficient(a_tokens, _tokenize_title(b.get("title", "")))
            if sim >= threshold:
                pairs.append((a, b))
                used.add(id(a))
                used.add(id(b))
                break
    return pairs

REQUIRED_KEYS_A = [
    "headline_for_image", "part1_headline", "part1_points",
    "reusable_for_summary", "audit_ledger",
]
REQUIRED_KEYS_B = ["part2_flow", "part2_summary"]

# 統合運用基準§3.1の逐語文言。呼び出しAが「候補はあるが書くに足る内容が無い」
# 場合に自らこの文言を出力する（プロンプトに埋め込む・下記NO_CANDIDATES_FALLBACK）。
# compose_post.py が呼び出しA自体の失敗時（L1/L2縮退）に代入する文言もこれと
# 同一（generate_post.FIXED_HEADLINE/FIXED_POINTS として compose_post.py 側が
# 参照する — 定義を二重に持たず、常に同じ文言であることを保証するため）。
FIXED_HEADLINE = "直近24時間に暗号通貨市場との関係を確認できる主要なマクロ材料は確認できない。"
FIXED_POINTS = "補足できる検証済み材料は確認できない。"
# v1.79（オーナー承認）: 【市場のフロー】・【総括】の縮退時固定文言も、上記2つと
# 同じ理由でここに定義を集約する（従来はcompose_post.py側に個別定義していたが、
# verify_post.pyのC27（総括の役割分離監査）がこの定型文を「LLM生成の散文ではない」
# と識別するために参照する必要が生じた——verify_post.pyはcompose_post.pyを
# importできない〈compose_post.py→verify_post.pyの依存が既にあり循環を生む〉ため、
# FIXED_HEADLINE/FIXED_POINTSと同様にgenerate_post.py側へ集約した。
# compose_post.pyは後方互換のためcompose_post.FIXED_FLOW/SUMMARY_BLANK_NOTEとして
# 引き続き参照できる（下記のcompose_post.py側のエイリアス参照）。
FIXED_FLOW = "価格変動との関係を確認できる主要材料は確認できない。"
SUMMARY_BLANK_NOTE = "（今回は自動生成できませんでした。確認可能な事実のみで人が補ってください。）"

# --- プロンプト（v0.3 §5.1・§5.2から逐語転記。台本改定時は本ファイルも追随させる） ---

ROLE_INTRO = (
    "あなたは金融機関に勤めるプロとして、初心者の投資家・トレーダー向けに\n"
    "暗号通貨・DEX市場の日次レポートを執筆します。専門用語には初心者向けの\n"
    "補足を添えてください。"
)

RULES_ABSOLUTE = """## 絶対規則

1. 対象日は入力の target_date_jst / weekday_jp をそのまま使う。自分で日付を決めない。
2. 数値を本文に書かない。価格・時価総額・出来高・APR・TVL・ドミナンス・
   為替レートは後段のテンプレートが差し込む。独自に算出・転記した数値を
   記載しない。定性表現（増加・低下・横ばい）は可。
   ただしニュース由来の数値（政策金利、経済指標の実数、企業の発表金額など）は
   原典で確認できた場合に限り記載してよい。
3. 「暗号通貨」と表記する。「仮想通貨」は使わない。
4. 変化率のラベルは「24時間比」。「前日比」は使わない。
5. 未確認・取得不能の事項を推測で補わない。確認できない場合はその旨を書く。
6. 投資判断の推奨・勧誘・断定的判断の提供を行わない。
7. 米連邦準備制度（連邦準備制度理事会）の略称は「FRB」に統一する（v1.85・オーナー承認）。
   英文の見出し・記事にある「Fed」「FED」も「FRB」と書き換え、1回の出力
   （ヘッドライン・主要なポイント・市場のフロー・総括・headline_for_image）の中で
   「Fed」と「FRB」を混在させない。FOMC（連邦公開市場委員会）は、会合・委員会
   そのものを指す場合に限って使ってよい。ダラス連銀などの地区連銀は
   日本語表記のままでよい。"""

RULES_HASHTAG = """## ハッシュタグ規則（X投稿本文のみ）

- ハッシュタグを付けてよいのは【市場のフロー】（呼び出しB）の連鎖の末尾だけとする。
  前編の【ヘッドライン】【主要なポイント】・【総括】・`headline_for_image` には
  付けない（v1.91・オーナー指示: 見出しにタグは不要）。銘柄名に言及する場合も
  平文で書く。以下は【市場のフロー】にタグを付ける場合の書き方である。
- `#` は行頭または半角スペースの直後にのみ置く（直前が「、」「。」等の
  日本語の句読点になる位置には置かない）。
- タグ名（英字部分）の直後に日本語を続けない（`#ETH偏り` `#BTCは` は
  不可——`#BTCは下落し、#ETHは` のように助詞・読点が続く書き方も同様に
  不可。v1.71・9/8実データで発見）。`：`・半角スペース・数値・行末の
  いずれかで終端する位置にのみ置く。
- 【市場のフロー】で銘柄を文中の主語にする場合は、先に銘柄名を平文で述べ、
  ハッシュタグは連鎖の末尾（句点の後）にまとめて置く。
  不可: #BTCは同時期に下落した一方、#ETHはほぼ横ばいでした。
  可（【市場のフロー】の連鎖の末尾の書き方。前編には使わない）:
  「…→ 【暗号通貨価格】BTC・ETHは同時期にそれぞれ下落・横ばいの形となりました
  が、因果は未確認です。 #BTC #ETH」
- 複合語の中では `#` を付けず平文にする（「ETH偏り」「USDCドミナンス」）。
- 使用するタグは `#BTC` `#ETH` `#BNB` および必要時の `#USDC` に限る。
- **タグを連続して並べるときの区切りは半角スペースのみとする。**
  中黒（`・`）やスラッシュ（`/`）で区切らない。
  可: `#BTC #ETH` / 不可: `#BTC・#ETH`、`#ETH/#USDC`
- `ETH/USDC` のようなペア表記にはタグを使わず平文で書く。
- `headline_for_image` には `#` を一切使わない。"""

# v1.82（オーナー承認）: 統合運用基準§3.1は【ヘッドライン】【主要なポイント】に
# 価格・24時間比を書かないと定めている。従来のINTRADAY_MOVE_GUIDANCEは
# notable_moveの値動きを「ヘッドラインの主題」として書く例外（旧③）を
# 認めていたが、この例外を廃止し、値動きを伝える先を「headline_for_image」
# （呼び出しA）と「市場のフローの最終段階【暗号通貨価格】」（呼び出しB）の
# 2か所に限定した。呼び出しBにも同じ指示が要るためSYSTEM_Bにも含める。
INTRADAY_MOVE_GUIDANCE = """## 24時間の値動き（notable_move）

入力の intraday_range に notable_move: true の銘柄がある場合、
その24時間の値動きは記述に値する材料である（データはNY 17:00区切りの
24時間窓で集計しており、暦日の「日中」ではない。v1.49・オーナー指示）。
ただし統合運用基準§3.1により、【ヘッドライン】【主要なポイント】には価格・
24時間比・値動きを書かない（notable_moveを理由にした例外も設けない。
v1.82・オーナー承認）。値動きを伝えるのは次の2か所に限る。

- headline_for_image（呼び出しA）: 図版下部帯用の短い見出しで、値動きの形状を
  反映してよい。
- 【市場のフロー】の最終段階【暗号通貨価格】（呼び出しB）: 材料がある日の連鎖の
  最終段階として、同時期に確認された値動きの形状を記述してよい。材料が無い日は
  市場のフロー自体を定型文とするため、値動きは書かない。

具体的な数値は後段のテンプレートが差し込むため、あなたは数値を書かないこと。
「一時的に上昇したのち上げ幅を縮小した」のような、値動きの形状のみを
記述する。"""

# v1.53（オーナー指示）: CPI・PCE・FOMC・要人講演等、その日最大の材料を
# 繰り返し取りこぼした事象（8/22カナダ関税・8/26 PCE・8/28ジャクソンホール
# 講演）への対応。scheduled_eventsは「探すべき材料」のヒントに過ぎず、
# それ自体を本文の根拠にしてはならない——対応するRSS候補が無ければ何も
# 書かない（未確認の事項を推測で補わないという絶対規則5と同じ考え方）。
SCHEDULED_EVENTS_GUIDANCE = """## 経済カレンダー（scheduled_events）

入力の daily_data.scheduled_events は対象日に予定されていた経済イベント
です。これらは「探すべき材料」のヒントであり、それ自体を材料として本文に
書いてはいけません。対応するRSS候補が存在する場合に限り、通常の採否判定
（tier1・tier2の裏付け、または独立2ソース）を経て本文へ反映してください。
予定はあったが候補が無い場合は、その旨を書かず、単に掲載しないでください。

重要度High・米国（USD）の指標の日は、その指標に対応しうる候補に
`scheduled_event_match`（例:「雇用統計（Non-Farm Employment Change）」）が
付きます（v1.93・オーナー承認）。これはタイトルのキーワード照合による
機械的な目印であり、事実の根拠でも採否の根拠でもありません（採否は
従来どおりtier・独立2ソースの規律で判断する）。目印があっても指標と
無関係な記事なら無視してよい。目印が付いた候補をuse:trueにした場合の
ヘッドラインでの扱いは、下記「①の中での主題の選び方」に従う。"""

RULES_CAUSAL = """## 因果表現

- 事実の記述と価格変動の因果を混同しない。
- 「により」「を受けて」「が原因で」「のため」「によって」「せいで」
  「を機に」のいずれかと、「上昇」「下落」「高騰」「急落」「暴落」
  「急騰」「反落」のいずれかが同じ文の中にある場合、必ず「可能性」
  「意識された」「とみられる」「考えられる」「未確認」「断定（できない/
  できません）」のいずれかで文を締め、断定を避ける（語順は問わない。
  価格変動語が先に来る文にも適用される）。「〜が牽引した」も同様に、
  限定する語句を伴わない単独の断定表現として扱わない。特に値動きを
  記述する際（notable_moveを含む）はこの組み合わせが生じやすいため
  注意すること。
- 上記の限定語句を伴わない断定文は機械監査（C18）で検出され、
  生成物全体がコミットされない（1文の断定表現がレポート全体の不採用に
  つながる。v1.49・オーナー指示）。"""

# v1.70（オーナー指示・9/7実データ「Coldcard関連の盗難資金」の手直しへの
# 対処）: 「Coldcard（ハードウェアウォレットの一種）関連の盗難資金」という
# 記述が、Coldcard自体に不備があったかのように読めたが、その製品・企業が
# 事案にどう関わったか（被害を受けた当事者なのか、単に事案の説明に付随して
# 触れられただけなのか）はsummary・titleからは確認できなかった。
ENTITY_INVOLVEMENT_GUIDANCE = """## 固有名詞の関与の描写（v1.70・オーナー指示）

これは書き方（表現）の制約であり、採否（use）の判断基準ではない。
独立2ソース規定・tier1/tier2の採否基準を満たすかどうかの判断には
影響しない——関わり方が不明確であることを理由に、採否基準を満たす
材料をuse:falseにしてはならない。事実自体は通常どおり掲載し、
下記のとおり表現のみを言い換える。

事故・不正・盗難等の事案を報じる候補に特定の製品名・企業名が含まれて
いても、その名称を出してよいのは、事案とその製品・企業がどう関わったか
（例:被害を受けた当事者であることが明確等）がsummary・titleの記載から
明確に読み取れる場合に限る。関わり方が明確でない場合は、名称は出さず
種別のみを示す等、その製品・企業に問題があったかのように読める書き方を
避ける一般的な表現に言い換えること。

例: 「VaultKey関連の盗難資金」のように製品名を関与の主語にせず、
「あるハードウェアウォレットブランドに関連するアドレス」のように
種別のみを示す表現に言い換えたうえで、資金移動という事実自体は通常
どおり本文に記載する（名称を理由に事実ごと不採用にしない）。"""

# v1.56（オーナー指示）: 統合運用基準の週末表記規定（土日はETFフローの
# 具体的金額を掲載しない）は、これまでこのパイプラインがETFフローの
# 数値データ（Farside/SoSoValue）を一度も保有しなかったため適用対象が
# 無かった（v1.36・v1.37）。2026-08-29（土曜）の実データで、ニュース経由
# （tier1裏付けまたは独立2ソース採用）でETF資金フローの方向がpart1_points
# へ採用されうることが実証されたため、適用対象が生じた。weekday_jpは
# fetch_data.pyのWEEKDAYS_JPにより「月」「火」「水」「木」「金」「土」
# 「日」の1文字で渡される。
ETF_WEEKEND_GUIDANCE = """## ETF資金フローの土日表記（統合運用基準・v1.56・オーナー指示）

入力の weekday_jp が「土」または「日」の場合（対象日target_date_jstが
土曜または日曜の場合）、ビットコイン/イーサリアムETFの資金流入・流出に
ついて具体的な金額を本文に記載してはならない。方向（流入・流出）のみを
記載し、「直近営業日までの確定値として確認された」旨を明記すること。
平日（月〜金）は通常どおり金額を記載してよい。この規定は書き方のみに
関するものであり、ETF資金フローに関する事実の採否（tier1裏付けまたは
独立2ソースが必要）は別途の規律に従う——採否規律を満たさない材料を
この規定を理由に掲載してよいわけではない。"""

NEWS_SELECTION = """## ニュース候補の扱いと選定根拠

news_candidates_today に、collect_news.py が公式発表RSS等から収集した候補が
candidate_id・title・summary・published_at・source・tier・eligibility
付きで渡される（candidate_idはaudit_ledgerで候補を参照する際に使う。
下記「audit_ledger」参照）。eligibilityはtierに基づき機械的に付与した
掲載可否の判定であり、この判定に従うこと（tier番号から自分で可否を
導く必要はない）。web_searchは使わない — 独自に調べたり、候補一覧に
無い情報を付け加えたりしない。本文はこの候補一覧のみを根拠にする。

### 重要性判定と因果表現の分離（v1.33・オーナー指示）

ニュースの採否は、重要性（関連性）と、暗号通貨価格への因果関係を
分けて判定する。両者を同一の判定にしてはならない――「因果が確認できない
→ 関係がない → 不採用」という推論は誤りである。

材料を次の3段階に分類する。

A：暗号通貨への直接材料
   SEC・CFTC等の規制、ETF、取引所・プロトコルの動向、
   ハッキング、法制化など。原則として掲載する。

B：明確な波及経路があるマクロ・地政学材料
   金利、金融政策、物価統計、為替・ドル、流動性、通商政策・関税、
   原油、地政学（ホルムズ海峡等）など。
   暗号通貨への直接の言及がなくても、金利・為替・流動性・原油・
   リスク選好などの波及経路を説明できる場合は、
   「市場環境の参考材料」として掲載する。

C：波及経路を説明できない一般ニュース
   原則として不採用とする。

【厳守】「暗号通貨価格への直接因果が未確認である」ことを、
不採用の理由としてはならない。因果を裏付けられない場合は、
掲載したうえで「暗号通貨価格への直接因果は未確認」と明記する。

判断に迷う材料は、まずBに該当するか（波及経路を説明できるか）を
検討すること。

上記のA/B/C分類は、下記tier（情報源の信頼性）とは別の軸である。
掲載にはA/B/C分類（内容面の関連性）とtier・eligibility（情報源面の
規律）の両方を満たす必要がある。

tier 1: 規制当局・政府機関の公式発表RSS（SEC・FRB・OCC・CFTC・金融庁・
        日本銀行等）。summaryの記載内容を一次情報として扱ってよい。
tier 2: 優先度2：Reuters等の独立報道。単独で採用可能だが、tier1の公式発表と
        異なり報道であることを明示すること（『Reutersによると』等）。
tier 3: CoinDesk・Cointelegraph等の暗号通貨特化メディアRSS。統合運用基準の
        位置づけどおり「補完・裏取り」に用い、単独の主根拠にはしない。
        tier 1・tier 2のsummaryで確認できた事実を補強する（同一材料が独立
        して報じられていることを示す）用途、またはtier 1・tier 2のsummary
        に無い暗号通貨特有の細部を補う用途に限る。tier 3の候補のみを根拠に
        【ヘッドライン】の新規項目を立てない。【主要なポイント】については
        下記「独立2ソース規定」の例外を除き、同様に単独では根拠にしない。
        【重要・v1.53フォローアップ】tier1・tier2の事実をtier3が裏取り・補強する
        上記の用途は、audit_ledgerでは該当tier3候補をuse:falseのまま
        記録する（媒体名を（媒体名、日付）へ追加で列挙する形で本文へ反映
        してよいが、tier3側の use を true にはしない）。tier3のuse:trueは
        「独立2ソース規定」に該当し pairs_with_candidate_id で相手を
        申告できる場合に限る。「本文中でこの記事の内容に言及・参照した」
        ことと「audit_ledgerでuse:trueにする」ことは別であり、前者だけを
        理由にuse:trueにしないこと（下記「audit_ledger」参照）。
tier 4: Google News経由の候補発見のみの結果（見出し・URLのみで、内容の
        裏取りをしていない）。単独では事実の根拠にしない。audit_ledger上は
        常に不採用とし、【ヘッドライン】【主要なポイント】【総括】のいずれにも
        書かない（reusable_for_summaryにも書かない。v1.92・オーナー指示:
        tier4を総括に残すと情報源の規律の抜け道になるため）。

### Bの扱いの基準（v1.99・オーナー指示）

B（波及経路のあるマクロ・地政学材料）の採否は、次の基準で判定する。
基準の趣旨: 掲載できる材料を見落として定型文（材料なし）にしてしまわないこと。
一方で、根拠の薄い材料で項目を埋めることはしない。

1. 当事者の主張: 紛争・攻撃の当事者が「攻撃した」「封鎖した」等と主張している
   との報道（例:「〇〇（当事者）が△△（施設）を攻撃したと主張」。〇〇・△△は
   例示用のプレースホルダーであり、この文言や内容を事実として流用しないこと）は、
   事実の確認ではなく主張の報道である。次の2点を付ければ、Bとして掲載してよい
   （主張であることだけを理由に不採用にしない）。
   (a) 「〜と主張しました」「〜と述べました」等で、誰の主張かを明示する。
       【ヘッドライン】・headline_for_imageに書く場合にも付ける（主張を事実として書かない）。
   (b) 候補のtitle・summaryに被害・影響の確認が書かれていない範囲について、
       「被害・影響は未確認です」等と書く（【ヘッドライン】または該当する
       【主要なポイント】の項目）。書かれている場合は、その記載の範囲で書く。
2. 見出し程度の情報: titleとsummaryが見出し程度の短さでも、「誰が・何を・どこで」
   （どこでが当てはまらない材料は「誰が・何を」）を、候補のtitle・summaryの記載
   だけで書けるなら、Bとして掲載してよい。書ける事実は、tier 1・tier 2の
   title・summaryに記載されている範囲に限る（これまでと同じ。補足・推測は
   しない）。書けない場合は掲載しない（reasonにその旨を書く）。
3. 定型文（材料なし）より優先して掲載する地政学・エネルギー材料（この3は、地政学・
   エネルギー材料に限った規則である）: 地政学・エネルギー材料のうち、原油や金利への
   波及経路がはっきりした次のものに当たるtier 1・tier 2の候補は、use:trueにして
   本文に掲載する（本節の2を満たす場合）。定型文を使う前に、必ずこれに当たる
   候補が無いかを確認すること。
   - 産油・精製・輸送施設（油田・製油所・パイプライン・タンカー・港湾等）への攻撃・被害
     （攻撃した当事者の主張の報道を含む。上記1の帰属と限定を付ける）
   - ホルムズ海峡・紅海など主要な海上輸送路の封鎖・攻撃
   - 産油国・産油地域や主要な海上輸送路（ホルムズ海峡・紅海など）に関わる軍事行動。
     当事者が国家か武装勢力かは問わない（ロシア・ウクライナの一般的な戦況の記事は
     この項目に含めない。下記参照）
   - 停戦の成立・破綻
   - 主要国の制裁、石油備蓄の放出
   上記に挙げた種類以外の地政学・エネルギー材料は、定型文より優先しない（ロシア・
   ウクライナの一般的な戦況の記事も同様に優先の対象外とする。ただし、そのうち
   エネルギー施設への攻撃、停戦の成立・破綻、主要国の制裁に当たるものは対象）。
   地政学・エネルギー材料のうち、解説記事・論評・人事（要人の辞任・任命等）も優先の
   対象外とする。優先の対象外の
   材料は、定型文に代えて掲載する材料にしない（他に採用する材料がある日に補足として
   載せるかは、従来どおりB／Cの判定による）。
   この3は地政学・エネルギー材料にだけかかる規則であり、金融政策・FRB発言・経済指標・
   物価統計・為替・通商政策など従来のBの判定は変えない（本節で優先も不採用の根拠も
   せず、従来どおり波及経路を説明できるかで判定する）。
   tier 3は「独立2ソース規定」、tier 4は掲載不可のまま（上記tierの規定どおり）。
4. 不採用の理由にしてはならないもの: 「内容が薄い」「情報が少ない」「単独報道」
   だけを理由にuse:falseにしてはならない。tier 2（Reuters等）は、上記tier 2の規定の
   とおり単独で採用できる。「他の採用材料がある」「ヘッドラインには採らない」
   「ヘッドラインの主題ではない」ことだけを理由にしてもならない（本節の6参照）。
   use:falseにしてよいのは、次の場合に限る（reasonに、どれに当たるかが分かるように
   書く）。
   (a) C判定（波及経路を説明できない一般ニュース）
   (b) 本節の2で「誰が・何を・どこで」を書けない場合
   (c) 採用済みの候補と同一の事実を報じている重複（reasonに重複先のcandidate_idを書く）
   (d) part1_pointsの上限4項目に収まらず、重要度の低いものを見送る場合
       （reasonに「上限4項目のため見送り」と書く）
   (e) 手続き的な発表しか材料が無い日（下記「①の中での主題の選び方」(3)）
   (f) tier・eligibilityを満たさない場合（tier 3単独・tier 4等）
   (g) 地政学・エネルギー材料のうち、本節の3の優先の対象外（挙げた種類以外の地政学・
       エネルギー材料、一般的な戦況の記事、解説・論評・人事）のもの（reasonに
       「優先して掲載する対象に当たらない」と書く）。この語は地政学・エネルギー材料
       だけに使い、金融政策・FRB発言・経済指標・金利・為替・通商政策など従来のBには
       使わない。
5. 数を埋めるためのBは不要: 項目数を増やすために、本節の3に当たらない根拠の薄いBを
   採用しない。根拠が少ない日は数を埋めない。
6. 見出しにするかとuseは別の判断: useは「【ヘッドライン】または【主要なポイント】の
   どちらかに載せるか」の判定であり、「ヘッドラインの主題にするか」の判定ではない。
   判断の順序は、まずA/B/Cとtier・eligibility（上記）でuseを決め、そのうえでuse:trueの
   材料から【ヘッドライン】の主題を、下記「part1_headline・part1_pointsの決定」の
   ①〜③・「①の中での主題の選び方」で選ぶ。ヘッドラインの主題にしなかった材料も、
   A/B/Cの判定で掲載対象なら、use:trueにして【主要なポイント】に載せる。

### 情報源規律と項目数の優先順位（v1.29・オーナー指示）

情報源の規律は項目数より優先する。tier1・tier2（または下記「独立2ソース
規定」に該当するtier3）の裏付けがある材料が1件しかなければpart1_pointsは
1項目、0件なら0項目とし、下記「候補が無い場合の扱い」の定型文を使うこと。
項目数を満たすためにtier3単独ソースを採用してはならない。0項目
（定型文のみ）は失敗ではなく、統合運用基準§3.1が定める正しい結果である
（「根拠が少ない日は数を埋めず、確認できる材料と限界を明記する」）。

- 掲載する事実はtier 1・tier 2のsummaryに記載されている内容、または下記
  「独立2ソース規定」に該当するtier 3の事実報道に限る。tier 3は
  原則としてtier 1・tier 2の事実を補強する裏取りとしてのみ併記してよく、
  tier 3単独を新規項目の根拠にしない。

### 独立2ソース規定（v1.28・統合運用基準の既定を実装へ反映。v1.53
フォローアップでaudit_ledgerへの記録方法を改定・オーナー指示）

tier3のみで報じられた材料であっても、次の3条件をすべて満たす場合は
【主要なポイント】への掲載を許可する。
 (a) 2つ以上の独立したtier3媒体が同一の事実を報じている
 (b) 意見・予想・分析ではなく、事実の報道である
     （発表、認可、取得、提携、施行など）
 (c) 掲載時に媒体名を複数列挙し、公式発表での確認が取れていない旨を
     明記する（「一次情報」等の内部用語は使わず、読者向けの平易な表現を
     用いること。例:「公式発表での確認は取れていません」）
上記に該当しない場合は従来どおりtier1・tier2の裏付けを必要とする。

この規定に該当すると判断した場合は、**組になる2件（以上）のtier3候補を、すべてaudit_ledgerで
use:trueにする**（片方だけuse:trueにすると、システムの確認で必ず失敗してやり直しになる）。
pairs_with_candidate_idには、同一事実を報じている相手（別sourceのtier3候補）のcandidate_idを、
どちらか片方に書けば足りる（相互に書く必要はない。下記「audit_ledger」参照）。
なお、tier1・tier2の裏付けがある材料を補強するtier3は、従来どおりuse:falseのままにする（上記tier 3の節）。
この規定は、tier1・tier2の裏付けが無く、tier3だけで報じられた材料の組についての扱いである。
候補に machine_pair_hint が付いている場合は、システムが題名の語の重なりから「同一事実の可能性がある
別媒体のtier3候補」として機械的に検出した相手のcandidate_idと重なり係数である。同一事実かどうかは、
あなたがtitle・summaryを読んで判断する。同一事実でなければ無視してよい（目印が付いていない候補どうしでも、
同一事実なら同様に扱ってよい）。
"採用"／"採用（独立2ソース）"／"不採用"という記録文言自体はあなたが
書かず、tier・use・pairs_with_candidate_idの妥当性からシステム側が
機械的に確定する（v1.53フォローアップ・オーナー指示。単独ソースを
独立2ソースと誤って記録する等の事故が繰り返し発生したため）。
part1_headlineでの扱いは下記「part1_headline・part1_pointsの決定」を
参照。

### ヘッドラインの判定手順（v1.44改定・下記へ委譲）

part1_headline・headline_for_imageの決定手順は下記
「part1_headline・part1_pointsの決定」の①〜③を参照。
- 数値・固有名詞・日時はsummary・titleの記載と一致させる。候補に無い情報を
  推測で補わない（確認できないものは掲載しない）。
- 入力の previous_posts（前日以前の投稿本文。ヘッドライン・主要なポイント）で
  既に扱った法案・政策・企業動向について、当日の候補のsummaryに新しい動きが
  ある場合のみ【ヘッドライン】【主要なポイント】へ再掲載する。新しい動きが
  なければ本文には書かず、reusable_for_summary に記す（v1.92・オーナー指示。
  従来の news_candidates_yesterday は本番では常に空だったため、比較対象を
  previous_posts に改めた）。
- 十分な材料がない日は項目数を埋めない。確認できた事実と、確認できなかった
  範囲を明記する。"""

# v1.44（オーナー指示）: 従来、独立2ソース材料単独（tier1裏付けなし）は
# 【ヘッドライン】へ昇格しない設計だった（v1.30）。しかし8/26実データで、
# 独立2媒体ペア救済（v1.39フォローアップ）により採用された独立2ソース材料
# （BankChain Alliance）がpart1_pointsには記載されたにもかかわらず
# part1_headlineが定型文のままになる事象が実測され、これは8/23（BitMart）・
# 8/24（Bitmine）と同型の「ヘッドラインと本文の矛盾」の再発と判断された。
# 独立2ソース材料の有無を(i)tier1・(iii)notable_moveと並ぶ独立した第3の
# 軸(ii)として明示し、(i)(ii)(iii)いずれか1つでも「あり」なら定型文を
# 使わない、という単一の判定手順（下記）に一本化した。旧来この制約は
# NEWS_SELECTIONの「ヘッドラインの判定手順」「独立2ソース規定」の2箇所、
# 本セクションの(i)判定基準、WRITES_Aの計4箇所に分散して記述されており、
# 今回の再発は分散した記述の一部（本セクション）だけを更新し他を据え置いた
# ことが一因（v1.42→v1.43改定時）。今回は全箇所を本セクションへの参照へ
# 統一し、単一の記述箇所以外では判定基準を繰り返さない構成へ変更した。
NO_CANDIDATES_FALLBACK = f"""## part1_headline・part1_pointsの決定（v1.44・オーナー指示。
(i)(ii)の判定方法はv1.53フォローアップで改定・オーナー指示。
(i)にtier2を追加はv1.59・オーナー承認。v1.82でnotable_move（旧(iii)・旧③）を
判定軸から除外・オーナー承認）

part1_headline および part1_points は、次の2つを独立に確認して
決定する。
(i)   tier1またはtier2の候補でuse:trueと判断したものがあるか
(ii)  tier3の候補で、独立2ソース規定に該当すると判断し、
      pairs_with_candidate_idで関連付けてuse:trueとしたものが
      2件以上あるか

定型文を使うのは、(i)(ii)の両方が「なし」の場合に限る。
どちらか1つでも「あり」なら、定型文を使わずその材料に基づく記述を行う。
(i)を判断する前に、上記NEWS_SELECTION「Bの扱いの基準」3（地政学・エネルギー材料に
限った規則）の、定型文より優先して掲載する材料——産油・精製・輸送施設への攻撃・
被害、主要な海上輸送路の封鎖・攻撃、産油国・産油地域や主要な海上輸送路に関わる
軍事行動、停戦の成立・破綻、主要国の制裁・石油備蓄の放出——に当たるtier1・tier2の
候補が無いかを確認する。当たる候補があれば（同「Bの扱いの基準」2の「誰が・何を・
どこで」を書ける場合）、use:trueにする（use:trueにすれば(i)は「あり」になり、
定型文は使わない）。この確認は地政学・エネルギー材料に限り、金融政策・FRB発言・
経済指標など従来のBの判定は変えない。

【ヘッドライン】【主要なポイント】には、材料の有無にかかわらず、価格・
24時間比・値動きを書かない（統合運用基準§3.1）。入力の intraday_range に
notable_move: true の銘柄があっても、それを理由にヘッドライン・主要な
ポイントで値動きを記述せず、定型文を使うかどうかも(i)(ii)のみで決める。
大きな値動きは、headline_for_image（呼び出しA）と【市場のフロー】の最終段階
（呼び出しB）で伝える（上記「24時間の値動き（notable_move）」参照）。

優先順位（(i)(ii)の両方が「あり」の場合、ヘッドラインで何を主とするかを決める）：

① (i)あり → tier1・tier2裏付けの材料をヘッドラインの主とする。(ii)も
   あれば、重要度の高い方を主、他方を従として併記してよい。
② (i)なし・(ii)あり → 独立2ソース材料をヘッドラインの主とする。
③ (i)なし・(ii)なし → 統合運用基準§3.1の定型文を使う。

①〜③は本文の構成方針を表す優先順位であり、下記audit_ledgerの
reasonで使うA/B/C——個々の候補材料の重要性判定（「重要性判定と
因果表現の分離」参照）——とは別の分類である。混同しないこと。

### ①の中での主題の選び方（v1.93・オーナー指示）

①で、use:trueとした材料が複数ある場合、part1_headline（①のheadline_for_imageも同じ）の
主題は次の順で決める。A/B/Cの分類やtierの違い（tier1かtier2か）では決めない。

(1) 指標日: 入力の daily_data.scheduled_events に、重要度High・米国（USD）の
    経済指標（雇用統計・CPI・PPI・PCE・GDP・FOMC など）があり、それに対応する
    材料（候補の scheduled_event_match が付いたもの）をuse:trueにした場合は、
    原則としてその材料をpart1_headlineの主とする。指標の結果（予想との比較等）を、
    候補のtitle・summaryに書かれている事実の範囲で書く。指標の結果（発表後の数値・
    予想との比較）が候補に書かれていない場合（発表前の予想記事など）は、この(1)を
    適用しない（結果を推測で書かない）。
(2) 例外: 暗号通貨に直接関わる大型の制度材料——SEC・CFTC等の規則案・最終規則・
    登録承認、ETFの承認など——が公式発表（tier1）で確認できる日は、その材料を
    part1_headlineの主とする。この場合、(1)の指標の材料はpart1_pointsの1番目に置く。
(3) 手続き的な発表: 暗号通貨との関係が薄い個別の申請の承認、意見募集期間の延長
    など手続き的な発表は、use:trueにしてもpart1_headlineの主題にしない
    （part1_pointsに載せる）。use:trueにしたい材料がその手続き的な発表しか無い日
    （ほかに採用できる材料が無い日）は、その材料をuse:falseにして、定型文
    （材料なし）を使う（v1.93追補・オーナー指示: 関係の薄い手続きを見出しにする
    より「主要材料は確認できない」と書くほうが趣旨に合う。A/B/Cの分類にかかわらず
    この扱いとする）。この場合のaudit_ledgerのreasonには「手続き的な発表のため
    不採用」と書く。
(1)〜(3)に当てはまる材料が無い日は、上記①の「重要度の高い方」（暗号通貨市場への
関わりの大きい材料）を主とする。

### ②（(i)なし・(ii)あり）の詳細

独立2ソース材料の内容に基づき、part1_headlineに実文言を書く。
「公式発表での確認が取れていない」旨の但し書きはpart1_headlineに
書かず、part1_pointsの該当項目に明記する（v1.70・オーナー指示。
「一次情報」等の内部用語は使わず、読者向けの平易な表現を用いること）。
headline_for_imageも同様にこの材料の内容を反映してよい（但し書きは
含めない）。

### ③（(i)なし・(ii)なし）の詳細

- part1_headline: 統合運用基準§3.1の指定文言をそのまま使う（言い換えない）:
  「{FIXED_HEADLINE}」
- part1_points: 同じく指定文言をそのまま使う（項目数は1件でよい）:
  「{FIXED_POINTS}」

### 共通

- headline_for_image: 図版下部帯用。【ヘッドライン】【主要なポイント】と
  異なり、値動きの形状を反映してよい（数値は書かない）。①②の場合は
  主材料の内容を反映してよい。入力の intraday_range に notable_move: true
  の銘柄がある場合は、その値動きの形状を反映してよい（材料の内容に代えて、
  または併せて）。材料も notable_move も無い場合は、daily_data.json内の
  BTC・ETHのdirection（up/down）に基づく短い定性的な見出しにとどめる
  （例:「BTC・ETHともに上昇基調」）。`#`は使わず全角40字以内。
- reusable_for_summary: 前日以前の投稿本文（previous_posts）で扱った材料のうち、
  当日になっても新しい動きがないものだけを記す。該当が無ければ空配列
  （空配列が通常の状態である）。当日の候補・tier4・当日初出の材料は書かない。
  書式は下記「あなたが書くもの」を参照。

### ヘッドラインの構成要件（v1.70・オーナー指示。v1.82・v1.91改定）

part1_headlineは次の点を満たすこと（v1.82・オーナー承認: 価格・値動きの禁止と
文数を統合運用基準§3.1に合わせて改定）。
- 1〜2文にとどめる（統合運用基準§3.1）。
- 価格・24時間比・値動き・Fear & Greed・相対強弱・DEX・APR・LP助言を
  書かない（統合運用基準§3.1）。
- ハッシュタグ（`#`）は付けない（v1.91・オーナー指示: 見出しにタグは不要。
  v1.70の「主要銘柄に言及する場合はタグを付す」は廃止）。
- 「公式発表での確認が取れていない」旨の但し書きをpart1_headlineに
  書かない（上記②の詳細を参照。part1_pointsの該当項目に明記する）。
- 対象日の日付をヘッドライン冒頭に書かない（【対象日】欄で別途表示
  されるため重複になる）。「9月7日は、」「9月7日、」のように日付から
  書き出さない。材料の内容から書き始めること
  （例:「〇〇（発表主体）が△△を発表しました。」。〇〇・△△は例示用の
  プレースホルダーであり、この文言や内容を事実として流用しないこと）。

**audit_ledgerは上記と切り離して扱う（統合運用基準・台本の要求）。**
audit_ledgerは「採否を判断した全候補の記録」であり、本文（ヘッドライン・
主要なポイント）に採用したかどうかとは無関係に、news_candidates_today に
渡された候補（tier 1・2・3・4のすべて）を1件残らず記録する。ヘッドライン・
主要なポイントに使わなかった候補も use:false とその理由を記録する。

各要素は candidate_id（news_candidates_today内の該当候補のID）・use・
pairs_with_candidate_id・verified_by・reason のみを書く（v1.48・v1.53
フォローアップ・オーナー指示）。source・url・title・published_atは
書かない——candidate_idからシステム側が候補一覧の該当データをそのまま
補完するため、あなたが転記する必要は無い（転記ミスの防止のため）。
1件の候補につきcandidate_idはちょうど1回のみ使う（重複・欠落は不可）。
"採用"／"採用（独立2ソース）"／"不採用"という記録文言自体もあなたは
書かない（下記参照）。

- use（true/false）: この候補を、本文（ヘッドライン・主要なポイント）で
  ある事実の**単独で独立した根拠**として使ったかどうか。
  tier1・tier2はその事実の直接の根拠として使えばtrue（tier2はReutersに
  よる報道である旨を明示すること）。tier3がtrueになるのは
  「独立2ソース規定」に該当し、下記pairs_with_candidate_idで相手を
  申告できる場合に限る。tier1・tier2の事実をtier3が裏取り・補強するために
  本文中で言及した場合（媒体名を（媒体名、日付）へ追加で列挙する等）は、
  そのtier3候補のuse自体はfalseのままにする——「本文で言及・参照した」
  ことと「useをtrueにする」ことは別であり、混同しないこと（v1.53
  フォローアップ・オーナー指示。上記NEWS_SELECTIONのtier3の節も参照）。
  tier4の候補は候補発見専用の位置づけのため、useの値に関わらず
  audit_ledger上は常に不採用として扱われる（tier4の候補は本文・総括の
  どこにも書かない。reusable_for_summaryにも書かない。v1.92・オーナー指示）。
- pairs_with_candidate_id: tier3でuse:trueの候補のうち、上記
  「独立2ソース規定」に該当すると判断したものにのみ、同一事実を
  報じている相手（別sourceのtier3候補）のcandidate_idを記す
  （該当しなければ省略、またはnull）。申告は片方に書けば成立する
  （相互に指し合う必要はない）が、相手もuse:trueにすること（上記
  「独立2ソース規定」参照）。この申告はシステム側が機械的に妥当性を
  確認したうえで"採用（独立2ソース）"の記録に反映される（相手が
  実在しtier3・use:trueであること、sourceが異なること、タイトルの
  内容が実際に重なっていることを確認する）。妥当性が確認できない
  場合はこの呼び出し自体がリトライされる。

use:false の場合、reasonの冒頭に上記A/B/Cのどの段階と判定したかを
明記する（例:「C: 自動車産業の国内回帰に関する内容で、金利・為替・流動性等
への波及経路を説明できない」「B: 地政学の論評のため、優先して掲載する対象に当たらない」
「B: 地政学・エネルギーの人事のため、優先して掲載する対象に当たらない」
「B: ロシア・ウクライナの一般的な戦況の記事で、優先して掲載する対象に当たらない」
「B: 見出しだけでは「誰が・何を・どこで」を書けない」
「B: 候補5と同一の事実の重複（候補5を採用）」
「B: 上限4項目のため、優先順位の低い材料として見送り」等）。理由は、上記
NEWS_SELECTION「Bの扱いの基準」の4の(a)〜(g)のどれに当たるかが分かるように書く。
「暗号通貨価格への直接因果が未確認」であること
のみを理由にuse:falseとしてはならない（上記【厳守】参照）。同様に、「内容が薄い」
「情報が少ない」「単独報道」だけを理由にuse:falseとしてはならない（上記
NEWS_SELECTION「Bの扱いの基準」4参照）。
use:false のreasonは全角60字以内に収める（判定段階＋簡潔な理由のみでよく、
詳細な論述は不要）。use:trueのreasonにはこの字数制限を適用しない。
verified_byはuse:trueの場合のみ書く（判断に属する情報のため）。
use:falseの場合は空文字でよい。
audit_ledgerを空配列 [] にしてよいのは、news_candidates_today が
空配列で渡された（候補が1件も無かった）場合のみである。
候補が1件でも渡されている場合、audit_ledgerを空配列で返してはならない。"""

WRITES_A = """## あなたが書くもの

### 文体（v1.64・オーナー指示）

本文はです・ます調で統一する。「である調」（「〜した。」「〜である。」
「〜とみられる。」等の言い切り体）は使わない。

- headline_for_image: 図版下部帯用。`#` を使わず全角40字以内。体言止め可。
  当事者の主張を材料にする場合は、「〜と主張」の帰属を付ける（上記「Bの扱いの基準」1）。
  上記「part1_headline・part1_pointsの決定」の「共通」に従う（値動きの形状は
  ここで伝えてよい）。
- part1_headline: 前編のヘッドライン。1〜2文。当日の最重要材料を記述する。
  価格・24時間比・値動き・Fear & Greed・相対強弱・DEX・APR・LP助言には
  触れない（統合運用基準§3.1）。notable_moveを理由にした例外は設けない
  （値動きはheadline_for_imageと【市場のフロー】で伝える）。材料が無い日
  （上記(i)(ii)がともに「なし」）は、定型文をそのまま使う。
  上記「part1_headline・part1_pointsの決定」の①〜③に従う。
- part1_points: 上限4項目。ヘッドラインと重複しない補足。各項目末尾に
  （媒体名、日付）を付す。項目数は目標ではなく情報源の規律に従った結果
  である——tier1・tier2（または独立2ソース規定該当のtier3）の裏付けがある
  材料の件数がそのまま項目数になる（1件なら1項目、0件なら0項目で
  定型文）。項目数を埋めるためにtier3単独ソースを採用しない。
  上記「重要性判定と因果表現の分離」のB（波及経路のあるマクロ・地政学
  材料）を掲載する場合、「暗号通貨価格への直接因果は未確認」等の限定
  表現を項目文に含める——因果が未確認であることは不採用の理由にせず、
  掲載したうえで明記する。当事者の主張を掲載する場合は、「〜と主張しました」の帰属と
  「被害・影響は未確認です」等の限定を含める（上記「Bの扱いの基準」1）。
- audit_ledger: 候補一覧（tier 1・2・3・4のすべて）の採否を判断した記録。
  各要素は candidate_id・use・pairs_with_candidate_id（tier3で
  use:trueかつ独立2ソース規定該当時のみ）・verified_by・reason のみを
  書く（source・url・title・published_at・decisionは書かない。詳細は
  上記「part1_headline・part1_pointsの決定」内のaudit_ledgerの節を参照）。
- reusable_for_summary（v1.92・オーナー指示）: 前日以前の投稿本文（入力の
  previous_posts）で既に扱った材料のうち、当日になっても新しい動きがない
  ものだけを、総括用の1行要約として書く（0〜2件。該当が無ければ空配列）。
  次は書かない: 当日の候補（採用・不採用を問わず）、tier4、当日初出の材料。
  各要素は {"text": 1行要約（です・ます調。末尾に（媒体名、掲載日）を付す）,
  "carried_from": その材料を扱った投稿の日付（previous_postsのdate。YYYY-MM-DD）,
  "candidate_ids": 当日の候補のうち同じ話題のcandidate_id（無ければ[]）}。
  この形式でない項目、carried_fromがprevious_postsの日付に無い項目、
  前日以前の本文と題材が対応しない項目は、システムが機械的に除外する。
- 採用（use:true）した材料はすべて part1_headline・part1_points に載せる
  （reusable_for_summaryに回さない）。載せない材料は use:false にする
  （use:falseにしてよい理由は、上記「Bの扱いの基準」の4に限る。ヘッドラインの主題に
  しないことは理由にならない）。
  採用した材料が複数ある日は、part1_pointsの項目でヘッドラインの主題と同じ
  材料を繰り返さない（項目枠は他の採用材料に使う）。採用した材料がヘッドライン
  の1件だけの日は、従来どおり1項目とする（項目数は材料の件数）。
  上限4項目に収まらない場合は、関連する材料を1項目に
  まとめる。まとめられない場合は、重要度の低い材料を use:false にする
  （載せないまま use:true のままにしない・reusable_for_summaryへ回さない）。"""

OUTPUT_FORMAT_A = """## 出力形式

次のJSONのみを出力。前置き・後置き・コードフェンスを付けない。

{
  "headline_for_image": "...",
  "part1_headline": "...",
  "part1_points": ["...", "..."],
  "reusable_for_summary": [
    { "text": "...", "carried_from": "YYYY-MM-DD", "candidate_ids": [] }
  ],
  "audit_ledger": [
    { "candidate_id": 1, "use": true, "pairs_with_candidate_id": null,
      "verified_by": "", "reason": "" }
  ]
}

part1_pointsの各項目は、本文だけを書く。先頭に「・」などの行頭記号や空白を付けない（システムが「・」を付けて
箇条書きにするため、付けると「・・」と二重になる。入力のprevious_postsの項目にも先頭の記号は付いていない）。"""

SYSTEM_A = "\n\n".join([
    ROLE_INTRO, RULES_ABSOLUTE, RULES_HASHTAG, NEWS_SELECTION, NO_CANDIDATES_FALLBACK,
    INTRADAY_MOVE_GUIDANCE, SCHEDULED_EVENTS_GUIDANCE, RULES_CAUSAL, ENTITY_INVOLVEMENT_GUIDANCE,
    ETF_WEEKEND_GUIDANCE, WRITES_A, OUTPUT_FORMAT_A,
])

# v1.82（オーナー承認）: 統合運用基準§3.1（【市場のフロー】【総括】に書いては
# いけない項目）・§3.3（市場フローの書式）に合わせて全面改定した。
# 変更点: (1)材料が無い日はpart2_flowを§3.1の定型文にし、市場データからの
# 作文をやめる、(2)材料がある日は§3.3の書式（【出来事・ニュース】→
# 【地政学・マクロの変化】→【中間市場指標・市場心理】→【暗号通貨価格】、複数は
# ①②③で区切る）を使う、(3)part2_summaryへ1〜2文の上限と§3.1の禁止項目を明記、
# (4)入力daily_dataからFear & Greed・ドミナンス・DEX（base）・LP・国内取引所の
# データを除外した旨を明記（_daily_data_for_call_b参照）。
CALL_B_INSTRUCTIONS = f"""入力として、当日の市場データ（daily_data.json）と、呼び出しAの出力
（採用したニュース、reusable_for_summary）を受け取ります。
入力のdaily_dataは、統合運用基準§3.1が【市場のフロー】【総括】に書いてはいけない
項目（Fear & Greed・DEX・APR・LP助言・相対強弱）に当たるデータを除外したもの
です（v1.82・オーナー承認）。
Aが失敗している場合はニュースが空で渡されます。その場合、part2_flowは下記
「材料が無い日」の定型文とし、part2_summaryは確認可能な事実のみで簡潔に記述し、
ニュース材料が確認できなかった旨を明記してください。

### 文体（v1.35・オーナー指示）

文体は「です・ます調」で統一する。「である調」（「〜示唆される」
「〜とみられる」等の言い切り体）は使わない。前編（part1_headline・
part1_points）と文体を揃えること。

- part2_flow: 統合運用基準§3.3の書式だけを使った条件付き仮説連鎖
  （v1.82・オーナー承認）。ここで扱う材料は、呼び出しAのpart1_headline・
  part1_pointsに既に掲載されている材料に限る。reusable_for_summary
  （前日以前の投稿で扱った継続材料。part2_summaryでの1行言及にのみ使う）や、
  part1_headline・part1_pointsに書かれていない新規の材料をpart2_flowで持ち出さない
  （v1.56・オーナー指示）。part2_flowは「意識された可能性」という因果連鎖を
  組む分、part2_summaryの1行言及より踏み込んだ主張になるため、根拠の基準も
  掲載済み材料に厳格化する——tier1・tier2裏付けまたは独立2ソースの採否規律を
  経ていない材料（単独tier3ソース等）を因果連鎖の起点にしない。

  【材料が無い日】part1_headlineが定型文で、かつpart1_pointsも定型文のみの日、
  またはAが失敗している日は、市場データから流れを作文しない。part2_flowを
  次の定型文1件のみとする（統合運用基準§3.1）:
  ["{FIXED_FLOW}"]

  【材料がある日】各連鎖を次の書式で1文（句点は末尾に1つだけ）として書く
  （統合運用基準§3.3）:
  「【出来事・ニュース】確認済み事実 → 【地政学・マクロの変化】市場で意識された
  可能性がある変化 → 【中間市場指標・市場心理】確認済みの指標・心理 →
  【暗号通貨価格】同時期に確認された値動き」
  - 【出来事・ニュース】: 掲載済みの確認済み事実（媒体名を添える）。掲載済みの材料が
    当事者の主張として書かれている場合（part1に「〜と主張」とある場合）は、確認済み事実
    に書き直さず、「〜と主張しました」の帰属と「未確認」の限定を保つ（v1.99）。
  - 【地政学・マクロの変化】: 市場で意識された可能性がある変化。断定しない。
  - 【中間市場指標・市場心理】: 報道で確認できた金利・原油・為替・株価等の
    指標や、それに伴うリスク選好・回避の心理。Fear & Greed指数には触れない。
  - 【暗号通貨価格】: BTC・ETHまたは市場全体の同時期の値動きを、24時間比の
    観点で形状のみ記述する（数値は書かない）。intraday_rangeにnotable_move:
    trueの銘柄があれば、その値動きの形状を反映してよい（上記「24時間の値動き
    （notable_move）」参照）。価格因果は断定せず、報道事実は「同時期の材料」
    として限定して扱う。
  根拠のある段階のみを書き（統合運用基準§3.1「根拠のない段階」は書かない）、
  段階の順序は変えない。【出来事・ニュース】と【暗号通貨価格】は必ず置く。

  【ラベルの使い分け（v1.101・オーナー指示）】
  - 各連鎖は、必ず先頭を「【出来事・ニュース】」のラベルで書き始める（①②③を付ける
    場合は「①【出来事・ニュース】…」の形）。ラベルの語は一字一句そのまま書き、省略
    しない。
  - 【地政学・マクロの変化】は、金融政策・通商政策・財政・物価統計・地政学情勢など、
    マクロの政策・情勢の変化に限って使う（金利・為替・原油・株価などの指標の動きそのもの
    は【中間市場指標・市場心理】に置く）。制度・政策（SEC・CFTC・FinCEN等の規則案・
    承認・訴訟）や、企業財務・資金調達・市場構造（取引所・上場・提携・資金調達等）の
    材料には、このラベルを使わない。そうした材料で、報道で確認できたマクロの変化が
    無いときは、この段階を書かず（根拠のない段階は書かない）、「【出来事・ニュース】…
    → 【暗号通貨価格】…」の2段階でよい。報道で確認できた指標・心理があれば
    【中間市場指標・市場心理】を置く。
  書式の例（〇〇・△△は例示用のプレースホルダーであり、この内容を事実として流用
  しないこと。連鎖が1本の日は①を付けない）:
  「【出来事・ニュース】〇〇が△△を発表しました（媒体名、日付） → 【暗号通貨価格】
  □□（銘柄）は同時期に◇◇（値動きの形状）でしたが、因果は未確認です。 #BTC #ETH」
  ハッシュタグ規則に従い、【暗号通貨価格】では銘柄名を平文（BTC・ETH）で
  述べ、ハッシュタグを付す場合は連鎖の末尾（句点の後に半角スペースを空けて）
  にまとめて置く。
  複数の確認済み材料がある日は、地政学・マクロ、制度・政策、企業財務・資金
  調達・市場構造のうち根拠がある異なる2系統以上を、最大3本まで、各連鎖の
  先頭に①②③を付して区切る。根拠が1系統しかない日は、無理に数を埋めず1本に
  とどめ（①は付けない）、取得できた事実と限界を明記する。
  各連鎖の末尾（句点の直前）に「可能性」「意識された可能性」「因果は未確認」
  等の限定を必ず置く。
- part2_summary: 総括。地合い・不確実性・今後の確認事項のみ、1〜2文に
  収める（3文以上は機械監査でFAILとなる）。ニュースの再説明をしない。
  reusable_for_summary（前日以前の投稿で扱った継続材料。システムが検証済みで、
  空配列の日が通常である）があれば1行だけ言及してよい。空配列の日は、前編に
  無い材料への言及を総括に書かない（v1.92・オーナー指示）。価格・24時間比・
  Fear & Greed・DEX・APR・LP助言には触れない（統合運用基準§3.1）。
  地合いは「改善」「悪化」「不透明」等の定性的な表現にとどめ、指数や
  数値を根拠に挙げない。
  対象日の翌日が土日の場合は「翌日」ではなく「今後」「週明け」と書く。
  総括で言及してよい固有名詞・材料は、part1_headline・part1_points に
  掲載済みのもの、または reusable_for_summary に渡された継続材料（前日以前の
  投稿で扱ったもの）に限る
  （v1.35・オーナー指示。v1.82・オーナー承認でヘッドラインを追加）。
  本文（part1_headline・part1_points）で扱っていない新規の固有名詞・
  材料を総括で初めて持ち出さない——読者が文脈を追えないため。

出力形式（JSONのみ）:
{{ "part2_flow": ["...", "..."], "part2_summary": "..." }}

part2_flowの各連鎖は、本文だけを書く。先頭に「・」などの行頭記号や空白を付けない（システムが必要に応じて
「・」を付ける。①②③は付けてよい）。"""

SYSTEM_B = "\n\n".join([
    ROLE_INTRO, RULES_ABSOLUTE, RULES_HASHTAG, RULES_CAUSAL, INTRADAY_MOVE_GUIDANCE,
    ETF_WEEKEND_GUIDANCE, CALL_B_INSTRUCTIONS,
])


# --- v1.102（オーナー承認）: 項目の先頭の記号・空白の整形 ---
#
# 背景: 2026-10-05分の主要なポイントの行頭が「・・」と二重になった（システムが各項目の先頭に「・」を付ける〔compose_post.
# _render_bullets〕のに対し、呼び出しAの出力の項目がすでに「・」で始まっていた）。【市場のフロー】にも同じ穴があった。
# 過去39日で二重は10/5の2行だけ、ほかに9/2に「・」の後ろに空白が2つ付いた行が1行。呼び出しAに渡す前日以前の投稿
# （previous_posts）の項目が「・」付きだったことが原因の可能性が高いが、モデルの出力は保存されておらず推定にとどまる。
# 対処: 呼び出しA・Bの出力を受け取った直後に、項目（part1_points・part2_flow）の先頭の行頭記号・空白を機械的に除去し、
# 除去した件数をbundleに記録して警告欄に表示する（モデルが指示を守らなかった頻度の追跡）。整形前の項目は診断用に保存する。
# 行頭記号として除くもの: 中点・黒点の類（・ ･ • · ‧ ∙ ◦ ▪ ‣ ⁃）と空白は常に除く。●○■□◆◇は直後が空白のときだけ
# （「○○社が…」「●●銀行」の先頭を壊さない）。ダッシュ類（- * – — − ‐ ＊ －）は直後が空白で、その後が数字でないときだけ
# （「-5%」「- 5%」「−0.3%」で始まる項目の符号を落とさない）。
_HEAD_RE = re.compile(r"^(?:[\s\u3000・･•·‧∙◦▪‣⁃]|[●○■□◆◇](?=\s)|[-*–—−‐＊－](?=\s+(?!\d)))+")


def normalize_item_head(text: Any) -> Any:
    """項目の先頭の行頭記号（・ ･ • · 等）と空白を除く。ダッシュ類（- * – —等）は直後が空白のときだけ記号とみなす
    （「-5%」「−0.3%」で始まる項目を壊さない）。文字列でないものはそのまま返す。冪等。"""
    if not isinstance(text, str):
        return text
    return _HEAD_RE.sub("", text)


def normalize_items(items: Any) -> tuple[Any, int]:
    """項目のリストの各要素を整形し、(整形後のリスト, 変更した件数) を返す。リストでなければそのまま（0件）。
    整形（または元から）空になった文字列の項目は除外し、件数に含める（「・」だけの行を出さない）。"""
    if not isinstance(items, list):
        return items, 0
    normalized = [normalize_item_head(x) for x in items]
    changed = sum(1 for a, b in zip(items, normalized) if a != b)
    kept = [x for x in normalized if not (isinstance(x, str) and not x.strip())]
    dropped_orig_empty = sum(1 for a, b in zip(items, normalized) if a == b and isinstance(b, str) and not b.strip())
    return kept, changed + dropped_orig_empty


class CallOutcome:
    def __init__(self, ok: bool, data: dict | None, attempts: int, error: str | None,
                 usage: dict[str, int] | None = None, truncation_stats: dict[str, int] | None = None,
                 attempt_errors: list[str] | None = None, audit_ledger_auto_filled_count: int = 0,
                 rejected_pairs: list[dict] | None = None, force_dropped_candidates: list[dict] | None = None,
                 attempt_diagnostics: list[dict] | None = None):
        self.ok = ok
        self.data = data
        self.attempts = attempts
        self.error = error
        self.usage = usage or {"input_tokens": 0, "output_tokens": 0}
        self.truncation_stats = truncation_stats or {}
        # v1.48（オーナー指示）: 最終的に成功した場合でも、それ以前の試行が
        # 何を理由に失敗したかを保持する（従来はlast_errが最後の1件のみを
        # 保持し、成功時はCallOutcomeへ一切渡らず失われていた）。リトライが
        # 常態化する劣化の兆候をGENERATION_STATUS.mdで早期に検知するため。
        self.attempt_errors = attempt_errors or []
        # v1.54フォローアップ（オーナー指示）: audit_ledgerのdecision/reason
        # 空欄自動補完（_reconstruct_audit_ledger参照）が発生した件数。
        # GENERATION_STATUS.mdへ記録し、非決定的な発生頻度を追跡する。
        self.audit_ledger_auto_filled_count = audit_ledger_auto_filled_count
        # v1.79（オーナー承認）: ペア判定で却下された候補の診断（両側の
        # title/source・重なり係数・却下理由）。GitHub Actionsアーティファクト
        # （rejected_pairs.json）として保存し、config/pair_overlap.jsonの
        # 閾値調整判断に使う——リポジトリへはコミットしない。
        self.rejected_pairs = rejected_pairs or []
        # v1.79（オーナー承認）: 最終試行でも独立2ソースの相方が成立せず
        # 強制的に不採用にした候補（_derive_decisions参照）。
        # GENERATION_STATUS.mdへ記録する。
        self.force_dropped_candidates = force_dropped_candidates or []
        # v1.86（オーナー承認・案G）: 試行ごとの「相方が成立しなかった候補」の診断
        # （候補ID・タイトル・媒体・申告先・却下理由コード）。rejected_pairsは最終
        # 試行の分しか残らない（試行ごとにclear）ため、1・2試行目の理由が消えていた。
        # 各要素: {"attempt", "force_drop", "unresolved": [...], "rejected_pairs": [...]}。
        self.attempt_diagnostics = attempt_diagnostics or []
        # v1.92（オーナー承認・R2）: reusable_for_summaryの機械フィルタで除外した項目
        # （{"text","reason"}。GENERATION_STATUS.mdへ記録する）。
        self.reusable_dropped: list[dict] = []
        # v1.97（オーナー承認・案1）: 候補IDごとの{"decision","use","reason"}（候補の記録用。
        # 呼び出しAが成功した場合のみ。to_dict()には含めない）。
        self.candidate_decisions: dict[int, dict] = {}
        # v1.102（オーナー承認）: 項目の先頭の記号・空白を整形した記録（{"<キー>_raw": 整形前のリスト, "<キー>_changed": 件数}）。
        # 整形前の項目を診断用（attempt_diagnostics.json。コミットしない）に残すため。
        self.format_normalization: dict[str, Any] = {}

    def to_dict(self) -> dict:
        return {"ok": self.ok, "attempts": self.attempts, "error": self.error,
                "usage": self.usage, "data": self.data, "truncation_stats": self.truncation_stats,
                "attempt_errors": self.attempt_errors,
                "audit_ledger_auto_filled_count": self.audit_ledger_auto_filled_count,
                "rejected_pairs": self.rejected_pairs,
                "force_dropped_candidates": self.force_dropped_candidates,
                "attempt_diagnostics": self.attempt_diagnostics,
                "reusable_dropped": self.reusable_dropped,
                "format_normalization": self.format_normalization}


def _extract_text(response: Any) -> str:
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()


_CODE_FENCE_RE = re.compile(r"```[A-Za-z]*\n(.*?)\n?```", re.DOTALL)


def _strip_code_fence(text: str) -> str:
    """出力形式でコードフェンス禁止を指示済みだが、万一付与された場合のみ剥がす。

    v1.29: 位置0のフェンスしか想定していなかった旧実装は、モデルが
    フェンスの前に説明文（プリアンブル）を付けた場合に何もせず、生テキストが
    そのままjson.loads()へ渡り"char 0"のJSONDecodeErrorで失敗する事象が
    実データで確認された（DESIGN_CHANGES.md参照。情報源規律の優先順位付けの
    ようなより踏み込んだ判断を求める指示を追加した後に顕在化した）。
    テキスト中のどこにあってもフェンスを検出して中身のみを取り出す。
    フェンスが無い場合も、プリアンブル付き・無しいずれにも対応するため
    最初の '{' から対応する最後の '}' までを抽出するフォールバックを試みる。
    """
    t = text.strip()
    fence_match = _CODE_FENCE_RE.search(t)
    if fence_match:
        return fence_match.group(1).strip()
    if t.startswith("{"):
        return t
    first_brace = t.find("{")
    last_brace = t.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return t[first_brace:last_brace + 1].strip()
    return t


def _extract_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    return {
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
    }


def _add_usage(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {"input_tokens": a["input_tokens"] + b["input_tokens"],
            "output_tokens": a["output_tokens"] + b["output_tokens"]}


def _call_json(
    client: "anthropic.Anthropic", *, system: str, user_content: str, max_tokens: int,
    required_keys: list[str], post_process: Callable[[dict, int], dict] | None = None,
    build_retry_note: Callable[[Exception], str | None] | None = None,
) -> CallOutcome:
    """system/userプロンプトでJSON応答を取得し、必須キーの充足まで検証する。
    ツールは一切使わない通常のメッセージ呼び出し（v1.15。呼び出しA・B共通）。

    例外（ネットワーク・認証・レート制限・refusal・空応答・JSON不正・必須キー欠落）は
    すべて「この呼び出しの失敗」として扱い、最大MAX_ATTEMPTS回まで再試行したうえで
    最終的に CallOutcome(ok=False) を返す。呼び出し元はこれを個別呼び出しの失敗として
    縮退ラダーへ渡す設計（§5.3）のため、ここでの except は意図的に広く取っている
    （個別の例外型ごとに扱いを変えると、想定外の失敗モードが縮退せずクラッシュしうる）。

    post_process（v1.48）: 必須キー充足後・成功として返す前に呼ぶ任意のフック。
    呼び出し元固有の後処理（call_aのaudit_ledger再構成など）をここに差し込む。
    例外を送出した場合もこのtryブロック内で捕捉され、他の失敗と同様に
    リトライされる——post_process内の検証エラーもJSON不正等と同列に扱う。
    v1.79（オーナー承認）: 第2引数として現在の試行回数（1始まり）を渡す。
    call_a()が最終試行（attempt==MAX_ATTEMPTS）でのみforce_drop_unresolved=Trueを
    有効にするために使う（それ以外の呼び出し元は無視してよい）。

    build_retry_note（v1.66・オーナー承認）: 従来、リトライは直前の試行と
    完全に同一のuser_contentを無変更で再送しており、失敗理由（attempt_errors
    へは記録される）が次の試行のプロンプトに一切反映されなかった。9/3実データ
    でtier3の独立2ソースペア判定エラーが1・2試行目で同一の候補IDのまま
    2回連続再現し、3試行目まで無駄なトークンを消費した事象（DESIGN_CHANGES.md
    v1.64参照）への対処。build_retry_noteを渡すと、各失敗の直後に例外から
    追記テキストを生成し、直前1回分の失敗のみを反映した形でuser_contentへ
    追記して次の試行へ渡す（複数回分の失敗を蓄積しない——直前の状態だけを
    示す方が明確なため）。Noneまたは空文字列を返せば追記しない。未指定
    （デフォルトNone）の呼び出し元（call_b等）は従来どおり無変更で動作する。
    """
    attempt_errors: list[str] = []
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    effective_content = user_content
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": effective_content}],
                # v1.28（オーナー承認）: claude-sonnet-5はthinking未指定時に
                # 既定でadaptive thinkingが動作し、そのトークン消費は
                # _extract_text（type=="text"のみ抽出）から完全に不可視になる。
                # 候補急増日でmax_tokensが不可視のthinking消費だけで枯渇し
                # JSON本体が生成されない事象を実測で確認したため無効化する
                # （DESIGN_CHANGES.md参照。audit_ledgerの分量そのものを
                # 縮める対症療法ではなく、不可視消費という根本原因への対応）。
                thinking={"type": "disabled"},
            )
            # 応答を受け取れた時点で実消費量を確定させる（この後の検証で例外が
            # 出てもトークンは既に消費済みのため、成否によらず加算する）。
            total_usage = _add_usage(total_usage, _extract_usage(response))
            if response.stop_reason == "refusal":
                category = getattr(getattr(response, "stop_details", None), "category", None)
                raise ValueError(f"refusal (category={category})")
            text = _strip_code_fence(_extract_text(response))
            if not text:
                raise ValueError("空応答")
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("JSON応答がオブジェクトでない")
            missing = [k for k in required_keys if k not in data]
            if missing:
                raise ValueError(f"必須キー欠落: {missing}")
            if post_process is not None:
                data = post_process(data, attempt)
            return CallOutcome(True, data, attempt, None, total_usage, attempt_errors=list(attempt_errors))
        except Exception as e:  # noqa: BLE001 — 上記docstring参照
            attempt_errors.append(f"{type(e).__name__}: {e}")
            if attempt < MAX_ATTEMPTS:
                if build_retry_note is not None:
                    note = build_retry_note(e)
                    effective_content = f"{user_content}\n\n{note}" if note else user_content
                time.sleep(RETRY_DELAYS_SEC[attempt - 1])
    return CallOutcome(False, None, MAX_ATTEMPTS, attempt_errors[-1], total_usage,
                        attempt_errors=list(attempt_errors))


def _select_candidates_for_call_a(
        candidates: list[dict],
        pair_overlap_threshold: float = PAIR_OVERLAP_THRESHOLD_DEFAULT) -> tuple[list[dict], dict[str, int]]:
    """選定の本体は_select_candidates_detail（v1.97でdetailを返す形に分離。戻り値・挙動は従来どおり）。"""
    selected, stats, _detail = _select_candidates_detail(candidates, pair_overlap_threshold)
    return selected, stats


def _select_candidates_detail(
        candidates: list[dict],
        pair_overlap_threshold: float = PAIR_OVERLAP_THRESHOLD_DEFAULT
) -> tuple[list[dict], dict[str, int], dict[str, Any]]:
    """呼び出しAへ渡す候補を選ぶ（v1.21・v1.39フォローアップでペア救済を追加・
    v1.51でtier4上限を追加・v1.59でtier2上限を追加）。
    tier 1（公式発表）は全件、tier 3（CoinDesk・Cointelegraph等）は公開日時の
    新しい順で上位TIER3_CANDIDATE_LIMIT件までに絞る。候補急増日（実測30件・
    うちtier3が28件）でaudit_ledgerの全候補記録がCALL_A_MAX_TOKENSを
    超過した事象への対処（DESIGN_CHANGES.md v1.21参照）。

    v1.39フォローアップ（オーナー承認）: 「新しい順で上位N件」だけでは、
    独立2媒体が同一事実を報じているペアの一方が、単に公開時刻が早いという
    理由でTIER3_CANDIDATE_LIMIT外へ落ちる（窓序盤の記事が窓終盤の記事群に
    押しやられる時間帯バイアス）。上位N件確定後、tier3全件を対象にペアを
    検出し、上位N件に入っていないペアの相手を上限外で救済する
    （PAIR_RESCUE_MAX_PAIRS組まで）。

    v1.51（オーナー指示）: tier4（Google News等・候補発見専用）も、公開日時の
    新しい順で上位TIER4_CANDIDATE_LIMIT件までに絞る。tier4は単独では事実の
    根拠にしない候補発見専用の位置づけ（tier1裏付け・独立2ソースいずれも
    対象外）のため、tier3のようなペア救済は行わない。

    v1.59（オーナー承認）: tier2（Reuters・実体確認済みのGoogle News経由
    記事）は、tier1と異なり無制限にはせず、公開日時の新しい順で上位
    TIER2_CANDIDATE_LIMIT件までに絞る（tier3と同格の上限。オーナー指定。
    Reuters検索クエリが金融・暗号資産に絞られておらず無関係な一般
    ニュースを多く含むため）。tier2は単独採用可能（tier1と同じ位置づけ）
    でありtier3のような独立2ソースのペア救済は不要のため行わない。
    """
    tier1 = [c for c in candidates if c.get("tier") == 1]
    tier2 = [c for c in candidates if c.get("tier") == 2]
    tier3 = [c for c in candidates if c.get("tier") == 3]
    others = [c for c in candidates if c.get("tier") not in (1, 2, 3)]

    def pub_dt(c: dict):
        return collect_news.parse_pubdate_jst(c.get("published_at", "")) or datetime.min.replace(
            tzinfo=collect_news.JST)

    tier2_sorted = sorted(tier2, key=pub_dt, reverse=True)
    tier2_selected = tier2_sorted[:TIER2_CANDIDATE_LIMIT]

    tier3_sorted = sorted(tier3, key=pub_dt, reverse=True)
    tier3_top = tier3_sorted[:TIER3_CANDIDATE_LIMIT]
    top_ids = {id(c) for c in tier3_top}

    rescued: list[dict] = []
    rescued_ids: set[int] = set()
    pairs_rescued = 0
    all_pairs = _find_independent_pairs(tier3_sorted, pair_overlap_threshold)
    for a, b in all_pairs:
        if pairs_rescued >= PAIR_RESCUE_MAX_PAIRS:
            break
        missing = [c for c in (a, b) if id(c) not in top_ids and id(c) not in rescued_ids]
        if not missing:
            continue  # 両方既に上位N件内、または既に救済済み → 救済不要
        for c in missing:
            rescued.append(c)
            rescued_ids.add(id(c))
        pairs_rescued += 1

    tier3_selected = tier3_top + rescued

    others_sorted = sorted(others, key=pub_dt, reverse=True)
    others_selected = others_sorted[:TIER4_CANDIDATE_LIMIT]

    stats = {
        "tier2_total": len(tier2),
        "tier2_selected": len(tier2_selected),
        "tier2_dropped": len(tier2) - len(tier2_selected),
        "tier3_total": len(tier3),
        "tier3_selected": len(tier3_selected),
        "tier3_dropped": len(tier3) - len(tier3_selected),
        "tier3_pairs_rescued": pairs_rescued,
        "tier3_pair_rescued_articles": len(rescued),
        "tier4_total": len(others),
        "tier4_selected": len(others_selected),
        "tier4_dropped": len(others) - len(others_selected),
    }
    # v1.97（オーナー承認・案1）: 候補の記録（build_candidate_selection_report）が、実際の選定と
    # 同じ並べ替え結果・救済結果を参照できるように返す（選定ロジックを二重に持たない）。
    detail = {"tier1": tier1, "tier2_sorted": tier2_sorted, "tier3_sorted": tier3_sorted,
              "others_sorted": others_sorted, "rescued_ids": rescued_ids, "pairs": all_pairs}
    return tier1 + tier2_selected + tier3_selected + others_selected, stats, detail


# v1.29（オーナー指示・修正2）: tier1が薄い日にpart1_pointsの項目数を
# 埋めるためtier3単独ソースが誤って"採用"される事象が実データで
# 繰り返し再現した（DESIGN_CHANGES.md参照）。ルールをプロンプト文中の
# 記憶に委ねるのではなく、候補ごとに掲載可否を機械的に付与して渡す。
_ELIGIBILITY_LABELS = {
    1: "掲載可",
    2: "掲載可",
    3: "単独では掲載不可（tier1・tier2の裏取り、または独立2ソース規定に該当する場合のみ可）",
    4: "掲載不可（候補発見専用。単独では事実の根拠にしない）",
}
_ELIGIBILITY_UNKNOWN = "掲載不可（tier不明）"


def _label_eligibility(candidates: list[dict]) -> list[dict]:
    return [
        {**c, "eligibility": _ELIGIBILITY_LABELS.get(c.get("tier"), _ELIGIBILITY_UNKNOWN)}
        for c in candidates
    ]


def _assign_candidate_ids(candidates: list[dict]) -> list[dict]:
    """news_candidates_todayの各候補へ1始まりの連番candidate_idを振る
    （v1.48・オーナー指示）。audit_ledgerでLLMがsource/url/title/
    published_atを転記せず、このIDだけで候補を参照できるようにするため。
    """
    return [{**c, "candidate_id": i} for i, c in enumerate(candidates, start=1)]


# --- v1.97（オーナー承認・案1）: 候補の記録 ---
#
# 背景（2026-10-04の調査）: tier2（Reuters）は新しい順で上位TIER2_CANDIDATE_LIMIT件に絞るため、
# 件数上限で落ちた記事は、どこにも記録が残らなかった（news_candidates.jsonはCI成果物でコミット
# されず、audit_ledgerは渡した候補の分しか記録しない）。どの記事が上限で落ちたか、その時刻範囲は
# いつ・どの日にどの程度落ちているかを、事後に確認できるようにする。
# 全候補（選定・救済・除外）について、tier・媒体・題名・公開時刻（UTC）・選定状態・tier内の新しい順の
# 順位・呼び出しAの採否と理由を記録する。選定ロジックは_select_candidates_detail()をそのまま使う
# （二重に持たない）。ここは記録のみで、選定・採否には一切影響しない。
CANDIDATE_LOG_SUMMARY_HEAD_CHARS = 120


def _iso_utc_minute(raw: Any) -> str | None:
    """RSSのpubDate（RFC 822）をUTCの'YYYY-MM-DDTHH:MMZ'へ。解釈できなければNone。"""
    dt = collect_news.parse_pubdate_jst(raw if isinstance(raw, str) else "")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ") if dt is not None else None


def build_candidate_selection_report(target_date: str, news_today: Any,
                                      pair_overlap_threshold: float = PAIR_OVERLAP_THRESHOLD_DEFAULT,
                                      decisions: dict[int, dict] | None = None) -> dict:
    """当日の全候補（news_candidates.json）について、呼び出しAへ渡したか・落としたかを記録する。

    candidate_idは_assign_candidate_ids()が実際に振る番号と同じ（選定結果の並びの1始まり）。
    落とした候補（status="dropped"）にはcandidate_idが無い（呼び出しAには渡していない）。
    status: "selected"（上限内）／"rescued"（tier3の独立2媒体ペア救済で上限外から追加）／
    "dropped"（件数上限により除外）。recency_rankはtier内の新しい順の順位（1が最新。tier1は無し）。
    decisions: {candidate_id: {"decision","use","reason"}}（呼び出しAが成功した場合のみ）。
    入力が不正でも例外にしない（記録は本文生成の成否に影響させない）。
    """
    candidates = news_today.get("candidates", []) if isinstance(news_today, dict) else []
    candidates = [c for c in candidates if isinstance(c, dict)]
    selected, stats, detail = _select_candidates_detail(candidates, pair_overlap_threshold)
    id_by_obj = {id(c): i for i, c in enumerate(selected, start=1)}
    rescued_ids = detail["rescued_ids"]

    def entry(c: dict, rank: int | None) -> dict:
        cid = id_by_obj.get(id(c))
        status = "dropped" if cid is None else ("rescued" if id(c) in rescued_ids else "selected")
        e: dict[str, Any] = {
            "candidate_id": cid, "tier": c.get("tier"), "source": c.get("source", ""),
            "title": c.get("title", ""), "published_at_utc": _iso_utc_minute(c.get("published_at")),
            "status": status, "recency_rank": rank, "url": c.get("url", ""),
            "summary_head": str(c.get("summary", ""))[:CANDIDATE_LOG_SUMMARY_HEAD_CHARS],
        }
        d = (decisions or {}).get(cid) if cid is not None else None
        if isinstance(d, dict):
            e["decision"] = d.get("decision")
            e["use"] = d.get("use")
            e["reason"] = d.get("reason", "")
            if d.get("force_dropped"):
                e["force_dropped"] = True
        return e

    entries = [entry(c, None) for c in detail["tier1"]]
    for key in ("tier2_sorted", "tier3_sorted", "others_sorted"):
        entries += [entry(c, rank) for rank, c in enumerate(detail[key], start=1)]

    window = None
    try:
        w_start, w_end = collect_news.collection_window_ny(date.fromisoformat(target_date))
        window = {"start_utc": w_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
                  "end_utc": w_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
    except (TypeError, ValueError):
        pass
    return {
        "target_date_jst": target_date,
        "collected_at": news_today.get("collected_at") if isinstance(news_today, dict) else None,
        "window": window,
        "source_status": news_today.get("source_status", {}) if isinstance(news_today, dict) else {},
        "limits": {"tier2": TIER2_CANDIDATE_LIMIT, "tier3": TIER3_CANDIDATE_LIMIT,
                   "tier4": TIER4_CANDIDATE_LIMIT, "pair_rescue_max_pairs": PAIR_RESCUE_MAX_PAIRS,
                   "raw_item_limit": collect_news.RAW_ITEM_LIMIT},
        "stats": stats,
        "call_a_decisions_recorded": decisions is not None,
        "candidates": entries,
    }


_AUDIT_LEDGER_STATIC_FIELDS = ("source", "url", "title", "published_at")


class AuditLedgerReconstructionError(ValueError):
    """LLMのaudit_ledger出力が候補一覧と整合しない場合に送出する（v1.48・
    v1.53フォローアップで対象を拡張）。_call_json()の広いexceptで捕捉され、
    他の解析失敗と同様にリトライされる。

    unresolved_details（v1.96・オーナー承認）: 独立2ソースの相方が成立しなかった候補ごとの
    理由（_explain_unresolvedの出力。重なり係数・閾値を含む）。リトライ指示
    （_build_call_a_retry_note）が、なぜ成立しなかったかをモデルへ伝えるために使う。
    """

    unresolved_details: "list[dict] | None" = None


def _pair_claim_detail(claimant_id: int, target_id: int, id_to_candidate: dict[int, dict],
                        use_by_id: dict[int, bool], threshold: float) -> dict:
    """_validate_pair_claim()と同じ妥当性判定を行い、判定根拠（両側の
    タイトル・出典・重なり係数・却下理由）を構造化して返す（v1.79・
    オーナー承認）。config/pair_overlap.jsonの閾値調整判断のため、却下された
    ペア申告の実例をGENERATION_STATUS.mdとは別にGitHub Actionsアーティファクト
    （rejected_pairs.json）として保存する用途で追加した。判定ロジック自体は
    _validate_pair_claim()から移設したものであり、判定結果（valid）は同一
    （既存テストで確認）。
    """
    claimant = id_to_candidate.get(claimant_id, {})
    detail = {
        "claimant_id": claimant_id,
        "claimant_title": claimant.get("title", ""),
        "claimant_source": claimant.get("source", ""),
        "claimant_tier": claimant.get("tier"),
        "target_id": target_id,
        "threshold": threshold,
    }
    target = id_to_candidate.get(target_id)
    if target is None or target_id == claimant_id:
        detail.update(target_title="", target_source="", target_tier=None, target_use=None,
                      overlap=None, valid=False,
                      reason="target_not_found" if target is None else "self_reference")
        return detail
    detail.update(target_title=target.get("title", ""), target_source=target.get("source", ""),
                  target_tier=target.get("tier"), target_use=bool(use_by_id.get(target_id)))
    if target.get("tier") != 3:
        detail.update(overlap=None, valid=False, reason="target_not_tier3")
        return detail
    if not use_by_id.get(target_id):
        detail.update(overlap=None, valid=False, reason="target_use_false")
        return detail
    if target.get("source") == claimant.get("source"):
        detail.update(overlap=None, valid=False, reason="same_source")
        return detail
    sim = _overlap_coefficient(_tokenize_title(claimant.get("title", "")), _tokenize_title(target.get("title", "")))
    valid = sim >= threshold
    detail.update(overlap=sim, valid=valid, reason=None if valid else "overlap_below_threshold")
    return detail


def _validate_pair_claim(claimant_id: int, target_id: int, id_to_candidate: dict[int, dict],
                          use_by_id: dict[int, bool], threshold: float) -> bool:
    """tier3のuse:trueエントリがpairs_with_candidate_idで自己申告した相手が
    独立2ソースの相方として妥当かを確認する（v1.53フォローアップ・
    オーナー指示）。以下4条件をすべて満たす場合のみ有効。
      - target_idが実在し、claimant_id自身でない
      - 相手もtier3であること
      - 相手もuse:trueであること
      - sourceが異なること（同一媒体の2記事は不可）
      - タイトルのトークン重なり係数がthreshold以上であること
    相互申告（双方が互いを指す）は要求しない——片方向の申告が上記条件を
    満たせば成立する（オーナー指示）。

    v1.79: 判定本体は_pair_claim_detail()へ移設し、本関数はvalidのみを
    取り出す薄いラッパーとした（挙動は完全に同一）。
    """
    return bool(_pair_claim_detail(claimant_id, target_id, id_to_candidate, use_by_id, threshold)["valid"])


# v1.86（オーナー承認・案G）: 相方不成立の理由コードの表示用ラベル。先頭6つは
# _pair_claim_detail()の却下理由コードそのもの。"no_claim"は表示専用に新設した
# ラベルで、LLMがpairs_with_candidate_idを書かなかった（申告なし）場合を、理由欄が
# 空白にならないよう明示するためのもの（_pair_claim_detail()は呼ばれず、却下ペア診断
# rejected_pairsにも記録されない）。
PAIR_REJECT_REASON_LABELS = {
    "target_not_found": "申告先の候補IDが存在しない",
    "self_reference": "自分自身を申告している",
    "target_not_tier3": "申告先がtier3でない",
    "target_use_false": "申告先がuse:false（不採用）。同一事実の独立2ソースなら、申告先もuse:trueにすれば成立する",
    "same_source": "申告先が同じ媒体",
    "overlap_below_threshold": "タイトルの重なり係数が閾値未満",
    "no_claim": "相方の申告なし（pairs_with_candidate_id=null）",
}


def _explain_unresolved(unresolved: list[int], claim_by_id: dict, id_to_candidate: dict[int, dict],
                         use_by_id: dict[int, bool], threshold: float) -> list[dict]:
    """tier3のuse:trueなのに独立2ソースの相方が成立しなかった候補ごとに、
    「なぜ成立しなかったか」を構造化して返す（v1.86・オーナー承認・案G）。
    own_claim=その候補自身の申告、incoming_claim=他のtier3・use:true候補からの
    その候補を指す申告。判定は_pair_claim_detail()をそのまま使う（成立判定と同一）。
    """
    out = []
    for cid in sorted(unresolved):
        cand = id_to_candidate.get(cid, {})
        entry = {"candidate_id": cid, "title": cand.get("title", ""), "source": cand.get("source", ""),
                 "tier": cand.get("tier"), "own_claim_target_id": claim_by_id.get(cid), "reasons": []}
        if claim_by_id.get(cid) is None:
            entry["reasons"].append({"role": "own_claim", "code": "no_claim"})
        else:
            d = _pair_claim_detail(cid, claim_by_id[cid], id_to_candidate, use_by_id, threshold)
            entry["reasons"].append({
                "role": "own_claim", "code": d.get("reason") or "no_claim", "other_id": d.get("target_id"),
                "other_title": d.get("target_title", ""), "other_source": d.get("target_source", ""),
                "overlap": d.get("overlap"), "threshold": d.get("threshold")})
        for other, target in claim_by_id.items():
            if other == cid or target != cid:
                continue
            if id_to_candidate.get(other, {}).get("tier") != 3 or not use_by_id.get(other):
                continue
            d = _pair_claim_detail(other, cid, id_to_candidate, use_by_id, threshold)
            if d.get("valid"):
                continue
            entry["reasons"].append({
                "role": "incoming_claim", "code": d.get("reason"), "other_id": other,
                "other_title": d.get("claimant_title", ""), "other_source": d.get("claimant_source", ""),
                "overlap": d.get("overlap"), "threshold": d.get("threshold")})
        out.append(entry)
    return out


def _derive_decisions(llm_entries: list[dict], id_to_candidate: dict[int, dict],
                       pair_overlap_threshold: float, rejected_pairs: list[dict] | None = None,
                       force_drop_unresolved: bool = False,
                       force_dropped: list[dict] | None = None,
                       diagnostics: dict | None = None) -> dict[int, str]:
    """candidate_idごとのdecision（"採用"/"採用（独立2ソース）"/"不採用"）を
    コード側で機械的に導出する（v1.53フォローアップ・オーナー指示）。

    rejected_pairs（v1.79・オーナー承認）: 渡された場合、ペア申告が
    _pair_claim_detail()の条件を満たさず却下されるたびに、その判定根拠
    （両側のtitle/source・重なり係数・却下理由）を追記する（ミュータブル
    な蓄積先を渡す既存のstats引数と同じ規約）。config/pair_overlap.jsonの
    閾値調整判断のため、call_a()がGitHub Actionsアーティファクトとして
    保存する目的でのみ使う——decisionの導出ロジック自体には影響しない。

    force_drop_unresolved／force_dropped（v1.79・オーナー承認）: 従来、
    tier3のuse:trueで独立2ソースの相方が最後まで成立しない候補は必ず
    AuditLedgerReconstructionErrorを送出していた（_call_json()が
    MAX_ATTEMPTS回リトライしても解消しないaudit_ledgerペア判定エラーが
    2026-09-26に発生し、L1へ縮退した事象への対処）。force_drop_unresolved=
    Trueを渡すと、リトライを尽くしても解消しない候補は例外にせず
    「不採用」へ強制変更して続行する（call_a()が最終試行でのみ渡す）。
    force_droppedを渡した場合、強制不採用にした候補ごとにcandidate_id・
    title・source・reasonを追記する——呼び出し元がGENERATION_STATUS.mdへ
    記録するために使う。この強制変更後は呼び出し元（compose_post.py）が
    C12〜C24を再監査し、なお失敗する場合は従来どおりのL1（呼び出しA失敗
    扱い）へフォールバックする設計（オーナー指示・verify_post.py自体は
    変更しない）。

    C21（decision/tier整合性監査）が、tier3候補に対する呼び出しAの誤った
    decisionラベル付け（単独ソースを独立2ソースと誤判定・tier1限定のはずの
    "採用"をtier3が名乗る等）を繰り返し検出していた事象への対応。LLMには
    "採用"のような記録文言を直接書かせず、候補ごとのuse:true/falseと
    （tier3のuse:trueに限り）pairs_with_candidate_idの自己申告のみを
    書かせ、tierと申告の妥当性からdecisionを構成的に確定する——誤った
    文言が生じる経路自体を無くす（C19のsource/url/title/published_at
    再構成＝v1.48と同じ設計思想）。

    tier1・tier2: use:true→"採用"、use:false→"不採用"（v1.59・オーナー
      承認。tier2はReuters・実体確認済みのGoogle News経由記事であり、
      統合運用基準§2の優先度2〈独立報道〉としてtier1と同様に単独採用
      可能）。
    tier3: use:trueかつ_validate_pair_claim()を満たすペアが（自己申告
      またはpairs_with_candidate_idで自分を指す他候補からの申告いずれかで）
      成立→双方"採用（独立2ソース）"。use:trueだがどの方向からもペアが
      成立しない場合はAuditLedgerReconstructionErrorを送出し、
      _call_json()のリトライへ委ねる（C21で検知させる設計だと1回のFAILが
      即座に生成物全体を不採用にするため、まずリトライでLLMに自己修正の
      機会を与える。オーナー指示）。use:false→"不採用"。
    tier1・tier2・tier3以外（tier4等・候補発見専用）: useの値によらず常に
    "不採用"（NEWS_SELECTIONの「単独では事実の根拠にしない」規定と整合。
    tier4はペアの対象に含めない——オーナー指示）。
    """
    use_by_id = {e["candidate_id"]: bool(e.get("use")) for e in llm_entries}
    claim_by_id: dict[int, int | None] = {}
    for e in llm_entries:
        pc = e.get("pairs_with_candidate_id")
        claim_by_id[e["candidate_id"]] = pc if isinstance(pc, int) and not isinstance(pc, bool) else None

    paired: set[int] = set()
    for cid, target_id in claim_by_id.items():
        if id_to_candidate[cid].get("tier") != 3 or not use_by_id.get(cid) or target_id is None:
            continue
        detail = _pair_claim_detail(cid, target_id, id_to_candidate, use_by_id, pair_overlap_threshold)
        if detail["valid"]:
            paired.add(cid)
            paired.add(target_id)
        elif rejected_pairs is not None:
            rejected_pairs.append(detail)

    decisions: dict[int, str] = {}
    unresolved: list[int] = []
    for cid, candidate in id_to_candidate.items():
        use = use_by_id.get(cid, False)
        tier = candidate.get("tier")
        if not use:
            decisions[cid] = "不採用"
        elif tier in (1, 2):
            decisions[cid] = "採用"
        elif tier == 3:
            if cid in paired:
                decisions[cid] = "採用（独立2ソース）"
            else:
                unresolved.append(cid)
        else:
            decisions[cid] = "不採用"

    if unresolved:
        if diagnostics is not None:
            # v1.86（案G）: 例外化・強制不採用のどちらの前でも、成立しなかった理由を残す
            # （呼び出し元がtry/finallyで試行ごとに回収する）。
            diagnostics["unresolved"] = _explain_unresolved(
                unresolved, claim_by_id, id_to_candidate, use_by_id, pair_overlap_threshold)
        if not force_drop_unresolved:
            err = AuditLedgerReconstructionError(
                f"tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: {sorted(unresolved)}")
            # v1.96: リトライ指示へ重なり係数・閾値を伝えるため、理由を例外に添える（診断の有無によらない）
            err.unresolved_details = _explain_unresolved(
                unresolved, claim_by_id, id_to_candidate, use_by_id, pair_overlap_threshold)
            raise err
        for cid in unresolved:
            decisions[cid] = "不採用"
            if force_dropped is not None:
                force_dropped.append({
                    "candidate_id": cid,
                    "title": id_to_candidate[cid].get("title", ""),
                    "source": id_to_candidate[cid].get("source", ""),
                    "reason": "最終試行でも独立2ソースの相方が成立しなかったため強制的に不採用にした",
                })
    return decisions


def _reconstruct_audit_ledger(llm_entries: Any, id_to_candidate: dict[int, dict],
                               pair_overlap_threshold: float = PAIR_OVERLAP_THRESHOLD_DEFAULT,
                               stats: dict[str, int] | None = None,
                               rejected_pairs: list[dict] | None = None,
                               force_drop_unresolved: bool = False,
                               force_dropped: list[dict] | None = None,
                               diagnostics: dict | None = None,
                               decisions_out: dict[int, str] | None = None) -> list[dict]:
    """LLMが出力した candidate_id・use・pairs_with_candidate_id・
    verified_by・reason のみのaudit_ledgerを、候補データのsource/url/
    title/published_atで補完し、decisionをコード側で導出した完全な形へ
    復元する（v1.48・オーナー指示。decision導出はv1.53フォローアップで
    追加）。source等をLLMに書かせないことで転記ミスの経路を無くし、
    decisionもLLMに書かせないことで誤ラベリングの経路を無くす。

    候補ID参照が候補一覧と過不足なく一致することを要求する——不明なID・
    重複・欠落のいずれも例外を送出し、呼び出し元の_call_json()のリトライへ
    委ねる（架空のIDを容認しない・「候補が1件も渡されていない場合を除き
    全件記録する」という既存要求を機械的に強制する）。tier3のuse:trueで
    独立2ソースの相方が成立しない場合も同様に例外化する（_derive_decisions
    参照）。

    v1.54フォローアップ（8/28実データ・オーナー指示）: reason（LLM自由
    記述）が空文字で返る事象が非決定的に複数回観測された（v1.49・v1.53×2・
    本件で計4例目）。C19が検査するのは「フィールドが揃っていること」で
    あり理由の質そのものではないため、空欄で生成物全体を止めるより、
    欠落を明示した定型文で補完して通す方が実害が小さいというオーナー
    判断により、reasonが空の場合は「理由が記載されませんでした（自動
    補完）」で埋める。decisionはv1.53フォローアップ以降コード側で
    tier・use・ペア申告の妥当性から導出するため空文字になる経路は
    通常ないが（_derive_decisions参照）、オーナー指示により安全側の
    フォールバックとして"不採用"で補完する処理を残す（防御的コード。
    現状の設計では原理的に到達しない想定）。補完件数はstatsへ記録し、
    呼び出し元がGENERATION_STATUS.mdへ記録する。
    """
    if not isinstance(llm_entries, list):
        raise AuditLedgerReconstructionError("audit_ledgerがリストでない")
    seen_ids: set[int] = set()
    parsed: list[dict] = []
    for e in llm_entries:
        if not isinstance(e, dict):
            raise AuditLedgerReconstructionError(f"audit_ledgerの要素がオブジェクトでない: {e!r}")
        cid = e.get("candidate_id")
        if not isinstance(cid, int) or isinstance(cid, bool) or cid not in id_to_candidate:
            raise AuditLedgerReconstructionError(f"audit_ledgerに存在しない候補ID: {cid!r}")
        if cid in seen_ids:
            raise AuditLedgerReconstructionError(f"audit_ledgerで候補IDが重複: {cid}")
        seen_ids.add(cid)
        parsed.append(e)
    missing = set(id_to_candidate) - seen_ids
    if missing:
        raise AuditLedgerReconstructionError(f"audit_ledgerに記録されていない候補ID: {sorted(missing)}")

    decisions = _derive_decisions(parsed, id_to_candidate, pair_overlap_threshold,
                                   rejected_pairs=rejected_pairs, force_drop_unresolved=force_drop_unresolved,
                                   force_dropped=force_dropped, diagnostics=diagnostics)

    reconstructed = []
    auto_filled = 0
    for e in parsed:
        cid = e["candidate_id"]
        candidate = id_to_candidate[cid]
        entry = {field: candidate.get(field, "") for field in _AUDIT_LEDGER_STATIC_FIELDS}
        entry["verified_by"] = e.get("verified_by", "")
        decision = decisions[cid]
        if not str(decision).strip():
            decision = "不採用"
            auto_filled += 1
        reason = e.get("reason", "")
        if not str(reason).strip():
            reason = "理由が記載されませんでした（自動補完）"
            auto_filled += 1
        entry["decision"] = decision
        entry["reason"] = reason
        reconstructed.append(entry)
    if stats is not None:
        stats["audit_ledger_auto_filled_count"] = auto_filled
    if decisions_out is not None:
        # v1.92: 候補IDごとのdecision（採用／採用（独立2ソース）／不採用）を呼び出し元へ返す
        # （reusable_for_summaryの機械フィルタが「当日採用済みの材料」を判定するため）。
        decisions_out.clear()
        decisions_out.update({e["candidate_id"]: decisions[e["candidate_id"]] for e in parsed})
    return reconstructed


def _flag_scheduled_event_matches(candidates: list[dict], scheduled_events: Any) -> list[dict]:
    """v1.93（オーナー承認・案2）: 当日の候補のうち、その日のHigh米指標（scheduled_events）に対応しうる
    ものに、機械的な目印 `scheduled_event_match`（例: 「雇用統計（Non-Farm Employment Change）」）を付ける。
    対象はtier1〜3（tier4は候補発見のみで採否の対象外）。キーワード照合による目印にすぎず、事実の根拠でも
    採否の根拠でもない。指標日でない日（Highの米指標が無い日）は何も付けない。元の候補は変更しない。"""
    families = indicator_events.high_us_event_families(scheduled_events)
    if not families:
        return candidates
    out = []
    for c in candidates:
        label = indicator_events.match_label(c.get("title", ""), families) if c.get("tier") in (1, 2, 3) else ""
        out.append({**c, "scheduled_event_match": label} if label else c)
    return out


# --- v1.103（オーナー承認・調査2の案1）: 独立2ソースの相方の目印（machine_pair_hint）---
#
# 背景: 2026-10-05に、独立2媒体ペア救済で追加した4組（ID 41/42・43/44・45/46・47/48）がすべて不採用になった。
# 救済したペア（および自然に上位に入ったペア）の相方は、入力（news_candidates_today）のどこにも示されておらず、
# モデルが約23件のtier3から相方を自分で探す必要があった（候補のキーはtitle・url・source・published_at・summary・kind・tier・
# candidate_id・eligibilityの9個だけ）。1・2試行目の失敗は、ペアの片方だけをuse:trueにしたことが原因だった。
# 対処: システムが検出したペア（_find_independent_pairs。題名の語の重なり係数が閾値以上・別媒体）のうち、両方が呼び出しAへ
# 渡す候補に入っているものについて、双方の候補に相方のcandidate_idと重なり係数を目印として付ける。目印は題名の語の重なりだけで
# 機械的に付くため、同一事実でない偽ペア（10/5のMetaplanet 41/42のように、別の話で語が重なっただけの組）も含みうる。
# そのため、目印には必ず「同一事実でなければ無視してよい」を添える（判断はモデルが題名・要約を読んで行う）。
MACHINE_PAIR_HINT_NOTE = "機械検出（題名の語の重なり）。同一事実でなければ無視してよい"


def _build_machine_pair_hints(pairs: list[tuple[dict, dict]], id_of: dict[int, int]) -> dict[int, dict]:
    """{candidate_id: {"candidate_id": 相方のID, "title_overlap": 重なり係数, "note": …}}。
    id_ofは候補オブジェクトのid()→candidate_id。両方が渡す候補に入っているペアだけが対象（片方が渡されていなければ目印は付けない）。"""
    hints: dict[int, dict] = {}
    for a, b in pairs:
        ia, ib = id_of.get(id(a)), id_of.get(id(b))
        if ia is None or ib is None:
            continue
        overlap = round(_overlap_coefficient(_tokenize_title(a.get("title", "")), _tokenize_title(b.get("title", ""))), 2)
        hints[ia] = {"candidate_id": ib, "title_overlap": overlap, "note": MACHINE_PAIR_HINT_NOTE}
        hints[ib] = {"candidate_id": ia, "title_overlap": overlap, "note": MACHINE_PAIR_HINT_NOTE}
    return hints


def _build_call_a_user_content(daily_data: dict, news_today: dict, news_yesterday: dict | None,
                                pair_overlap_threshold: float = PAIR_OVERLAP_THRESHOLD_DEFAULT,
                                previous_posts: list[dict] | None = None
                                ) -> tuple[str, dict, dict[int, dict]]:
    selected_objs, stats, detail = _select_candidates_detail(news_today.get("candidates", []), pair_overlap_threshold)
    selected_today = _assign_candidate_ids(selected_objs)
    # v1.103: 独立2ソースの相方の目印（machine_pair_hint）。candidate_idは_assign_candidate_idsと同じ番号（選定結果の並びの1始まり）。
    hints = _build_machine_pair_hints(detail["pairs"], {id(c): i for i, c in enumerate(selected_objs, start=1)})
    selected_today = [{**c, "machine_pair_hint": hints[c["candidate_id"]]} if c["candidate_id"] in hints else c
                      for c in selected_today]
    id_to_candidate = {c["candidate_id"]: c for c in selected_today}
    selected_yesterday, _ = _select_candidates_for_call_a(
        (news_yesterday or {}).get("candidates", []), pair_overlap_threshold)
    payload = {
        "target_date_jst": daily_data.get("target_date_jst", ""),
        "weekday_jp": daily_data.get("weekday_jp", ""),
        "daily_data": daily_data,
        # v1.93: 指標日は、その日のHigh米指標に対応しうる候補にscheduled_event_matchの目印を付ける
        "news_candidates_today": _label_eligibility(
            _flag_scheduled_event_matches(selected_today, daily_data.get("scheduled_events"))),
        "news_candidates_yesterday": _label_eligibility(selected_yesterday),
        # v1.92（オーナー承認）: 前日以前の投稿本文（reusable_for_summaryの「前日以前の投稿本文で扱った
        # 材料」の比較対象）。news_candidates_yesterdayは本番では常に空だったため、この項目を追加した。
        "previous_posts": previous_posts or [],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2), stats, id_to_candidate


# v1.82（オーナー承認）: 呼び出しBへ渡すdaily_dataから除外する項目。統合運用基準
# §3.1が【市場のフロー】【総括】に書いてはいけない項目（Fear & Greed・DEX・APR・
# LP助言・相対強弱）に当たるデータを、モデルへ渡さないことで混入を防ぐ
# （9/22〜9/27の5日分ドライランでC26/C27が5日中5日FAILした原因の一つ）。
# 渡し続けるのはassets（価格・24時間比）・intraday_range・scheduled_events・
# market.market_cap/volume_24h等。呼び出しA（ヘッドライン・主要なポイント）
# 側のdaily_dataは対象外（変更していない）。
CALL_B_EXCLUDED_DAILY_DATA_PATHS: tuple[tuple[str, ...], ...] = (
    ("market", "fear_greed"),
    ("market", "btc_dominance"),
    ("market", "eth_dominance"),
    ("base",),
    ("lp",),
    ("domestic",),
)


def _daily_data_for_call_b(daily_data: dict) -> dict:
    """呼び出しB向けに、CALL_B_EXCLUDED_DAILY_DATA_PATHSの項目を除いた
    daily_dataのコピーを返す（元のdaily_dataは変更しない）。存在しない
    パスは無視する。
    """
    sanitized = copy.deepcopy(daily_data)
    for path in CALL_B_EXCLUDED_DAILY_DATA_PATHS:
        node = sanitized
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict):
            node.pop(path[-1], None)
    return sanitized


def _build_call_b_user_content(daily_data: dict, call_a_data: dict | None) -> str:
    if call_a_data:
        news_from_a = {
            "part1_headline": call_a_data.get("part1_headline", ""),
            "part1_points": call_a_data.get("part1_points", []),
            "reusable_for_summary": call_a_data.get("reusable_for_summary", []),
        }
    else:
        news_from_a = None  # 呼び出しA失敗 → ニュースは空で渡す（§5.2）
    payload = {
        "target_date_jst": daily_data.get("target_date_jst", ""),
        "weekday_jp": daily_data.get("weekday_jp", ""),
        "daily_data": _daily_data_for_call_b(daily_data),
        "news_from_call_a": news_from_a,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# --- v1.92（オーナー承認）: reusable_for_summaryを「前日以前の投稿本文で扱った材料のうち、新しい動きが
# ないものだけ」に限る（R1: プロンプト／R2: 機械フィルタ）---
#
# 背景: 2026-10-02分で、当日初報（台帳では採用）のBlastが主要なポイントに載らないまま
# reusable_for_summary経由で総括にだけ出た。調査（L0の24日・48項目）で、reusable_for_summaryの
# 98%（47件）が当日の材料で、前日から続く材料はわずか1件だった。「前日から更新がない材料は
# reusable_for_summaryへ」という従来の指示は、比較対象（news_candidates_yesterday）が本番では
# 常に空だったため（news_candidates.jsonはCI成果物でコミットされず、前日分が存在しない）、
# そもそも働いていなかった。オーナー判断（10/4）: reusable_for_summaryは「前日以前の投稿本文で
# 扱った材料のうち、新しい動きがないものだけ」。当日の候補・tier4は書かない（tier4を残すと
# 情報源規律の抜け道になるため）。採用したのに本文に載らない材料は主要なポイントへ回す。
#
# 実装:
#  (R1) プロンプトで上記を指示し、比較対象として前日以前の投稿本文（コミット済みの
#       outputs/<日付>/draft/post_bundle.jsonのヘッドライン・主要なポイント）をpayloadの
#       previous_posts（直近3件・7日以内）として渡す。
#  (R2) call_Aの出力のreusable_for_summaryは {"text","carried_from","candidate_ids"} 形式。コードが
#       次を満たさない項目を機械的に除外する（除外内容はGENERATION_STATUS.mdに記録）:
#       ①carried_fromがprevious_postsの日付のいずれか ②textの語が、その日の投稿本文と対応する
#       （固有名詞等の特徴語が2つ以上、または7文字以上の特徴語が1つ共通） ③candidate_idsに
#       tier4の候補・当日採用済みの候補を含まない ④最大2件。文字列だけの旧形式は除外する。
#       ②は「前日以前の投稿で扱った」との自己申告を裏付ける最低限の照合で、意味の同一性までは
#       保証しない（過去50項目の試算では4件だけが通り、いずれも前日以前の本文と題材が同じだった）。
PREVIOUS_POSTS_MAX = 3
PREVIOUS_POSTS_WINDOW_DAYS = 7
REUSABLE_MAX_ITEMS = 2
_REUSABLE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&.\-]{3,}|[一-龥ァ-ヶー][一-龥ァ-ヶー0-9]{4,}")
# 媒体名・汎用語は「同じ題材」の根拠にならないため、特徴語から除く
_REUSABLE_NON_DISTINCTIVE = frozenset({
    "coindesk", "cointelegraph", "reuters", "bloomberg", "block", "theblock", "tier1", "tier2", "tier3", "tier4",
    "ethereum", "bitcoin", "crypto", "ビットコイン", "イーサリアム", "ステーブルコイン", "暗号通貨", "暗号資産",
    "公式発表", "継続監視", "直接因果", "未確認", "報じられ", "確認できません", "確認できない",
})


_HASHTAG_RE = re.compile(r"\s*(?<![A-Za-z0-9_])#[A-Za-z0-9_]+")


def _strip_hashtags(text: str) -> str:
    return _HASHTAG_RE.sub("", text).strip()


def _is_fixed_post(headline: str, points: str) -> bool:
    # L0のbundleの主要なポイントは「・補足できる検証済み材料は確認できない。」と箇条書き記号つきで保存される
    # （L1は記号なし）ため、先頭の「・」を除いて比べる。
    return (headline.strip().startswith(FIXED_HEADLINE.rstrip("。"))
            and points.strip().lstrip("・").strip().startswith(FIXED_POINTS.rstrip("。")))


def _load_previous_posts(target_date: str, outputs_root: Path | None = None) -> list[dict]:
    """対象日より前の、コミット済みの投稿本文（ヘッドライン・主要なポイント）を新しい順に最大
    PREVIOUS_POSTS_MAX件、PREVIOUS_POSTS_WINDOW_DAYS日以内から集める（v1.92）。
    ファイルが無い・壊れている日、定型文だけの日（材料なし）は飛ばす。失敗しても例外にしない。
    各要素: {"date", "part1_headline", "part1_points"（項目のリスト。v1.102から先頭の「・」等は除く）}。"""
    root = outputs_root or Path("outputs")
    result: list[dict] = []
    try:
        base = date.fromisoformat(target_date)
    except ValueError:
        return result
    for i in range(1, PREVIOUS_POSTS_WINDOW_DAYS + 1):
        d = (base - timedelta(days=i)).isoformat()
        bundle = _load_json_or(root / d / "draft" / "post_bundle.json", default=None)
        sections = bundle.get("sections") if isinstance(bundle, dict) else None
        if not isinstance(sections, dict):
            continue
        headline, points = sections.get("part1_headline"), sections.get("part1_points")
        if not isinstance(headline, str) or not isinstance(points, str) or _is_fixed_post(headline, points):
            continue
        # 過去の見出しには、v1.91より前の指示で付いたハッシュタグ（「 #BTC #ETH」）が残っている。
        # モデルが前日以前の見出しの形を真似てタグを付けないよう、payloadからはタグを除く。
        result.append({"date": d, "part1_headline": _strip_hashtags(headline),
                       # v1.102: 先頭の行頭記号（「・」「・・」等）と空白も除く（モデルが入力の「・」を真似て出力に付けないように）
                       "part1_points": [x for x in (normalize_item_head(_strip_hashtags(ln)) for ln in points.split("\n"))
                                        if x.strip()]})
        if len(result) >= PREVIOUS_POSTS_MAX:
            break
    return result


def _reusable_distinctive_tokens(text: str) -> set[str]:
    text = re.sub(r"（[^（）]*）", "", str(text or ""))  # （媒体名、日付）は照合に使わない
    return {m.group(0).lower() for m in _REUSABLE_TOKEN_RE.finditer(text)
            if m.group(0).lower() not in _REUSABLE_NON_DISTINCTIVE}


def _reusable_grounded_in(text: str, body: str) -> list[str]:
    """textの特徴語のうち、bodyに含まれるもの（共通語）。2語以上、または7文字以上の1語があれば
    「その投稿本文と同じ題材」とみなす（呼び出し元の判定）。"""
    body_l = body.lower()
    return sorted(t for t in _reusable_distinctive_tokens(text) if t in body_l)


def _normalize_reusable_for_summary(raw: Any, previous_posts: list[dict] | None,
                                    id_to_candidate: dict[int, dict] | None = None,
                                    decisions: dict[int, str] | None = None) -> tuple[list[str], list[dict]]:
    """reusable_for_summaryを検証し、(保持するtextのリスト, 除外した項目の記録) を返す（v1.92・R2）。
    例外は送出しない（形式不正の項目は除外として記録する。試行のやり直しを起こさない）。"""
    prev_by_date = {p["date"]: p for p in (previous_posts or [])}
    id_to_candidate = id_to_candidate or {}
    decisions = decisions or {}
    items = raw if isinstance(raw, list) else []
    kept: list[str] = []
    dropped: list[dict] = []

    def drop(item: Any, reason: str) -> None:
        text = item.get("text") if isinstance(item, dict) else item
        dropped.append({"text": str(text or ""), "reason": reason})

    for item in items:
        if not isinstance(item, dict):
            drop(item, "形式不正（文字列。carried_fromが無く、前日以前の投稿で扱った材料と確認できない）")
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            drop(item, "形式不正（textが空）")
            continue
        carried = item.get("carried_from")
        if not isinstance(carried, str) or carried not in prev_by_date:
            drop(item, f"carried_from（{carried!r}）が、渡した前日以前の投稿の日付"
                       f"（{'・'.join(sorted(prev_by_date)) or 'なし'}）に無い")
            continue
        body = prev_by_date[carried]["part1_headline"] + "\n" + "\n".join(prev_by_date[carried]["part1_points"])
        shared = _reusable_grounded_in(text, body)
        if not (len(shared) >= 2 or any(len(t) >= 7 for t in shared)):
            drop(item, f"{carried}の投稿本文と対応する語が見つからない（当日初出の材料の可能性。共通語: {shared or 'なし'}）")
            continue
        cids = item.get("candidate_ids")
        if isinstance(cids, int) and not isinstance(cids, bool):
            cids = [cids]  # 数値1つで書かれた場合も候補IDとして扱う（tier4・採用済みの判定を飛ばさない）
        cids = [c for c in cids if isinstance(c, int) and not isinstance(c, bool)] if isinstance(cids, list) else []
        if any(id_to_candidate.get(c, {}).get("tier") == 4 for c in cids):
            drop(item, "tier4（候補発見のみ）の候補を含む（tier4は本文・総括のどこにも書かない）")
            continue
        if any(str(decisions.get(c, "")).startswith("採用") for c in cids):
            drop(item, "当日の候補で採用済みの材料を含む（採用した材料は主要なポイントへ載せる）")
            continue
        if len(kept) >= REUSABLE_MAX_ITEMS:
            drop(item, f"上限{REUSABLE_MAX_ITEMS}件を超過")
            continue
        kept.append(text.strip())
    return kept, dropped


def _describe_pair_reason(r: dict) -> str:
    """相方不成立の理由1件（_explain_unresolvedのreasons要素）を、リトライ指示用の1文にする（v1.96）。
    タイトルの重なり係数が閾値に届かなかった場合は、その係数と閾値を明記する。"""
    code = r.get("code") or "no_claim"
    label = PAIR_REJECT_REASON_LABELS.get(code, str(code))
    if code == "overlap_below_threshold" and r.get("overlap") is not None:
        label = f"タイトルの重なり係数{r['overlap']:.2f}が閾値{r.get('threshold')}に届かない"
    other = ""
    if r.get("other_id") is not None:
        other = f"ID{r['other_id']}（{r.get('other_source', '')}「{str(r.get('other_title', ''))[:60]}」）"
    if r.get("role") == "incoming_claim":
        return f"{other}からの申告: {label}"
    if code == "no_claim":
        return f"自身の申告: {label}"
    return f"自身の申告→{other}: {label}"


def _build_call_a_retry_note(exc: Exception) -> str | None:
    """call_a()のbuild_retry_note（v1.66・オーナー承認）。
    AuditLedgerReconstructionError（tier3の独立2ソースペア申告が
    _validate_pair_claim()の条件を満たさない場合に送出。エラーメッセージ
    自体が該当する候補IDを機械的に列挙している）に限り、次の試行への
    修正指示を生成する。それ以外の例外（JSON不正・必須キー欠落・refusal等）
    はcandidate_idに紐づく情報を持たず本文脈での修正指示を書けないため
    Noneを返し、user_contentは無変更のまま再送する（既存の挙動を維持）。

    文言は「名指しされた候補IDについてのみ」「名指しされていない他の候補は
    変更しない」を明示し、「疑わしければ全て落とす」という広範な誤読を
    防ぐことを狙う（オーナー指示。実装時の確認事項）。
    """
    if not isinstance(exc, AuditLedgerReconstructionError):
        return None
    detail_lines = ""
    details = getattr(exc, "unresolved_details", None) or []
    if details:
        # v1.96（オーナー承認）: 成立しなかった理由（重なり係数・閾値を含む）を伝える。
        # 閾値そのものはconfig/pair_overlap.jsonの値（据え置き）で、変更はしない。
        detail_lines = (
            "システムが判定した、相方が成立しなかった理由は次のとおりです（重なり係数は、2つのタイトルの"
            "英数字の語の重なり＝共通語数÷語数の少ない方、です。閾値以上でないと同じニュースでも"
            "独立2ソースとして成立しません）:\n"
            + "\n".join(
                f"- 候補ID{d['candidate_id']}（{d.get('source', '')}「{str(d.get('title', ''))[:60]}」）: "
                + "／".join(_describe_pair_reason(r) for r in d.get("reasons", []))
                for d in details)
            + "\n\n")
    return (
        "### 直前の試行への修正指示（自動リトライ）\n\n"
        f"直前の試行は次のエラーで失敗しました: {exc}\n\n"
        f"{detail_lines}"
        "このエラーで名指しされた候補IDについてのみ、pairs_with_candidate_idが"
        "「独立2ソース規定」の条件（相手もtier3・use:true・情報源が異なる・"
        "タイトルの内容が十分類似）を満たすか再確認してください。満たす場合は"
        "pairs_with_candidate_idを正しい相方の候補IDへ修正し、相方がuse:falseに"
        "なっているときは相方もuse:trueに変更してください（同一事実を報じた独立2ソースは、"
        "両方をuse:trueにして成立します。相方をuse:trueにする修正は、名指しされた候補の相方に限って"
        "かまいません）。満たさない場合は"
        "その候補のuseをfalseに変更してください。名指しされていない他の候補（上記の相方を除く）の"
        "use・pairs_with_candidate_idは変更しないでください。"
    )


def call_a(client: "anthropic.Anthropic", daily_data: dict, news_today: dict,
           news_yesterday: dict | None, pair_overlap_threshold: float | None = None,
           previous_posts: list[dict] | None = None) -> CallOutcome:
    """pair_overlap_threshold省略時はconfig/pair_overlap.jsonから読む。run()は
    news_candidate_count集計用の候補選定（下記）とここで同一の値を使う必要が
    あるため、run()側で読み込んだ値を明示的に渡す（v1.53フォローアップ・
    二重読み込みによる値のズレを防ぐ）。
    """
    if pair_overlap_threshold is None:
        pair_overlap_threshold = load_pair_overlap_threshold()
    user_content, truncation_stats, id_to_candidate = _build_call_a_user_content(
        daily_data, news_today, news_yesterday, pair_overlap_threshold, previous_posts)

    audit_ledger_stats: dict[str, int] = {}
    # v1.79（オーナー承認）: rejected_pairs_stats・force_dropped_statsは
    # audit_ledger_statsと同じ「試行ごとにリセットし、最終的に成功した
    # （＝outcomeを生んだ）試行の値だけが残る」規約に従うミュータブルな
    # 蓄積先。post_processは_call_json()内で試行ごとに呼ばれるため、
    # 各試行の開始時にclear()し、失敗した試行分の値が混入しないようにする。
    rejected_pairs_stats: list[dict] = []
    force_dropped_stats: list[dict] = []
    # v1.86（オーナー承認・案G）: 上の2つと異なり試行をまたいで蓄積する（1・2試行目の
    # 「相方が成立しなかった候補と理由」を、最終的な成否によらず残すため）。
    attempt_diagnostics: list[dict] = []
    # v1.92: reusable_for_summaryの機械フィルタ（R2）で除外した項目（試行ごとにリセット）
    reusable_dropped_stats: list[dict] = []
    decisions_by_id: dict[int, str] = {}
    # v1.97: 候補IDごとの採否・理由（試行ごとにリセット。最終的に成功した試行の値だけが残る）
    candidate_decisions_stats: dict[int, dict] = {}
    # v1.102: 項目の先頭の記号・空白の整形の記録（試行ごとにリセット）
    format_norm_stats: dict[str, Any] = {}

    def _rebuild_audit_ledger(data: dict, attempt: int) -> dict:
        rejected_pairs_stats.clear()
        force_dropped_stats.clear()
        reusable_dropped_stats.clear()
        candidate_decisions_stats.clear()
        format_norm_stats.clear()
        # v1.102（オーナー承認）: 主要なポイントの項目の先頭の記号・空白を、受け取った直後に整形する
        # （以降の監査・呼び出しBの入力・描画がすべて整形後の項目を使う）。整形前は診断用に残す。
        try:
            raw_points = list(data.get("part1_points")) if isinstance(data.get("part1_points"), list) else None
            data["part1_points"], n_changed = normalize_items(data.get("part1_points"))
            if raw_points is not None:
                format_norm_stats.update(part1_points_raw=raw_points, part1_points_changed=n_changed)
        except Exception:  # noqa: BLE001 — 整形の失敗で試行（リトライ・採否）を変えない
            format_norm_stats.clear()
        llm_entries = data.get("audit_ledger")
        # v1.79（オーナー承認）: 最終試行でも独立2ソースの相方が解消しない
        # tier3候補は、従来はAuditLedgerReconstructionErrorで例外化し
        # MAX_ATTEMPTS回リトライしてもなお解消しない場合そのままcall_a失敗
        # （縮退L1）としていた。最終試行（attempt==MAX_ATTEMPTS）に限り、
        # 例外化する代わりに強制的に不採用へ変更して続行する——呼び出し元
        # （compose_post.py）がこの後C12〜C24を再監査し、なお失敗する場合は
        # 従来どおりのL1へフォールバックする（_derive_decisionsのdocstring
        # 参照）。
        force_drop = attempt >= MAX_ATTEMPTS
        diag: dict = {}
        try:
            data["audit_ledger"] = _reconstruct_audit_ledger(
                data.get("audit_ledger"), id_to_candidate, pair_overlap_threshold, audit_ledger_stats,
                rejected_pairs=rejected_pairs_stats, force_drop_unresolved=force_drop,
                force_dropped=force_dropped_stats, diagnostics=diag, decisions_out=decisions_by_id)
        finally:
            if diag.get("unresolved"):
                attempt_diagnostics.append({
                    "attempt": attempt, "force_drop": force_drop, "unresolved": diag["unresolved"],
                    "rejected_pairs": list(rejected_pairs_stats)})
        # v1.97: 再構成が成功した（＝上のtryが例外にならなかった）場合だけ、候補IDごとの採否・理由を残す。
        # 再構成の成功時、llm_entriesは「全要素がdictで、candidate_idが過不足なく一致」と検証済み。
        try:
            forced_ids = {d.get("candidate_id") for d in force_dropped_stats}
            for e in llm_entries:
                cid = e["candidate_id"]
                candidate_decisions_stats[cid] = {
                    "decision": decisions_by_id.get(cid), "use": bool(e.get("use")),
                    "reason": str(e.get("reason", ""))}
                if cid in forced_ids:
                    candidate_decisions_stats[cid]["force_dropped"] = True  # 最終試行でも相方が成立せず強制的に不採用にした
        except Exception:  # noqa: BLE001 — 記録の失敗で試行（リトライ・採否）を変えない
            candidate_decisions_stats.clear()
        # v1.92（オーナー承認・R2）: reusable_for_summaryを機械フィルタにかけ、前日以前の投稿本文で
        # 扱った材料だけを文字列のリストとして残す（以降のcall_B・bundle・C23は従来どおり文字列を扱う）。
        try:
            data["reusable_for_summary"], dropped = _normalize_reusable_for_summary(
                data.get("reusable_for_summary"), previous_posts, id_to_candidate, decisions_by_id)
        except Exception as e:  # noqa: BLE001 — 想定外の入力でも試行を失敗させない（総括の1行言及が出ない側＝安全側に倒す）
            data["reusable_for_summary"], dropped = [], [
                {"text": "", "reason": f"機械フィルタが例外で失敗したため全件除外（{type(e).__name__}: {e}）"}]
        reusable_dropped_stats.extend(dropped)
        return data

    outcome = _call_json(
        client, system=SYSTEM_A, user_content=user_content,
        max_tokens=CALL_A_MAX_TOKENS, required_keys=REQUIRED_KEYS_A,
        post_process=_rebuild_audit_ledger,
        build_retry_note=_build_call_a_retry_note,
    )
    outcome.truncation_stats = truncation_stats
    # v1.54フォローアップ: post_processは_call_json()内で試行ごとに呼ばれるため、
    # audit_ledger_statsは最終的に成功した（＝outcomeを生んだ）試行の値で
    # 上書きされている。失敗した試行分の値が混入することはない。
    outcome.audit_ledger_auto_filled_count = audit_ledger_stats.get("audit_ledger_auto_filled_count", 0)
    outcome.rejected_pairs = list(rejected_pairs_stats)
    outcome.force_dropped_candidates = list(force_dropped_stats)
    outcome.attempt_diagnostics = list(attempt_diagnostics)
    outcome.reusable_dropped = list(reusable_dropped_stats)
    outcome.candidate_decisions = dict(candidate_decisions_stats)
    outcome.format_normalization = dict(format_norm_stats)
    return outcome


def regenerate_call_b_as_l1(daily_data: dict, client: "anthropic.Anthropic | None" = None) -> CallOutcome:
    """v1.79（オーナー承認）: force_drop_unresolvedで続行した呼び出しAの結果を
    使って合成した本文が、除外後の再監査（C12〜C24）でもFAILする場合、
    呼び出し元（compose_post.py）が呼び出しAを失敗扱いへ差し戻し、本関数で
    呼び出しBを news_from_call_a=None で生成し直す（＝従来のL1と同じ状態に
    戻す）。呼び出しBは元々「Aが失敗している場合はニュースが空で渡される」
    前提でプロンプト設計されているため（CALL_B_INSTRUCTIONS参照）、
    call_b()をそのまま再利用できる。
    """
    return call_b(client or anthropic.Anthropic(), daily_data, None)


# v1.101（オーナー承認）: 【市場のフロー】の書式のWARN（verify_post.find_flow_format_violations）が出たとき、
# call_Bを1回だけ再生成する。10/2・10/3・10/5と、材料のあるL0の日でWARNが続いたため。
# 再生成の要否判定・採用の判断・STATUSへの記録はcompose_post.pyが行い、ここは再生成の呼び出しだけを担う
# （regenerate_call_b_as_l1と同じ位置づけ）。再生成しても書式が直らない場合は元の版のまま出力する（WARNのまま）。
def _build_flow_regen_note(previous_flow: list, violations: list[dict], previous_summary: str = "") -> str:
    """直前のpart2_flowと、機械チェックが検出した違反を伝え、書式だけを直させる追記テキスト。"""
    import verify_post  # 循環importを避けるため遅延（verify_postはこのモジュールをimportする）
    lines = []
    for v in violations:
        labels = "・".join(verify_post.FLOW_FORMAT_REASON_LABELS.get(c, c) for c in v.get("reasons", []))
        lines.append(f"- {v.get('chain_no')}本目: 「{v.get('text', '')}」 → 検出された違反: {labels}")
    return (
        "### 直前の生成への修正指示（自動再生成・v1.101）\n\n"
        "直前の生成の【市場のフロー】は、統合運用基準§3.3の書式から外れていると機械チェックが検出しました。\n"
        "検出された連鎖と違反:\n" + "\n".join(lines) + "\n\n"
        "part2_flowとpart2_summaryを、次の点だけを直して出力し直してください。\n"
        "- 取り上げる材料・事実・媒体名・限定表現の趣旨は変えない（呼び出しAのpart1に掲載済みの材料だけを使う）。\n"
        "- 各連鎖は、必ず先頭を「【出来事・ニュース】」のラベルで書き始める（①②③を付ける場合は「①【出来事・ニュース】…」）。"
        "「→」の直後は必ずラベル。ラベルの語は一字一句そのまま。\n"
        "- ラベルの使い分けは上記の指示のとおり（【地政学・マクロの変化】はマクロの変化に限る。制度・政策や企業財務・市場構造の"
        "材料にはこのラベルを使わず、根拠のない段階は書かない）。\n"
        "- 1連鎖は1文（句点は末尾に1つだけ）。ハッシュタグは句点の後。末尾に「可能性」「因果は未確認」等の限定を置く。\n"
        "- part2_summaryは、直前の文をそのまま出力する（システムは元の総括を使うため、変えない）。\n\n"
        "直前のpart2_flow:\n" + json.dumps(previous_flow, ensure_ascii=False, indent=2)
        + "\n\n直前のpart2_summary:\n" + json.dumps(str(previous_summary or ""), ensure_ascii=False)
    )


def regenerate_call_b_for_flow_format(daily_data: dict, call_a_data: dict | None, previous_flow: list,
                                       violations: list[dict], previous_summary: str = "",
                                       client: "anthropic.Anthropic | None" = None) -> CallOutcome:
    """フロー書式のWARNが出たときの、呼び出しBの1回だけの再生成（v1.101）。通常のuser_contentに、
    直前の連鎖と検出された違反を伝える追記を付けて送る。JSON不正等の技術的な失敗は_call_json()が従来どおり
    再試行する（再生成の「1回」は、書式を直すためのやり直しの回数）。"""
    client = client or anthropic.Anthropic()
    user_content = _build_call_b_user_content(daily_data, call_a_data) + "\n\n" + _build_flow_regen_note(
        previous_flow, violations, previous_summary)
    has_material = _has_adopted_material(call_a_data)
    format_norm_stats: dict[str, Any] = {}

    def _enforce_fixed_flow(data: dict, attempt: int) -> dict:
        if not has_material:
            data["part2_flow"] = [FIXED_FLOW]
        _normalize_flow_items(data, format_norm_stats)  # v1.102
        return data

    outcome = _call_json(client, system=SYSTEM_B, user_content=user_content, max_tokens=CALL_B_MAX_TOKENS,
                         required_keys=REQUIRED_KEYS_B, post_process=_enforce_fixed_flow)
    outcome.format_normalization = dict(format_norm_stats)
    return outcome


def _has_adopted_material(call_a_data: dict | None) -> bool:
    """呼び出しAの出力に、採用された材料（定型文以外のpart1_headline、または
    定型文以外のpart1_points）があるかを返す。呼び出しA失敗（None）は材料なし。
    """
    if not call_a_data:
        return False
    headline = call_a_data.get("part1_headline")
    if isinstance(headline, str) and headline.strip() and headline.strip() != FIXED_HEADLINE:
        return True
    points = call_a_data.get("part1_points") or []
    # v1.102: 先頭の行頭記号・空白を除いて比べる（「・補足できる検証済み材料は確認できない。」を材料ありと誤判定しない）
    return any(isinstance(p, str) and normalize_item_head(p).strip()
               and normalize_item_head(p).strip() != FIXED_POINTS for p in points)


def _normalize_flow_items(data: dict, stats: dict[str, Any]) -> None:
    """v1.102: part2_flowの連鎖の先頭の記号・空白を整形し、整形前と件数をstatsへ記録する（試行ごとに上書き）。
    ①②③で始まる連鎖は、先頭の「・」を除くと①②③が先頭になる（描画で「・」を付けない）。"""
    stats.clear()
    try:
        raw = list(data.get("part2_flow")) if isinstance(data.get("part2_flow"), list) else None
        data["part2_flow"], n_changed = normalize_items(data.get("part2_flow"))
        if raw is not None:
            stats.update(part2_flow_raw=raw, part2_flow_changed=n_changed)
    except Exception:  # noqa: BLE001 — 整形の失敗で試行を変えない
        stats.clear()


def call_b(client: "anthropic.Anthropic", daily_data: dict, call_a_data: dict | None) -> CallOutcome:
    user_content = _build_call_b_user_content(daily_data, call_a_data)
    has_material = _has_adopted_material(call_a_data)
    format_norm_stats: dict[str, Any] = {}

    def _enforce_fixed_flow(data: dict, attempt: int) -> dict:
        # v1.82（オーナー承認）: 材料が無い日（呼び出しA失敗を含む）の
        # part2_flowは、統合運用基準§3.1の定型文とし、市場データから流れを
        # 作文しない。CALL_B_INSTRUCTIONSにも同じ指示を書いているが、指示は
        # 常に遵守されるとは限らない（C26等の既往事象）ため、コード側でも
        # 確定させる——プロンプトの遵守状況に依存しない。
        if not has_material:
            data["part2_flow"] = [FIXED_FLOW]
        _normalize_flow_items(data, format_norm_stats)  # v1.102
        return data

    outcome = _call_json(
        client, system=SYSTEM_B, user_content=user_content,
        max_tokens=CALL_B_MAX_TOKENS, required_keys=REQUIRED_KEYS_B,
        post_process=_enforce_fixed_flow,
    )
    outcome.format_normalization = dict(format_norm_stats)
    return outcome


# v1.76（オーナー承認・2026-09-16）: C18（断定表現）局所修正用の呼び出し
# （repair_post.pyから呼ばれる。「呼び出しR」）。9/9・9/11・9/15の3日分の
# 監査FAILが全てC18のみに起因していたこと（DESIGN_CHANGES.md v1.75）を受け、
# 違反文1文だけを渡し、事実関係を変えずに限定表現を含む形へ書き直させる。
# verify_post.py自体はLLM非依存の「純粋な機械監査」のまま変更しないため、
# 本呼び出しはverify_post.pyとは独立にrepair_post.py側だけが使う。
CALL_R_MAX_TOKENS = 500
REQUIRED_KEYS_R = ["rewritten_sentence"]

REPAIR_SYSTEM_TEMPLATE = """あなたは暗号通貨市況レポートの校正者です。

以下に渡す1文について、事実関係（数値・銘柄名・固有名詞・方向性・述べられて
いる因果関係の内容そのもの）を一切変えずに、限定表現を含む形へ書き直して
ください。

限定表現の候補（このいずれかを文中に含めること。文末に置くのが自然です）:
{limiting_expressions}

制約:
- 元の文が述べている事実・数値・銘柄名・固有名詞は削除・変更しないこと。
- 元の文にない新しい事実を付け加えないこと。
- 文を分割せず、1文のまま書き直すこと。
- 渡される文は文末の句点（。）を含まない形になっています。書き直した文にも
  句点（。）を含めないでください（後続処理で句点を補います）。
- 出力は書き直した文1文のみとし、前後に説明・引用符・箇条書き記号を付けないこと。

出力形式（JSONのみ）:
{{"rewritten_sentence": "書き直した文（句点なし）"}}"""


def call_r(client: "anthropic.Anthropic", sentence: str, limiting_expressions: list[str]) -> CallOutcome:
    """C18違反文1文の局所修正。verify_post.LIMITING_EXPRESSIONSをそのまま
    候補として渡すことで、判定基準と修正指示を常に一致させる
    （判定基準側を変更しても修正指示が自動的に追随する設計）。
    """
    system = REPAIR_SYSTEM_TEMPLATE.format(limiting_expressions="、".join(limiting_expressions))
    return _call_json(
        client, system=system, user_content=sentence,
        max_tokens=CALL_R_MAX_TOKENS, required_keys=REQUIRED_KEYS_R,
    )


def _load_json_or(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return default


def run(target_date: str, *, client: "anthropic.Anthropic | None" = None) -> dict[str, Any]:
    """呼び出しA・Bを実行し、結果と縮退レベルをまとめて返す。

    daily_data.json の存在は呼び出し元が保証すること（L3判定はcompose_post.py側）。
    news_candidates.json（当日・前日）は欠損・不正でも空扱いとし、本関数は失敗しない。
    """
    if client is None:
        client = anthropic.Anthropic()

    daily_data = json.loads(Path(f"outputs/{target_date}/daily_data.json").read_text(encoding="utf-8"))

    news_today = _load_json_or(Path(f"outputs/{target_date}/news_candidates.json"),
                                default={"candidates": [], "source_status": {}})
    prev_date = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    news_yesterday = _load_json_or(Path(f"outputs/{prev_date}/news_candidates.json"), default=None)

    pair_overlap_threshold = load_pair_overlap_threshold()
    previous_posts = _load_previous_posts(target_date)  # v1.92: 前日以前の投稿本文（コミット済みのdraft/）
    a = call_a(client, daily_data, news_today, news_yesterday, pair_overlap_threshold, previous_posts)
    b = call_b(client, daily_data, a.data if a.ok else None)

    failed_count = (0 if a.ok else 1) + (0 if b.ok else 1)
    level = {0: "L0", 1: "L1", 2: "L2"}[failed_count]

    # C19（v1.21改定）: 「渡した候補数」を基準にする（取得総数ではない）。
    # tier3を件数上限で絞るため、取得総数のままだと絞り込み後にAが実際に
    # 見た候補数とaudit_ledgerの記録件数が原理的に一致しなくなる
    # （オーナー指示・DESIGN_CHANGES.md v1.21参照）。call_a()内部の選定と
    # 同じpair_overlap_thresholdを使うこと（v1.53フォローアップ）——
    # 閾値をconfigで変更した際、ここだけデフォルト値のままだとペア救済の
    # 件数がcall_a()の実際の選定とズレ、news_candidate_countがaudit_ledger
    # の実件数と一致しなくなりC19が誤って発火しうる。
    selected_today, _ = _select_candidates_for_call_a(news_today.get("candidates", []), pair_overlap_threshold)

    # v1.97（オーナー承認・案1）: 全候補の選定状態と呼び出しAの採否の記録（記録のみ。例外でも本文生成は続行）。
    try:
        candidate_selection = build_candidate_selection_report(
            target_date, news_today, pair_overlap_threshold,
            decisions=a.candidate_decisions if a.ok else None)
    except Exception as e:  # noqa: BLE001 — 記録の失敗で本文生成を止めない
        candidate_selection = {"error": f"{type(e).__name__}: {e}"}

    return {
        "target_date_jst": target_date,
        "level": level,
        "call_a": a.to_dict(),
        "call_b": b.to_dict(),
        "news_source_status": news_today.get("source_status", {}),
        "news_candidate_count": len(selected_today),
        "candidate_selection": candidate_selection,
        "previous_posts_dates": [p["date"] for p in previous_posts],
        "total_usage": _add_usage(a.usage, b.usage),
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: generate_post.py <対象日 YYYY-MM-DD>", file=sys.stderr)
        return 1
    target_date = sys.argv[1]
    result = run(target_date)

    out_dir = Path(f"outputs/{target_date}/draft")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "post_generation.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    a_status = "OK" if result["call_a"]["ok"] else f"FAILED（{result['call_a']['error']}）"
    b_status = "OK" if result["call_b"]["ok"] else f"FAILED（{result['call_b']['error']}）"
    u = result["total_usage"]
    print(f"OK: {out_path}（level={result['level']}, call_A={a_status}, call_B={b_status}）")
    print(f"トークン使用量（実消費量）: input={u['input_tokens']}, output={u['output_tokens']} "
          f"（call_A: in={result['call_a']['usage']['input_tokens']} out={result['call_a']['usage']['output_tokens']} / "
          f"call_B: in={result['call_b']['usage']['input_tokens']} out={result['call_b']['usage']['output_tokens']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
