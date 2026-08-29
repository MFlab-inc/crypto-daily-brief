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

import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import anthropic

import collect_news

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

# v1.39フォローアップ（オーナー承認）: 「公開日時の新しい順で上位N件」という
# 選定方式は、収集ウィンドウ序盤に出た記事を窓終盤の記事群に押しやる構造的な
# 時間帯バイアスを持つ（実データ: 8/25のBTC $80,000到達＝3か月ぶり高値を
# 報じたCoinDesk記事2本が、公開時刻が早いという理由だけで44件中24位・43位
# となりLIMIT=15後も候補集合から漏れていた）。件数上限の引き上げでは
# 解決しないため、独立2媒体が同一事実を報じているペアは、順位に関わらず
# 両方を候補集合へ残す（ペア救済）。救済はTIER3_CANDIDATE_LIMIT件の
# 上限外で加算する（当初オーナー案の「上限を超えても両方残す」を反映）。
PAIR_OVERLAP_THRESHOLD = 0.4  # タイトルのトークン重なり係数（overlap coefficient）の閾値。
# 8/24のCoinbase/Baseトークン化株式ペア（既知の独立2ソース成功例）で0.45と
# 実測し較正した値（DESIGN_CHANGES.md v1.39参照。較正基盤は1件のみで薄い）。
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


def _tokenize_title(title: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(title).lower()))


def _overlap_coefficient(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _find_independent_pairs(tier3_sorted: list[dict]) -> list[tuple[dict, dict]]:
    """独立2媒体が同一事実を報じているとみられるペアを検出する（v1.39
    フォローアップ）。タイトルのトークン重なり係数がPAIR_OVERLAP_THRESHOLD
    以上、かつsourceが異なる組み合わせをペアとみなす。1記事が複数ペアへ
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
            if sim >= PAIR_OVERLAP_THRESHOLD:
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
6. 投資判断の推奨・勧誘・断定的判断の提供を行わない。"""

RULES_HASHTAG = """## ハッシュタグ規則（X投稿本文のみ）

- `#` は行頭または半角スペースの直後にのみ置く。
- `#` の直後に日本語を続けない（`#ETH偏り` は不可）。`：`・半角スペース・
  数値・行末のいずれかで終端する位置にのみ置く。
- 複合語の中では `#` を付けず平文にする（「ETH偏り」「USDCドミナンス」）。
- 使用するタグは `#BTC` `#ETH` `#BNB` および必要時の `#USDC` に限る。
- **タグを連続して並べるときの区切りは半角スペースのみとする。**
  中黒（`・`）やスラッシュ（`/`）で区切らない。
  可: `#BTC #ETH` / 不可: `#BTC・#ETH`、`#ETH/#USDC`
- `ETH/USDC` のようなペア表記にはタグを使わず平文で書く。
- `headline_for_image` には `#` を一切使わない。"""

INTRADAY_MOVE_GUIDANCE = """## 24時間の値動き（notable_move）

入力の intraday_range に notable_move: true の銘柄がある場合、
その24時間の値動きは記述に値する材料である（データはNY 17:00区切りの
24時間窓で集計しており、暦日の「日中」ではない。v1.49・オーナー指示）。
ただし具体的な数値は後段のテンプレートが差し込むため、
あなたは数値を書かないこと。「一時的に上昇したのち上げ幅を縮小した」の
ような、値動きの形状のみを記述する。"""

# v1.53（オーナー指示）: CPI・PCE・FOMC・要人講演等、その日最大の材料を
# 繰り返し取りこぼした事象（8/22カナダ関税・8/26 PCE・8/28ジャクソンホール
# 講演）への対応。scheduled_eventsは「探すべき材料」のヒントに過ぎず、
# それ自体を本文の根拠にしてはならない——対応するRSS候補が無ければ何も
# 書かない（未確認の事項を推測で補わないという絶対規則5と同じ考え方）。
SCHEDULED_EVENTS_GUIDANCE = """## 経済カレンダー（scheduled_events）

入力の daily_data.scheduled_events は対象日に予定されていた経済イベント
です。これらは「探すべき材料」のヒントであり、それ自体を材料として本文に
書いてはいけません。対応するRSS候補が存在する場合に限り、通常の採否判定
（tier1の裏付け、または独立2ソース）を経て本文へ反映してください。
予定はあったが候補が無い場合は、その旨を書かず、単に掲載しないでください。"""

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
tier 3: CoinDesk・Cointelegraph等の暗号通貨特化メディアRSS。統合運用基準の
        位置づけどおり「補完・裏取り」に用い、単独の主根拠にはしない。
        tier 1のsummaryで確認できた事実を補強する（同一材料が独立して
        報じられていることを示す）用途、またはtier 1のsummaryに無い
        暗号通貨特有の細部を補う用途に限る。tier 3の候補のみを根拠に
        【ヘッドライン】の新規項目を立てない。【主要なポイント】については
        下記「独立2ソース規定」の例外を除き、同様に単独では根拠にしない。
tier 4: Google News経由の候補発見のみの結果（見出し・URLのみで、内容の
        裏取りをしていない）。単独では事実の根拠にしない。継続監視の
        対象として reusable_for_summary に記すにとどめ、【ヘッドライン】
        【主要なポイント】の記述根拠には使わない。

### 情報源規律と項目数の優先順位（v1.29・オーナー指示）

情報源の規律は項目数より優先する。tier1（または下記「独立2ソース規定」に
該当するtier3）の裏付けがある材料が1件しかなければpart1_pointsは1項目、
0件なら0項目とし、下記「候補が無い場合の扱い」の定型文を使うこと。
項目数を満たすためにtier3単独ソースを採用してはならない。0項目
（定型文のみ）は失敗ではなく、統合運用基準§3.1が定める正しい結果である
（「根拠が少ない日は数を埋めず、確認できる材料と限界を明記する」）。

- 掲載する事実はtier 1のsummaryに記載されている内容、または下記
  「独立2ソース規定」に該当するtier 3の事実報道に限る。tier 3は
  原則としてtier 1の事実を補強する裏取りとしてのみ併記してよく、
  tier 3単独を新規項目の根拠にしない。

### 独立2ソース規定（v1.28・統合運用基準の既定を実装へ反映）

tier3のみで報じられた材料であっても、次の3条件をすべて満たす場合は
【主要なポイント】への掲載を許可する。
 (a) 2つ以上の独立したtier3媒体が同一の事実を報じている
 (b) 意見・予想・分析ではなく、事実の報道である
     （発表、認可、取得、提携、施行など）
 (c) 掲載時に媒体名を複数列挙し、一次情報での裏付けが未確認である旨を
     明記する
上記に該当しない場合は従来どおりtier1の裏付けを必要とする。
この規定で採用した候補は、audit_ledgerのdecisionを
"採用（独立2ソース）" と記録する（"採用"や"不採用"と区別する）。
part1_headlineでの扱いは下記「part1_headline・part1_pointsの決定」を
参照。

### ヘッドラインの判定手順（v1.44改定・下記へ委譲）

part1_headline・headline_for_imageの決定手順は下記
「part1_headline・part1_pointsの決定」の①〜④を参照。
- 数値・固有名詞・日時はsummary・titleの記載と一致させる。候補に無い情報を
  推測で補わない（確認できないものは掲載しない）。
- news_candidates_yesterday に同一の法案・政策・企業動向の候補が含まれる
  場合、summaryの内容が前日から更新されているときのみ【ヘッドライン】
  【主要なポイント】へ再掲載する。更新がなければ、その旨を
  reusable_for_summary に記し、本文には書かない。
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
NO_CANDIDATES_FALLBACK = f"""## part1_headline・part1_pointsの決定（v1.44・オーナー指示）

part1_headline および part1_points は、次の3つを独立に確認して
決定する。
(i)   tier1の裏付けがある採用材料（decision:"採用"）があるか
(ii)  独立2ソース材料（decision:"採用（独立2ソース）"）があるか
(iii) 入力の intraday_range に notable_move: true の銘柄があるか

定型文を使うのは、(i)(ii)(iii)のすべてが「なし」の場合に限る。
いずれか1つでも「あり」なら、定型文を使わずその材料・値動きに基づく
記述を行う。③と④を取り違えないこと。定型文を使うのは④の場合のみである。

優先順位（複数が「あり」の場合、ヘッドラインで何を主とするかを決める）：

① (i)あり → tier1裏付けの材料をヘッドラインの主とする。(ii)・(iii)も
   あれば、重要度の高い方を主、他方を従として併記してよい。
② (i)なし・(ii)あり → 独立2ソース材料をヘッドラインの主とする。
   (iii)もあれば値動きを従として併記してよい。
③ (i)なし・(ii)なし・(iii)あり → 値動きを記述する。定型文は使わない。
   ただし、ニュース材料が確認できなかった旨は主要なポイントに
   1項目として明記する。
④ (i)なし・(ii)なし・(iii)なし → 統合運用基準§3.1の定型文を使う。

①〜④は本文の構成方針を表す優先順位であり、下記audit_ledgerの
reasonで使うA/B/C——個々の候補材料の重要性判定（「重要性判定と
因果表現の分離」参照）——とは別の分類である。混同しないこと。

### ②（(i)なし・(ii)あり）の詳細

独立2ソース材料の内容に基づき、part1_headlineに実文言を書く。
tier1裏付けが無いため、上記「独立2ソース規定」の(c)と同様に、
一次情報での確認ができていない旨を明記する。headline_for_imageも
同様にこの材料の内容を反映してよい。

### ③（(i)なし・(ii)なし・(iii)あり）の詳細

上記「24時間の値動き（notable_move）」の指示に従い、値動きの形状のみを
記述する（数値は書かない・後段のテンプレートが差し込む）。
part1_headlineはこの値動きの記述とし、下記④用の定型文は使わない。
part1_pointsには、値動きの記述に加え「ニュース材料は確認できなかった」
旨を1項目として明記する。

### ④（(i)なし・(ii)なし・(iii)なし）の詳細

- part1_headline: 統合運用基準§3.1の指定文言をそのまま使う（言い換えない）:
  「{FIXED_HEADLINE}」
- part1_points: 同じく指定文言をそのまま使う（項目数は1件でよい）:
  「{FIXED_POINTS}」

### 共通

- headline_for_image: ④の場合（tier1材料・独立2ソース材料・値動きの
  いずれも無い場合）は、daily_data.json内のBTC・ETHのdirection
  （up/down）に基づく短い定性的な見出しにとどめる（例:「BTC・ETHとも
  に上昇基調」）。数値は書かない。`#`は使わず全角40字以内。
- reusable_for_summary: tier 4等の継続監視材料があれば記す。無ければ空配列。

**audit_ledgerは上記と切り離して扱う（統合運用基準・台本の要求）。**
audit_ledgerは「採否を判断した全候補の記録」であり、本文（ヘッドライン・
主要なポイント）に採用したかどうかとは無関係に、news_candidates_today に
渡された候補（tier 1・3・4のすべて）を1件残らず記録する。ヘッドライン・
主要なポイントに使わなかった候補も decision:"不採用" とその理由を記録する。

各要素は candidate_id（news_candidates_today内の該当候補のID）・
decision・verified_by・reason のみを書く（v1.48・オーナー指示）。
source・url・title・published_atは書かない——candidate_idからシステム側が
候補一覧の該当データをそのまま補完するため、あなたが転記する必要は無い
（転記ミスの防止のため）。1件の候補につきcandidate_idはちょうど1回のみ
使う（重複・欠落は不可）。

decision:"不採用" の場合、reasonの冒頭に上記A/B/Cのどの段階と判定したかを
明記する（例:「C: 自動車産業の国内回帰に関する内容で、金利・為替・流動性等
への波及経路を説明できない」「B: 波及経路は説明できるが、内容が薄く参考
材料としても不十分」等）。「暗号通貨価格への直接因果が未確認」であること
のみを理由に不採用としてはならない（上記【厳守】参照）。
decision:"不採用" のreasonは全角60字以内に収める（判定段階＋簡潔な理由の
みでよく、詳細な論述は不要）。decision:"採用"・"採用（独立2ソース）"の
reasonにはこの字数制限を適用しない。
verified_byは採用系decision（"採用"・"採用（独立2ソース）"）の場合のみ
書く（判断に属する情報のため）。不採用の場合は空文字でよい。
audit_ledgerを空配列 [] にしてよいのは、news_candidates_today が
空配列で渡された（候補が1件も無かった）場合のみである。
候補が1件でも渡されている場合、audit_ledgerを空配列で返してはならない。"""

WRITES_A = """## あなたが書くもの

- headline_for_image: 図版下部帯用。`#` を使わず全角40字以内。体言止め可。
  上記「part1_headline・part1_pointsの決定」の①〜④に従う。
- part1_headline: 前編のヘッドライン。2〜3文。当日の最重要材料と価格の方向。
  上記「part1_headline・part1_pointsの決定」の①〜④に従う。
- part1_points: 上限4項目。ヘッドラインと重複しない補足。各項目末尾に
  （媒体名、日付）を付す。項目数は目標ではなく情報源の規律に従った結果
  である——tier1（または独立2ソース規定該当のtier3）の裏付けがある
  材料の件数がそのまま項目数になる（1件なら1項目、0件なら0項目で
  定型文）。項目数を埋めるためにtier3単独ソースを採用しない。
  上記「重要性判定と因果表現の分離」のB（波及経路のあるマクロ・地政学
  材料）を掲載する場合、「暗号通貨価格への直接因果は未確認」等の限定
  表現を項目文に含める——因果が未確認であることは不採用の理由にせず、
  掲載したうえで明記する。
- audit_ledger: 候補一覧（tier 1・3・4のすべて）の採否を判断した記録。
  各要素は candidate_id・decision・verified_by・reason のみを書く
  （source・url・title・published_atは書かない。詳細は上記
  「part1_headline・part1_pointsの決定」内のaudit_ledgerの節を参照）。
- reusable_for_summary: 継続材料で本文に載せなかったものの1行要約（0〜2件）。"""

OUTPUT_FORMAT_A = """## 出力形式

次のJSONのみを出力。前置き・後置き・コードフェンスを付けない。

{
  "headline_for_image": "...",
  "part1_headline": "...",
  "part1_points": ["...", "..."],
  "reusable_for_summary": ["..."],
  "audit_ledger": [
    { "candidate_id": 1, "decision": "採用/採用（独立2ソース）/不採用",
      "verified_by": "", "reason": "" }
  ]
}"""

SYSTEM_A = "\n\n".join([
    ROLE_INTRO, RULES_ABSOLUTE, RULES_HASHTAG, NEWS_SELECTION, NO_CANDIDATES_FALLBACK,
    INTRADAY_MOVE_GUIDANCE, SCHEDULED_EVENTS_GUIDANCE, RULES_CAUSAL, WRITES_A, OUTPUT_FORMAT_A,
])

CALL_B_INSTRUCTIONS = """入力として、当日の市場データ（daily_data.json）と、呼び出しAの出力
（採用したニュース、reusable_for_summary）を受け取ります。
Aが失敗している場合はニュースが空で渡されます。その場合は市場データのみで
記述し、ニュース材料が確認できなかった旨を明記してください。

### 文体（v1.35・オーナー指示）

文体は「です・ます調」で統一する。「である調」（「〜示唆される」
「〜とみられる」等の言い切り体）は使わない。前編（part1_headline・
part1_points）と文体を揃えること。

- part2_flow: 2〜3本の条件付き連鎖。各連鎖は「材料 → 意識された可能性 →
  同時期に確認された値動き」の形にし、末尾を因果の限定で締める。
  地政学・マクロ、制度・政策、企業財務・市場構造のうち根拠のある系統から選ぶ。
  ニュースが無い日は、市場データ内の事実（出来高の増減、市場心理の変化、
  国内取引所とDEXの出来高動向）のみで1〜2本にとどめる。
- part2_summary: 総括。地合い・不確実性・今後の確認事項のみ。ニュースの
  再説明をしない。reusable_for_summary があれば1行だけ言及する。
  対象日の翌日が土日の場合は「翌日」ではなく「今後」「週明け」と書く。
  総括で言及してよい固有名詞・材料は、part1_points に掲載済みのもの、
  または reusable_for_summary に渡された継続材料に限る（v1.35・
  オーナー指示）。本文（part1_points）で扱っていない新規の固有名詞・
  材料を総括で初めて持ち出さない——読者が文脈を追えないため。

出力形式（JSONのみ）:
{ "part2_flow": ["...", "..."], "part2_summary": "..." }"""

SYSTEM_B = "\n\n".join([
    ROLE_INTRO, RULES_ABSOLUTE, RULES_HASHTAG, RULES_CAUSAL, CALL_B_INSTRUCTIONS,
])


class CallOutcome:
    def __init__(self, ok: bool, data: dict | None, attempts: int, error: str | None,
                 usage: dict[str, int] | None = None, truncation_stats: dict[str, int] | None = None,
                 attempt_errors: list[str] | None = None):
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

    def to_dict(self) -> dict:
        return {"ok": self.ok, "attempts": self.attempts, "error": self.error,
                "usage": self.usage, "data": self.data, "truncation_stats": self.truncation_stats,
                "attempt_errors": self.attempt_errors}


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
    required_keys: list[str], post_process: Callable[[dict], dict] | None = None,
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
    """
    attempt_errors: list[str] = []
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_content}],
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
                data = post_process(data)
            return CallOutcome(True, data, attempt, None, total_usage, attempt_errors=list(attempt_errors))
        except Exception as e:  # noqa: BLE001 — 上記docstring参照
            attempt_errors.append(f"{type(e).__name__}: {e}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAYS_SEC[attempt - 1])
    return CallOutcome(False, None, MAX_ATTEMPTS, attempt_errors[-1], total_usage,
                        attempt_errors=list(attempt_errors))


def _select_candidates_for_call_a(candidates: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """呼び出しAへ渡す候補を選ぶ（v1.21・v1.39フォローアップでペア救済を追加・
    v1.51でtier4上限を追加）。
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
    """
    tier1 = [c for c in candidates if c.get("tier") == 1]
    tier3 = [c for c in candidates if c.get("tier") == 3]
    others = [c for c in candidates if c.get("tier") not in (1, 3)]

    def pub_dt(c: dict):
        return collect_news.parse_pubdate_jst(c.get("published_at", "")) or datetime.min.replace(
            tzinfo=collect_news.JST)

    tier3_sorted = sorted(tier3, key=pub_dt, reverse=True)
    tier3_top = tier3_sorted[:TIER3_CANDIDATE_LIMIT]
    top_ids = {id(c) for c in tier3_top}

    rescued: list[dict] = []
    rescued_ids: set[int] = set()
    pairs_rescued = 0
    for a, b in _find_independent_pairs(tier3_sorted):
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
        "tier3_total": len(tier3),
        "tier3_selected": len(tier3_selected),
        "tier3_dropped": len(tier3) - len(tier3_selected),
        "tier3_pairs_rescued": pairs_rescued,
        "tier3_pair_rescued_articles": len(rescued),
        "tier4_total": len(others),
        "tier4_selected": len(others_selected),
        "tier4_dropped": len(others) - len(others_selected),
    }
    return tier1 + tier3_selected + others_selected, stats


# v1.29（オーナー指示・修正2）: tier1が薄い日にpart1_pointsの項目数を
# 埋めるためtier3単独ソースが誤って"採用"される事象が実データで
# 繰り返し再現した（DESIGN_CHANGES.md参照）。ルールをプロンプト文中の
# 記憶に委ねるのではなく、候補ごとに掲載可否を機械的に付与して渡す。
_ELIGIBILITY_LABELS = {
    1: "掲載可",
    3: "単独では掲載不可（tier1の裏取り、または独立2ソース規定に該当する場合のみ可）",
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


_AUDIT_LEDGER_STATIC_FIELDS = ("source", "url", "title", "published_at")


class AuditLedgerReconstructionError(ValueError):
    """LLMのaudit_ledger出力が候補一覧と整合しない場合に送出する（v1.48）。
    _call_json()の広いexceptで捕捉され、他の解析失敗と同様にリトライされる。
    """


def _reconstruct_audit_ledger(llm_entries: Any, id_to_candidate: dict[int, dict]) -> list[dict]:
    """LLMが出力した candidate_id・decision・verified_by・reason のみの
    audit_ledgerを、候補データのsource/url/title/published_atで補完した
    完全な形へ復元する（v1.48・オーナー指示）。これらのフィールドをLLMに
    書かせないことで、URLの書き間違い等の転記ミスの経路自体を無くす。

    候補ID参照が候補一覧と過不足なく一致することを要求する——不明なID・
    重複・欠落のいずれも例外を送出し、呼び出し元の_call_json()のリトライへ
    委ねる（架空のIDを容認しない・「候補が1件も渡されていない場合を除き
    全件記録する」という既存要求を機械的に強制する）。
    """
    if not isinstance(llm_entries, list):
        raise AuditLedgerReconstructionError("audit_ledgerがリストでない")
    seen_ids: set[int] = set()
    reconstructed = []
    for e in llm_entries:
        if not isinstance(e, dict):
            raise AuditLedgerReconstructionError(f"audit_ledgerの要素がオブジェクトでない: {e!r}")
        cid = e.get("candidate_id")
        if not isinstance(cid, int) or isinstance(cid, bool) or cid not in id_to_candidate:
            raise AuditLedgerReconstructionError(f"audit_ledgerに存在しない候補ID: {cid!r}")
        if cid in seen_ids:
            raise AuditLedgerReconstructionError(f"audit_ledgerで候補IDが重複: {cid}")
        seen_ids.add(cid)
        candidate = id_to_candidate[cid]
        entry = {field: candidate.get(field, "") for field in _AUDIT_LEDGER_STATIC_FIELDS}
        entry["verified_by"] = e.get("verified_by", "")
        entry["decision"] = e.get("decision", "")
        entry["reason"] = e.get("reason", "")
        reconstructed.append(entry)
    missing = set(id_to_candidate) - seen_ids
    if missing:
        raise AuditLedgerReconstructionError(f"audit_ledgerに記録されていない候補ID: {sorted(missing)}")
    return reconstructed


def _build_call_a_user_content(daily_data: dict, news_today: dict, news_yesterday: dict | None
                                ) -> tuple[str, dict, dict[int, dict]]:
    selected_today, stats = _select_candidates_for_call_a(news_today.get("candidates", []))
    selected_today = _assign_candidate_ids(selected_today)
    id_to_candidate = {c["candidate_id"]: c for c in selected_today}
    selected_yesterday, _ = _select_candidates_for_call_a((news_yesterday or {}).get("candidates", []))
    payload = {
        "target_date_jst": daily_data.get("target_date_jst", ""),
        "weekday_jp": daily_data.get("weekday_jp", ""),
        "daily_data": daily_data,
        "news_candidates_today": _label_eligibility(selected_today),
        "news_candidates_yesterday": _label_eligibility(selected_yesterday),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2), stats, id_to_candidate


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
        "daily_data": daily_data,
        "news_from_call_a": news_from_a,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def call_a(client: "anthropic.Anthropic", daily_data: dict, news_today: dict,
           news_yesterday: dict | None) -> CallOutcome:
    user_content, truncation_stats, id_to_candidate = _build_call_a_user_content(
        daily_data, news_today, news_yesterday)

    def _rebuild_audit_ledger(data: dict) -> dict:
        data["audit_ledger"] = _reconstruct_audit_ledger(data.get("audit_ledger"), id_to_candidate)
        return data

    outcome = _call_json(
        client, system=SYSTEM_A, user_content=user_content,
        max_tokens=CALL_A_MAX_TOKENS, required_keys=REQUIRED_KEYS_A,
        post_process=_rebuild_audit_ledger,
    )
    outcome.truncation_stats = truncation_stats
    return outcome


def call_b(client: "anthropic.Anthropic", daily_data: dict, call_a_data: dict | None) -> CallOutcome:
    user_content = _build_call_b_user_content(daily_data, call_a_data)
    return _call_json(
        client, system=SYSTEM_B, user_content=user_content,
        max_tokens=CALL_B_MAX_TOKENS, required_keys=REQUIRED_KEYS_B,
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

    a = call_a(client, daily_data, news_today, news_yesterday)
    b = call_b(client, daily_data, a.data if a.ok else None)

    failed_count = (0 if a.ok else 1) + (0 if b.ok else 1)
    level = {0: "L0", 1: "L1", 2: "L2"}[failed_count]

    # C19（v1.21改定）: 「渡した候補数」を基準にする（取得総数ではない）。
    # tier3を件数上限で絞るため、取得総数のままだと絞り込み後にAが実際に
    # 見た候補数とaudit_ledgerの記録件数が原理的に一致しなくなる
    # （オーナー指示・DESIGN_CHANGES.md v1.21参照）。
    selected_today, _ = _select_candidates_for_call_a(news_today.get("candidates", []))

    return {
        "target_date_jst": target_date,
        "level": level,
        "call_a": a.to_dict(),
        "call_b": b.to_dict(),
        "news_source_status": news_today.get("source_status", {}),
        "news_candidate_count": len(selected_today),
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
