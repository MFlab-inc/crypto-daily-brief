level: L0
call_A: OK（1回試行）
call_B: OK（1回試行）
token_usage（実消費量）: input=33517, output=5626 (call_A: in=28387 out=5041 / call_B: in=5130 out=585)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日1件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日1件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日0件／取得10件）
  - ホワイトハウス: ok（対象日5件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日2件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日15件／取得25件）
  - Cointelegraph: ok（対象日18件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - Google News (Reuters検索): ok（対象日44件／取得50件）
news_candidates_today: 43件 / audit_ledger: 43件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
tier3候補 33件中 19件を選定（14件を件数上限により除外）
独立2媒体ペア救済: 2組（4件を上限外で追加）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（前編・後編）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

月次累計（2026-09）: input=268348, output=47714（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
