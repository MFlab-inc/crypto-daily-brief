level: L0
call_A: OK（1回試行）
call_B: OK（1回試行）
token_usage（実消費量）: input=33281, output=5696 (call_A: in=28333 out=5228 / call_B: in=4948 out=468)
news_sources:
  - SEC: ok（対象日1件／取得25件）
  - FRB: ok（対象日1件／取得20件）
  - FRB（speeches）: ok（対象日3件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日1件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日0件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日0件／取得10件）
  - ホワイトハウス: ok（対象日4件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日1件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日13件／取得25件）
  - Cointelegraph: ok（対象日19件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - The Block: ok（対象日7件／取得20件）
  - Google News (Reuters検索): ok（対象日47件／取得50件）
news_candidates_today: 44件 / audit_ledger: 44件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
tier3候補 39件中 18件を選定（21件を件数上限により除外）
独立2媒体ペア救済: 2組（3件を上限外で追加）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24）: overall=FAIL
  FAIL: C23_summary_no_new_entities — 総括に本文未確認の固有名詞候補（限界あり・ASCII表記のみ検知。誤検知時は要目視確認）: ['Fed']

月次累計（2026-09）: input=1316243, output=214461（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
