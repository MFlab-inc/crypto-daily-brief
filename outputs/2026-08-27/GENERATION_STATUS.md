level: L1
call_A: FAILED (JSONDecodeError: Expecting ',' delimiter: line 255 column 6 (char 13551) / 3回試行)
call_B: OK（1回試行）
token_usage（実消費量）: input=62188, output=24358 (call_A: in=58905 out=24000 / call_B: in=3283 out=358)
news_sources:
  - SEC: ok（対象日0件／取得25件）
  - FRB: ok（対象日1件／取得20件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日2件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日3件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日0件／取得10件）
  - ホワイトハウス: ok（対象日4件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日1件／取得30件）
  - CoinDesk: ok（対象日25件／取得25件）
  - Cointelegraph: ok（対象日19件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - Google News (Reuters検索): ok（対象日0件／取得0件）
news_candidates_today: 30件 / audit_ledger: N/A件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
tier3候補 44件中 19件を選定（25件を件数上限により除外）
独立2媒体ペア救済: 3組（4件を上限外で追加）

手当が必要な箇所:
  - 前編【ヘッドライン】
  - 前編【主要なポイント】

自動生成できた箇所:
  - 数値全項目（前編・後編）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

月次累計（2026-08）: input=182854, output=72912（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
