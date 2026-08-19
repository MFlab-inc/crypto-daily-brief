level: L1
call_A: FAILED (JSONDecodeError: Unterminated string starting at: line 85 column 16 (char 4098) / 3回試行)
call_B: OK（1回試行）
token_usage（実消費量）: input=36907, output=12880 (call_A: in=34152 out=12000 / call_B: in=2755 out=880)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日1件／取得10件）
  - 金融庁: ok（対象日1件／取得15件）
  - 日本銀行: ok（対象日0件／取得50件）
  - CoinDesk: ok（対象日12件／取得25件）
  - Cointelegraph: ok（対象日16件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - Google News (Reuters検索): ok（対象日0件／取得0件）
news_candidates_today: 30件 / audit_ledger: N/A件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）

手当が必要な箇所:
  - 前編【ヘッドライン】
  - 前編【主要なポイント】

自動生成できた箇所:
  - 数値全項目（前編・後編）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】
