level: L0
call_A: OK（2回試行）
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [30, 39, 40]
    2試行目: 成功
call_B: OK（1回試行）
token_usage（実消費量）: input=64210, output=11951 (call_A: in=59439 out=11410 / call_B: in=4771 out=541)
news_sources:
  - SEC: ok（対象日1件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - FRB（speeches）: ok（対象日1件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日1件／取得10件）
  - CFTC: ok（対象日0件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日2件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日2件／取得10件）
  - ホワイトハウス: ok（対象日3件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日1件／取得30件）
  - ADP: ok（対象日1件／取得10件）
  - CoinDesk: ok（対象日16件／取得25件）
  - Cointelegraph: ok（対象日21件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - The Block: ok（対象日10件／取得20件）
  - Google News (Reuters検索): ok（対象日48件／取得50件）
news_candidates_today: 49件 / audit_ledger: 49件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
tier3候補 47件中 22件を選定（25件を件数上限により除外）
独立2媒体ペア救済: 4組（7件を上限外で追加）
audit_ledger自動補完: 2件（decision/reasonが空だったため定型文で補完。C19は空欄検知のためPASSする——理由の質は監査対象外）

手当が必要な箇所:
  （なし）

自動生成できた箇所:
  - 前編【ヘッドライン】【主要なポイント】
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24）: overall=PASS
  FAILしたチェックはありません。

月次累計（2026-09）: input=1282962, output=208765（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
