level: L0
call_A: OK（1回試行）
call_B: OK（1回試行）
token_usage（実消費量）: input=11036, output=6415 (call_A: in=8010 out=5440 / call_B: in=3026 out=975)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日3件／取得20件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日1件／取得10件）
  - 金融庁: ok（対象日1件／取得15件）
  - 日本銀行: ok（対象日2件／取得50件）
  - CoinDesk: ok（対象日18件／取得25件）
  - Cointelegraph: ok（対象日18件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - Google News (Reuters検索): ok（対象日0件／取得0件）
news_candidates_today: 17件 / audit_ledger: 17件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
tier3候補 36件中 10件を選定（26件を件数上限により除外）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（前編・後編）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

月次累計（2026-08）: input=22378, output=15316（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
