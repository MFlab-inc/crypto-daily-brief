level: L1
call_A: FAILED (force_drop_unresolvedで続行したが除外後の再監査（C12〜C28）がFAILしたためL1へフォールバック（FAILしたチェック: ['C18_causal_assertion']） / 3回試行)
  call_A試行履歴（リトライ発生・劣化の兆候として記録）:
    1試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [43, 46]
    2試行目: AuditLedgerReconstructionError: tier3のuse:trueだが独立2ソースの相方が成立しない候補ID: [43, 46]
call_B: OK（1回試行）
token_usage（実消費量）: input=104103, output=18376 (call_A: in=92801 out=17545 / call_B: in=5307 out=141)
news_sources:
  - SEC: ok（対象日2件／取得25件）
  - FRB: ok（対象日0件／取得20件）
  - FRB（speeches）: ok（対象日3件／取得15件）
  - FRB（testimony）: ok（対象日0件／取得15件）
  - BLS: failed（HTTP 403）
  - OCC: ok（対象日1件／取得10件）
  - CFTC: ok（対象日1件／取得10件）
  - 金融庁: ok（対象日0件／取得15件）
  - 日本銀行: ok（対象日6件／取得50件）
  - 米財務省: ok（対象日0件／取得10件）
  - USTR: ok（対象日3件／取得10件）
  - ホワイトハウス: ok（対象日2件／取得30件）
  - ホワイトハウス（大統領令等）: ok（対象日0件／取得30件）
  - ADP: ok（対象日0件／取得10件）
  - CoinDesk: ok（対象日13件／取得25件）
  - Cointelegraph: ok（対象日18件／取得30件）
  - Cointelegraph Japan: failed（HTTP 410）
  - The Block: ok（対象日8件／取得18件）
  - Google News (Reuters検索): ok（対象日47件／取得50件）
news_candidates_today: 51件 / audit_ledger: N/A件（候補があるのにaudit_ledgerが0件の場合はC19がFAILする想定。要目視確認）
tier3候補 39件中 18件を選定（21件を件数上限により除外）
独立2媒体ペア救済: 2組（3件を上限外で追加）
call_A 強制不採用（v1.79）: 最終試行でも独立2ソースの相方が成立しなかった1件を強制的に不採用にして続行しました。
  - candidate_id=46 title="NEAR Intents hit by $3.8 million exploit as crypto's rough year of hacks continues" source='CoinDesk': 最終試行でも独立2ソースの相方が成立しなかったため強制的に不採用にした
call_A 強制不採用後の再監査（C12〜C28）がFAILしたため、call_Aを失敗扱いへ差し戻しL1へフォールバックしました（FAILしたチェック: ['C18_causal_assertion']）。

手当が必要な箇所:
  - 前編【ヘッドライン】
  - 前編【主要なポイント】

自動生成できた箇所:
  - 数値全項目（numeric_record.md）
  - 後編【LP運用者向けに一言】
  - 後編【市場のフロー】【総括】

本文機械監査（C12〜C24・C26〜C28・計17項目）: overall=PASS
  FAILしたチェックはありません。
向きの食い違いチェック（警告のみ・FAILにしない）: 警告なし

月次累計（2026-10）: input=104103, output=18376（outputs/token_usage_log.csv集計・同日複数回実行分を含む）
