level: L0
call_A: OK（1回試行）
call_B: OK（1回試行）
token_usage（実消費量）: input=10140, output=1351 (call_A: in=7176 out=835 / call_B: in=2964 out=516)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日0件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日0件／取得10件）
  - ホワイトハウス: ok（対象日0件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日0件／取得30件）
  - CoinDesk: ok（対象日2件／取得25件）
  - Cointelegraph: ok（対象日0件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - Google News (Reuters検索): ok（対象日0件／取得0件）
news_candidates_today: 2件 / audit_ledger: 2件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（前編・後編）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

月次累計（2026-08）: input=70397, output=31867（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
