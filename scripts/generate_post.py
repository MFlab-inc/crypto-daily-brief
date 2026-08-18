#!/usr/bin/env python3
"""generate_post.py — 呼び出しA・B（LLM生成）と縮退レベル判定（v0.3 §5・§10 第2弾-5）。

呼び出しA（ヘッドライン・主要なポイント／web_search使用）と呼び出しB（フロー・総括）
を分離し、片方の失敗が全体を巻き添えにしない（§2.2・§5.3）。各呼び出しは最大
MAX_ATTEMPTS回まで試行し、それでも失敗した呼び出しは compose_post.py 側の
縮退ラダー（§7）へ「失敗」として渡す。

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
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import anthropic

MODEL = "claude-sonnet-5"
CALL_A_MAX_TOKENS = 4000
CALL_B_MAX_TOKENS = 2000
MAX_ATTEMPTS = 3  # 初回+リトライ2回（§5.3「リトライ: 各2回まで」）
RETRY_DELAYS_SEC = (2, 4)
MAX_PAUSE_RESTARTS = 3  # server-side tool の pause_turn 再開回数の上限（暴走防止のガード値。台本に規定なし）

WEB_SEARCH_TOOL = [{"type": "web_search_20260209", "name": "web_search"}]

REQUIRED_KEYS_A = [
    "headline_for_image", "part1_headline", "part1_points",
    "reusable_for_summary", "audit_ledger",
]
REQUIRED_KEYS_B = ["part2_flow", "part2_summary"]

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
- 価格との関係は「可能性」「意識された可能性」「同時期に確認された材料」
  「因果は未確認」等で限定する。
- 次の断定表現を使わない: 「〜が原因で」「〜により上昇した」「〜を受けて
  下落した」「〜のため上昇」「〜のため下落」「〜が牽引した」。"""

NEWS_SELECTION = """## ニュースの選定と根拠

優先度1: 規制当局・議会・政府・企業・取引所の公式発表
優先度2: Reuters、Bloomberg 等の独立報道
優先度3: Financial Times、日経、CoinDesk 等（補完・裏取り）
優先度4: CoinPost、BeInCrypto Japan 等（論点の発見のみ。主根拠にしない）

- 掲載する事実は優先度1〜3のいずれかで確認できたものに限る。
- 数値・固有名詞・日時は原典の記載と一致させる。確認できないものは掲載しない
  （誤りと断定できなくとも、裏取り不足なら不掲載）。
- 前日の候補一覧に同一の法案・政策・企業動向が含まれる場合、前日から新たな
  一次情報の更新（具体的な進展・数値・発言）が確認できるときのみ
  【ヘッドライン】【主要なポイント】へ再掲載する。新展開がなければ、その旨を
  reusable_for_summary に記し、本文には書かない。
- 十分な材料がない日は項目数を埋めない。確認できた事実と、確認できなかった
  範囲を明記する。"""

WRITES_A = """## あなたが書くもの

- headline_for_image: 図版下部帯用。`#` を使わず全角40字以内。体言止め可。
- part1_headline: 前編のヘッドライン。2〜3文。当日の最重要材料と価格の方向。
- part1_points: 3〜4項目。ヘッドラインと重複しない補足。各項目末尾に
  （媒体名、日付）を付す。材料が乏しい日は項目数を減らし、その旨を書く。
- audit_ledger: 採否を判断した全候補の記録。
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
      "verified_by": "", "decision": "採用/不採用", "reason": "" }
  ]
}"""

SYSTEM_A = "\n\n".join([
    ROLE_INTRO, RULES_ABSOLUTE, RULES_HASHTAG, NEWS_SELECTION, RULES_CAUSAL,
    WRITES_A, OUTPUT_FORMAT_A,
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
                 web_search_count: int = 0):
        self.ok = ok
        self.data = data
        self.attempts = attempts
        self.error = error
        self.web_search_count = web_search_count

    def to_dict(self) -> dict:
        return {"ok": self.ok, "attempts": self.attempts, "error": self.error,
                "web_search_count": self.web_search_count, "data": self.data}


def _extract_text(response: Any) -> str:
    return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()


def _strip_code_fence(text: str) -> str:
    """出力形式でコードフェンス禁止を指示済みだが、万一付与された場合のみ剥がす。"""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[A-Za-z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    return t.strip()


def _count_web_search(response: Any) -> int:
    return sum(
        1 for b in response.content
        if getattr(b, "type", None) == "server_tool_use" and getattr(b, "name", None) == "web_search"
    )


def _run_with_pause_handling(client: "anthropic.Anthropic", kwargs: dict) -> tuple[Any, int]:
    """server-side tool（web_search）が反復上限で pause_turn を返した場合、
    会話履歴を引き継いで再送する（SDK付属ドキュメント記載の手順）。
    GENERATION_STATUS.md報告用に、全リクエストを通じたweb_search呼び出し回数も返す。
    """
    messages = kwargs["messages"]
    response = client.messages.create(**kwargs)
    web_search_count = _count_web_search(response)
    restarts = 0
    while response.stop_reason == "pause_turn" and restarts < MAX_PAUSE_RESTARTS:
        messages = messages + [{"role": "assistant", "content": response.content}]
        kwargs = {**kwargs, "messages": messages}
        response = client.messages.create(**kwargs)
        web_search_count += _count_web_search(response)
        restarts += 1
    return response, web_search_count


def _call_json(
    client: "anthropic.Anthropic", *, system: str, user_content: str, max_tokens: int,
    required_keys: list[str], tools: list[dict] | None = None,
) -> CallOutcome:
    """system/userプロンプトでJSON応答を取得し、必須キーの充足まで検証する。

    例外（ネットワーク・認証・レート制限・refusal・空応答・JSON不正・必須キー欠落）は
    すべて「この呼び出しの失敗」として扱い、最大MAX_ATTEMPTS回まで再試行したうえで
    最終的に CallOutcome(ok=False) を返す。呼び出し元はこれを個別呼び出しの失敗として
    縮退ラダーへ渡す設計（§5.3）のため、ここでの except は意図的に広く取っている
    （個別の例外型ごとに扱いを変えると、想定外の失敗モードが縮退せずクラッシュしうる）。
    """
    last_err: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            kwargs: dict[str, Any] = dict(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            if tools:
                kwargs["tools"] = tools
            response, web_search_count = _run_with_pause_handling(client, kwargs)
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
            return CallOutcome(True, data, attempt, None, web_search_count)
        except Exception as e:  # noqa: BLE001 — 上記docstring参照
            last_err = f"{type(e).__name__}: {e}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAYS_SEC[attempt - 1])
    return CallOutcome(False, None, MAX_ATTEMPTS, last_err)


def _build_call_a_user_content(daily_data: dict, news_today: dict, news_yesterday: dict | None) -> str:
    payload = {
        "target_date_jst": daily_data.get("target_date_jst", ""),
        "weekday_jp": daily_data.get("weekday_jp", ""),
        "daily_data": daily_data,
        "news_candidates_today": news_today.get("candidates", []),
        "news_candidates_yesterday": (news_yesterday or {}).get("candidates", []),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


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
    user_content = _build_call_a_user_content(daily_data, news_today, news_yesterday)
    return _call_json(
        client, system=SYSTEM_A, user_content=user_content,
        max_tokens=CALL_A_MAX_TOKENS, required_keys=REQUIRED_KEYS_A, tools=WEB_SEARCH_TOOL,
    )


def call_b(client: "anthropic.Anthropic", daily_data: dict, call_a_data: dict | None) -> CallOutcome:
    user_content = _build_call_b_user_content(daily_data, call_a_data)
    return _call_json(
        client, system=SYSTEM_B, user_content=user_content,
        max_tokens=CALL_B_MAX_TOKENS, required_keys=REQUIRED_KEYS_B, tools=None,
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
                                default={"candidates": [], "source_status": {"cryptopanic": "failed", "count": 0}})
    prev_date = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    news_yesterday = _load_json_or(Path(f"outputs/{prev_date}/news_candidates.json"), default=None)

    a = call_a(client, daily_data, news_today, news_yesterday)
    b = call_b(client, daily_data, a.data if a.ok else None)

    failed_count = (0 if a.ok else 1) + (0 if b.ok else 1)
    level = {0: "L0", 1: "L1", 2: "L2"}[failed_count]

    return {
        "target_date_jst": target_date,
        "level": level,
        "call_a": a.to_dict(),
        "call_b": b.to_dict(),
        "news_source_status": news_today.get("source_status", {}),
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
    print(f"OK: {out_path}（level={result['level']}, call_A={a_status}, call_B={b_status}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
