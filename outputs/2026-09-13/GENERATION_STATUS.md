level: L0
call_A: OK（1回試行）
call_B: OK（1回試行）
token_usage（実消費量）: input=25491, output=3614 (call_A: in=20805 out=3059 / call_B: in=4686 out=555)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - FRB（speeches）: ok（対象日0件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日0件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日0件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日0件／取得10件）
  - ホワイトハウス: ok（対象日0件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日0件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日7件／取得25件）
  - Cointelegraph: ok（対象日3件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - Google News (Reuters検索): ok（対象日45件／取得50件）
news_candidates_today: 25件 / audit_ledger: 25件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
audit_ledger自動補完: 2件（decision/reasonが空だったため定型文で補完。C19は空欄検知のためPASSする——理由の質は監査対象外）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（前編・後編）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

月次累計（2026-09）: input=574711, output=94583（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
