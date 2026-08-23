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
from typing import Any

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
TIER3_CANDIDATE_LIMIT = 10

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

RULES_CAUSAL = """## 因果表現

- 事実の記述と価格変動の因果を混同しない。
- 「により」「を受けて」「が原因で」「のため」「によって」「せいで」
  「を機に」のいずれかと、「上昇」「下落」「高騰」「急落」「暴落」
  「急騰」「反落」のいずれかが同じ文の中にある場合、必ず「可能性」
  「意識された」「とみられる」「考えられる」「未確認」「断定（できない/
  できません）」のいずれかで文を締め、断定を避ける（語順は問わない。
  価格変動語が先に来る文にも適用される）。「〜が牽引した」も同様に、
  限定する語句を伴わない単独の断定表現として扱わない。
- 上記の限定語句を伴わない断定表現は使わない（機械監査C18の対象）。"""

NEWS_SELECTION = """## ニュース候補の扱いと選定根拠

news_candidates_today に、collect_news.py が公式発表RSS等から収集した候補が
title・summary・published_at・source・tier・eligibility 付きで渡される。
eligibilityはtierに基づき機械的に付与した掲載可否の判定であり、この
判定に従うこと（tier番号から自分で可否を導く必要はない）。web_searchは
使わない — 独自に調べたり、候補一覧に無い情報を付け加えたりしない。
本文はこの候補一覧のみを根拠にする。

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
【ヘッドライン】への昇格は引き続きtier1の裏付けを必要とする。
この規定で採用した候補は、audit_ledgerのdecisionを
"採用（独立2ソース）" と記録する（"採用"や"不採用"と区別する）。

### ヘッドラインの判定手順（v1.30・オーナー指示）

上記「【ヘッドライン】への昇格は引き続きtier1の裏付けを必要とする」を
実際の判定手順として明示する。part1_headline・headline_for_imageは
次の手順で決定する。
 (1) tier1の裏付けがある採用材料（decision:"採用"）が1件以上あるか確認する
 (2) ある場合のみ、その材料に基づく実文言のヘッドラインを書く
 (3) 1件もない場合は、独立2ソース材料（decision:"採用（独立2ソース）"）が
     【主要なポイント】に採用されていても、下記「候補が無い場合の扱い」の
     定型文をそのまま使う。
独立2ソース材料は【主要なポイント】には掲載できるが、【ヘッドライン】の
根拠にはできない。
- 数値・固有名詞・日時はsummary・titleの記載と一致させる。候補に無い情報を
  推測で補わない（確認できないものは掲載しない）。
- news_candidates_yesterday に同一の法案・政策・企業動向の候補が含まれる
  場合、summaryの内容が前日から更新されているときのみ【ヘッドライン】
  【主要なポイント】へ再掲載する。更新がなければ、その旨を
  reusable_for_summary に記し、本文には書かない。
- 十分な材料がない日は項目数を埋めない。確認できた事実と、確認できなかった
  範囲を明記する。tier 1の候補が0件、またはいずれも書くに足る内容が無い
  場合は、次の「候補が無い場合の扱い」に従う。"""

NO_CANDIDATES_FALLBACK = f"""## 候補が無い場合の扱い

tier 1の候補が0件、またはいずれも【ヘッドライン】【主要なポイント】に
書けるだけの内容を持たない場合、part1_headline・part1_points・
headline_for_imageは以下のとおり出力する。ただし、上記「独立2ソース規定」に
該当するtier3材料がある場合はpart1_pointsの定型文フォールバックを使わず、
その材料を記載する（headline_for_image・part1_headlineは独立2ソース材料
だけでは昇格しないため、この場合も下記のフォールバックのままとする）。

- part1_headline: 統合運用基準§3.1の指定文言をそのまま使う（言い換えない）:
  「{FIXED_HEADLINE}」
- part1_points: 独立2ソース規定に該当する材料が無い場合、同じく指定文言を
  そのまま使う（項目数は1件でよい）:
  「{FIXED_POINTS}」
- headline_for_image: ニュースが無いため、daily_data.json内のBTC・ETHの
  direction（up/down）に基づく短い定性的な見出しにとどめる
  （例:「BTC・ETHともに上昇基調」）。数値は書かない。`#`は使わず全角40字以内。
- reusable_for_summary: tier 4等の継続監視材料があれば記す。無ければ空配列。

**audit_ledgerは上記と切り離して扱う（統合運用基準・台本の要求）。**
audit_ledgerは「採否を判断した全候補の記録」であり、本文（ヘッドライン・
主要なポイント）に採用したかどうかとは無関係に、news_candidates_today に
渡された候補（tier 1・3・4のすべて）を1件残らず記録する。ヘッドライン・
主要なポイントに使わなかった候補も decision:"不採用" とその理由
（例:「暗号通貨市場との関係が確認できない」「内容が薄く一次情報として
不十分」等）を記録する。audit_ledgerを空配列 [] にしてよいのは、
news_candidates_today が空配列で渡された（候補が1件も無かった）場合の
みである。候補が1件でも渡されている場合、audit_ledgerを空配列で返して
はならない。埋めるための架空のsource・url・published_atを作ることは
禁止のままだが（絶対規則2と同じ理由で捏造にあたる）、渡された候補自体は
実在するため、その候補について採否と理由を記録することは捏造ではない。"""

WRITES_A = """## あなたが書くもの

- headline_for_image: 図版下部帯用。`#` を使わず全角40字以内。体言止め可。
  上記「ヘッドラインの判定手順」に従う——tier1裏付けの採用材料が無ければ
  独立2ソース材料の有無にかかわらず定型見出し（direction基準の定性的な
  見出し）にとどめる。
- part1_headline: 前編のヘッドライン。2〜3文。当日の最重要材料と価格の方向。
  上記「ヘッドラインの判定手順」に従う——tier1裏付けの採用材料が無ければ
  独立2ソース材料の有無にかかわらず定型文をそのまま使う。
- part1_points: 上限4項目。ヘッドラインと重複しない補足。各項目末尾に
  （媒体名、日付）を付す。項目数は目標ではなく情報源の規律に従った結果
  である——tier1（または独立2ソース規定該当のtier3）の裏付けがある
  材料の件数がそのまま項目数になる（1件なら1項目、0件なら0項目で
  定型文）。項目数を埋めるためにtier3単独ソースを採用しない。
- audit_ledger: 候補一覧（tier 1・3・4のすべて）の採否を判断した記録。
- reusable_for_summary: 継続材料で本文に載せなかったものの1行要約（0〜2件）。"""

OUTPUT_FORMAT_A = """## 出力形式

次のJSONのみを出力。前置き・後置き・コードフェンスを付けない。

{
  "headline_for_image": "...",
  "part1_headline": "...",
  "part1_points": ["...", "..."],
  "reusable_for_summary": ["..."],
  "audit_ledger": [
    { "source": "", "url": "", "title": "", "published_at": "",
      "verified_by": "", "decision": "採用/採用（独立2ソース）/不採用", "reason": "" }
  ]
}"""

SYSTEM_A = "\n\n".join([
    ROLE_INTRO, RULES_ABSOLUTE, RULES_HASHTAG, NEWS_SELECTION, NO_CANDIDATES_FALLBACK,
    RULES_CAUSAL, WRITES_A, OUTPUT_FORMAT_A,
])

CALL_B_INSTRUCTIONS = """入力として、当日の市場データ（daily_data.json）と、呼び出しAの出力
（採用したニュース、reusable_for_summary）を受け取ります。
Aが失敗している場合はニュースが空で渡されます。その場合は市場データのみで
記述し、ニュース材料が確認できなかった旨を明記してください。

- part2_flow: 2〜3本の条件付き連鎖。各連鎖は「材料 → 意識された可能性 →
  同時期に確認された値動き」の形にし、末尾を因果の限定で締める。
  地政学・マクロ、制度・政策、企業財務・市場構造のうち根拠のある系統から選ぶ。
  ニュースが無い日は、市場データ内の事実（出来高の増減、市場心理の変化、
  国内取引所とDEXの出来高動向）のみで1〜2本にとどめる。
- part2_summary: 総括。地合い・不確実性・今後の確認事項のみ。ニュースの
  再説明をしない。reusable_for_summary があれば1行だけ言及する。
  対象日の翌日が土日の場合は「翌日」ではなく「今後」「週明け」と書く。

出力形式（JSONのみ）:
{ "part2_flow": ["...", "..."], "part2_summary": "..." }"""

SYSTEM_B = "\n\n".join([
    ROLE_INTRO, RULES_ABSOLUTE, RULES_HASHTAG, RULES_CAUSAL, CALL_B_INSTRUCTIONS,
])


class CallOutcome:
    def __init__(self, ok: bool, data: dict | None, attempts: int, error: str | None,
                 usage: dict[str, int] | None = None, truncation_stats: dict[str, int] | None = None):
        self.ok = ok
        self.data = data
        self.attempts = attempts
        self.error = error
        self.usage = usage or {"input_tokens": 0, "output_tokens": 0}
        self.truncation_stats = truncation_stats or {}

    def to_dict(self) -> dict:
        return {"ok": self.ok, "attempts": self.attempts, "error": self.error,
                "usage": self.usage, "data": self.data, "truncation_stats": self.truncation_stats}


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
    required_keys: list[str],
) -> CallOutcome:
    """system/userプロンプトでJSON応答を取得し、必須キーの充足まで検証する。
    ツールは一切使わない通常のメッセージ呼び出し（v1.15。呼び出しA・B共通）。

    例外（ネットワーク・認証・レート制限・refusal・空応答・JSON不正・必須キー欠落）は
    すべて「この呼び出しの失敗」として扱い、最大MAX_ATTEMPTS回まで再試行したうえで
    最終的に CallOutcome(ok=False) を返す。呼び出し元はこれを個別呼び出しの失敗として
    縮退ラダーへ渡す設計（§5.3）のため、ここでの except は意図的に広く取っている
    （個別の例外型ごとに扱いを変えると、想定外の失敗モードが縮退せずクラッシュしうる）。
    """
    last_err: str | None = None
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
            return CallOutcome(True, data, attempt, None, total_usage)
        except Exception as e:  # noqa: BLE001 — 上記docstring参照
            last_err = f"{type(e).__name__}: {e}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAYS_SEC[attempt - 1])
    return CallOutcome(False, None, MAX_ATTEMPTS, last_err, total_usage)


def _select_candidates_for_call_a(candidates: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """呼び出しAへ渡す候補を選ぶ（v1.21）。tier 1（公式発表）は全件、
    tier 3（CoinDesk・Cointelegraph等）は公開日時の新しい順で上位
    TIER3_CANDIDATE_LIMIT件までに絞る。候補急増日（実測30件・うち
    tier3が28件）でaudit_ledgerの全候補記録がCALL_A_MAX_TOKENSを
    超過した事象への対処（DESIGN_CHANGES.md v1.21参照）。tier 4等は
    実測で毎回0件のため現状据え置き。
    """
    tier1 = [c for c in candidates if c.get("tier") == 1]
    tier3 = [c for c in candidates if c.get("tier") == 3]
    others = [c for c in candidates if c.get("tier") not in (1, 3)]

    def pub_dt(c: dict):
        return collect_news.parse_pubdate_jst(c.get("published_at", "")) or datetime.min.replace(
            tzinfo=collect_news.JST)

    tier3_sorted = sorted(tier3, key=pub_dt, reverse=True)
    tier3_selected = tier3_sorted[:TIER3_CANDIDATE_LIMIT]
    stats = {
        "tier3_total": len(tier3),
        "tier3_selected": len(tier3_selected),
        "tier3_dropped": len(tier3) - len(tier3_selected),
    }
    return tier1 + tier3_selected + others, stats


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


def _build_call_a_user_content(daily_data: dict, news_today: dict, news_yesterday: dict | None) -> tuple[str, dict]:
    selected_today, stats = _select_candidates_for_call_a(news_today.get("candidates", []))
    selected_yesterday, _ = _select_candidates_for_call_a((news_yesterday or {}).get("candidates", []))
    payload = {
        "target_date_jst": daily_data.get("target_date_jst", ""),
        "weekday_jp": daily_data.get("weekday_jp", ""),
        "daily_data": daily_data,
        "news_candidates_today": _label_eligibility(selected_today),
        "news_candidates_yesterday": _label_eligibility(selected_yesterday),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2), stats


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
    user_content, truncation_stats = _build_call_a_user_content(daily_data, news_today, news_yesterday)
    outcome = _call_json(
        client, system=SYSTEM_A, user_content=user_content,
        max_tokens=CALL_A_MAX_TOKENS, required_keys=REQUIRED_KEYS_A,
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
