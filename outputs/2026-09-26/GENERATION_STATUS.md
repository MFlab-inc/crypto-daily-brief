level: L1
call_A: FAILED (AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [19, 29] / 3回試行)
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [19, 29]
    2試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [19, 29]
    3試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [19, 29]
call_B: OK（1回試行）
token_usage（実消費量）: input=72161, output=11041 (call_A: in=67976 out=10602 / call_B: in=4185 out=439)
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
  - ホワイトハウス: ok（対象日2件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日0件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日8件／取得25件）
  - Cointelegraph: ok（対象日4件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - Google News (Reuters検索): ok（対象日46件／取得50件）
news_candidates_today: 29件 / audit_ledger: N/A件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）

手当が必要な箇所:
  - 前編【ヘッドライン】
  - 前編【主要なポイント】

自動生成できた箇所:
  - 数値全項目（前編・後編）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

月次累計（2026-09）: input=1195774, output=194254（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
